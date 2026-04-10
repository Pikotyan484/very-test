from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests
import trafilatura
from bs4 import BeautifulSoup

from autopedia.config import Settings
from autopedia.llm_client import LLMClient
from autopedia.models import FetchedSource, RequestContext, ResearchRun, SearchResult, TopicPlan, TurnDigest
from autopedia.planner import Planner
from autopedia.search import SearchClient
from autopedia.utils import (
    binary_like_url,
    canonical_url,
    compact_lines,
    domain_for_url,
    ensure_dir,
    excerpt_lines,
    iso_timestamp,
    slugify_text,
    truncate_text,
    utc_timestamp,
)


@dataclass
class DownloadedPage:
    result: SearchResult
    final_url: str
    html: str


class ResearchEngine:
    USER_AGENT = (
        "Mozilla/5.0 (compatible; AutoPediaBot/1.0; +https://github.com/) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    def __init__(
        self,
        settings: Settings,
        llm: LLMClient,
        planner: Planner,
        search_client: SearchClient,
    ):
        self.settings = settings
        self.llm = llm
        self.planner = planner
        self.search_client = search_client

    def run(self, plan: TopicPlan) -> ResearchRun:
        return self.run_with_request(plan, RequestContext())

    def run_with_request(self, plan: TopicPlan, request: RequestContext | None = None) -> ResearchRun:
        request = request or RequestContext()
        run_id = f"{utc_timestamp()}-{plan.slug}"
        turns: list[TurnDigest] = []
        seen_urls: set[str] = set()

        for turn_index in range(1, self.settings.research_turns + 1):
            focus, queries = self.planner.build_turn_queries(plan, turn_index, turns, request)
            search_results = self.search_client.search_many(
                queries,
                self.settings.search_results_per_query,
            )
            selected = self._select_fetch_candidates(search_results, seen_urls)
            fetched_sources = self._fetch_sources(plan, run_id, turn_index, selected)
            seen_urls.update(source.final_url for source in fetched_sources)
            turns.append(
                self._summarize_turn(
                    plan=plan,
                    turn_index=turn_index,
                    focus=focus,
                    queries=queries,
                    search_results=search_results,
                    sources=fetched_sources,
                    prior_turns=turns,
                )
            )

        synthesis = self._synthesize(plan, turns, request)
        return ResearchRun(
            run_id=run_id,
            generated_at=iso_timestamp(),
            plan=plan,
            request=request,
            turns=turns,
            synthesis=synthesis,
        )

    def _select_fetch_candidates(
        self,
        results: list[SearchResult],
        seen_urls: set[str],
    ) -> list[SearchResult]:
        candidates: list[SearchResult] = []
        max_candidates = self.settings.max_pages_per_turn * self.settings.max_fetch_candidates_multiplier
        domain_counts: dict[str, int] = {}

        for result in results:
            if len(candidates) >= max_candidates:
                break
            normalized = canonical_url(result.url)
            if not normalized or normalized in seen_urls or binary_like_url(normalized):
                continue
            domain = domain_for_url(normalized)
            if domain_counts.get(domain, 0) >= 5:
                continue
            result.url = normalized
            candidates.append(result)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        if len(candidates) < max_candidates:
            for result in results:
                if len(candidates) >= max_candidates:
                    break
                normalized = canonical_url(result.url)
                if not normalized or normalized in seen_urls or binary_like_url(normalized):
                    continue
                if any(existing.url == normalized for existing in candidates):
                    continue
                result.url = normalized
                candidates.append(result)
        return candidates

    def _fetch_sources(
        self,
        plan: TopicPlan,
        run_id: str,
        turn_index: int,
        results: list[SearchResult],
    ) -> list[FetchedSource]:
        output: list[FetchedSource] = []
        downloaded_pages: list[DownloadedPage] = []
        with ThreadPoolExecutor(max_workers=self._effective_fetch_workers()) as executor:
            futures = {
                executor.submit(self._download_one, result): result
                for result in results
            }
            for future in as_completed(futures):
                source = future.result()
                if source:
                    downloaded_pages.append(source)

        for downloaded_page in sorted(downloaded_pages, key=lambda item: (item.result.rank, item.final_url)):
            source = self._build_source_from_downloaded_page(plan, run_id, turn_index, downloaded_page)
            if source and source.word_count >= self.settings.min_source_words:
                    output.append(source)

        ranked = sorted(output, key=lambda source: (-source.relevance_score, source.rank, source.domain))
        return ranked[: self.settings.max_pages_per_turn]

    def _effective_fetch_workers(self) -> int:
        worker_count = max(1, self.settings.fetch_workers)
        if os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true":
            return min(worker_count, 8)
        return worker_count

    def _download_one(self, result: SearchResult) -> DownloadedPage | None:
        headers = {"User-Agent": self.USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
        try:
            response = requests.get(result.url, headers=headers, timeout=(10, 35))
            response.raise_for_status()
        except Exception:
            return None

        content_type = response.headers.get("content-type", "")
        if not any(kind in content_type for kind in ("text/html", "application/xhtml+xml", "text/plain")):
            return None

        html = response.text
        final_url = canonical_url(str(response.url)) or result.url
        return DownloadedPage(result=result, final_url=final_url, html=html)

    def _build_source_from_downloaded_page(
        self,
        plan: TopicPlan,
        run_id: str,
        turn_index: int,
        downloaded_page: DownloadedPage,
    ) -> FetchedSource | None:
        text = self._extract_main_text(downloaded_page.html)
        if not text:
            return None

        title = self._extract_title(downloaded_page.html) or downloaded_page.result.title
        preview = "\n".join(compact_lines(text)[:40])
        if not preview:
            return None

        html_archive_path = None
        if self.settings.store_raw_html:
            html_archive_path = self._archive_html(run_id, turn_index, downloaded_page.final_url, downloaded_page.html)

        source_id = hashlib.sha1(downloaded_page.final_url.encode("utf-8")).hexdigest()[:12]
        relevance_score = self._score_relevance(plan, downloaded_page.result, preview)

        return FetchedSource(
            source_id=source_id,
            turn_index=turn_index,
            query=downloaded_page.result.query,
            url=downloaded_page.result.url,
            final_url=downloaded_page.final_url,
            domain=domain_for_url(downloaded_page.final_url),
            provider=downloaded_page.result.provider,
            rank=downloaded_page.result.rank,
            search_title=downloaded_page.result.title,
            search_snippet=downloaded_page.result.snippet,
            page_title=title,
            status="ok",
            word_count=len(preview.split()),
            excerpt=excerpt_lines(preview, max_lines=12),
            text_preview=truncate_text(preview, 9000),
            relevance_score=relevance_score,
            html_archive_path=html_archive_path,
        )

    def _extract_main_text(self, html: str) -> str:
        if os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true":
            return self._fallback_extract_text(html)

        try:
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                favor_recall=True,
                deduplicate=True,
            )
        except Exception:
            extracted = None
        return extracted or self._fallback_extract_text(html)

    def _archive_html(self, run_id: str, turn_index: int, url: str, html: str) -> str:
        folder = ensure_dir(self.settings.html_cache_dir / run_id / f"turn-{turn_index:02d}")
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        file_path = folder / f"{slugify_text(domain_for_url(url), fallback='source')}-{digest}.html"
        file_path.write_text(html, encoding="utf-8")
        return str(file_path.relative_to(self.settings.root_dir)).replace("\\", "/")

    def _fallback_extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        return soup.get_text("\n", strip=True)

    def _extract_title(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        return truncate_text(title, 180)

    def _score_relevance(self, plan: TopicPlan, result: SearchResult, preview: str) -> float:
        haystack = f"{plan.title} {' '.join(plan.tags)} {' '.join(plan.search_angles)}".lower()
        keywords = [token for token in haystack.replace("/", " ").split() if len(token) > 2]
        target = f"{result.title} {result.snippet} {preview}".lower()
        overlap = sum(1 for token in keywords if token in target)
        return overlap + max(0.0, 12 - result.rank / 3)

    def _summarize_turn(
        self,
        *,
        plan: TopicPlan,
        turn_index: int,
        focus: str,
        queries: list[str],
        search_results: list[SearchResult],
        sources: list[FetchedSource],
        prior_turns: list[TurnDigest],
    ) -> TurnDigest:
        fallback = self._fallback_turn_summary(turn_index, focus, queries, search_results, sources)
        source_bundle = []
        for source in sources[:18]:
            source_bundle.append(
                f"- [{source.source_id}] {source.display_title()} | {source.domain} | {source.final_url}\n"
                f"  Query: {source.query}\n"
                f"  Snippet: {truncate_text(source.search_snippet, 220)}\n"
                f"  Excerpt: {' | '.join(source.excerpt[:3])}"
            )

        payload = self.llm.complete_json(
            system_prompt=(
                "You are summarizing one turn of deep web research. "
                "Return JSON only and do not invent facts."
            ),
            user_prompt=(
                f"Topic: {plan.title}\n"
                f"Summary: {plan.summary}\n"
                f"Turn focus: {focus}\n"
                f"Queries: {queries}\n"
                f"Prior turn highlights: {[item for turn in prior_turns[-2:] for item in turn.key_findings[:4]]}\n\n"
                "Sources reviewed:\n"
                + "\n".join(source_bundle)
                + "\n\nReturn an object with keys key_findings, contradictions, open_questions. "
                "Each value except contradictions may be empty lists, but keep them concrete and evidence-aware."
            ),
            fallback=lambda: fallback,
            max_tokens=2200,
        )

        return TurnDigest(
            turn_index=turn_index,
            focus=focus,
            queries=queries,
            search_result_count=len(search_results),
            sources=sources,
            key_findings=[str(item) for item in payload.get("key_findings", fallback["key_findings"])][:12],
            contradictions=[str(item) for item in payload.get("contradictions", fallback["contradictions"])][:10],
            open_questions=[str(item) for item in payload.get("open_questions", fallback["open_questions"])][:12],
        )

    def _fallback_turn_summary(
        self,
        turn_index: int,
        focus: str,
        queries: list[str],
        search_results: list[SearchResult],
        sources: list[FetchedSource],
    ) -> dict[str, list[str]]:
        findings = []
        for source in sources[:6]:
            lead = source.excerpt[0] if source.excerpt else source.search_snippet
            findings.append(f"{source.display_title()}: {truncate_text(lead, 180)}")
        if not findings:
            findings = [f"Turn {turn_index} gathered {len(search_results)} candidate results around {focus}."]
        contradictions = []
        if len(sources) > 8:
            contradictions.append("Different sources emphasize different baselines, metrics, or time horizons. These require explicit comparison in the article.")
        open_questions = [
            f"Which claims under {focus} are supported by official or primary sources?",
            f"Which metrics or dates recur across high-relevance sources for turn {turn_index}?",
            f"Which criticism appears consistently versus only in opinion pieces?",
        ]
        if queries:
            open_questions[0] = f"How do authoritative sources answer: {queries[0]}?"
        return {
            "key_findings": findings,
            "contradictions": contradictions,
            "open_questions": open_questions,
        }

    def _synthesize(self, plan: TopicPlan, turns: list[TurnDigest], request: RequestContext | None = None) -> str:
        request = request or RequestContext()
        fallback = self._fallback_synthesis(plan, turns)
        turn_digest = []
        for turn in turns:
            turn_digest.append(
                f"Turn {turn.turn_index}: {turn.focus}\n"
                f"Findings: {turn.key_findings}\n"
                f"Contradictions: {turn.contradictions}\n"
                f"Open questions: {turn.open_questions}"
            )
        source_digest = []
        for source in [item for turn in turns for item in turn.sources][:24]:
            source_digest.append(
                f"[{source.source_id}] {source.display_title()} | {source.domain}\n"
                f"Excerpt: {' | '.join(source.excerpt[:3])}"
            )

        return self.llm.complete_markdown(
            system_prompt=(
                "You synthesize deep research runs into a compact neutral brief for a wiki writer. "
                "Do not invent claims and emphasize uncertainty when evidence conflicts."
            ),
            user_prompt=(
                f"Topic: {plan.title}\n"
                f"Summary: {plan.summary}\n"
                f"Outline goals: {plan.outline}\n\n"
                f"Request mode: {request.normalized_mode()}\n"
                f"Request notes: {request.request_notes or 'No extra request notes.'}\n"
                f"Existing page excerpt:\n{request.existing_page_excerpt[:5000] or 'No existing page excerpt.'}\n\n"
                "Turn digests:\n"
                + "\n\n".join(turn_digest)
                + "\n\nRepresentative sources:\n"
                + "\n\n".join(source_digest)
                + "\n\nWrite a concise synthesis with sections: core points, contested points, missing data, and recommended article emphasis."
            ),
            fallback=lambda: fallback,
            max_tokens=2200,
        )

    def _fallback_synthesis(self, plan: TopicPlan, turns: list[TurnDigest]) -> str:
        findings = [item for turn in turns for item in turn.key_findings[:4]]
        open_questions = [item for turn in turns for item in turn.open_questions[:4]]
        contradictions = [item for turn in turns for item in turn.contradictions[:3]]
        contradiction_lines = [f"- {item}" for item in contradictions[:6]] or [
            "- Conflicting definitions and baselines need careful wording."
        ]
        lines = [
            "## Core points",
            *[f"- {item}" for item in findings[:10]],
            "",
            "## Contested points",
            *contradiction_lines,
            "",
            "## Missing data",
            *[f"- {item}" for item in open_questions[:8]],
            "",
            "## Recommended article emphasis",
            f"- Keep the article scoped around {plan.title} rather than broad adjacent topics.",
            "- Separate established facts, current deployment status, and speculative future claims.",
            "- Attribute contentious statements to cited source clusters rather than presenting them as settled.",
        ]
        return "\n".join(lines)
