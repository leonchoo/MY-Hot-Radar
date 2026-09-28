"""
Minimal RSS / Atom adapter.

Refuses:
- Auto-discovery of any random URL found on a page.
- Multiple HTTP requests per source.

Accepts:
- A single, manually configured feed URL.
- Standard RSS 2.0 and Atom 1.0 shapes.
"""

from __future__ import annotations

from typing import List
import re
from xml.etree import ElementTree as ET

from .base import SourceAdapter, FetchError
from ..models import Story, Source, SourceType, Category, Language


# RSS / Atom tag-name maps. Different namespaces, same idea.
# Default RSS 2.0 uses no namespace; Atom uses the "atom:" prefix or a default namespace.
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _strip_ns(tag: str) -> str:
    if tag.startswith(_ATOM_NS):
        return tag[len(_ATOM_NS):]
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


class RSSAdapter(SourceAdapter):
    """Pulls a single configured RSS or Atom feed into Story objects.

    The adapter doesn't auto-detect category; the configured `category`
    is assigned to every Story it produces. Real classification belongs
    to a future per-story classifier (out of Phase 1 scope)."""

    def __init__(self, source: Source, *, category: Category):
        if source.type not in (SourceType.RSS, SourceType.NEWS_SITE):
            raise ValueError(f"RSSAdapter used with non-RSS source type: {source.type}")
        self.source = source
        self._category = category

    # ---- public API ----

    def fetch(self) -> List[Story]:
        try:
            body = self._http_get(self.source.url)
        except FetchError:
            raise
        try:
            root = ET.fromstring(body)
        except ET.ParseError as e:
            raise FetchError(f"{self.source.name}: malformed feed XML: {e}") from e

        items: list = []
        # RSS 2.0: <rss><channel><item>
        if _strip_ns(root.tag) == "rss":
            for ch in root.findall("channel"):
                items.extend(ch.findall("item"))
        # Atom 1.0: <feed><entry>
        elif _strip_ns(root.tag) == "feed":
            items.extend(root.findall(f"{_ATOM_NS}entry"))
        else:
            # Some feeds use RDF; we keep Phase 1 simple and refuse unknown shapes.
            raise FetchError(f"{self.source.name}: unsupported feed root '{root.tag}'")

        stories: List[Story] = []
        for it in items:
            story = self._item_to_story(it)
            if story is not None:
                stories.append(story)

        # Hard cap: refuse runaway items (defensive against misconfigured feeds).
        if len(stories) > 200:
            stories = stories[:200]
        return stories

    # ---- internals ----

    def _item_to_story(self, item) -> Story | None:
        title = self._first_text(item, "title")
        link = self._first_text(item, "link")
        if not title or not link:
            return None

        # Atom <link> may carry an href attribute instead of text content
        if title is None or link is None:
            return None

        summary = self._first_text(item, "description") or self._first_text(item, "summary") or ""
        pub_at = (
            self._first_text(item, "pubDate")
            or self._first_text(item, "published")
            or self._first_text(item, "updated")
            or None
        )

        s = Story(
            title=self._clean_title(title)[:300],
            summary=summary.strip()[:1200],
            url=link.strip()[:1000],
            source=self.source.name,
            source_type=self.source.type,
            published_at=pub_at.strip()[:40] if pub_at else None,
            category=self._category,
            language=self.source.languages[0] if self.source.languages else Language.EN,
            country=self.source.country,
        )
        return s

    # Feed-specific title cleanup.
    # Some aggregators (Google News) append " - Outlet Name" or " | outlet.com"
    # to item titles. That's attribution, not part of the topic. We strip it
    # defensively: anything after the LAST " - ", " | ", " — ", or " · " is
    # dropped. Then we also remove domain-looking trailing tokens like
    # "theborneopost.com" or "freemalaysiatoday.com".
    @staticmethod
    def _clean_title(title: str) -> str:
        if not title:
            return title
        s = title.strip()
        # Trim trailing attribution separators (use last occurrence)
        for sep in (" - ", " \u2014 ", " | ", " / ", " \u00b7 "):
            if sep in s:
                s = s.rsplit(sep, 1)[0].rstrip()
        # Trim trailing " - sitename.xxx" exactly when the suffix looks like a domain
        m = re.search(r"\s*-\s*([a-z0-9-]+\.[a-z]{2,}(\.[a-z]{2,})?)\s*$", s, re.IGNORECASE)
        if m and " " not in m.group(1):
            s = s[:m.start()].rstrip()
        return s.strip()

    def _first_text(self, parent, name) -> str | None:
        """Find the first matching child element (RSS or Atom naming) and return text."""
        # RSS-style
        for child in parent:
            if _strip_ns(child.tag) == name:
                return (child.text or "").strip()
        # Atom-style: href attribute on <link>
        if name == "link":
            for child in parent:
                if _strip_ns(child.tag) == "link":
                    href = child.attrib.get("href")
                    if href:
                        return href
        return None
