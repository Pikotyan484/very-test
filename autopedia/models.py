from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class RequestContext:
    mode: str = "auto"
    topic_title: str = ""
    topic_slug: str = ""
    request_notes: str = ""
    issue_number: int | None = None
    issue_url: str = ""
    requested_by: str = ""
    existing_summary: str = ""
    existing_page_excerpt: str = ""

    def normalized_mode(self) -> str:
        aliases = {
            "new": "new-topic",
            "topic": "new-topic",
            "update": "update-page",
            "refresh": "update-page",
            "expand": "expand-page",
        }
        raw_mode = self.mode.strip().lower() or "auto"
        return aliases.get(raw_mode, raw_mode)

    def is_manual(self) -> bool:
        return self.normalized_mode() != "auto"

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["mode"] = self.normalized_mode()
        return payload


@dataclass
class TopicPlan:
    title: str
    slug: str
    summary: str
    rationale: str
    tags: list[str]
    search_angles: list[str]
    outline: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchResult:
    query: str
    title: str
    url: str
    snippet: str
    rank: int
    provider: str


@dataclass
class FetchedSource:
    source_id: str
    turn_index: int
    query: str
    url: str
    final_url: str
    domain: str
    provider: str
    rank: int
    search_title: str
    search_snippet: str
    page_title: str
    status: str
    word_count: int
    excerpt: list[str]
    text_preview: str
    relevance_score: float
    html_archive_path: str | None = None

    def display_title(self) -> str:
        return self.page_title or self.search_title or self.url

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TurnDigest:
    turn_index: int
    focus: str
    queries: list[str]
    search_result_count: int
    sources: list[FetchedSource] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "turn_index": self.turn_index,
            "focus": self.focus,
            "queries": self.queries,
            "search_result_count": self.search_result_count,
            "sources": [source.to_dict() for source in self.sources],
            "key_findings": self.key_findings,
            "contradictions": self.contradictions,
            "open_questions": self.open_questions,
        }


@dataclass
class ResearchRun:
    run_id: str
    generated_at: str
    plan: TopicPlan
    turns: list[TurnDigest]
    synthesis: str
    request: RequestContext = field(default_factory=RequestContext)

    @property
    def source_count(self) -> int:
        return sum(len(turn.sources) for turn in self.turns)

    def top_sources(self, limit: int = 24) -> list[FetchedSource]:
        flat_sources = [source for turn in self.turns for source in turn.sources]
        ranked = sorted(
            flat_sources,
            key=lambda source: (-source.relevance_score, source.rank, source.domain),
        )
        return ranked[:limit]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "plan": self.plan.to_dict(),
            "request": self.request.to_dict(),
            "turns": [turn.to_dict() for turn in self.turns],
            "synthesis": self.synthesis,
            "source_count": self.source_count,
        }
