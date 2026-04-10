from __future__ import annotations

import yaml

from autopedia.config import Settings
from autopedia.llm_client import LLMClient
from autopedia.models import ResearchRun
from autopedia.requests import build_request_issue_url
from autopedia.utils import chunk_text, truncate_text


class WikiWriter:
    def __init__(self, settings: Settings, llm: LLMClient):
        self.settings = settings
        self.llm = llm

    def build_page(self, run: ResearchRun, report_text: str) -> str:
        report_chunks = chunk_text(report_text, self.settings.max_report_chunk_chars)[: self.settings.max_report_chunks]
        chunk_digests: list[str] = []
        for index, chunk in enumerate(report_chunks, start=1):
            chunk_digests.append(self._digest_chunk(index, chunk))

        references = run.top_sources(18)
        if len(references) < self.settings.minimum_reference_count:
            raise RuntimeError(
                "Refusing to publish a wiki page because too few grounded references were fetched. "
                f"Need at least {self.settings.minimum_reference_count}, got {len(references)}."
            )
        reference_catalog = []
        for index, source in enumerate(references, start=1):
            reference_catalog.append(
                f"[{index}] {source.display_title()} | {source.domain} | {source.final_url} | {truncate_text(' | '.join(source.excerpt[:2]), 240)}"
            )

        body = self.llm.complete_markdown(
            system_prompt=(
                "You write a careful, citation-aware Markdown wiki page in Japanese. "
                "Use a neutral tone, distinguish evidence from uncertainty, and do not invent facts."
            ),
            user_prompt=(
                f"Topic: {run.plan.title}\n"
                f"Summary: {run.plan.summary}\n"
                f"Rationale: {run.plan.rationale}\n"
                f"Preferred outline: {run.plan.outline}\n\n"
                f"Request mode: {run.request.normalized_mode()}\n"
                f"Request notes: {run.request.request_notes or 'No extra request notes.'}\n"
                f"Existing page excerpt:\n{run.request.existing_page_excerpt[:6000] or 'No prior page excerpt available.'}\n\n"
                "Chunk digests derived from the full 2000+ line report:\n\n"
                + "\n\n".join(chunk_digests)
                + "\n\nCross-turn synthesis:\n"
                + run.synthesis
                + "\n\nReference catalog (cite these as [1], [2], ... in the prose):\n"
                + "\n".join(reference_catalog)
                + "\n\nWrite the article body only in Markdown. Requirements:\n"
                "- Start with a concise lead paragraph.\n"
                "- Use sections that fit a modern wiki page.\n"
                "- Use MkDocs Material admonitions at least twice.\n"
                "- Add one compact comparison table when relevant.\n"
                "- End major sections with source markers like `参照: [1], [3], [5]`.\n"
                "- If evidence is conflicting, state that explicitly.\n"
                "- Do not include YAML front matter."
            ),
            fallback=lambda: self._fallback_body(run, reference_catalog),
            max_tokens=4200,
        )

        metadata = {
            "title": run.plan.title,
            "summary": run.plan.summary,
            "generated_at": run.generated_at,
            "topic_slug": run.plan.slug,
            "sources_analyzed": run.source_count,
            "research_turns": len(run.turns),
            "model": self.settings.model if self.llm.enabled else "demo-mode",
            "request_mode": run.request.normalized_mode(),
            "request_issue": run.request.issue_url or None,
            "tags": run.plan.tags,
        }
        front_matter = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
        references_block = "\n".join(
            f"{index}. [{source.display_title()}]({source.final_url}) - {source.domain}."
            for index, source in enumerate(references, start=1)
        )
        page_path = f"docs/wiki/{run.plan.slug}.md"
        update_url = build_request_issue_url(
            self.settings,
            mode="update-page",
            topic_title=run.plan.title,
            topic_slug=run.plan.slug,
            request_notes="Please refresh this page against the latest trustworthy sources.",
            existing_page_path=page_path,
        )
        expand_url = build_request_issue_url(
            self.settings,
            mode="expand-page",
            topic_title=run.plan.title,
            topic_slug=run.plan.slug,
            request_notes="Please expand this page with additional depth, missing sections, and newly available evidence.",
            existing_page_path=page_path,
        )
        new_topic_url = build_request_issue_url(
            self.settings,
            mode="new-topic",
            request_notes="Please create a new wiki page for the requested topic.",
        )
        action_block = ""
        if update_url and expand_url:
            action_block = (
                '<div class="ap-inline-actions">\n'
                f'  <a class="md-button md-button--primary" href="{expand_url}" target="_blank" rel="noopener">このWikiページを更新または拡張して</a>\n'
                f'  <a class="md-button" href="{update_url}" target="_blank" rel="noopener">最新情報で更新する</a>\n'
                + (
                    f'  <a class="md-button" href="{new_topic_url}" target="_blank" rel="noopener">別トピックを依頼</a>\n'
                    if new_topic_url
                    else ""
                )
                + '</div>\n\n'
            )

        return (
            f"---\n{front_matter}\n---\n\n"
            f"# {run.plan.title}\n\n"
            f"> {run.plan.summary}\n\n"
            f"!!! info \"生成メタデータ\"\n"
            f"    - Generated: {run.generated_at}\n"
            f"    - Sources analyzed: {run.source_count}\n"
            f"    - Research turns: {len(run.turns)}\n"
            f"    - Topic slug: {run.plan.slug}\n\n"
            f"{action_block}"
            f"{body.strip()}\n\n"
            f"## References\n\n{references_block}\n"
        )

    def _digest_chunk(self, index: int, chunk: str) -> str:
        return self.llm.complete_markdown(
            system_prompt=(
                "You distill one research-report chunk into wiki-ready notes. "
                "Preserve only claims that appear supported by the chunk."
            ),
            user_prompt=(
                f"Chunk index: {index}\n\n"
                "Summarize this report chunk into four short sections: hard facts, recurring themes, contested claims, and useful references.\n\n"
                f"{chunk}"
            ),
            fallback=lambda: self._fallback_chunk_digest(index, chunk),
            max_tokens=1600,
        )

    def _fallback_chunk_digest(self, index: int, chunk: str) -> str:
        preview = chunk.splitlines()[:30]
        bullet_lines = [line for line in preview if line.strip().startswith("-")][:10]
        hard_fact_lines = bullet_lines[:4] or [
            "- The chunk contains evidence entries and source metadata."
        ]
        reference_lines = bullet_lines[4:8] or [
            "- Use the highest-ranked sources from this chunk in the final article."
        ]
        return "\n".join(
            [
                f"## Chunk {index}",
                "### Hard facts",
                *hard_fact_lines,
                "",
                "### Recurring themes",
                "- Multiple sources repeat core terminology and timeline markers.",
                "",
                "### Contested claims",
                "- Baselines, metrics, or practical constraints may differ across sources.",
                "",
                "### Useful references",
                *reference_lines,
            ]
        )

    def _fallback_body(self, run: ResearchRun, reference_catalog: list[str]) -> str:
        findings = [item for turn in run.turns for item in turn.key_findings[:3]]
        conflicts = [item for turn in run.turns for item in turn.contradictions[:2]]
        questions = [item for turn in run.turns for item in turn.open_questions[:2]]
        refs = ", ".join([f"[{index}]" for index in range(1, min(6, len(reference_catalog)) + 1)])
        finding_lines = [f"- {item}" for item in findings[:6]] or [
            "- 調査から重要論点を抽出できなかったため、追加調査が必要。"
        ]
        question_lines = [f"    - {question}" for question in questions] or [
            "    - 証拠の強さが不均一な論点が残っている。"
        ]
        lines = [
            "このページは複数ターンの大規模オンライン調査をもとに、話題の全体像と現在地をできるだけ中立的にまとめたものです。",
            "",
            "!!! abstract \"要点\"",
            f"    - {findings[0] if findings else '主要論点は複数の一次・二次ソースを横断して整理されている。'}",
            f"    - {findings[1] if len(findings) > 1 else '実装状況、性能、制約を分けて読む必要がある。'}",
            f"    - {findings[2] if len(findings) > 2 else '将来予測と現時点の実績は切り分けるべきである。'}",
            "",
            "## 概要",
            run.plan.summary,
            f"参照: {refs}",
            "",
            "## 何が重要か",
            *finding_lines,
            f"参照: {refs}",
            "",
            "## 主要な論点",
            "| 観点 | 現状 | 注意点 |",
            "| --- | --- | --- |",
            f"| 技術・仕組み | {truncate_text(findings[0], 70) if findings else '整理中'} | 文脈依存のため一次ソース確認が必要 |",
            f"| 導入・実装 | {truncate_text(findings[1], 70) if len(findings) > 1 else '整理中'} | ベンダー主張との差分に注意 |",
            f"| 制約・批判 | {truncate_text(conflicts[0], 70) if conflicts else '見解が割れている'} | 定義や指標の違いを比較する必要がある |",
            f"参照: {refs}",
            "",
            "!!! warning \"未解決点\"",
            *question_lines,
            "",
            "## 現時点での評価",
            "複数ソースを横断すると、確立した事実、条件付きで有望な主張、まだ検証が足りない主張の三層に分けて読むのが妥当です。",
            f"参照: {refs}",
        ]
        return "\n".join(lines)
