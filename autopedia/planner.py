from __future__ import annotations

from autopedia.config import Settings
from autopedia.llm_client import LLMClient
from autopedia.models import RequestContext, TopicPlan, TurnDigest
from autopedia.utils import markdown_headings, slugify_text, truncate_text, unique_preserve_order


class Planner:
    def __init__(self, settings: Settings, llm: LLMClient):
        self.settings = settings
        self.llm = llm

    def select_topic(self, state: dict, request: RequestContext | None = None) -> TopicPlan:
        request = request or RequestContext()
        completed_titles = [item["title"] for item in state.get("completed_topics", [])[:40]]
        failed_titles = [item["title"] for item in state.get("failed_topics", [])[:30]]
        failed_slugs = {str(item.get("slug", "")).strip().lower() for item in state.get("failed_topics", [])[:30]}
        latest_tags = unique_preserve_order(
            tag for item in state.get("completed_topics", [])[:15] for tag in item.get("tags", [])
        )[:25]

        if request.is_manual():
            fallback_plan = self._fallback_requested_plan(state, request)
            payload = self.llm.complete_json(
                system_prompt=(
                    "You are planning a requested wiki generation or update. "
                    "Return JSON only. Keep the scope practical, evidence-seeking, and aligned to the user's request."
                ),
                user_prompt=(
                    f"Site: {self.settings.site_name}\n"
                    f"Language: {self.settings.language}\n"
                    f"Request mode: {request.normalized_mode()}\n"
                    f"Requested topic title: {request.topic_title}\n"
                    f"Requested topic slug: {request.topic_slug}\n"
                    f"Request notes: {request.request_notes or 'No extra notes provided.'}\n"
                    f"Existing summary: {request.existing_summary or 'No prior page summary available.'}\n"
                    f"Existing page excerpt:\n{request.existing_page_excerpt[:6000] or 'No prior page excerpt available.'}\n\n"
                    f"Already covered topics: {completed_titles}\n"
                    f"Recently failed topics: {failed_titles}\n"
                    f"Recent tags: {latest_tags}\n\n"
                    "Return an object with keys: title, slug, summary, rationale, tags, search_angles, outline. "
                    "Preserve the existing topic if this is an update/expand request. Use an ASCII slug."
                ),
                fallback=lambda: fallback_plan.to_dict(),
                max_tokens=2200,
            )
        else:
            fallback_plan = self._fallback_plan(state)
            payload = self.llm.complete_json(
                system_prompt=(
                    "You are the planning brain for an autonomous research wiki. "
                    "Pick one high-signal topic that benefits from deep research, avoids duplication, "
                    "and can support a rigorous multi-source article. Return JSON only."
                ),
                user_prompt=(
                    f"Site: {self.settings.site_name}\n"
                    f"Language: {self.settings.language}\n"
                    f"Already covered topics: {completed_titles}\n"
                    f"Recently failed topics to avoid immediately retrying: {failed_titles}\n"
                    f"Recent tags: {latest_tags}\n"
                    f"Seed topics: {self.settings.seed_topics}\n\n"
                    "Return an object with keys: title, slug, summary, rationale, tags, search_angles, outline. "
                    "Use an ASCII slug. Keep the topic specific enough for one article."
                ),
                fallback=lambda: fallback_plan.to_dict(),
                max_tokens=1800,
            )

        title = str(payload.get("title", fallback_plan.title)).strip() or fallback_plan.title
        preferred_slug = request.topic_slug if request.is_manual() and request.topic_slug else str(payload.get("slug", title))
        slug = slugify_text(preferred_slug, fallback=fallback_plan.slug)
        if not request.is_manual() and (title in failed_titles or slug in failed_slugs):
            title = fallback_plan.title
            slug = fallback_plan.slug
        summary = truncate_text(str(payload.get("summary", fallback_plan.summary)).strip(), 420)
        rationale = truncate_text(str(payload.get("rationale", fallback_plan.rationale)).strip(), 420)
        tags = unique_preserve_order(str(tag) for tag in payload.get("tags", fallback_plan.tags))[:8]
        search_angles = unique_preserve_order(
            str(angle) for angle in payload.get("search_angles", fallback_plan.search_angles)
        )[:12]
        outline = unique_preserve_order(str(item) for item in payload.get("outline", fallback_plan.outline))[:10]

        return TopicPlan(
            title=title,
            slug=slug,
            summary=summary or fallback_plan.summary,
            rationale=rationale or fallback_plan.rationale,
            tags=tags or fallback_plan.tags,
            search_angles=search_angles or fallback_plan.search_angles,
            outline=outline or fallback_plan.outline,
        )

    def build_turn_queries(
        self,
        plan: TopicPlan,
        turn_index: int,
        previous_turns: list[TurnDigest],
        request: RequestContext | None = None,
    ) -> tuple[str, list[str]]:
        request = request or RequestContext()
        prior_findings = [finding for turn in previous_turns[-2:] for finding in turn.key_findings[:5]]
        open_questions = [question for turn in previous_turns[-2:] for question in turn.open_questions[:6]]
        fallback_focus, fallback_queries = self._fallback_queries(plan, turn_index, open_questions, request)

        payload = self.llm.complete_json(
            system_prompt=(
                "You are building the next research turn for a deep web investigation. "
                "Return JSON only. Create diverse, evidence-seeking queries."
            ),
            user_prompt=(
                f"Topic title: {plan.title}\n"
                f"Summary: {plan.summary}\n"
                f"Research angles: {plan.search_angles}\n"
                f"Request mode: {request.normalized_mode()}\n"
                f"Request notes: {request.request_notes or 'No extra request notes.'}\n"
                f"Turn: {turn_index}/{self.settings.research_turns}\n"
                f"Prior findings: {prior_findings}\n"
                f"Open questions: {open_questions}\n\n"
                "Return an object with keys focus and queries. queries must be a list of distinct search strings. "
                f"Provide {self.settings.search_queries_per_turn} queries that mix official docs, academic sources, data, criticism, history, and expert analysis."
            ),
            fallback=lambda: {"focus": fallback_focus, "queries": fallback_queries},
            max_tokens=1800,
        )

        focus = str(payload.get("focus", fallback_focus)).strip() or fallback_focus
        queries = unique_preserve_order(str(query) for query in payload.get("queries", fallback_queries))
        queries = queries[: self.settings.search_queries_per_turn]
        return focus, queries or fallback_queries

    def _fallback_plan(self, state: dict) -> TopicPlan:
        completed = {item["title"] for item in state.get("completed_topics", [])}
        failed = {item["title"] for item in state.get("failed_topics", [])[:30]}
        blocked = completed | failed
        topic_title = next(
            (topic for topic in self.settings.seed_topics if topic not in blocked),
            f"{self.settings.seed_topics[0]} applications and constraints",
        )
        slug = slugify_text(topic_title)
        return TopicPlan(
            title=topic_title,
            slug=slug,
            summary=(
                f"{topic_title} is selected because it has active scientific, industrial, and policy developments "
                "that reward a high-evidence synthesis."
            ),
            rationale=(
                "The topic is concrete enough for one article but broad enough to benefit from multi-turn source gathering."
            ),
            tags=["research", "technology", "analysis"],
            search_angles=[
                "official documentation and standards",
                "recent academic literature",
                "industry adoption and timelines",
                "known limitations and criticism",
                "safety, regulation, and economics",
            ],
            outline=[
                "Overview",
                "Why it matters",
                "History and current state",
                "Core mechanisms",
                "Applications",
                "Risks and constraints",
                "Outlook",
            ],
        )

    def _fallback_requested_plan(self, state: dict, request: RequestContext) -> TopicPlan:
        topic_title = request.topic_title or request.existing_summary or self._fallback_plan(state).title
        slug = slugify_text(request.topic_slug or topic_title)
        mode = request.normalized_mode()
        outline = markdown_headings(request.existing_page_excerpt) or [
            "Overview",
            "Latest developments",
            "Evidence and benchmarks",
            "Open questions",
            "References",
        ]
        rationale = {
            "new-topic": "The topic was explicitly requested by a user and should be researched as a dedicated new article.",
            "update-page": "The existing page should be refreshed against newer evidence and corrected where the source landscape changed.",
            "expand-page": "The existing page should be expanded with deeper coverage in the requested areas while keeping grounded citations.",
        }.get(mode, "The request should be fulfilled with a high-evidence research plan.")
        search_angles = [
            "official documentation and standards",
            "recent academic literature",
            "latest developments and announcements",
            "benchmarks, data, and timelines",
            "known limitations and criticism",
        ]
        if request.request_notes:
            search_angles.insert(0, request.request_notes)
        return TopicPlan(
            title=topic_title,
            slug=slug,
            summary=request.existing_summary or f"{topic_title} was requested by a user and should be researched as a focused wiki page.",
            rationale=rationale,
            tags=["requested", mode, "research"],
            search_angles=unique_preserve_order(search_angles)[:12],
            outline=outline[:10],
        )

    def _fallback_queries(
        self,
        plan: TopicPlan,
        turn_index: int,
        open_questions: list[str],
        request: RequestContext | None = None,
    ) -> tuple[str, list[str]]:
        request = request or RequestContext()
        focus = [
            "high-level map and authoritative definitions",
            "recent evidence, performance, and industrial reality",
            "limitations, risks, and unresolved debates",
        ][min(turn_index - 1, 2)]

        base_queries = [
            f'"{plan.title}" overview',
            f'"{plan.title}" official documentation',
            f'"{plan.title}" academic review',
            f'"{plan.title}" site:gov',
            f'"{plan.title}" site:edu',
            f'"{plan.title}" market analysis',
            f'"{plan.title}" limitations criticism',
            f'"{plan.title}" timeline history',
            f'"{plan.title}" safety regulation',
            f'"{plan.title}" benchmark data',
        ]
        if request.request_notes:
            base_queries.insert(0, f'"{plan.title}" {truncate_text(request.request_notes, 90)}')
        if request.normalized_mode() in {"update-page", "expand-page"}:
            base_queries.extend(
                [
                    f'"{plan.title}" latest developments 2025 2026',
                    f'"{plan.title}" recent review paper',
                    f'"{plan.title}" roadmap current state',
                ]
            )
        if open_questions:
            base_queries[0] = f'"{plan.title}" {open_questions[0]}'
        return focus, unique_preserve_order(base_queries)[: self.settings.search_queries_per_turn]
