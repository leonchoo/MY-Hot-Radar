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

from typing import List, Dict, Tuple, Set
from urllib.parse import urlsplit, urlunsplit

from .models import Story, Topic, Category, VerificationStatus, SourceType, Language
from .normalize import (
    normalize_title, tokens, extract_keywords,
    token_jaccard, keyword_overlap, entity_overlap,
)
from .thresholds import (
    TITLE_JACCARD_THRESHOLD, KEYWORD_OVERLAP_THRESHOLD,
    ENTITY_MIN_OVERLAP, ENTITY_MIN_SHARE, EVENT_WINDOW_DAYS,
)
from .thresholds import (
    TITLE_JACCARD_THRESHOLD,
    KEYWORD_OVERLAP_THRESHOLD,
)


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
                and _same_event_window(a.published_at, b.published_at)):
            return True
    return False


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
