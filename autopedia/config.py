from __future__ import annotations

import math
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
    deep_research_multiplier: float
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
    translation_languages: list[str]
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


def _env_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _env_csv(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _scale_setting(
    base_value: int,
    multiplier: float,
    *,
    exponent: float,
    minimum: int,
    maximum: int | None = None,
) -> int:
    scaled = base_value
    if multiplier > 1:
        scaled = math.ceil(base_value * (multiplier**exponent))
    scaled = max(minimum, scaled)
    if maximum is not None:
        scaled = min(maximum, scaled)
    return scaled


def load_settings() -> Settings:
    load_env_file(ROOT_DIR / ".env")

    docs_dir = ensure_dir(ROOT_DIR / "docs")
    wiki_dir = ensure_dir(docs_dir / "wiki")
    reports_dir = ensure_dir(ROOT_DIR / "reports")
    data_dir = ensure_dir(ROOT_DIR / "data")
    html_cache_dir = ensure_dir(reports_dir / "html-cache")
    site_language = os.getenv("AUTOPEDIA_LANGUAGE", "ja")
    api_key = os.getenv("AUTOPEDIA_API_KEY")
    brave_api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    searxng_url = os.getenv("AUTOPEDIA_SEARXNG_URL")
    default_providers = ["searxng", "ddgs"] if searxng_url else ["ddgs"]
    deep_research_multiplier = max(1.0, _env_float("AUTOPEDIA_DEEP_RESEARCH_MULTIPLIER", 1.0))
    running_in_github_actions = _env_bool("GITHUB_ACTIONS", False)

    explicit_research_turns = _env_optional_int("AUTOPEDIA_RESEARCH_TURNS")
    explicit_search_queries_per_turn = _env_optional_int("AUTOPEDIA_SEARCH_QUERIES_PER_TURN")
    explicit_search_results_per_query = _env_optional_int("AUTOPEDIA_SEARCH_RESULTS_PER_QUERY")
    explicit_min_pages_per_turn = _env_optional_int("AUTOPEDIA_MIN_PAGES_PER_TURN")
    explicit_max_pages_per_turn = _env_optional_int("AUTOPEDIA_MAX_PAGES_PER_TURN")
    explicit_fetch_workers = _env_optional_int("AUTOPEDIA_FETCH_WORKERS")
    explicit_fetch_candidate_multiplier = _env_optional_int("AUTOPEDIA_FETCH_CANDIDATE_MULTIPLIER")
    explicit_report_min_lines = _env_optional_int("AUTOPEDIA_REPORT_MIN_LINES")
    explicit_min_reference_count = _env_optional_int("AUTOPEDIA_MIN_REFERENCE_COUNT")
    explicit_max_report_chunk_chars = _env_optional_int("AUTOPEDIA_MAX_REPORT_CHUNK_CHARS")
    explicit_max_report_chunks = _env_optional_int("AUTOPEDIA_MAX_REPORT_CHUNKS")

    base_research_turns = max(1, explicit_research_turns or 3)
    base_search_queries_per_turn = max(3, explicit_search_queries_per_turn or 10)
    base_search_results_per_query = max(5, explicit_search_results_per_query or 24)
    base_min_pages_per_turn = max(10, explicit_min_pages_per_turn or 100)
    base_max_pages_per_turn = max(20, explicit_max_pages_per_turn or 160)
    base_fetch_workers = max(4, explicit_fetch_workers or 16)
    base_fetch_candidate_multiplier = max(1, explicit_fetch_candidate_multiplier or 2)
    base_report_min_lines = max(200, explicit_report_min_lines or 2000)
    base_min_reference_count = max(1, explicit_min_reference_count or 8)
    base_max_report_chunk_chars = max(2000, explicit_max_report_chunk_chars or 12000)
    base_max_report_chunks = max(2, explicit_max_report_chunks or 20)

    settings = Settings(
        root_dir=ROOT_DIR,
        docs_dir=docs_dir,
        wiki_dir=wiki_dir,
        reports_dir=reports_dir,
        data_dir=data_dir,
        html_cache_dir=html_cache_dir,
        state_file=data_dir / "site-state.json",
        site_name=os.getenv("AUTOPEDIA_SITE_NAME", "AutoPedia"),
        language=site_language,
        github_repository=os.getenv("AUTOPEDIA_GITHUB_REPOSITORY") or os.getenv("GITHUB_REPOSITORY", ""),
        api_key=api_key,
        base_url=os.getenv("AUTOPEDIA_BASE_URL", "https://apifreellm.com/api/v1"),
        model=os.getenv("AUTOPEDIA_MODEL", "llama-3"),
        demo_mode=_env_bool("AUTOPEDIA_DEMO_MODE", not bool(api_key)),
        deep_research_multiplier=deep_research_multiplier,
        research_turns=_scale_setting(
            base_research_turns,
            1.0 if explicit_research_turns is not None else deep_research_multiplier,
            exponent=0.5,
            minimum=1,
            maximum=18,
        ),
        search_queries_per_turn=_scale_setting(
            base_search_queries_per_turn,
            1.0 if explicit_search_queries_per_turn is not None else deep_research_multiplier,
            exponent=0.12,
            minimum=3,
            maximum=18,
        ),
        search_results_per_query=_scale_setting(
            base_search_results_per_query,
            1.0 if explicit_search_results_per_query is not None else deep_research_multiplier,
            exponent=0.08,
            minimum=5,
            maximum=36,
        ),
        min_pages_per_turn=_scale_setting(
            base_min_pages_per_turn,
            1.0 if explicit_min_pages_per_turn is not None else deep_research_multiplier,
            exponent=0.35,
            minimum=10,
            maximum=320,
        ),
        max_pages_per_turn=_scale_setting(
            base_max_pages_per_turn,
            1.0 if explicit_max_pages_per_turn is not None else deep_research_multiplier,
            exponent=0.4,
            minimum=20,
            maximum=560,
        ),
        fetch_workers=_scale_setting(
            base_fetch_workers,
            1.0 if explicit_fetch_workers is not None else deep_research_multiplier,
            exponent=0.28,
            minimum=4,
            maximum=40,
        ),
        max_fetch_candidates_multiplier=_scale_setting(
            base_fetch_candidate_multiplier,
            1.0 if explicit_fetch_candidate_multiplier is not None else deep_research_multiplier,
            exponent=0.12,
            minimum=1,
            maximum=4,
        ),
        min_source_words=max(50, _env_int("AUTOPEDIA_MIN_SOURCE_WORDS", 180)),
        report_min_lines=_scale_setting(
            base_report_min_lines,
            1.0 if explicit_report_min_lines is not None else deep_research_multiplier,
            exponent=0.72,
            minimum=200,
            maximum=18000,
        ),
        store_raw_html=_env_bool("AUTOPEDIA_STORE_RAW_HTML", False),
        max_reports_to_keep=max(1, _env_int("AUTOPEDIA_MAX_REPORTS_TO_KEEP", 10)),
        minimum_reference_count=_scale_setting(
            base_min_reference_count,
            1.0 if explicit_min_reference_count is not None else deep_research_multiplier,
            exponent=0.2,
            minimum=1,
            maximum=16,
        ),
        translation_languages=_env_csv("AUTOPEDIA_TRANSLATION_LANGUAGES", [site_language, "en", "zh-CN", "es"]),
        seed_topics=_env_csv("AUTOPEDIA_SEED_TOPICS", DEFAULT_SEED_TOPICS),
        search_providers=_env_csv("AUTOPEDIA_SEARCH_PROVIDERS", default_providers),
        brave_api_key=brave_api_key,
        searxng_url=searxng_url,
        max_report_chunk_chars=_scale_setting(
            base_max_report_chunk_chars,
            1.0 if explicit_max_report_chunk_chars is not None else deep_research_multiplier,
            exponent=0.12,
            minimum=2000,
            maximum=18000,
        ),
        max_report_chunks=_scale_setting(
            base_max_report_chunks,
            1.0 if explicit_max_report_chunks is not None else deep_research_multiplier,
            exponent=0.28,
            minimum=2,
            maximum=48,
        ),
    )
    if running_in_github_actions:
        settings.research_turns = min(settings.research_turns, 12)
        settings.fetch_workers = min(settings.fetch_workers, 8)
        settings.max_fetch_candidates_multiplier = min(settings.max_fetch_candidates_multiplier, 2)
        settings.min_pages_per_turn = min(settings.min_pages_per_turn, 160)
        settings.max_pages_per_turn = min(settings.max_pages_per_turn, 220)
        settings.report_min_lines = min(settings.report_min_lines, 12000)
        settings.max_report_chunks = min(settings.max_report_chunks, 24)
    settings.max_pages_per_turn = max(settings.max_pages_per_turn, settings.min_pages_per_turn)
    return settings
