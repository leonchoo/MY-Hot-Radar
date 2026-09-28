"""
Public-social adapter.

Reads an Atom feed (Reddit RSS uses Atom format under the hood) and converts
each entry into a Story with source_type=PUBLIC_SOCIAL.

This adapter is restricted to:
  - Atom feeds (Reddit's /r/<name>/.rss is Atom)
  - No login
  - No user-data fetching
  - Public subreddit / public page only

If a future source is not a plain Atom feed (e.g. requires OAuth), it does
NOT belong in this adapter. Use a separate adapter or skip.
"""

from __future__ import annotations

import re
from typing import List
from xml.etree import ElementTree as ET

from .base import SourceAdapter, FetchError
from ..models import Story, Source, SourceType, Category, Language


# Reddit's RSS is Atom; reuse the Atom handling logic.
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _strip_ns(tag: str) -> str:
    if tag.startswith(_ATOM_NS):
        return tag[len(_ATOM_NS):]
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


class PublicSocialAdapter(SourceAdapter):
    """Reads a public Atom feed marked as SOCIAL_PUBLIC source-type.

    Limitation Phase 1: only Atom feeds that look like Reddit's.
    Anything more complex is out of scope.
    """

    def __init__(self, source: Source, *, category: Category):
        if source.type != SourceType.PUBLIC_SOCIAL:
            raise ValueError(f"PublicSocialAdapter used with non-PUBLIC_SOCIAL source: {source.type}")
        self.source = source
        self._category = category

    def fetch(self) -> List[Story]:
        try:
            body = self._http_get(self.source.url)
        except FetchError:
            raise
        try:
            root = ET.fromstring(body)
        except ET.ParseError as e:
            raise FetchError(f"{self.source.name}: malformed feed XML: {e}") from e

        # Only handle Atom; refuse other shapes for PUBLIC_SOCIAL.
        if _strip_ns(root.tag) != "feed":
            raise FetchError(f"{self.source.name}: PUBLIC_SOCIAL adapter only supports Atom (got '{root.tag}')")

        items = root.findall(f"{_ATOM_NS}entry")
        # Reddit occasionally returns fewer than 25 entries. That's fine.
        out: List[Story] = []
        for e in items:
            t = (e.findtext(f"{_ATOM_NS}title") or "").strip()
            link = ""
            for child in e:
                if _strip_ns(child.tag) == "link" and child.attrib.get("rel", "alternate") == "alternate":
                    link = child.attrib.get("href", "")
                    if link:
                        break
            if not link:
                # fallback: any link element
                for child in e:
                    if _strip_ns(child.tag) == "link":
                        link = child.attrib.get("href", "")
                        if link:
                            break
            if not t or not link:
                continue
            summary = (e.findtext(f"{_ATOM_NS}content") or e.findtext(f"{_ATOM_NS}summary") or "").strip()[:600]
            pub = e.findtext(f"{_ATOM_NS}updated") or e.findtext(f"{_ATOM_NS}published") or ""
            out.append(Story(
                title=t[:300],
                summary=summary[:1200],
                url=link[:1000],
                source=self.source.name,
                source_type=self.source.type,
                published_at=pub[:40] if pub else None,
                category=self._category,
                language=self.source.languages[0] if self.source.languages else Language.EN,
                country=self.source.country,
            ))
            if len(out) >= 200:
                break
        return out
