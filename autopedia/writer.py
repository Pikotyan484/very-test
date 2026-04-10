from __future__ import annotations

import html
import re
from pathlib import Path

import markdown
import yaml

from autopedia.config import Settings
from autopedia.llm_client import LLMClient
from autopedia.models import ResearchRun
from autopedia.requests import build_request_issue_url
from autopedia.utils import chunk_text, markdown_headings, truncate_text, unique_preserve_order


LANGUAGE_LABELS = {
    "ja": "日本語",
    "en": "English",
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "ko": "한국어",
    "pt-BR": "Português (Brasil)",
}


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

        body_markdown = self.llm.complete_markdown(
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
        ).strip()

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
            "available_translations": self._resolved_translation_languages(),
        }
        references_markdown = self._references_markdown(references)
        body = self._compose_page(
            title=run.plan.title,
            summary=run.plan.summary,
            slug=run.plan.slug,
            generated_at=run.generated_at,
            source_count=run.source_count,
            research_turns=len(run.turns),
            model=metadata["model"],
            request_mode=run.request.normalized_mode(),
            request_issue=run.request.issue_url or "",
            tags=run.plan.tags,
            body_markdown=body_markdown,
            references_markdown=references_markdown,
        )
        front_matter = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
        return f"---\n{front_matter}\n---\n\n{body}\n"

    def upgrade_existing_pages(self) -> int:
        upgraded = 0
        for page_path in sorted(self.settings.wiki_dir.glob("*.md")):
            if page_path.name == "index.md":
                continue
            if self.upgrade_existing_page(page_path):
                upgraded += 1
        return upgraded

    def upgrade_existing_page(self, page_path: Path) -> bool:
        raw_text = page_path.read_text(encoding="utf-8")
        if "data-ap-translation-shell" in raw_text:
            return False

        metadata, content = self._split_front_matter(raw_text)
        if not metadata:
            return False

        body_markdown, references_markdown = self._extract_body_and_references(content)
        if not body_markdown:
            return False

        upgraded_body = self._compose_page(
            title=str(metadata.get("title", page_path.stem)).strip() or page_path.stem,
            summary=str(metadata.get("summary", "")).strip(),
            slug=str(metadata.get("topic_slug", page_path.stem)).strip() or page_path.stem,
            generated_at=str(metadata.get("generated_at", "")).strip(),
            source_count=int(metadata.get("sources_analyzed", 0) or 0),
            research_turns=int(metadata.get("research_turns", 0) or 0),
            model=str(metadata.get("model", "demo-mode")).strip() or "demo-mode",
            request_mode=str(metadata.get("request_mode", "auto")).strip() or "auto",
            request_issue=str(metadata.get("request_issue", "") or ""),
            tags=[str(tag) for tag in metadata.get("tags", [])],
            body_markdown=body_markdown,
            references_markdown=references_markdown,
        )

        normalized_metadata = dict(metadata)
        normalized_metadata["available_translations"] = self._resolved_translation_languages()
        front_matter = yaml.safe_dump(normalized_metadata, sort_keys=False, allow_unicode=True).strip()
        page_path.write_text(f"---\n{front_matter}\n---\n\n{upgraded_body}\n", encoding="utf-8")
        return True

    def _compose_page(
        self,
        *,
        title: str,
        summary: str,
        slug: str,
        generated_at: str,
        source_count: int,
        research_turns: int,
        model: str,
        request_mode: str,
        request_issue: str,
        tags: list[str],
        body_markdown: str,
        references_markdown: str,
    ) -> str:
        page_path = f"docs/wiki/{slug}.md"
        update_url = build_request_issue_url(
            self.settings,
            mode="update-page",
            topic_title=title,
            topic_slug=slug,
            request_notes="Please refresh this page against the latest trustworthy sources.",
            existing_page_path=page_path,
        )
        expand_url = build_request_issue_url(
            self.settings,
            mode="expand-page",
            topic_title=title,
            topic_slug=slug,
            request_notes="Please expand this page with additional depth, missing sections, and newly available evidence.",
            existing_page_path=page_path,
        )
        new_topic_url = build_request_issue_url(
            self.settings,
            mode="new-topic",
            request_notes="Please create a new wiki page for the requested topic.",
        )

        language_articles = self._build_language_articles(title, summary, body_markdown)
        translation_count = max(0, len(language_articles) - 1)
        sections = markdown_headings(body_markdown, max_items=8)
        section_items = "\n".join(
            f"      <li>{html.escape(item)}</li>" for item in sections
        ) or "      <li>Overview</li>"
        tag_items = "\n".join(
            f'      <span class="ap-tag-pill">{html.escape(tag)}</span>' for tag in tags[:6]
        )
        references_html = self._render_markdown_html(references_markdown)

        action_lines = []
        if expand_url:
            action_lines.append(
                f'  <a class="md-button md-button--primary" href="{expand_url}" target="_blank" rel="noopener">このWikiページを更新または拡張して</a>'
            )
        if update_url:
            action_lines.append(
                f'  <a class="md-button" href="{update_url}" target="_blank" rel="noopener">最新情報で更新する</a>'
            )
        if new_topic_url:
            action_lines.append(
                f'  <a class="md-button" href="{new_topic_url}" target="_blank" rel="noopener">別トピックを依頼</a>'
            )
        action_block = (
            '<div class="ap-inline-actions">\n' + "\n".join(action_lines) + "\n</div>"
            if action_lines
            else ""
        )

        button_items = []
        view_items = []
        for index, article in enumerate(language_articles):
            active_class = " is-active" if index == 0 else ""
            hidden_attr = "" if index == 0 else " hidden"
            button_items.append(
                f'      <button type="button" class="ap-language-pill{active_class}" data-ap-language-button="{article["code"]}" aria-pressed="{"true" if index == 0 else "false"}">{html.escape(article["label"])}</button>'
            )
            view_items.append(
                f'    <section class="ap-language-view{active_class}" data-ap-language-view="{article["code"]}"{hidden_attr}>\n'
                f'      <div class="ap-rendered-article" lang="{article["code"]}">\n{article["html"]}\n      </div>\n'
                f'    </section>'
            )

        return "\n".join(
            [
                '<div class="ap-article-shell">',
                '  <aside class="ap-article-sidebar">',
                '    <section class="ap-meta-card ap-meta-card--strong">',
                '      <p class="ap-meta-card__eyebrow">Reader View</p>',
                f'      <h2>{html.escape(title)}</h2>',
                '      <p>読みやすさを優先したレイアウトと AI 多言語翻訳ビューを同じページ内に統合しています。</p>',
                '    </section>',
                '    <section class="ap-meta-card">',
                '      <p class="ap-meta-card__eyebrow">Signals</p>',
                '      <ul class="ap-stat-list">',
                f'        <li><strong>{source_count}</strong><span>sources analyzed</span></li>',
                f'        <li><strong>{research_turns}</strong><span>research turns</span></li>',
                f'        <li><strong>{translation_count}</strong><span>translated views</span></li>',
                '      </ul>',
                '    </section>',
                '    <section class="ap-meta-card">',
                '      <p class="ap-meta-card__eyebrow">Snapshot</p>',
                f'      <p><strong>Generated</strong><br>{html.escape(generated_at or "n/a")}</p>',
                f'      <p><strong>Mode</strong><br>{html.escape(request_mode)}</p>',
                f'      <p><strong>Model</strong><br>{html.escape(model)}</p>',
                '    </section>',
                '    <section class="ap-meta-card">',
                '      <p class="ap-meta-card__eyebrow">Sections</p>',
                '      <ul class="ap-section-list">',
                section_items,
                '      </ul>',
                '    </section>',
                '    <section class="ap-meta-card">',
                '      <p class="ap-meta-card__eyebrow">Tags</p>',
                '      <div class="ap-tag-list">',
                tag_items or '      <span class="ap-tag-pill">research</span>',
                '      </div>',
                '    </section>',
                '    <section class="ap-meta-card ap-meta-card--subtle">',
                '      <p class="ap-meta-card__eyebrow">Translation</p>',
                '      <p>AI-generated translations preserve section structure and citation markers. For critical use, verify claims against the references below.</p>',
                '    </section>',
                (f'    <section class="ap-meta-card ap-meta-card--subtle"><p class="ap-meta-card__eyebrow">Request</p><p><a href="{html.escape(request_issue)}" target="_blank" rel="noopener">Open the originating request</a></p></section>' if request_issue else ''),
                action_block,
                '  </aside>',
                '  <div class="ap-article-main">',
                '    <section class="ap-translation-shell" data-ap-translation-shell>',
                '      <div class="ap-language-toolbar">',
                '        <div class="ap-language-toolbar__copy">',
                '          <p class="ap-meta-card__eyebrow">AI Multilingual Translation</p>',
                '          <h2>Read this page in multiple languages</h2>',
                '          <p>Original references stay unchanged for traceability. The original page language remains the authoritative rendering.</p>',
                '        </div>',
                '        <div class="ap-language-toolbar__controls">',
                *button_items,
                '        </div>',
                '      </div>',
                *view_items,
                '    </section>',
                '    <section class="ap-reference-card">',
                '      <div class="ap-reference-card__head">',
                '        <p class="ap-meta-card__eyebrow">Sources</p>',
                '        <h2>References</h2>',
                '        <p>Reference titles and URLs remain in their source language to preserve auditability.</p>',
                '      </div>',
                f'      <div class="ap-rendered-article ap-reference-card__body">\n{references_html}\n      </div>',
                '    </section>',
                '  </div>',
                '</div>',
            ]
        )

    def _build_language_articles(self, title: str, summary: str, body_markdown: str) -> list[dict[str, str]]:
        original_package = self._article_markdown_package(title, summary, body_markdown)
        articles = [
            {
                "code": self.settings.language,
                "label": self._language_label(self.settings.language),
                "html": self._render_markdown_html(original_package),
            }
        ]
        for code in self._resolved_translation_languages()[1:]:
            translated_package = self._translate_markdown_package(original_package, code)
            articles.append(
                {
                    "code": code,
                    "label": self._language_label(code),
                    "html": self._render_markdown_html(translated_package),
                }
            )
        return articles

    def _translate_markdown_package(self, article_markdown: str, language_code: str) -> str:
        language_label = self._language_label(language_code)
        return self.llm.complete_markdown(
            system_prompt=(
                "You are an expert multilingual wiki translator. "
                "Translate Markdown accurately while preserving structure, tables, admonitions, links, and citation markers like [1]."
            ),
            user_prompt=(
                f"Target language: {language_label} ({language_code})\n"
                "Translate the following Markdown article. Requirements:\n"
                "- Preserve Markdown structure.\n"
                "- Keep links and citation markers unchanged.\n"
                "- Keep the tone neutral and encyclopedic.\n"
                "- Return Markdown only.\n\n"
                f"{article_markdown}"
            ),
            fallback=lambda: self._fallback_translation(article_markdown, language_label),
            temperature=0.1,
            max_tokens=4800,
        ).strip()

    def _fallback_translation(self, article_markdown: str, language_label: str) -> str:
        return (
            '!!! note "Translation fallback"\n'
            f'    AI translation for {language_label} was unavailable during this build. The original-language article is shown below.\n\n'
            f'{article_markdown}'
        )

    def _render_markdown_html(self, markdown_text: str) -> str:
        renderer = markdown.Markdown(
            extensions=[
                "admonition",
                "attr_list",
                "footnotes",
                "md_in_html",
                "tables",
                "pymdownx.details",
                "pymdownx.highlight",
                "pymdownx.inlinehilite",
                "pymdownx.superfences",
                "pymdownx.tabbed",
            ],
            extension_configs={
                "pymdownx.highlight": {"anchor_linenums": True},
                "pymdownx.tabbed": {"alternate_style": True},
            },
            output_format="html5",
        )
        return renderer.convert(markdown_text)

    def _article_markdown_package(self, title: str, summary: str, body_markdown: str) -> str:
        return f"# {title}\n\n> {summary}\n\n{body_markdown.strip()}\n"

    def _references_markdown(self, references) -> str:
        return "\n".join(
            f"{index}. [{source.display_title()}]({source.final_url}) - {source.domain}."
            for index, source in enumerate(references, start=1)
        )

    def _resolved_translation_languages(self) -> list[str]:
        preferred = [self.settings.language, *self.settings.translation_languages]
        return unique_preserve_order(preferred)[:6]

    def _language_label(self, code: str) -> str:
        return LANGUAGE_LABELS.get(code, code)

    def _split_front_matter(self, text: str) -> tuple[dict, str]:
        normalized = text.replace("\r\n", "\n")
        match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", normalized, flags=re.DOTALL)
        if not match:
            return {}, normalized
        payload = yaml.safe_load(match.group(1)) or {}
        return payload, match.group(2)

    def _extract_body_and_references(self, content: str) -> tuple[str, str]:
        normalized = content.replace("\r\n", "\n").strip()
        parts = re.split(r"\n## References\s*\n", normalized, maxsplit=1)
        body = self._strip_existing_page_chrome(parts[0])
        references = parts[1].strip() if len(parts) > 1 else ""
        return body, references

    def _strip_existing_page_chrome(self, markdown_text: str) -> str:
        lines = markdown_text.splitlines()
        index = 0

        while index < len(lines) and not lines[index].strip():
            index += 1
        if index < len(lines) and lines[index].startswith("# "):
            index += 1
        while index < len(lines) and (not lines[index].strip() or lines[index].lstrip().startswith("> ")):
            index += 1
        if index < len(lines) and lines[index].startswith('!!! info "生成メタデータ"'):
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index].startswith("    ")):
                index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index < len(lines) and lines[index].startswith('<div class="ap-inline-actions"'):
            while index < len(lines) and "</div>" not in lines[index]:
                index += 1
            if index < len(lines):
                index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        return "\n".join(lines[index:]).strip()

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

    # ------------------------------------------------------------------
    # Retranslation of existing pages
    # ------------------------------------------------------------------

    def retranslate_existing_pages(self) -> int:
        """Re-translate wiki pages whose non-primary language sections are still
        showing the 'Translation fallback' placeholder.  Requires an LLM client.
        Returns the number of pages that were updated."""
        if not self.llm.enabled:
            print("LLM is not enabled. Skipping retranslation.")
            return 0
        count = 0
        for page_path in sorted(self.settings.wiki_dir.glob("*.md")):
            if page_path.name == "index.md":
                continue
            if self._retranslate_page(page_path):
                count += 1
        return count

    def _retranslate_page(self, page_path: Path) -> bool:
        raw_text = page_path.read_text(encoding="utf-8")
        if "Translation fallback" not in raw_text:
            return False

        # Extract the primary (ja) language HTML block
        ja_match = re.search(
            r'<section[^>]*\bdata-ap-language-view="ja"[^>]*>\s*\n\s*'
            r'<div[^>]*class="ap-rendered-article"[^>]*>\n(.*?)\n\s*</div>\s*\n\s*</section>',
            raw_text,
            flags=re.DOTALL,
        )
        if not ja_match:
            return False

        primary_html = ja_match.group(1)

        metadata, _ = self._split_front_matter(raw_text)
        available_translations: list[str] = metadata.get(
            "available_translations", self._resolved_translation_languages()
        )
        # Translation targets = all languages except the primary (ja)
        primary_code = self.settings.language
        translation_codes = [code for code in available_translations if code != primary_code]
        if not translation_codes:
            return False

        updated_text = raw_text
        changed = False
        for code in translation_codes:
            label = self._language_label(code)
            print(f"  Translating {page_path.name} → {label} ({code}) …")
            translated_html = self._translate_html_content(primary_html, code, label)

            section_re = re.compile(
                r'(<section[^>]*\bdata-ap-language-view="'
                + re.escape(code)
                + r'"[^>]*>\s*\n\s*<div[^>]*class="ap-rendered-article"[^>]*>\n)'
                r"(.*?)"
                r'(\n\s*</div>\s*\n\s*</section>)',
                flags=re.DOTALL,
            )
            new_text = section_re.sub(
                lambda m: m.group(1) + translated_html + m.group(3),
                updated_text,
            )
            if new_text != updated_text:
                updated_text = new_text
                changed = True

        if changed:
            page_path.write_text(updated_text, encoding="utf-8")
        return changed

    def _translate_html_content(self, html_content: str, language_code: str, language_label: str) -> str:
        """Translate the visible text in an HTML snippet via LLM while preserving tags."""
        return self.llm.complete_markdown(
            system_prompt=(
                "You are an expert multilingual wiki translator. "
                "Translate the visible text in the provided HTML snippet into the target language. "
                "Preserve ALL HTML tags, attributes, href/src values, citation markers like [1] and [2], "
                "and any code blocks exactly as-is. Return only the translated HTML with no extra commentary."
            ),
            user_prompt=(
                f"Target language: {language_label} ({language_code})\n\n"
                "Translate all visible text in this HTML to the target language. "
                "HTML tags and attributes must remain unchanged:\n\n"
                f"{html_content}"
            ),
            fallback=lambda: html_content,
            temperature=0.1,
            max_tokens=6000,
        ).strip()
