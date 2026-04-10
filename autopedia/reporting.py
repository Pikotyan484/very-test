from __future__ import annotations

from pathlib import Path

from autopedia.config import Settings
from autopedia.models import ResearchRun
from autopedia.utils import ensure_dir


class ReportBuilder:
    def __init__(self, settings: Settings):
        self.settings = settings

    def write(self, run: ResearchRun) -> tuple[Path, str]:
        report_text = self._build_markdown(run)
        report_path = self.settings.reports_dir / f"{run.run_id}.md"
        ensure_dir(report_path.parent)
        report_path.write_text(report_text, encoding="utf-8")
        self._trim_old_reports()
        return report_path, report_text

    def _build_markdown(self, run: ResearchRun) -> str:
        lines: list[str] = [
            f"# AutoPedia Research Report: {run.plan.title}",
            "",
            "## Run Metadata",
            f"- Run ID: {run.run_id}",
            f"- Generated at: {run.generated_at}",
            f"- Topic slug: {run.plan.slug}",
            f"- Research turns: {len(run.turns)}",
            f"- Total fetched sources: {run.source_count}",
            f"- Request mode: {run.request.normalized_mode()}",
            "",
            "## Request Context",
            f"- Topic title: {run.request.topic_title or run.plan.title}",
            f"- Topic slug: {run.request.topic_slug or run.plan.slug}",
            f"- Requested by: {run.request.requested_by or 'n/a'}",
            f"- Issue number: {run.request.issue_number if run.request.issue_number is not None else 'n/a'}",
            f"- Issue URL: {run.request.issue_url or 'n/a'}",
            f"- Request notes: {run.request.request_notes or 'n/a'}",
            "",
            "## Topic Plan",
            f"- Title: {run.plan.title}",
            f"- Summary: {run.plan.summary}",
            f"- Rationale: {run.plan.rationale}",
            f"- Tags: {', '.join(run.plan.tags)}",
            "- Search Angles:",
            *[f"  - {angle}" for angle in run.plan.search_angles],
            "- Outline:",
            *[f"  - {item}" for item in run.plan.outline],
            "",
            "## Cross-Turn Synthesis",
            run.synthesis,
            "",
        ]

        source_counter = 1
        reserve_lines: list[str] = []

        for turn in run.turns:
            finding_lines = [f"- {finding}" for finding in turn.key_findings] or [
                "- No clear findings were distilled for this turn."
            ]
            contradiction_lines = [f"- {item}" for item in turn.contradictions] or [
                "- No explicit contradictions extracted in this turn."
            ]
            question_lines = [f"- {item}" for item in turn.open_questions] or [
                "- No additional open questions recorded."
            ]
            lines.extend(
                [
                    f"## Turn {turn.turn_index}",
                    "",
                    f"### Focus",
                    turn.focus,
                    "",
                    "### Queries",
                    *[f"- {query}" for query in turn.queries],
                    "",
                    "### Turn Findings",
                    *finding_lines,
                    "",
                    "### Contradictions",
                    *contradiction_lines,
                    "",
                    "### Open Questions",
                    *question_lines,
                    "",
                    "### Source Catalog",
                ]
            )

            for source in turn.sources:
                lines.extend(
                    [
                        f"#### Source {source_counter:04d}: {source.display_title()}",
                        f"- Source ID: {source.source_id}",
                        f"- Turn: {source.turn_index}",
                        f"- Query: {source.query}",
                        f"- Provider: {source.provider}",
                        f"- Search rank: {source.rank}",
                        f"- Domain: {source.domain}",
                        f"- URL: {source.final_url}",
                        f"- Search snippet: {source.search_snippet or 'n/a'}",
                        f"- Page word count estimate: {source.word_count}",
                        f"- Relevance score: {source.relevance_score:.2f}",
                    ]
                )
                if source.html_archive_path:
                    lines.append(f"- HTML archive: {source.html_archive_path}")
                lines.extend(["- Key excerpt lines:"])
                lines.extend([f"  - {line}" for line in source.excerpt] or ["  - No excerpt lines available."])
                lines.extend(["- Extended extract lines:"])
                preview_lines = source.text_preview.splitlines()[:18]
                lines.extend([f"  - {line}" for line in preview_lines] or ["  - No preview available."])
                lines.append("")

                reserve_lines.extend([f"- {line}" for line in source.text_preview.splitlines()[:24]])
                source_counter += 1

        if len(lines) < self.settings.report_min_lines:
            lines.extend(["## Detail Reserve Appendix", ""])
            reserve_index = 0
            while len(lines) < self.settings.report_min_lines and reserve_index < len(reserve_lines):
                lines.append(reserve_lines[reserve_index])
                reserve_index += 1

        while len(lines) < self.settings.report_min_lines:
            lines.append("- Additional detail not available; consider increasing AUTOPEDIA_MAX_PAGES_PER_TURN or AUTOPEDIA_RESEARCH_TURNS.")

        return "\n".join(lines) + "\n"

    def _trim_old_reports(self) -> None:
        reports = sorted(self.settings.reports_dir.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
        for stale_report in reports[self.settings.max_reports_to_keep :]:
            stale_report.unlink(missing_ok=True)
