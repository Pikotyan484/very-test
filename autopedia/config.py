from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from autopedia.utils import ROOT_DIR, ensure_dir, load_env_file


DEFAULT_SEED_TOPICS = [
    "Quantum error correction",
    "mRNA vaccine manufacturing",
    "Direct air capture",
    "Advanced lithography",
    "CRISPR therapeutics",
    "Grid-scale battery safety",
    "Protein structure prediction",
    "Geothermal closed-loop systems",
    "Synthetic aperture radar satellites",
    "Water desalination membranes",
]


@dataclass
class Settings:
    root_dir: Path
    docs_dir: Path
    wiki_dir: Path
    reports_dir: Path
    data_dir: Path
    html_cache_dir: Path
    state_file: Path
    site_name: str
    language: str
    github_repository: str
    api_key: str | None
    base_url: str
    model: str
    demo_mode: bool
    research_turns: int
    search_queries_per_turn: int
    search_results_per_query: int
    min_pages_per_turn: int
    max_pages_per_turn: int
    fetch_workers: int
    max_fetch_candidates_multiplier: int
    min_source_words: int
    report_min_lines: int
    store_raw_html: bool
    max_reports_to_keep: int
    minimum_reference_count: int
    seed_topics: list[str]
    search_providers: list[str]
    brave_api_key: str | None
    searxng_url: str | None
    max_report_chunk_chars: int
    max_report_chunks: int

    def repository_url(self) -> str:
        repository = self.github_repository.strip().strip("/")
        if not repository:
            return ""
        return f"https://github.com/{repository}"

    def issues_new_url(self) -> str:
        repository_url = self.repository_url()
        if not repository_url:
            return ""
        return f"{repository_url}/issues/new"

    def build_issue_url(self, *, title: str, body: str, labels: list[str] | None = None) -> str:
        issues_url = self.issues_new_url()
        if not issues_url:
            return ""
        params = {
            "title": title,
            "body": body,
        }
        if labels:
            params["labels"] = ",".join(label.strip() for label in labels if label.strip())
        return f"{issues_url}?{urlencode(params)}"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _env_csv(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_settings() -> Settings:
    load_env_file(ROOT_DIR / ".env")

    docs_dir = ensure_dir(ROOT_DIR / "docs")
    wiki_dir = ensure_dir(docs_dir / "wiki")
    reports_dir = ensure_dir(ROOT_DIR / "reports")
    data_dir = ensure_dir(ROOT_DIR / "data")
    html_cache_dir = ensure_dir(reports_dir / "html-cache")
    api_key = os.getenv("AUTOPEDIA_API_KEY")
    brave_api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    searxng_url = os.getenv("AUTOPEDIA_SEARXNG_URL")
    default_providers = ["searxng", "ddgs"] if searxng_url else ["ddgs"]

    settings = Settings(
        root_dir=ROOT_DIR,
        docs_dir=docs_dir,
        wiki_dir=wiki_dir,
        reports_dir=reports_dir,
        data_dir=data_dir,
        html_cache_dir=html_cache_dir,
        state_file=data_dir / "site-state.json",
        site_name=os.getenv("AUTOPEDIA_SITE_NAME", "AutoPedia"),
        language=os.getenv("AUTOPEDIA_LANGUAGE", "ja"),
        github_repository=os.getenv("AUTOPEDIA_GITHUB_REPOSITORY") or os.getenv("GITHUB_REPOSITORY", ""),
        api_key=api_key,
        base_url=os.getenv("AUTOPEDIA_BASE_URL", "https://apifreellm.com/api/v1"),
        model=os.getenv("AUTOPEDIA_MODEL", "llama-3"),
        demo_mode=_env_bool("AUTOPEDIA_DEMO_MODE", not bool(api_key)),
        research_turns=max(1, _env_int("AUTOPEDIA_RESEARCH_TURNS", 3)),
        search_queries_per_turn=max(3, _env_int("AUTOPEDIA_SEARCH_QUERIES_PER_TURN", 10)),
        search_results_per_query=max(5, _env_int("AUTOPEDIA_SEARCH_RESULTS_PER_QUERY", 24)),
        min_pages_per_turn=max(10, _env_int("AUTOPEDIA_MIN_PAGES_PER_TURN", 100)),
        max_pages_per_turn=max(20, _env_int("AUTOPEDIA_MAX_PAGES_PER_TURN", 160)),
        fetch_workers=max(4, _env_int("AUTOPEDIA_FETCH_WORKERS", 16)),
        max_fetch_candidates_multiplier=max(1, _env_int("AUTOPEDIA_FETCH_CANDIDATE_MULTIPLIER", 2)),
        min_source_words=max(50, _env_int("AUTOPEDIA_MIN_SOURCE_WORDS", 180)),
        report_min_lines=max(200, _env_int("AUTOPEDIA_REPORT_MIN_LINES", 2000)),
        store_raw_html=_env_bool("AUTOPEDIA_STORE_RAW_HTML", False),
        max_reports_to_keep=max(1, _env_int("AUTOPEDIA_MAX_REPORTS_TO_KEEP", 10)),
        minimum_reference_count=max(1, _env_int("AUTOPEDIA_MIN_REFERENCE_COUNT", 8)),
        seed_topics=_env_csv("AUTOPEDIA_SEED_TOPICS", DEFAULT_SEED_TOPICS),
        search_providers=_env_csv("AUTOPEDIA_SEARCH_PROVIDERS", default_providers),
        brave_api_key=brave_api_key,
        searxng_url=searxng_url,
        max_report_chunk_chars=max(2000, _env_int("AUTOPEDIA_MAX_REPORT_CHUNK_CHARS", 12000)),
        max_report_chunks=max(2, _env_int("AUTOPEDIA_MAX_REPORT_CHUNKS", 20)),
    )
    settings.max_pages_per_turn = max(settings.max_pages_per_turn, settings.min_pages_per_turn)
    return settings
