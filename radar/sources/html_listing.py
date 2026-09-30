"""
HTML listing source adapter.

Added in A2.2-A to consume custom-CMS HTML pages from sources
that DO NOT expose RSS, WP-JSON, or a sitemap. Live-verified
against the Sin Chew Johor desk (``https://johor.sinchew.com.my/``).

Why this adapter exists
-----------------------

Per ``docs/CHINESE_SOURCE_DISCOVERY_AUDIT.md`` §2 the Sin Chew
Johor desk is "RSS_READY" but a closer probe showed:

  - ``/wp-json/wp/v2/posts``    → 404
  - ``/feed/``                  → 404
  - ``/feed``                   → 404
  - ``/rss``                    → 404
  - ``/sitemap.xml``            → 404

The page itself is a 385 KB server-rendered HTML document with
``<h2 class="title skip-default-style">`` article cards and
``<a class="internalLink" data-title="...">`` blocks. Article
URLs follow ``/news/YYYYMMDD/johor/{id}`` (numeric id, 8-digit
date prefix). Per the discovery audit §3 there are ~38 dated
article URLs on the homepage; above-the-fold rendering exposes
6 ``<h2 class="title">`` cards and a further ~10 sidebar /
related ``<a class="internalLink">`` blocks.

This adapter walks both card families, filters for the strict
URL pattern, deduplicates, and emits one ``Story`` per article.

What this adapter deliberately does NOT do
------------------------------------------

  - Parse the homepage navigation (``/category/...``).
  - Visit individual article pages for absolute timestamps —
    the listing page carries only relative time strings
    (``16分钟前``, ``2小时前``, ``3月前``), and per the A2.2-A
    spec we treat relative time as ``published_at = None``
    rather than guessing. Filling ``published_at`` from the
    article page is deferred to a future batch.
  - Fall back to any date outside the article URL pattern.

Deterministic + offline
-----------------------

Given the same HTML body, the adapter produces the same list
of stories in the same order. No network calls are made during
parsing. The only HTTP step is the listing fetch in ``fetch()``
which inherits the standard 10s timeout from
``SourceAdapter._http_get``.
"""

from __future__ import annotations

import hashlib
import re
from html import unescape
from typing import List, Optional
from urllib.parse import urljoin

from .base import SourceAdapter, FetchError
from ..models import Story, Source, SourceType, Category, Language


# Strict URL pattern for Sin Chew Johor articles. Anchored to the
# 8-digit date prefix and a numeric article id. Any URL that does
# not match is filtered out (categories, tags, ads, etc.).
#
# Examples that match:
#   /news/20260930/johor/7895884
#   /news/20251203/johor/7079996
#
# Examples that do NOT match:
#   /category/地方/大柔佛/综合2
#   /news/20260930 (no /johor/{id})
#   /news/2026-09-30/johor/7895884 (date with dashes)
_ARTICLE_URL_RE = re.compile(
    r"^/news/\d{8}/johor/\d+/?$"
)

# <h2 class="title ..."><a href="...">TITLE</a></h2>
# Greedy enough to allow other class names; non-greedy on title text.
_H2_TITLE_RE = re.compile(
    r"""<h2[^>]*class=["'][^"']*\btitle\b[^"']*["'][^>]*>
        \s*<a[^>]+href=["'](?P<url>[^"']+)["'][^>]*>
        (?P<title>[^<]+)
        </a>
        \s*</h2>""",
    re.VERBOSE | re.DOTALL,
)

# <a class="...internalLink..." data-title="..." href="..."> ...
# Captures both the data-title attribute and the visible link text.
_INTERNAL_LINK_RE = re.compile(
    r"""<a[^>]+
        class=["'][^"']*\binternalLink\b[^"']*["'][^>]+
        data-title=["'](?P<data_title>[^"']+)["'][^>]+
        href=["'](?P<url>[^"']+)["']
        [^>]*>(?P<text>[^<]*)</a>""",
    re.VERBOSE | re.DOTALL,
)

# Anchor tags for article URLs found anywhere (used to extract the
# raw link text as a title fallback when neither <h2> nor
# data-title attribute is available).
_LONE_LINK_RE = re.compile(
    r"""<a[^>]+href=["'](?P<url>[^"']+)["'][^>]*>(?P<text>[^<]+)</a>""",
    re.VERBOSE | re.DOTALL,
)

# Navigation / category / tag / home URLs that must be rejected.
_NAV_PREFIXES = (
    "/category/",
    "/tag/",
    "/author/",
    "/wp-",
    "/about",
    "/contact",
    "/privacy",
    "/feedback",
    "/ratecard",
    "/intro",
    "/latest",
    "/newsletter",
    "/stocksummary",
    "/public/",
    "/member",
    "/mymain",
    "/prn",
    "/award",
    "/app",
    "/search",
    "/login",
)

# HTML entity table mirroring what the WP-JSON adapter uses.
# ``&hellip;`` renders as Unicode HORIZONTAL ELLIPSIS, matching
# the public-output truncation conventions.
_HTML_ENTITIES = {
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "apos": "'",
    "quot": '"',
    "nbsp": " ",
    "hellip": "\u2026",
    "mdash": "--",
    "ndash": "-",
    "ldquo": "\u201c",
    "rdquo": "\u201d",
    "lsquo": "\u2018",
    "rsquo": "\u2019",
    "laquo": "\u00ab",
    "raquo": "\u00bb",
}


def _strip_html(s: str) -> str:
    """Strip HTML tags, unescape entities, collapse whitespace.

    Used to turn Sin Chew article titles into clean plain-text.
    Mirrors the WP-JSON adapter's ``_strip_html`` so both Chinese
    source adapters produce consistent normalized text.

    Order matters:
      1. Strip HTML tags FIRST (regex matches real ``<...>`` markup).
      2. Unescape entities (so ``&amp;`` → ``&``, ``&#26032;`` →
         ``新``, etc.).
      3. Collapse whitespace.
      4. Strip whitespace before terminal punctuation.
    """
    if not s:
        return ""
    # 1. Strip HTML tags (real markup only).
    s = re.sub(r"<[^>]+>", "", s)
    # 2. Unescape entities. Decimal/hex first (most specific).
    s = unescape(s)
    s = _ENTITY_DECIMAL_RE.sub(
        lambda m: chr(int(m.group(1))) if m.group(1) else "", s
    )
    s = _ENTITY_HEX_RE.sub(
        lambda m: chr(int(m.group(2), 16)) if m.group(2) else "", s
    )
    s = _ENTITY_NAMED_RE.sub(lambda m: _HTML_ENTITIES.get(m.group(1), m.group(0)), s)
    # 3. Collapse whitespace.
    s = re.sub(r"\s+", " ", s)
    # 4. Strip whitespace before terminal punctuation so "Foo ."
    # collapses to "Foo." — matches the WP-JSON convention.
    s = re.sub(r"\s+([.,;:!?])", r"\1", s)
    return s.strip()


_ENTITY_DECIMAL_RE = re.compile(r"&#(\d+);")
_ENTITY_HEX_RE = re.compile(r"&#x([0-9a-fA-F]+);")
_ENTITY_NAMED_RE = re.compile(r"&(" + "|".join(_HTML_ENTITIES.keys()) + r");")


def _is_article_url(url: str) -> bool:
    """Return True iff ``url`` is a Sin Chew Johor article URL.

    Rejects:
      - absolute URLs to other hosts
      - navigation/category URLs
      - non-numeric article ids
      - URLs without the ``/news/YYYYMMDD/johor/{id}`` shape
    """
    if not url:
        return False
    # Accept absolute and relative forms; we will resolve later.
    parsed = url
    if parsed.startswith("http://") or parsed.startswith("https://"):
        # Must point at the source host (Sin Chew Johor).
        if "johor.sinchew.com.my" not in parsed:
            return False
        # Strip the host prefix.
        i = parsed.find("/news/")
        if i == -1:
            return False
        parsed = parsed[i:]
    # Reject obvious navigation patterns.
    for prefix in _NAV_PREFIXES:
        if parsed.startswith(prefix):
            return False
    return bool(_ARTICLE_URL_RE.match(parsed))


def _canonicalize_url(url: str, base: str) -> str:
    """Resolve a relative URL against the listing ``base`` URL.

    Drops a trailing slash so the canonical form is stable across
    feeds and the dedup pipeline's ``canonicalize_url`` matches
    it consistently.
    """
    full = urljoin(base, url)
    if full.endswith("/") and not full.endswith("://"):
        full = full[:-1]
    return full


def _make_story_id(url: str) -> str:
    """Deterministic Story id from the article URL.

    Same convention as ``WpJsonAdapter._make_story_id``: a 12-hex
    sha1 prefix prefixed with ``s_``. Given the same URL, the id
    is identical across runs.
    """
    return "s_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


class HtmlListingAdapter(SourceAdapter):
    """Parse a custom-CMS HTML listing page into Story objects.

    Live-verified against:
      - https://johor.sinchew.com.my/   (Sin Chew Johor desk)
    """

    def __init__(self, source: Source, *, category: Category):
        if source.type != SourceType.HTML_LISTING:
            raise ValueError(
                f"HtmlListingAdapter requires SourceType.HTML_LISTING; "
                f"got {source.type.value}"
            )
        self.source = source
        self._category = category

    def fetch(self) -> List[Story]:
        """Fetch the listing page and return normalized Stories."""
        html = self._http_get(self.source.url)
        return self._parse_listing(html)

    def _parse_listing(self, html: str) -> List[Story]:
        """Parse an HTML body and return deduplicated Stories.

        Strategy (deterministic, offline-safe):

          1. Walk ``<h2 class="title">`` cards first — these are the
             primary article teasers above the fold.
          2. Walk ``<a class="internalLink" data-title="...">`` blocks
             second — these cover sidebar widgets and related-story
             links. ``data-title`` is preferred when present.
          3. Walk bare ``<a href="/news/...">`` tags as a last-resort
             fallback (uses link text as title).
          4. Filter every URL through ``_is_article_url``.
          5. Deduplicate by canonical URL.
          6. Emit a Story per unique URL.

        ``published_at`` is always ``None`` (spec rule: relative
        time on the listing page is not a reliable absolute
        timestamp). The cluster pipeline handles missing
        ``published_at`` by relying on ``discovered_at`` for
        time-windowing.
        """
        base = self.source.url

        candidates: dict[str, str] = {}  # canonical_url -> title

        # Phase 1: <h2 class="title"> cards (highest priority).
        for m in _H2_TITLE_RE.finditer(html):
            url = m.group("url")
            title = m.group("title")
            if not _is_article_url(url):
                continue
            full = _canonicalize_url(url, base)
            clean = _strip_html(title)
            if not clean:
                continue
            candidates[full] = clean

        # Phase 2: <a class="internalLink" data-title="..."> blocks.
        for m in _INTERNAL_LINK_RE.finditer(html):
            url = m.group("url")
            data_title = m.group("data_title")
            text = m.group("text")
            if not _is_article_url(url):
                continue
            full = _canonicalize_url(url, base)
            if full in candidates:
                continue  # already have a (better) title
            clean = _strip_html(data_title) or _strip_html(text)
            if not clean:
                continue
            candidates[full] = clean

        # Phase 3: bare anchor tags (only fills gaps left by 1 + 2).
        for m in _LONE_LINK_RE.finditer(html):
            url = m.group("url")
            text = m.group("text")
            if not _is_article_url(url):
                continue
            full = _canonicalize_url(url, base)
            if full in candidates:
                continue
            clean = _strip_html(text)
            if not clean:
                continue
            candidates[full] = clean

        # Emit Stories in URL-sorted order so the output is
        # deterministic across runs given the same input HTML.
        stories: List[Story] = []
        for url in sorted(candidates.keys()):
            title = candidates[url]
            stories.append(
                Story(
                    id=_make_story_id(url),
                    title=title,
                    summary="",  # listing page has no excerpt
                    url=url,
                    source=self.source.name,
                    source_type=SourceType.HTML_LISTING,
                    published_at=None,  # see module docstring
                    discovered_at=Story.__dataclass_fields__["discovered_at"]
                    .default_factory(),
                    category=self._category,
                    language=Language.ZH,  # Sin Chew Johor is Chinese
                    country=self.source.country,
                )
            )
        return stories


__all__ = ["HtmlListingAdapter", "_strip_html", "_is_article_url"]
