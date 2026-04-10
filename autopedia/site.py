from __future__ import annotations

from pathlib import Path

from autopedia.config import Settings
from autopedia.models import RequestContext, ResearchRun
from autopedia.requests import build_request_issue_url
from autopedia.utils import ensure_dir, markdown_excerpt, read_json, slugify_text, write_json


class SiteBuilder:
    def __init__(self, settings: Settings):
        self.settings = settings

    def load_state(self) -> dict:
        state = read_json(
            self.settings.state_file,
            default={
                "project_name": self.settings.site_name,
                "started_at": "",
                "completed_topics": [],
                "run_history": [],
            },
        )
        state.setdefault("project_name", self.settings.site_name)
        state.setdefault("completed_topics", [])
        state.setdefault("run_history", [])
        return state

    def save_state(self, state: dict) -> None:
        write_json(self.settings.state_file, state)

    def prepare_request_context(self, state: dict, request: RequestContext) -> RequestContext:
        resolved = RequestContext(**request.to_dict())
        if not resolved.is_manual():
            return resolved

        entry = self._find_topic_entry(state, resolved.topic_slug, resolved.topic_title)
        if entry:
            if resolved.normalized_mode() == "new-topic":
                resolved.mode = "expand-page"
            resolved.topic_title = resolved.topic_title or str(entry.get("title", ""))
            resolved.topic_slug = resolved.topic_slug or str(entry.get("slug", ""))
            resolved.existing_summary = str(entry.get("summary", ""))
            resolved.existing_page_excerpt = self._read_existing_page_excerpt(str(entry.get("page_path", "")))
        elif resolved.topic_title and not resolved.topic_slug:
            resolved.topic_slug = slugify_text(resolved.topic_title)
        return resolved

    def write_wiki_page(self, run: ResearchRun, markdown: str, report_path: Path) -> Path:
        page_path = self.settings.wiki_dir / f"{run.plan.slug}.md"
        ensure_dir(page_path.parent)
        page_path.write_text(markdown, encoding="utf-8")
        return page_path

    def register_run(self, state: dict, run: ResearchRun, report_path: Path, page_path: Path) -> None:
        entry = {
            "title": run.plan.title,
            "slug": run.plan.slug,
            "summary": run.plan.summary,
            "tags": run.plan.tags,
            "generated_at": run.generated_at,
            "sources_analyzed": run.source_count,
            "research_turns": len(run.turns),
            "request_mode": run.request.normalized_mode(),
            "page_path": str(page_path.relative_to(self.settings.docs_dir)).replace("\\", "/"),
            "report_path": str(report_path.relative_to(self.settings.root_dir)).replace("\\", "/"),
        }

        completed = [item for item in state.get("completed_topics", []) if item.get("slug") != run.plan.slug]
        completed.insert(0, entry)
        state["completed_topics"] = completed[:200]

        run_entry = {
            "run_id": run.run_id,
            "topic": run.plan.title,
            "slug": run.plan.slug,
            "generated_at": run.generated_at,
            "sources_analyzed": run.source_count,
            "request_mode": run.request.normalized_mode(),
            "report_path": entry["report_path"],
            "page_path": entry["page_path"],
        }
        history = state.get("run_history", [])
        history.insert(0, run_entry)
        state["run_history"] = history[:300]

    def rebuild_static_pages(self, state: dict) -> None:
        self._write_home_page(state)
        self._write_wiki_index(state)

    def _write_home_page(self, state: dict) -> None:
        latest = state.get("completed_topics", [])[:6]
        page_count = len(state.get("completed_topics", []))
        source_total = sum(item.get("sources_analyzed", 0) for item in state.get("completed_topics", []))
        repo_url = self.settings.repository_url() or "https://github.com"
        issues_url = self.settings.issues_new_url()
        cards = []
        for item in latest:
            update_url = build_request_issue_url(
                self.settings,
                mode="expand-page",
                topic_title=item["title"],
                topic_slug=item["slug"],
                request_notes="Please update this page and expand missing sections with newer evidence.",
                existing_page_path=f"docs/{item['page_path']}",
            )
            cards.append(
                "\n".join(
                    [
                        '<article class="ap-card">',
                        f"  <span class=\"ap-card__kicker\">{item.get('generated_at', '')[:10]}</span>",
                        f"  <h3><a href=\"wiki/{item['slug']}/\">{item['title']}</a></h3>",
                        f"  <p>{item['summary']}</p>",
                        f"  <div class=\"ap-card__meta\">{item.get('sources_analyzed', 0)} sources</div>",
                        (
                            f"  <div class=\"ap-card__actions\"><a href=\"{update_url}\" target=\"_blank\" rel=\"noopener\">更新または拡張</a></div>"
                            if update_url
                            else ""
                        ),
                        "</article>",
                    ]
                )
            )
        card_markup = "\n".join(cards) if cards else '<article class="ap-card ap-card--empty"><p>No pages yet. Trigger the first AutoPedia cycle to generate one.</p></article>'

        if issues_url:
            request_section = "\n".join(
                [
                    '<section id="request-topic" class="ap-request-panel">',
                    '  <div class="ap-request-panel__copy">',
                    '    <p class="ap-eyebrow">User Requests</p>',
                    '    <h2>希望のトピックをAIに依頼</h2>',
                    '    <p>ここで話題名と要望を書いて送ると、GitHub Issue が作成され、その Issue をトリガーに GitHub Actions が全自動で long deep research と wiki 生成を実行します。</p>',
                    '  </div>',
                    f'  <form class="ap-request-form" data-autopedia-request-form data-issues-url="{issues_url}">',
                    '    <label><span>Topic Title</span><input type="text" name="topic_title" placeholder="Example: Solid-state batteries" required></label>',
                    '    <label><span>What should be covered?</span><textarea name="request_notes" rows="5" placeholder="Example: Focus on commercialization, safety constraints, and latest performance benchmarks."></textarea></label>',
                    '    <button class="md-button md-button--primary" type="submit">新しいWikiを依頼する</button>',
                    '  </form>',
                    '</section>',
                ]
            )
        else:
            request_section = "\n".join(
                [
                    "## Request a Topic",
                    "",
                    "> Request buttons become active after `AUTOPEDIA_GITHUB_REPOSITORY` is configured or the site is built on GitHub Actions.",
                ]
            )

        index_content = "\n".join(
            [
                f"# {self.settings.site_name}",
                "",
                '<section class="ap-hero">',
                '  <div class="ap-hero__copy">',
                '    <p class="ap-eyebrow">Continuous AI Research Wiki</p>',
                f"    <h1>{self.settings.site_name}</h1>",
                '    <p class="ap-lead">AI picks the next topic, performs large-scale multi-turn web research, produces a long-form report, and turns that evidence into a GitHub Pages wiki.</p>',
                '    <div class="ap-hero__actions">',
                '      <a class="md-button md-button--primary" href="wiki/">Wiki Index</a>',
                '      <a class="md-button" href="#request-topic">トピックを依頼</a>',
                f'      <a class="md-button" href="{repo_url}">GitHub</a>',
                '    </div>',
                '  </div>',
                '  <div class="ap-metrics">',
                f'    <div><span>{page_count}</span><small>pages</small></div>',
                f'    <div><span>{source_total}</span><small>sources</small></div>',
                f'    <div><span>{state.get("run_history", [])[:1][0]["generated_at"][:10] if state.get("run_history") else "--"}</span><small>latest run</small></div>',
                '  </div>',
                '</section>',
                "",
                "## Latest Pages",
                "",
                '<section class="ap-card-grid">',
                card_markup,
                '</section>',
                "",
                request_section,
                "",
                "## Pipeline",
                "",
                "1. The planner chooses a topic that is not already covered.",
                "2. The research engine runs multi-turn online search and bulk page retrieval.",
                "3. A 2000+ line evidence report is written under the reports directory.",
                "4. The writer converts distilled evidence into a Markdown wiki page.",
                "5. Users can request new topics or page refreshes through GitHub Issue links and Actions processes them automatically.",
                "6. GitHub Actions commits the result, deploys GitHub Pages, and can immediately queue the next cycle.",
                "",
                "## Notes",
                "",
                "- Accuracy still depends on the configured model and search provider quality.",
                "- The default search path is keyless and free: DDGS, with optional self-hosted SearXNG for more control.",
                "- The site intentionally keeps reports in the repository so the generation trail stays auditable.",
            ]
        )
        (self.settings.docs_dir / "index.md").write_text(index_content + "\n", encoding="utf-8")

    def _write_wiki_index(self, state: dict) -> None:
        lines = ["# Wiki Index", "", "| Title | Generated | Sources | Action |", "| --- | --- | --- | --- |"]
        for item in state.get("completed_topics", []):
            action_url = build_request_issue_url(
                self.settings,
                mode="expand-page",
                topic_title=item["title"],
                topic_slug=item["slug"],
                request_notes="Please update this wiki page and expand any sections that are still shallow.",
                existing_page_path=f"docs/{item['page_path']}",
            )
            action_cell = f"[Update / expand]({action_url})" if action_url else "--"
            lines.append(
                f"| [{item['title']}]({item['slug']}/) | {item.get('generated_at', '')[:10]} | {item.get('sources_analyzed', 0)} | {action_cell} |"
            )
        if len(lines) == 4:
            lines.append("| No pages yet | -- | -- | -- |")
        (self.settings.wiki_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _find_topic_entry(self, state: dict, slug: str, title: str) -> dict | None:
        normalized_slug = slug.strip().lower()
        normalized_title = title.strip().lower()
        for item in state.get("completed_topics", []):
            item_slug = str(item.get("slug", "")).strip().lower()
            item_title = str(item.get("title", "")).strip().lower()
            if normalized_slug and item_slug == normalized_slug:
                return item
            if normalized_title and item_title == normalized_title:
                return item
        return None

    def _read_existing_page_excerpt(self, page_path: str) -> str:
        relative_path = page_path.strip().lstrip("/")
        if not relative_path:
            return ""
        file_path = self.settings.docs_dir / relative_path.removeprefix("docs/")
        if not file_path.exists():
            return ""
        return markdown_excerpt(file_path.read_text(encoding="utf-8"))
