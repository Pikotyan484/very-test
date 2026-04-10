from __future__ import annotations

import os
from argparse import Namespace
from typing import TYPE_CHECKING

from autopedia.models import RequestContext
from autopedia.utils import slugify_text, truncate_text

if TYPE_CHECKING:
    from autopedia.config import Settings


ENV_KEYS = {
    "mode": "AUTOPEDIA_REQUEST_MODE",
    "topic_title": "AUTOPEDIA_REQUEST_TOPIC_TITLE",
    "topic_slug": "AUTOPEDIA_REQUEST_TOPIC_SLUG",
    "request_notes": "AUTOPEDIA_REQUEST_NOTES",
    "issue_number": "AUTOPEDIA_REQUEST_ISSUE_NUMBER",
    "issue_url": "AUTOPEDIA_REQUEST_ISSUE_URL",
    "requested_by": "AUTOPEDIA_REQUESTED_BY",
}


def request_from_args_and_env(args: Namespace) -> RequestContext:
    def read_value(arg_name: str, env_name: str) -> str:
        arg_value = getattr(args, arg_name, None)
        if arg_value not in (None, ""):
            return str(arg_value)
        return os.getenv(env_name, "")

    issue_number_value = read_value("issue_number", ENV_KEYS["issue_number"]).strip()
    issue_number = int(issue_number_value) if issue_number_value.isdigit() else None

    topic_title = read_value("topic_title", ENV_KEYS["topic_title"]).strip()
    topic_slug = read_value("topic_slug", ENV_KEYS["topic_slug"]).strip()
    if topic_title and not topic_slug:
        topic_slug = slugify_text(topic_title)

    return RequestContext(
        mode=read_value("request_mode", ENV_KEYS["mode"]).strip() or "auto",
        topic_title=topic_title,
        topic_slug=topic_slug,
        request_notes=read_value("request_notes", ENV_KEYS["request_notes"]).strip(),
        issue_number=issue_number,
        issue_url=read_value("issue_url", ENV_KEYS["issue_url"]).strip(),
        requested_by=read_value("requested_by", ENV_KEYS["requested_by"]).strip(),
    )


def build_request_issue_body(
    *,
    mode: str,
    topic_title: str = "",
    topic_slug: str = "",
    request_notes: str = "",
    existing_page_path: str = "",
) -> str:
    note = request_notes.strip() or "Describe what should be researched, updated, or expanded."
    lines = [
        "## Request Type",
        mode.strip(),
        "",
        "## Topic Title",
        topic_title.strip(),
        "",
        "## Topic Slug",
        topic_slug.strip(),
        "",
        "## Request Notes",
        note,
        "",
    ]
    if existing_page_path.strip():
        lines.extend(
            [
                "## Existing Page",
                existing_page_path.strip(),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def build_request_issue_url(
    settings: "Settings",
    *,
    mode: str,
    topic_title: str = "",
    topic_slug: str = "",
    request_notes: str = "",
    existing_page_path: str = "",
) -> str:
    normalized_mode = RequestContext(mode=mode).normalized_mode()
    labels = ["autopedia-request", normalized_mode]
    prefix = {
        "new-topic": "New Topic",
        "update-page": "Update Page",
        "expand-page": "Expand Page",
    }.get(normalized_mode, "AutoPedia Request")
    fallback_title = topic_title.strip() or "requested topic"
    issue_title = f"[{prefix}] {truncate_text(fallback_title, 90)}"
    return settings.build_issue_url(
        title=issue_title,
        body=build_request_issue_body(
            mode=normalized_mode,
            topic_title=topic_title,
            topic_slug=topic_slug,
            request_notes=request_notes,
            existing_page_path=existing_page_path,
        ),
        labels=labels,
    )