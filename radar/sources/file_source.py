"""
File-based adapter.

Pulls Story objects from a local JSONL file. This is the canonical way to test
the pipeline end-to-end without any network access and without fabricating
network results.

File format: one Story per line, JSON. Each line must contain at least title,
url, and source. Optional fields are coerced.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from .base import SourceAdapter, FetchError
from ..models import Story, Source, SourceType, Category, Language


class FileAdapter(SourceAdapter):
    """Reads Story records from a local JSONL file.

    The source URL is `file://<path>` (purely descriptive; we never open it as
    a URL). The actual path is taken from the Source's `url` field.
    """

    def __init__(self, source: Source, *, category: Category, file_path: str | None = None):
        self.source = source
        self._category = category
        # Either we got an explicit file_path, or we read from source.url.
        self._file_path = file_path

    def fetch(self) -> List[Story]:
        path = self._file_path or self.source.url.replace("file://", "")
        if not os.path.isabs(path):
            # fall back to project-root radar_data/ area
            root = Path(__file__).resolve().parents[1] / "radar_data"
            candidate = root / path
            if candidate.exists():
                path = str(candidate)
        if not os.path.exists(path):
            raise FetchError(f"{self.source.name}: file not found: {path}")
        out: List[Story] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for ln, raw in enumerate(f, 1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        d = json.loads(raw)
                    except json.JSONDecodeError as e:
                        raise FetchError(f"{self.source.name}: invalid JSON on line {ln}: {e}") from e
                    s = self._dict_to_story(d)
                    out.append(s)
        except OSError as e:
            raise FetchError(f"{self.source.name}: read error: {e!r}") from e
        return out

    def _dict_to_story(self, d: dict) -> Story:
        # We accept either a fully-formed Story dict or a minimal {title, url, source, ...}
        try:
            cat = Category(d.get("category", self._category.value))
        except ValueError:
            cat = self._category
        try:
            st = SourceType(d.get("source_type", SourceType.NEWS_SITE.value))
        except ValueError:
            st = SourceType.NEWS_SITE
        try:
            lang = Language(d.get("language", Language.EN.value))
        except ValueError:
            lang = Language.EN
        return Story(
            id=d.get("id") or "",
            title=d.get("title", ""),
            summary=d.get("summary", ""),
            url=d.get("url", ""),
            source=d.get("source", self.source.name),
            source_type=st,
            published_at=d.get("published_at"),
            discovered_at=d.get("discovered_at"),
            category=cat,
            language=lang,
            country=d.get("country", "MY"),
            normalized_title=d.get("normalized_title", ""),
            keywords=d.get("keywords", []),
        )
