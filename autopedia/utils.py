from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse


ROOT_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cleaned = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), cleaned)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_timestamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def iso_timestamp() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default: dict | list | None = None):
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict | list) -> None:
    ensure_dir(path.parent)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def compact_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return lines


def truncate_text(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."


def chunk_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for block in text.split("\n\n"):
        piece = block.strip()
        if not piece:
            continue
        piece_size = len(piece) + 2
        if current and current_size + piece_size > max_chars:
            chunks.append("\n\n".join(current))
            current = [piece]
            current_size = piece_size
            continue
        current.append(piece)
        current_size += piece_size

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def slugify_text(value: str, fallback: str = "topic") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug or fallback


def canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    cleaned = parsed._replace(fragment="")
    normalized = urlunparse(cleaned)
    if normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized


def domain_for_url(url: str) -> str:
    return urlparse(url).netloc.lower()


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        stripped = value.strip()
        if not stripped or stripped in seen:
            continue
        output.append(stripped)
        seen.add(stripped)
    return output


def excerpt_lines(text: str, max_lines: int = 10, max_line_length: int = 220) -> list[str]:
    selected: list[str] = []
    for line in compact_lines(text):
        selected.append(truncate_text(line, max_line_length))
        if len(selected) >= max_lines:
            break
    return selected


def markdown_excerpt(text: str, max_lines: int = 140, max_chars: int = 12000) -> str:
    selected: list[str] = []
    current_size = 0
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line and selected and not selected[-1]:
            continue
        piece = line + "\n"
        if selected and (len(selected) >= max_lines or current_size + len(piece) > max_chars):
            break
        selected.append(line)
        current_size += len(piece)
    return "\n".join(selected).strip()


def markdown_headings(text: str, max_items: int = 10) -> list[str]:
    headings: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            headings.append(line.removeprefix("## ").strip())
        elif line.startswith("### "):
            headings.append(line.removeprefix("### ").strip())
        if len(headings) >= max_items:
            break
    return headings


def binary_like_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.endswith(
        (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".svg",
            ".zip",
            ".gz",
            ".mp4",
            ".mp3",
            ".mov",
            ".avi",
            ".ppt",
            ".pptx",
            ".xls",
            ".xlsx",
            ".doc",
            ".docx",
        )
    )
