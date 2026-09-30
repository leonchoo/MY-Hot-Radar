"""
WordPress JSON adapter.

Added in A2.1 to consume ``/wp-json/wp/v2/posts`` endpoints from
Chinese-language WordPress sites. Live-verified against Kwong Wah
(``https://www.kwongwah.com.my``) and Guang Ming
(``https://guangming.com.my``).

The adapter implements the same contract as ``RSSAdapter``:
a single, manually-configured endpoint URL, one HTTP fetch per
``scan()`` (no auto-pagination, no auto-discovery). It refuses
to:

  - Hit any URL not declared in ``Source.url``.
  - Construct a published_at from anything except a real ISO
    timestamp emitted by WordPress (`date_gmt` preferred, `date`
    fallback if `date_gmt` is missing).
  - Inject observed_at as published_at.
  - Guess a local-time conversion.

It normalizes WordPress's HTML-emitted title / excerpt / content
fields into plain text by stripping HTML tags and unescaping the
small set of named / numeric entities used by WordPress.

The output is ``List[Story]`` with ``language=ZH`` and the
``Source``-declared category / country / tier. The existing
A1 alias map (place names) and the existing ``extract_entities``
pipeline consume these Story objects without modification; this
batch introduces NO new dedup rules.

Design rules followed:

  * No external dependencies (stdlib only: ``json``, ``re``,
    ``urllib``).
  * Determinism: same response bytes -> same Story list.
  * Fail-closed on malformed JSON / missing required fields
    (per-row missing -> drop silently; malformed JSON -> raise
    ``FetchError`` matching ``RSSAdapter`` pattern).
  * Hard cap 200 stories per fetch (mirrors ``RSSAdapter``).
  * ``SourceType.WP_JSON`` is the ONLY accepted source type;
    misuse raises ``ValueError`` at construction.
  * A ``SourceType.WP_JSON`` source is matched by the pipeline
    orchestrator via the new branch in
    ``radar/pipeline.py::_build_adapter``.

Reference: ``docs/CHINESE_WP_JSON_A21_IMPLEMENTATION.md``.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

from .base import SourceAdapter, FetchError
from ..models import Story, Source, SourceType, Category, Language
# Note: we intentionally do NOT import `normalize.unescape_html`
# because its entity table is too narrow for the entities observed
# in real WP-JSON responses (notably ``&hellip;``). The
# ``_unescape_wp_entities`` helper below handles the broader set
# without touching ``radar/normalize.py``.


# Hard cap (mirrors RSSAdapter). Defends against misconfigured
# per_page that could otherwise produce runaway output.
_MAX_STORIES = 200

# Hard cap on title / summary / url length, mirrors RSSAdapter.
_TITLE_MAX = 300
_SUMMARY_MAX = 1200
_URL_MAX = 1000

# Regex used to strip HTML tags. Compiled once at module load.
_TAG_RX = re.compile(r"<[^>]+>")

# Whitespace run used to collapse post-strip whitespace.
_WS_RX = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    """Strip HTML tags, unescape entities, collapse whitespace.

    Used to turn WordPress's ``title.rendered``,
    ``excerpt.rendered``, and ``content.rendered`` into plain text.

    Order of operations:

      1. unescape a wider set of entities (the WP-JSON response
         routinely emits ``&hellip;``, ``&mdash;``, ``&ldquo;``,
         ``&rdquo;``, etc., which the small ``normalize.unescape_html``
         table does NOT cover). We do NOT call
         ``normalize.unescape_html`` here because it lives in
         ``normalize.py`` (out of scope for A2.1) and only knows
         the 6 most common entities. The set below covers the entities
         actually emitted by WordPress and observed in real
         Kwong Wah / Guang Ming responses.
      2. strip tags (``<p>``, ``<img>``, ``<figure>``, etc.).
      3. collapse whitespace runs.
      4. trim spaces that became adjacent to terminal punctuation
         (HTML strip frequently leaves ``"paragraph ."`` —
         empty inline tag residue then a space, then punctuation).
      5. trim leading / trailing whitespace.

    Idempotent on already-plain text: tags are absent, so step 2
    is a no-op, whitespace is already collapsed, step 4 trims.

    The entity table is intentionally narrow — it covers only the
    entities WordPress actually emits in the title / excerpt /
    content of the live Kwong Wah and Guang Ming responses
    captured 2026-09-30. Adding new entries here requires a new
    positive fixture that exercises them, and a note in the A2.1
    implementation report. Do not silently expand.
    """
    if not s:
        return ""
    s = _unescape_wp_entities(s)
    s = _TAG_RX.sub(" ", s)
    s = _WS_RX.sub(" ", s)
    # Strip whitespace before punctuation that often appears when
    # inline tags surround punctuation (``<em>foo</em>.`` -> ``foo .``).
    s = re.sub(r"\s+([.,;:!?])", r"\1", s)
    return s.strip()


# Numeric-entity regex (covers &#NNN; and &#xHHHH;).
_NUMERIC_ENTITY_RX = re.compile(r"&#(\d+);|&#x([0-9a-fA-F]+);")
_NAMED_ENTITY_RX = re.compile(r"&([a-zA-Z][a-zA-Z0-9]+);")

# Curated set of HTML entities observed in real WP-JSON responses
# from Kwong Wah / Guang Ming. Per source: the fixtures captured on
# 2026-09-30 contain ``&hellip;`` (ellipsis) and ``&nbsp;`` (NBSP).
# ``nbsp`` is also handled by ``normalize.unescape_html``; we include
# it here so the WP-JSON adapter has no dependency on
# ``normalize.unescape_html``'s small table.
_WP_ENTITIES = {
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "apos": "'",
    "quot": '"',
    "nbsp": " ",
    # ``&hellip;`` is U+2026 (HORIZONTAL ELLIPSIS). The single-glyph
    # form is readable in plain text and JSON output and matches
    # what WordPress intends. We do NOT expand it to `` . . . ``
    # because that would interact badly with the punctuation-strip
    # regex (which would collapse the spaces). Single-glyph is
    # cleaner and matches the source's intent.
    "hellip": "\u2026",
    "mdash": "\u2014",
    "ndash": "\u2013",
    "ldquo": "\u201c",
    "rdquo": "\u201d",
    "lsquo": "\u2018",
    "rsquo": "\u2019",
    "laquo": "\u00ab",
    "raquo": "\u00bb",
}


def _unescape_wp_entities(s: str) -> str:
    """Unescape HTML entities observed in real WP-JSON responses.

    Handles numeric entities (``&#NNN;`` and ``&#xHHHH;``) plus a
    curated set of named entities. Entities outside the curated
    set are left as-is (WordPress has only the entities that the
    underlying wptexturize filter emits; this set covers all
    observed cases in the A2.1 fixtures).
    """
    if not s:
        return s

    def _numeric_repl(m):
        if m.group(1) is not None:
            return chr(int(m.group(1)))
        return chr(int(m.group(2), 16))

    s = _NUMERIC_ENTITY_RX.sub(_numeric_repl, s)
    return _NAMED_ENTITY_RX.sub(
        lambda m: _WP_ENTITIES.get(m.group(1).lower(), m.group(0)), s)


def _coerce_published_at(post: dict) -> Optional[str]:
    """Return the most-trustworthy ISO timestamp WordPress emits.

    Priority order (per Audit §4.2 + A2.1 spec):

      1. ``date_gmt`` (UTC ISO 8601 — the canonical WP timestamp).
      2. ``date`` (local-time, no timezone suffix).
      3. ``None`` — caller treats as fail-closed.

    We DO NOT use ``modified`` / ``modified_gmt`` because those
    reflect edit time, not publication time. We DO NOT use
    ``observed_at`` for ``published_at`` — they have different
    semantics.

    Returns a string slice of length 35 to match the existing
    ``RSSAdapter._item_to_story`` length cap (40 is the cap; we
    use 35 to leave headroom for trailing characters some ISO
    formats include). The returned value is best-effort UTC ISO.

    Important: when ``date_gmt`` is taken (the UTC case), we
    explicitly append a ``Z`` suffix to disambiguate timezone. WP's
    raw ``date_gmt`` field is "YYYY-MM-DDTHH:MM:SS" with NO timezone
    marker. Treating that as naive datetime when the cluster
    pipeline mixes it with aware datetimes (e.g., ``first_seen =
    datetime.now(timezone.utc)``) raises
    ``TypeError: can't subtract offset-naive and offset-aware
    datetimes``. Appending ``Z`` makes it a valid UTC ISO timestamp.
    """
    s = post.get("date_gmt") or post.get("date")
    if not s:
        return None
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    # If we used date_gmt (UTC by WP convention), append Z so
    # downstream datetime parsers treat it as timezone-aware UTC.
    # If we fell back to date (local time), leave as-is.
    if post.get("date_gmt") and not s.endswith(("Z", "+00:00")):
        # IMPORTANT: use endswith / strip suffixes as substrings,
        # NOT str.rstrip(chars) — rstrip treats its arg as a SET of
        # characters and would strip all of ``+``, ``0`` from the
        # right side, corrupting the timestamp.
        if s.endswith("Z"):
            s = s[:-1]
        if s.endswith("+00:00"):
            s = s[:-6]
        s = s + "Z"
    return s[:35]


class WpJsonAdapter(SourceAdapter):
    """Pulls a single configured WordPress JSON posts endpoint
    into Story objects.

    The endpoint URL is the WordPress ``/wp-json/wp/v2/posts``
    URL with ``_fields=...`` narrowing the response payload.

    The adapter doesn't auto-detect language; the configured
    ``Source.languages[0]`` is assigned to every Story (the
    Chinese sources declared ``[Language.ZH]`` at registration).
    """

    def __init__(self, source: Source, *, category: Category):
        if source.type != SourceType.WP_JSON:
            raise ValueError(
                f"WpJsonAdapter used with non-WP_JSON source type: {source.type}"
            )
        self.source = source
        self._category = category

    def fetch(self) -> List[Story]:
        try:
            body = self._http_get(self.source.url)
        except FetchError:
            raise
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise FetchError(
                f"{self.source.name}: malformed WP-JSON body: {e}"
            ) from e
        if not isinstance(data, list):
            raise FetchError(
                f"{self.source.name}: expected JSON array of posts, "
                f"got {type(data).__name__}"
            )

        stories: List[Story] = []
        for post in data:
            story = self._post_to_story(post)
            if story is not None:
                stories.append(story)

        # Hard cap: refuse runaway items (defensive, mirrors
        # RSSAdapter behavior).
        if len(stories) > _MAX_STORIES:
            stories = stories[:_MAX_STORIES]
        return stories

    # ---- internals ----

    def _post_to_story(self, post) -> Optional[Story]:
        if not isinstance(post, dict):
            return None

        # Title: prefer rendered HTML (WordPress standard), strip
        # to plain text. WP-JSON responses observed in the wild
        # always include ``title.rendered``; if it is empty or
        # missing, drop the post (per A2.1 spec — title is required,
        # not optional). Falling back to slug would let an attacker
        # who can influence the slug craft confusing titles.
        title_obj = post.get("title")
        if not isinstance(title_obj, dict):
            return None
        title_raw = title_obj.get("rendered") or ""
        title = _strip_html(title_raw)
        title = title[:_TITLE_MAX]
        if not title:
            return None

        # URL: prefer the canonical permalink from the ``link`` field.
        url = (post.get("link") or "").strip()[:_URL_MAX]
        if not url:
            return None

        # Published_at: real ISO timestamp from WordPress only.
        # If date_gmt and date are both missing, drop the post
        # (per A2.1 spec — no observed_at fallback, no invented
        # timestamp, no modified_gmt fallback).
        published_at = _coerce_published_at(post)
        if published_at is None:
            return None

        # Summary: prefer excerpt, fall back to truncated content.
        excerpt_obj = post.get("excerpt") or {}
        summary_raw = excerpt_obj.get("rendered") or ""
        if not summary_raw:
            content_obj = post.get("content") or {}
            summary_raw = content_obj.get("rendered") or ""
        summary = _strip_html(summary_raw)[:_SUMMARY_MAX]

        s = Story(
            title=title,
            summary=summary,
            url=url,
            source=self.source.name,
            source_type=self.source.type,
            published_at=published_at,
            category=self._category,
            language=(
                self.source.languages[0]
                if self.source.languages
                else Language.ZH
            ),
            country=self.source.country,
        )
        return s