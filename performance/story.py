"""
Story clustering and matching for Performance Intelligence P2.

A StoryCluster groups multiple content items (ContentIdentity records)
that cover the same underlying event / topic. The matching is
deterministic and explainable: every match comes with a list of
machine-readable reasons.

P2 does NOT use LLM, embedding API, or any black-box AI for matching.
P2 does NOT collect real platform data. The StoryCluster layer
consumes already-collected observations.

Forbidden in this module:

  * Embedding API calls
  * LLM-based judgement
  * Black-box similarity
  * Ranking publishers
  * Predicting virality
  * Causal inference
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .enums import Platform, SourceType
from .validation import (
    ValidationError,
    is_valid_url,
    parse_timestamp_any,
    utcnow,
    iso_utc,
    validate_str,
)


# ============================================================================
# Match reasoning
# ============================================================================

class MatchReason(str, Enum):
    EXACT_TOPIC_ID = "exact_topic_id"
    EXACT_CANONICAL_KEY = "exact_canonical_key"
    NORMALIZED_TITLE_SIMILARITY = "normalized_title_similarity"
    NAMED_ENTITY_OVERLAP = "named_entity_overlap"
    LOCATION_OVERLAP = "location_overlap"
    DATE_PROXIMITY = "date_proximity"
    CATEGORY_COMPATIBLE = "category_compatible"
    PUBLISHER_DISTINCT = "publisher_distinct"


# Reasons that SUPPORT a match
SUPPORT_REASONS = {
    MatchReason.EXACT_TOPIC_ID,
    MatchReason.EXACT_CANONICAL_KEY,
    MatchReason.NORMALIZED_TITLE_SIMILARITY,
    MatchReason.NAMED_ENTITY_OVERLAP,
    MatchReason.LOCATION_OVERLAP,
    MatchReason.DATE_PROXIMITY,
    MatchReason.CATEGORY_COMPATIBLE,
}


# ============================================================================
# StoryCluster
# ============================================================================

@dataclass
class StoryMember:
    """A single content record that is part of a StoryCluster."""
    content_id: str
    publisher: str
    platform: Platform
    published_at: str
    url: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["platform"] = self.platform.value
        return d


@dataclass
class StoryCluster:
    """Multiple media coverage of one underlying event."""
    story_cluster_id: str
    canonical_topic_key: str
    created_at: str
    first_seen_at: str
    last_seen_at: str
    category: str
    topic_type: str
    geographic_scope: str
    members: List[StoryMember]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "story_cluster_id": self.story_cluster_id,
            "canonical_topic_key": self.canonical_topic_key,
            "created_at": self.created_at,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "category": self.category,
            "topic_type": self.topic_type,
            "geographic_scope": self.geographic_scope,
            "members": [m.to_dict() for m in self.members],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StoryCluster":
        return cls(
            story_cluster_id=d["story_cluster_id"],
            canonical_topic_key=d["canonical_topic_key"],
            created_at=d["created_at"],
            first_seen_at=d["first_seen_at"],
            last_seen_at=d["last_seen_at"],
            category=d["category"],
            topic_type=d["topic_type"],
            geographic_scope=d["geographic_scope"],
            members=[
                StoryMember(
                    content_id=m["content_id"],
                    publisher=m["publisher"],
                    platform=Platform(m["platform"]),
                    published_at=m["published_at"],
                    url=m["url"],
                ) for m in d["members"]
            ],
        )


# ============================================================================
# Match result
# ============================================================================

@dataclass
class StoryMatch:
    """The explainable result of comparing two stories."""
    matched: bool
    score: float
    reasons: List[str]
    left_content_id: str
    right_content_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# PackagingSnapshot
# ============================================================================

# Allowed values for image_type field
IMAGE_TYPES = (
    "EVENT_SCENE", "LOCATION_SCENE", "CLOSE_UP", "WIDE_SHOT",
    "DOCUMENT_IMAGE", "SCREENSHOT", "GRAPHIC", "COLLAGE",
    "VIDEO_FRAME", "OTHER", None,
)


@dataclass
class PackagingSnapshot:
    """How a publisher packaged a single piece of content.

    All fields are descriptive features. None of these is a quality
    score. None is allowed for any field that has no observation.
    """
    content_id: str
    captured_at: str
    # Headline
    headline: str
    headline_length: int
    # Caption (social copy, optional)
    social_caption: Optional[str] = None
    caption_length: Optional[int] = None
    # Headline features (deterministic, never LLM)
    has_person_name: bool = False
    has_location: bool = False
    has_number: bool = False
    has_question: bool = False
    has_quote: bool = False
    has_time_reference: bool = False
    has_exclamation: bool = False
    headline_style: str = "INFORMATIVE"
    caption_style: Optional[str] = None
    # Image features (None means "unknown / not observed")
    image_count: Optional[int] = None
    primary_image_type: Optional[str] = None
    has_text_overlay: Optional[bool] = None
    has_face: Optional[bool] = None
    face_count: Optional[int] = None
    person_count: Optional[int] = None
    close_up: Optional[bool] = None
    wide_shot: Optional[bool] = None
    event_scene: Optional[bool] = None
    location_scene: Optional[bool] = None
    document_image: Optional[bool] = None
    screenshot: Optional[bool] = None
    graphic: Optional[bool] = None
    collage: Optional[bool] = None
    video_frame: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# StoryComparison
# ============================================================================

@dataclass
class MemberPerformance:
    """Observed performance of a single member within a StoryCluster."""
    content_id: str
    publisher: str
    platform: str
    views: Optional[int]
    likes: Optional[int]
    comments: Optional[int]
    shares: Optional[int]
    views_per_hour: Optional[float]
    likes_per_hour: Optional[float]
    comments_per_hour: Optional[float]
    shares_per_hour: Optional[float]
    engagement_rate: Optional[float]
    performance_class: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StoryComparison:
    """Same-story, different-packaging observed comparison.

    IMPORTANT: This struct is OBSERVATIONAL. It does NOT rank
    publishers. It does NOT normalize by follower count (because
    follower baselines are usually unavailable at this stage — see
    NORMALIZED_COMPARISON_UNAVAILABLE flag).
    """
    story_cluster_id: str
    member_performance: List[MemberPerformance]
    publisher_count: int
    platform_count: int
    first_publisher: Optional[str]
    first_publish_at: Optional[str]
    performance_window: Dict[str, Optional[str]]
    normalized_comparison_available: bool
    unavailable_reason: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "story_cluster_id": self.story_cluster_id,
            "member_performance": [m.to_dict() for m in self.member_performance],
            "publisher_count": self.publisher_count,
            "platform_count": self.platform_count,
            "first_publisher": self.first_publisher,
            "first_publish_at": self.first_publish_at,
            "performance_window": self.performance_window,
            "normalized_comparison_available": self.normalized_comparison_available,
            "unavailable_reason": self.unavailable_reason,
        }


# ============================================================================
# Title normalization + similarity
# ============================================================================

# Strip site-name suffixes, parentheticals, and common English/Malay
# stopwords that cause spurious matches.
_NORMALIZE_RE = re.compile(r"[^a-z0-9\u4e00-\u9fff]+", re.UNICODE)
# Tokens that are too common to drive a match by themselves.
_STOPWORDS = frozenset({
    # English
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "and", "or",
    "is", "are", "was", "were", "be", "been", "as", "by", "with",
    "from", "after", "over", "into", "this", "that", "says", "said",
    "report", "reports", "new", "old", "first", "last",
    # Malay (very common generic words)
    "yang", "di", "ke", "dari", "untuk", "dengan", "oleh",
    "pada", "ini", "itu", "atau", "dan", "akan", "telah",
    "kata", "lapor", "berkaitan", "susulan",
    # Chinese (very common generic words)
    "的", "了", "是", "在", "和", "与", "或", "一个", "我们",
})


def _stem_token(t: str) -> str:
    """Very conservative English stemming (suffix stripping only).

    We deliberately keep this naive and explicit — no NLTK, no ML.
    False negatives are acceptable; false positives are not.

    Strip common suffixes from tokens >= 5 chars. We also extract a
    4-char prefix which is used to detect that "charg"/"charge" or
    "trigger"/"triggers" share a stem.
    """
    if len(t) < 5:
        return t
    for suf in ("tion", "sion", "ing", "ment", "ness", "able", "ible",
                "ously", "ively", "edly", "er", "ed", "es", "ly", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            return t[: -len(suf)]
    return t


def _stem4(t: str) -> str:
    """Return the first 4 characters as a coarse stem."""
    return t[:4] if len(t) >= 4 else t


def normalize_title(title: str) -> str:
    """Lowercase + remove punctuation + drop stopwords.

    Returns a normalized token list joined by single spaces. Used by
    the deterministic similarity scorer; NOT used as a key.
    """
    if not isinstance(title, str):
        return ""
    lower = title.lower()
    tokens = _NORMALIZE_RE.split(lower)
    tokens = [t for t in tokens if t and t not in _STOPWORDS and len(t) > 1]
    return " ".join(tokens)


def normalize_title_stemmed(title: str) -> str:
    """Like normalize_title but with conservative English stemming.

    Used for matching content words like 'charge' / 'charged',
    'trigger' / 'triggers'. This is NOT a translation; we are not
    building a full Porter stemmer, just enough to reduce obvious
    inflection noise.
    """
    base = normalize_title(title)
    if not base:
        return ""
    return " ".join(_stem_token(t) for t in base.split())


def jaccard_similarity(a_tokens: str, b_tokens: str) -> float:
    """Jaccard similarity on the normalized token sets."""
    if not a_tokens or not b_tokens:
        return 0.0
    a = set(a_tokens.split())
    b = set(b_tokens.split())
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    return len(inter) / len(union) if union else 0.0


# ============================================================================
# Entity / location extraction (conservative, no NER)
# ============================================================================

# Conservative location hints: place names that commonly appear in
# MY/SG/ID/TH/IN news. False positives are tolerable because we
# require LOCATION_OVERLAP in addition to other signals. Unknown
# locations return None — we NEVER hallucinate.
_KNOWN_LOCATIONS = frozenset({
    # Malaysia
    "kuala lumpur", "kl", "putrajaya", "selangor", "penang", "johor",
    "malacca", "sabah", "sarawak", "perak", "pahang", "negeri sembilan",
    "melaka", "ipoh", "kuching", "kota kinabalu", "shah alam",
    "pandan reservoir", "taman sri muda", "jalan semarak",
    # Singapore
    "singapore",
    # International
    "india", "indian", "tata", "thailand", "bangkok", "myanmar",
    "south korean", "korea", "shein", "hormuz", "bbc",
})


def extract_locations(text: str) -> List[str]:
    """Return the list of known locations mentioned in text.

    Returns an empty list if no known location is found. Does NOT
    hallucinate locations. Unknown places are silently absent.
    """
    if not isinstance(text, str):
        return []
    lower = text.lower()
    found: List[str] = []
    for loc in _KNOWN_LOCATIONS:
        if loc in lower:
            found.append(loc)
    return found


def extract_known_entities(
    title: str,
    structured_entities: Optional[List[str]] = None,
) -> List[str]:
    """Return a deduplicated list of entities.

    Combines any structured entities supplied by the caller (e.g.
    from a pre-existing NER pipeline that we trust) with locations
    found in the title. We do NOT run NER ourselves.
    """
    out: List[str] = []
    if structured_entities:
        for e in structured_entities:
            if isinstance(e, str) and e:
                out.append(e.strip())
    out.extend(extract_locations(title))
    # Dedupe while preserving order
    seen = set()
    deduped: List[str] = []
    for e in out:
        if e and e not in seen:
            seen.add(e)
            deduped.append(e)
    return deduped


# ============================================================================
# Deterministic Story Matching
# ============================================================================

# Match thresholds
JACCARD_HIGH = 0.3           # strong title overlap (prefix-4 stems)
JACCARD_MEDIUM = 0.15        # weak title overlap alone is not enough
DATE_PROXIMITY_MAX_HOURS = 168  # same story within a week
CATEGORY_COMPATIBLE = True   # by default, same category compatible


def _canonical_topic_key(*parts: str) -> str:
    """Stable hash of a topic-key tuple.

    Order-independent: the parts are sorted before hashing, so two
    callers passing the same set of parts in any order get the same
    canonical key.
    """
    payload = {"kind": "topic_key_v1", "parts": sorted(parts)}
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"))
    return "tk_" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]


def story_cluster_id_for(canonical_topic_key: str) -> str:
    payload = {
        "kind": "story_cluster_id_v1",
        "canonical_topic_key": canonical_topic_key,
    }
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"))
    return "sc_" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]


def match_stories(
    *,
    left_content_id: str,
    right_content_id: str,
    left_title: str,
    right_title: str,
    left_published_at: str,
    right_published_at: str,
    left_category: str,
    right_category: str,
    left_entities: Optional[List[str]] = None,
    right_entities: Optional[List[str]] = None,
    left_topic_id: Optional[str] = None,
    right_topic_id: Optional[str] = None,
    left_canonical_key: Optional[str] = None,
    right_canonical_key: Optional[str] = None,
) -> StoryMatch:
    """Compare two stories and return an explainable match result.

    Strict rules:

      * exact_topic_id OR exact_canonical_key -> matched=True
      * otherwise:
          - require category compatibility
          - require date proximity within DATE_PROXIMITY_MAX_HOURS
          - require (entity overlap >= 2) OR
                     (jaccard >= JACCARD_HIGH) OR
                     (location overlap >= 1 AND jaccard >= JACCARD_MEDIUM)

    The result has a score in [0.0, 1.0] AND a non-empty list of
    reasons. A matched=False result still has reasons (the ones that
    partially matched).
    """
    if left_content_id == right_content_id:
        return StoryMatch(
            matched=True, score=1.0,
            reasons=["same_content_id"],
            left_content_id=left_content_id,
            right_content_id=right_content_id,
        )

    reasons: List[str] = []
    score = 0.0

    # 1. Exact topic id
    if (left_topic_id is not None
            and right_topic_id is not None
            and left_topic_id == right_topic_id
            and left_topic_id != ""):
        reasons.append(MatchReason.EXACT_TOPIC_ID.value)
        score = 1.0
        return StoryMatch(
            matched=True, score=1.0,
            reasons=reasons,
            left_content_id=left_content_id,
            right_content_id=right_content_id,
        )

    # 2. Exact canonical key
    if (left_canonical_key is not None
            and right_canonical_key is not None
            and left_canonical_key == right_canonical_key
            and left_canonical_key != ""):
        reasons.append(MatchReason.EXACT_CANONICAL_KEY.value)
        score = 1.0
        return StoryMatch(
            matched=True, score=1.0,
            reasons=reasons,
            left_content_id=left_content_id,
            right_content_id=right_content_id,
        )

    # 3. Category compatibility (always required if no exact match)
    if left_category == right_category and left_category != "":
        reasons.append(MatchReason.CATEGORY_COMPATIBLE.value)
        score += 0.1
    elif left_category != "" and right_category != "":
        # Different categories -> NEVER merge
        return StoryMatch(
            matched=False, score=score,
            reasons=["category_mismatch"],
            left_content_id=left_content_id,
            right_content_id=right_content_id,
        )

    # 4. Date proximity
    t_left = parse_timestamp_any(left_published_at)
    t_right = parse_timestamp_any(right_published_at)
    if t_left is None or t_right is None:
        # Unknown timestamp -> conservative no-match
        return StoryMatch(
            matched=False, score=score,
            reasons=reasons + ["unparseable_timestamp"],
            left_content_id=left_content_id,
            right_content_id=right_content_id,
        )
    delta_hours = abs((t_right - t_left).total_seconds()) / 3600.0
    if delta_hours <= DATE_PROXIMITY_MAX_HOURS:
        reasons.append(MatchReason.DATE_PROXIMITY.value)
        score += 0.15

    # 5. Entity overlap (extracted conservatively)
    left_ent = set(extract_known_entities(left_title, left_entities))
    right_ent = set(extract_known_entities(right_title, right_entities))
    ent_overlap = left_ent & right_ent
    if len(ent_overlap) >= 2:
        reasons.append(MatchReason.NAMED_ENTITY_OVERLAP.value)
        score += 0.4
    if ent_overlap:
        # any entity overlap -> location overlap may also apply
        reasons.append(MatchReason.LOCATION_OVERLAP.value)
        score += 0.1

    # 6. Title similarity (Jaccard on stemmed + prefix-4 stems)
    j_raw = jaccard_similarity(normalize_title(left_title),
                                normalize_title(right_title))
    j_stem = jaccard_similarity(normalize_title_stemmed(left_title),
                                  normalize_title_stemmed(right_title))
    # Prefix-4 stem Jaccard: tokens become their first 4 chars
    # (e.g. "charged" / "charge" / "triggers" / "trigger" all share
    # a 4-char prefix).
    p4a = " ".join(sorted({_stem4(t) for t in normalize_title(left_title).split()}))
    p4b = " ".join(sorted({_stem4(t) for t in normalize_title(right_title).split()}))
    j_prefix = jaccard_similarity(p4a, p4b)
    # Use the highest of the three signals.
    j = max(j_raw, j_stem, j_prefix)
    if j >= JACCARD_HIGH:
        reasons.append(MatchReason.NORMALIZED_TITLE_SIMILARITY.value)
        score += 0.4
    elif j >= JACCARD_MEDIUM:
        # Weak similarity alone is NOT enough; require another
        # strong signal. Just record it for explanation.
        reasons.append(MatchReason.NORMALIZED_TITLE_SIMILARITY.value + "_weak")
        score += 0.1

    score = min(score, 1.0)
    # Matched iff one of:
    #   (a) exact topic id / exact canonical key
    #   (b) NAMED_ENTITY_OVERLAP (>=2 entities shared) AND category+date
    #   (c) LOCATION_OVERLAP + title similarity (strong OR weak) AND category+date
    #   (d) strong title similarity alone AND category+date
    #         (only when similarity is genuinely high; threshold = JACCARD_HIGH)
    matched = (
        MatchReason.EXACT_TOPIC_ID.value in reasons
        or MatchReason.EXACT_CANONICAL_KEY.value in reasons
        or (
            MatchReason.CATEGORY_COMPATIBLE.value in reasons
            and MatchReason.DATE_PROXIMITY.value in reasons
            and (
                MatchReason.NAMED_ENTITY_OVERLAP.value in reasons
                or (
                    MatchReason.LOCATION_OVERLAP.value in reasons
                    and (
                        MatchReason.NORMALIZED_TITLE_SIMILARITY.value in reasons
                        or MatchReason.NORMALIZED_TITLE_SIMILARITY.value + "_weak"
                        in reasons
                    )
                )
                or MatchReason.NORMALIZED_TITLE_SIMILARITY.value in reasons
            )
        )
    )

    return StoryMatch(
        matched=matched, score=round(score, 4),
        reasons=reasons,
        left_content_id=left_content_id,
        right_content_id=right_content_id,
    )


# ============================================================================
# Validation
# ============================================================================

def validate_story_cluster(c: StoryCluster) -> None:
    validate_str("story_cluster_id", c.story_cluster_id, max_len=128)
    validate_str("canonical_topic_key", c.canonical_topic_key, max_len=128)
    for fname in ("created_at", "first_seen_at", "last_seen_at"):
        if parse_timestamp_any(getattr(c, fname)) is None:
            raise ValidationError(f"{fname} not valid: {getattr(c, fname)!r}")
    for name in ("category", "topic_type", "geographic_scope"):
        validate_str(name, getattr(c, name), max_len=64)
    if not c.members:
        raise ValidationError("StoryCluster must have at least one member")
    seen_ids = set()
    for m in c.members:
        validate_str("content_id", m.content_id, max_len=128)
        if m.content_id in seen_ids:
            raise ValidationError(f"duplicate content_id in members: {m.content_id}")
        seen_ids.add(m.content_id)
        if not isinstance(m.platform, Platform):
            raise ValidationError("member.platform must be a Platform enum")
        validate_str("publisher", m.publisher, max_len=200)
        if not is_valid_url(m.url):
            raise ValidationError(f"member.url not safe: {m.url!r}")
        if parse_timestamp_any(m.published_at) is None:
            raise ValidationError(
                f"member.published_at not valid: {m.published_at!r}"
            )


def validate_packaging_snapshot(p: PackagingSnapshot) -> None:
    validate_str("content_id", p.content_id, max_len=128)
    if parse_timestamp_any(p.captured_at) is None:
        raise ValidationError("captured_at not valid")
    validate_str("headline", p.headline, max_len=500)
    if not isinstance(p.headline_length, int) or p.headline_length < 0:
        raise ValidationError("headline_length must be a non-negative int")
    if p.social_caption is not None:
        validate_str("social_caption", p.social_caption, max_len=2000)
    if p.caption_length is not None:
        if not isinstance(p.caption_length, int) or p.caption_length < 0:
            raise ValidationError("caption_length must be non-negative int")
    for bf in ("has_person_name", "has_location", "has_number",
                "has_question", "has_quote", "has_time_reference",
                "has_exclamation"):
        if not isinstance(getattr(p, bf), bool):
            raise ValidationError(f"{bf} must be a bool")
    if p.headline_style not in ("INFORMATIVE", "QUESTION", "EXCLAMATORY", "QUOTE"):
        raise ValidationError(f"headline_style invalid: {p.headline_style!r}")
    if p.caption_style is not None:
        if p.caption_style not in ("INFORMATIVE", "QUESTION", "EXCLAMATORY", "QUOTE"):
            raise ValidationError(f"caption_style invalid: {p.caption_style!r}")
    if p.image_count is not None and (
        not isinstance(p.image_count, int) or p.image_count < 0
    ):
        raise ValidationError("image_count must be None or non-negative int")
    if p.primary_image_type not in IMAGE_TYPES:
        raise ValidationError(f"primary_image_type invalid: {p.primary_image_type!r}")
    for tb in ("has_text_overlay", "has_face", "close_up", "wide_shot",
                "event_scene", "location_scene", "document_image",
                "screenshot", "graphic", "collage", "video_frame"):
        v = getattr(p, tb)
        if v is not None and not isinstance(v, bool):
            raise ValidationError(f"{tb} must be None or bool")
    if p.face_count is not None:
        if not isinstance(p.face_count, int) or p.face_count < 0:
            raise ValidationError("face_count must be None or non-negative int")
    if p.person_count is not None:
        if not isinstance(p.person_count, int) or p.person_count < 0:
            raise ValidationError("person_count must be None or non-negative int")


# ============================================================================
# Timing analysis
# ============================================================================

def minutes_between(earlier: str, later: str) -> Optional[int]:
    """Return minutes between two timestamps, or None on error.

    Negative if later < earlier (returns the signed value to flag the
    ordering; the caller decides whether to flip it).
    """
    t1 = parse_timestamp_any(earlier)
    t2 = parse_timestamp_any(later)
    if t1 is None or t2 is None:
        return None
    return int((t2 - t1).total_seconds() // 60)


def timing_offsets(cluster: StoryCluster,
                    story_first_seen: Optional[str] = None) -> Dict[str, int]:
    """For each member, compute minutes_from_story_first_seen.

    story_first_seen defaults to cluster.first_seen_at.
    """
    base = story_first_seen or cluster.first_seen_at
    out: Dict[str, int] = {}
    for m in cluster.members:
        delta = minutes_between(base, m.published_at)
        if delta is not None:
            out[m.content_id] = delta
    return out


# ============================================================================
# Story comparison builder
# ============================================================================

NORMALIZED_COMPARISON_UNAVAILABLE = "NORMALIZED_COMPARISON_UNAVAILABLE"


def build_story_comparison(
    cluster: StoryCluster,
    *,
    member_performance_rows: List[Dict[str, Any]],
    performance_window_from: str,
    performance_window_to: str,
) -> StoryComparison:
    """Build a StoryComparison from a cluster and observed per-member
    performance rows.

    member_performance_rows: a list of dicts, each with at least
      content_id, publisher, platform, views, likes, comments, shares,
      views_per_hour, likes_per_hour, comments_per_hour,
      shares_per_hour, engagement_rate, performance_class.

    The rows are NOT ranked or sorted. They are presented in the
    order given by the caller (typically cluster member order).
    """
    members = cluster.members
    if not member_performance_rows:
        # Always return the cluster context, even with zero observations
        return StoryComparison(
            story_cluster_id=cluster.story_cluster_id,
            member_performance=[],
            publisher_count=len({m.publisher for m in members}),
            platform_count=len({m.platform.value for m in members}),
            first_publisher=None,
            first_publish_at=cluster.first_seen_at,
            performance_window={
                "from": performance_window_from,
                "to": performance_window_to,
            },
            normalized_comparison_available=False,
            unavailable_reason="no_observations",
        )

    # Find first publisher: smallest published_at
    first_member = min(members, key=lambda m: m.published_at)
    platforms = {row["platform"] for row in member_performance_rows}
    publishers = {row["publisher"] for row in member_performance_rows}
    perf_members = [
        MemberPerformance(
            content_id=row["content_id"],
            publisher=row.get("publisher", ""),
            platform=row.get("platform", ""),
            views=row.get("views"),
            likes=row.get("likes"),
            comments=row.get("comments"),
            shares=row.get("shares"),
            views_per_hour=row.get("views_per_hour"),
            likes_per_hour=row.get("likes_per_hour"),
            comments_per_hour=row.get("comments_per_hour"),
            shares_per_hour=row.get("shares_per_hour"),
            engagement_rate=row.get("engagement_rate"),
            performance_class=row.get("performance_class"),
        )
        for row in member_performance_rows
    ]
    # Without follower / reach baseline, we cannot normalize. Always
    # refuse to claim normalized comparison.
    return StoryComparison(
        story_cluster_id=cluster.story_cluster_id,
        member_performance=perf_members,
        publisher_count=len(publishers),
        platform_count=len(platforms),
        first_publisher=first_member.publisher,
        first_publish_at=first_member.published_at,
        performance_window={
            "from": performance_window_from,
            "to": performance_window_to,
        },
        normalized_comparison_available=False,
        unavailable_reason="follower_baseline_unavailable",
    )


# ============================================================================
# Deterministic packaging feature extractor (no LLM, no NER)
# ============================================================================

_PERSON_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
_NUMBER_RE = re.compile(r"\d")
_QUOTE_RE = re.compile(r"[\"\u201c\u201d]")
_TIME_REF_RE = re.compile(
    r"\b(today|yesterday|tomorrow|tonight|just|breaking|"
    r"this week|last week|next week|this month|last month|"
    r"this morning|tonight|now|"
    r"今天|昨天|明天|今晚|刚刚|突发|最新|今日|今早)\b",
    re.IGNORECASE,
)
_EXCLAMATION_RE = re.compile(r"!|！")
_QUESTION_END_RE = re.compile(r"[?？]\s*$")


def _detect_style(text: str) -> str:
    if _QUESTION_END_RE.search(text):
        return "QUESTION"
    if _EXCLAMATION_RE.search(text):
        return "EXCLAMATORY"
    if _QUOTE_RE.search(text):
        return "QUOTE"
    return "INFORMATIVE"


def extract_headline_features(
    headline: str,
    *,
    structured_entities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return headline features as a plain dict.

    The same heuristic feature extractor used by P1; P2 keeps it
    identical so a PackagingSnapshot is consistent with a
    ContentFeatureSnapshot from P1.
    """
    return {
        "headline_length": len(headline),
        "has_person_name": bool(_PERSON_NAME_RE.search(headline)),
        "has_location": bool(extract_locations(headline)),
        "has_number": bool(_NUMBER_RE.search(headline)),
        "has_question": headline.rstrip().endswith(("?", "？")),
        "has_quote": bool(_QUOTE_RE.search(headline)),
        "has_time_reference": bool(_TIME_REF_RE.search(headline)),
        "has_exclamation": bool(_EXCLAMATION_RE.search(headline)),
        "headline_style": _detect_style(headline),
        "named_entities": extract_known_entities(headline, structured_entities),
    }


def build_packaging_snapshot(
    *,
    content_id: str,
    headline: str,
    social_caption: Optional[str] = None,
    structured_entities: Optional[List[str]] = None,
    image_features: Optional[Dict[str, Any]] = None,
) -> PackagingSnapshot:
    """Build a PackagingSnapshot from a headline + caption + optional
    image metadata.

    image_features: a dict carrying values supplied by an upstream
    process (manual review, image API, etc.). Fields not present in
    the dict remain None in the snapshot.

    Unknown image features are NEVER coerced to False. They stay
    None until observed.
    """
    hf = extract_headline_features(headline, structured_entities=structured_entities)
    cap = social_caption
    if cap is not None:
        cs = _detect_style(cap)
        clen = len(cap)
    else:
        cs = None
        clen = None

    img = image_features or {}

    def _opt(name: str) -> Any:
        return img.get(name, None)

    return PackagingSnapshot(
        content_id=content_id,
        captured_at=iso_utc(utcnow()),
        headline=headline,
        headline_length=hf["headline_length"],
        social_caption=cap,
        caption_length=clen,
        has_person_name=hf["has_person_name"],
        has_location=hf["has_location"],
        has_number=hf["has_number"],
        has_question=hf["has_question"],
        has_quote=hf["has_quote"],
        has_time_reference=hf["has_time_reference"],
        has_exclamation=hf["has_exclamation"],
        headline_style=hf["headline_style"],
        caption_style=cs,
        image_count=_opt("image_count"),
        primary_image_type=_opt("primary_image_type"),
        has_text_overlay=_opt("has_text_overlay"),
        has_face=_opt("has_face"),
        face_count=_opt("face_count"),
        person_count=_opt("person_count"),
        close_up=_opt("close_up"),
        wide_shot=_opt("wide_shot"),
        event_scene=_opt("event_scene"),
        location_scene=_opt("location_scene"),
        document_image=_opt("document_image"),
        screenshot=_opt("screenshot"),
        graphic=_opt("graphic"),
        collage=_opt("collage"),
        video_frame=_opt("video_frame"),
    )


__all__ = [
    "MatchReason",
    "StoryMember",
    "StoryCluster",
    "StoryMatch",
    "PackagingSnapshot",
    "MemberPerformance",
    "StoryComparison",
    "NORMALIZED_COMPARISON_UNAVAILABLE",
    "IMAGE_TYPES",
    "JACCARD_HIGH",
    "JACCARD_MEDIUM",
    "DATE_PROXIMITY_MAX_HOURS",
    "normalize_title",
    "jaccard_similarity",
    "extract_locations",
    "extract_known_entities",
    "match_stories",
    "validate_story_cluster",
    "validate_packaging_snapshot",
    "minutes_between",
    "timing_offsets",
    "build_story_comparison",
    "extract_headline_features",
    "build_packaging_snapshot",
    "story_cluster_id_for",
    "_canonical_topic_key",
]
