"""
Explainable rule-based deduplication.

This module clusters Stories into Topics. The rules are deliberately explicit
so the output is auditable: every topic carries, for each member, which rule
caused the join.

In Phase 1 we use:
  1. Exact URL match (after canonicalization; we strip UTM / fragment).
  2. URL without query string match.
  3. Title similarity: same normalized title OR token-Jaccard >= TITLE_JACCARD_THRESHOLD.
  4. Keyword overlap >= KEYWORD_OVERLAP_THRESHOLD and shared category.

We deliberately do NOT depend on LLMs for clustering here.

Tunable thresholds live in radar.thresholds so changes don't scatter across files.
"""

from __future__ import annotations

import re
from typing import List, Dict, Tuple, Set, Optional
from urllib.parse import urlsplit, urlunsplit

from .models import Story, Topic, Category, VerificationStatus, SourceType, Language
from .normalize import (
    normalize_title, tokens, extract_keywords,
    token_jaccard, keyword_overlap, entity_overlap,
)
from .thresholds import (
    TITLE_JACCARD_THRESHOLD, KEYWORD_OVERLAP_THRESHOLD,
    ENTITY_MIN_OVERLAP, ENTITY_MIN_SHARE, EVENT_WINDOW_DAYS,
    ENTITY_PATH_REQUIRE_DATE_BOTH_SIDES,
)
from .thresholds import (
    TITLE_JACCARD_THRESHOLD,
    KEYWORD_OVERLAP_THRESHOLD,
)


# ============================================================================
# A2.3.2 — URL date extraction (Guard C helper)
# ============================================================================
#
# HTML_LISTING adapters (Sin Chew, China Press, Kwong Wah) don't populate
# ``Story.published_at``. However, their URL paths almost always embed a
# date: either ``/YYYYMMDD/`` (most common, e.g.
# ``https://mysinchew.sinchew.com.my/news/20260928/...``) or ``/YYYY/MM/DD/``
# (e.g. FMT: ``.../2026/09/30/...``).
#
# The dedup signal needs an extra date source for these adapters. We extract
# the date as a SEPARATE return value (an ISO ``YYYY-MM-DD`` string or
# ``None``) without mutating ``Story.published_at`` or ``Story.url``.
#
# Date validation is strict:
#   - 4-digit year in [1900, 2100]
#   - month in [1, 12]
#   - day in [1, max_day_in_that_month] (handles leap years)
#
# Both YYYYMMDD and YYYY/MM/DD patterns are tried; the first valid match wins.
# 8-digit runs that don't form valid dates (month 13, day 32, Feb 30, etc.)
# return ``None``.

_URL_DATE_YYYYMMDD = re.compile(r"/(\d{4})(\d{2})(\d{2})(?:/|$|[^0-9])")
_URL_DATE_YYYYMMDD_NO_SLASH = re.compile(r"(?:^|/|[^0-9])(\d{4})(\d{2})(\d{2})(?:/|$|[^0-9])")
_URL_DATE_SLASHED = re.compile(r"/(\d{4})/(\d{1,2})/(\d{1,2})(?:/|$)")


def _is_valid_yyyy_mm_dd(year: int, month: int, day: int) -> bool:
    """Strict validation: year range, month range, day-of-month with leap-year handling."""
    if not (1900 <= year <= 2100):
        return False
    if not (1 <= month <= 12):
        return False
    if not (1 <= day <= 31):
        return False
    # Days per month (index 0 = Jan)
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    # Leap year adjustment for February
    is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    if is_leap:
        days_in_month[1] = 29
    return day <= days_in_month[month - 1]


def _extract_date_from_url(url: str) -> Optional[str]:
    """Try to extract an ISO date (``YYYY-MM-DD``) from a URL path.

    Returns ``None`` if the URL is empty, malformed, or contains no valid
    date pattern. The function is a pure read — it does NOT mutate the
    ``Story.published_at`` field. URL-derived dates are passed to
    ``_same_event_window`` as an optional fallback signal.

    Patterns tried in order:
      1. ``/YYYY/MM/DD/`` (FMT-style)
      2. ``/YYYYMMDD/`` (Sin Chew / China Press / Kwong Wah style)

    Invalid dates (month 13, day 32, Feb 30, etc.) are rejected.
    """
    if not url or not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    path = parts.path

    # Pattern 1: /YYYY/MM/DD/ (FMT)
    m = _URL_DATE_SLASHED.search(path)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _is_valid_yyyy_mm_dd(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"

    # Pattern 2: /YYYYMMDD/ (Sin Chew / China Press / Kwong Wah)
    # We require a / or $ boundary before/after to avoid matching inside longer numbers
    m = _URL_DATE_YYYYMMDD.search(path)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _is_valid_yyyy_mm_dd(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"

    return None


def _known_date(*candidates: Optional[str]) -> Optional[str]:
    """Return the first non-empty string among ``candidates`` (used for date fallback chain)."""
    for c in candidates:
        if c:
            return c
    return None


def canonicalize_url(u: str) -> str:
    """Strip fragment; remove a small set of common tracking params."""
    if not u:
        return ""
    try:
        parts = urlsplit(u.strip())
    except ValueError:
        return u.strip()
    drop = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "ref", "ref_src", "igshid",
    }
    from urllib.parse import parse_qsl, urlencode
    q = parse_qsl(parts.query, keep_blank_values=True)
    q = [(k, v) for (k, v) in q if k.lower() not in drop]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(q), ""))


def _is_strong_match(a: Story, b: Story) -> bool:
    """Heuristic: Stories likely describe the same underlying event."""
    if not a.url or not b.url:
        pass
    else:
        ca, cb = canonicalize_url(a.url), canonicalize_url(b.url)
        if ca and ca == cb and ca != "":
            return True
        # same path on same host
        pa, pb = urlsplit(ca), urlsplit(cb)
        if pa.netloc == pb.netloc and pa.path and pa.path == pb.path:
            return True

    # Title-based
    nt_a, nt_b = a.normalized_title or normalize_title(a.title), b.normalized_title or normalize_title(b.title)
    if nt_a and nt_b and nt_a == nt_b:
        return True
    if nt_a and nt_b:
        if token_jaccard(a.title, b.title) >= TITLE_JACCARD_THRESHOLD:
            return True
    if a.keywords and b.keywords:
        if keyword_overlap(a.keywords, b.keywords) >= KEYWORD_OVERLAP_THRESHOLD and a.category == b.category:
            return True
    if a.title and b.title:
        eo, smaller, _ = entity_overlap(a.title, b.title)
        if (eo >= ENTITY_MIN_OVERLAP
                and smaller > 0
                and eo / smaller >= ENTITY_MIN_SHARE
                and _entity_window_ok(a, b)):
            return True
    return False


def _entity_window_ok(a: Story, b: Story) -> bool:
    """A2.3.2 Guard C — date-confident window for the entity-overlap merge path.

    Behavior matrix (when ENTITY_PATH_REQUIRE_DATE_BOTH_SIDES is True, default):

      | pa | pb | url_a | url_b | Result | Rationale
      |----|----|-------|-------|--------|----------
      | ok | ok |  any  |  any  | _same_event_window(pa,pb) | Both dated → trust dates
      | ok | -- |  any  |  any  | False | One side has date, other has no signal → fail-closed
      | -- | ok |  any  |  any  | False | Same as above
      | ok | -- |  --   | date  | False | Even URL date on other side differs → fail-closed
      | -- | -- | date  |  --   | False | Same as above
      | -- | -- | date  | date  | _same_event_window(url_a, url_b) | Both URL-dated → trust URL dates
      | -- | -- |  --   |  --   | True  | Permissive fallback: no date info either side

    Date fallback chain: ``published_at`` first, then ``_extract_date_from_url(url)``.

    The keyword-overlap path, title-Jaccard path, and URL path are NOT
    affected — they continue to use the original ``_same_event_window`` for
    their date semantics. This guard specifically targets the entity-path
    false merge identified in A2.3.2 Investigation 1.
    """
    if not ENTITY_PATH_REQUIRE_DATE_BOTH_SIDES:
        return _same_event_window(a.published_at, b.published_at)

    date_a = _known_date(a.published_at, _extract_date_from_url(a.url))
    date_b = _known_date(b.published_at, _extract_date_from_url(b.url))

    # Both dates available — defer to the standard window check
    if date_a and date_b:
        return _same_event_window(date_a, date_b)

    # Exactly one side has a date: fail-closed (reject the merge)
    if date_a or date_b:
        return False

    # Neither side has a date: permissive fallback (don't break historical
    # behavior when both adapters produce sparse dates)
    return True


def _same_event_window(pa, pb) -> bool:
    """Two stories must be within EVENT_WINDOW_DAYS of each other.
    If either timestamp is missing/unparseable, default to True so we don't
    artificially fail to merge on bad input."""
    if not pa or not pb:
        return True
    from datetime import datetime
    def _try(s):
        if not s:
            return None
        s = s.replace("Z", "+00:00")[:35]
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(s[:19], fmt[:19]) if "%z" not in fmt else datetime.strptime(s, fmt)
            except Exception:
                continue
        return None
    da, db = _try(pa), _try(pb)
    if da is None or db is None:
        return True
    try:
        return abs((da - db).total_seconds()) <= EVENT_WINDOW_DAYS * 86400
    except TypeError:
        return True


def cluster(stories: List[Story]) -> Tuple[List[Topic], Dict[str, str]]:
    """Group Stories into Topics.

    Returns:
        (topics, story_to_topic) — every Story in input maps to a topic id.

    Each Topic carries:
      - title: chosen from the longest / earliest story title.
      - summary: the longest non-empty summary among members.
      - story_ids: the contributing stories in input order.
      - categories_seen: the set of categories (we pick the most common).
      - related_urls: deduped list of URLs.

    The single-topic rule is:
      Greedy union-find: for each story in order, attach to the first
      existing topic it strongly matches; otherwise create a new topic.
    """
    topics: List[Topic] = []
    story_to_topic: Dict[str, str] = {}
    by_topic: Dict[str, List[Story]] = {}

    for s in stories:
        # Normalize once
        if not s.normalized_title:
            s.normalized_title = normalize_title(s.title)
        if not s.keywords:
            s.keywords = extract_keywords(s.title)

        matched_topic = None
        for t in topics:
            # pairwise match using existing topic members
            members = by_topic[t.id]
            if any(_is_strong_match(s, m) for m in members):
                matched_topic = t
                break
        if matched_topic is None:
            t = Topic(
                title=s.title,
                summary=s.summary,
                category=s.category,
                language=s.language,
            )
            topics.append(t)
            by_topic[t.id] = [s]
            story_to_topic[s.id] = t.id
        else:
            by_topic[matched_topic.id].append(s)
            story_to_topic[s.id] = matched_topic.id
            # Extend topic metadata from new member
            if len(s.title) > len(matched_topic.title):
                matched_topic.title = s.title
            if s.summary and len(s.summary) > len(matched_topic.summary):
                matched_topic.summary = s.summary

    # Backfill topic-level metadata
    for t in topics:
        members = by_topic[t.id]
        t.story_ids = [m.id for m in members]
        # dedup related_urls
        seen = set()
        rel: List[str] = []
        for m in members:
            cu = canonicalize_url(m.url)
            if cu and cu not in seen:
                seen.add(cu)
                rel.append(cu)
        t.related_urls = rel
        # canonical_url = first canonicalized URL; used as cross-scan stable key
        t.canonical_url = rel[0] if rel else ""
        t.mention_count = len(members)
        # pick most common category among members (fallback to topic's category)
        cat_counts: Dict[Category, int] = {}
        for m in members:
            cat_counts[m.category] = cat_counts.get(m.category, 0) + 1
        if cat_counts:
            t.category = max(cat_counts, key=lambda k: cat_counts[k])
        # earliest published_at if any
        pubs = [m.published_at for m in members if m.published_at]
        if pubs:
            t.first_seen = min(pubs)
            t.last_seen = max(pubs)
        # source-types seen
        types_seen: Set[SourceType] = set()
        for m in members:
            types_seen.add(m.source_type)
        t.statuses_seen = sorted(types_seen, key=lambda s: s.value)

    return topics, story_to_topic


def explain_match(story: Story, topic_members: List[Story]) -> List[str]:
    """Explain why this story belongs to this topic (for auditability)."""
    reasons = []
    others = [m for m in topic_members if m.id != story.id]
    if not others:
        return ["first member of new topic"]
    for m in others:
        if m.url and story.url:
            ca, cb = canonicalize_url(m.url), canonicalize_url(story.url)
            if ca == cb and ca:
                reasons.append(f"same canonical URL as story from {m.source}")
                continue
            from urllib.parse import urlsplit
            pa, pb = urlsplit(ca), urlsplit(cb)
            if pa.netloc == pb.netloc and pa.path and pa.path == pb.path:
                reasons.append(f"same host+path as {m.source}")
                continue
        j = token_jaccard(story.title, m.title)
        if j >= TITLE_JACCARD_THRESHOLD:
            reasons.append(f"high title similarity (jaccard={j:.2f}) with {m.source}")
            continue
        o = keyword_overlap(story.keywords, m.keywords)
        if o >= KEYWORD_OVERLAP_THRESHOLD and story.category == m.category:
            reasons.append(f"keyword overlap={o:.2f} + same category with {m.source}")
    return reasons
