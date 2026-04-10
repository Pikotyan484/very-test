from __future__ import annotations

import argparse
from pathlib import Path

from autopedia.config import load_settings
from autopedia.llm_client import LLMClient
from autopedia.models import RequestContext
from autopedia.planner import Planner
from autopedia.requests import request_from_args_and_env
from autopedia.reporting import ReportBuilder
from autopedia.research import ResearchEngine
from autopedia.search import SearchClient
from autopedia.site import SiteBuilder
from autopedia.writer import WikiWriter


def run_cycle(request: RequestContext | None = None) -> None:
    settings = load_settings()
    llm = LLMClient(settings)
    planner = Planner(settings, llm)
    search_client = SearchClient(settings)
    site = SiteBuilder(settings)
    state = site.load_state()
    request = site.prepare_request_context(state, request or RequestContext())

    plan = planner.select_topic(state, request)
    research_engine = ResearchEngine(settings, llm, planner, search_client)
    report_path: Path | None = None

    try:
        run = research_engine.run_with_request(plan, request)

        report_builder = ReportBuilder(settings)
        report_path, report_text = report_builder.write(run)

        writer = WikiWriter(settings, llm)
        page_markdown = writer.build_page(run, report_text)
        page_path = site.write_wiki_page(run, page_markdown, report_path)

        site.register_run(state, run, report_path, page_path)
        site.rebuild_static_pages(state)
        site.save_state(state)

        print(f"Generated {run.plan.title} with {run.source_count} sources.")
        print(f"Request mode: {run.request.normalized_mode()}")
        print(f"Report: {report_path}")
        print(f"Page: {page_path}")
    except Exception as exc:
        site.register_failure(
            state,
            title=plan.title,
            slug=plan.slug,
            request=request,
            error_message=str(exc),
            report_path=report_path,
        )
        site.rebuild_static_pages(state)
        site.save_state(state)
        if request.normalized_mode() == "auto":
            print(f"Auto cycle failed for {plan.title}: {exc}")
            if report_path is not None:
                print(f"Partial report: {report_path}")
            return
        raise


def rebuild_site() -> None:
    settings = load_settings()
    site = SiteBuilder(settings)
    state = site.load_state()
    site.rebuild_static_pages(state)
    site.save_state(state)
    print("Static site pages rebuilt.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoPedia autonomous wiki generator")
    parser.add_argument("--request-mode", default=None)
    parser.add_argument("--topic-title", default=None)
    parser.add_argument("--topic-slug", default=None)
    parser.add_argument("--request-notes", default=None)
    parser.add_argument("--issue-number", default=None)
    parser.add_argument("--issue-url", default=None)
    parser.add_argument("--requested-by", default=None)
    subparsers = parser.add_subparsers(dest="command", required=False)

    subparsers.add_parser("run-cycle", help="Run one full topic -> research -> wiki cycle")
    subparsers.add_parser("rebuild-site", help="Rebuild index pages from saved state")

    args = parser.parse_args()
    command = args.command or "run-cycle"
    if command == "rebuild-site":
        rebuild_site()
        return
    run_cycle(request_from_args_and_env(args))
