"""
Radar-6 — Existing Tier-B Source Review & Reliability Validation.

Per spec section 1, this module re-evaluates the 5 currently-registered
Tier-B sources and produces a structured review. It does NOT:
  - add new sources
  - modify the registry
  - modify any Radar engine code (verification, momentum, classification)

It DOES:
  - define a `TierBReview` dataclass with stability / freshness /
    content / wire-origin evidence
  - classify each source's content using the Radar-5B `ContentNature`
    taxonomy (reused, not redefined)
  - provide pure-function rules for the three registry decisions:
        KEEP_TIER_B / NEEDS_REVIEW / REMOVE_FROM_REGISTRY

The output of this module is a review record, not an automated
action. The registry file (`radar/sources_registry.py`) is only
edited by a human review pass that takes this record as input.

Per spec section 14: "不要为了制造变化而降级". A source whose only
problem is "today's item count is low" is NOT flagged. We only flag
sources whose underlying stability, freshness, or scope has actually
degraded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from .source_scope import ContentNature
from .models import Source


class RegistryDecision(str, Enum):
    """Per spec section 13. Not a score, not a rank. Three outcomes only."""
    KEEP_TIER_B = "KEEP_TIER_B"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REMOVE_FROM_REGISTRY = "REMOVE_FROM_REGISTRY"


class FreshnessVerdict(str, Enum):
    """Feed activity state. ACTIVE means a real article was published
    within the last 48 hours. DORMANT means no new content in 30+ days."""
    ACTIVE = "ACTIVE"      # newest item < 2 days old
    FRESH = "FRESH"        # newest item < 7 days old
    STALE = "STALE"        # newest item < 30 days old
    DORMANT = "DORMANT"    # newest item >= 30 days old
    UNKNOWN = "UNKNOWN"    # could not parse any pubDate


@dataclass
class FetchAttempt:
    """One probe of a source."""
    ok: bool
    status: int = 0
    bytes_received: int = 0
    sha12: str = ""
    parse_status: str = ""
    item_count: int = 0
    elapsed_ms: int = 0
    error: str = ""


@dataclass
class SourceProbe:
    """A complete probe of one source: N consecutive fetches."""
    source_name: str
    url: str
    fetches: List[FetchAttempt] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(f.ok for f in self.fetches)

    @property
    def all_sha_identical(self) -> bool:
        """True if every successful fetch returned the same SHA."""
        shas = {f.sha12 for f in self.fetches if f.ok and f.sha12}
        return len(shas) <= 1 and bool(shas)

    @property
    def parse_succeeds(self) -> bool:
        return all(f.parse_status.startswith("ok_") for f in self.fetches if f.ok)

    @property
    def item_count(self) -> int:
        """Items in a single fetch (all 3 should be equal for a stable feed)."""
        for f in self.fetches:
            if f.ok and f.item_count > 0:
                return f.item_count
        return 0

    @property
    def all_item_counts_equal(self) -> bool:
        counts = [f.item_count for f in self.fetches if f.ok]
        return len(set(counts)) <= 1 and bool(counts)


@dataclass
class ContentSample:
    """A single classified item from a source's feed."""
    title: str
    url: str
    pub_date: Optional[str]
    nature: ContentNature


@dataclass
class SourceReview:
    """The complete output of a Radar-6 review of one source."""
    source_name: str
    url: str
    probe: SourceProbe
    samples: List[ContentSample]
    content_distribution: dict  # ContentNature -> percentage
    freshness: FreshnessVerdict
    newest_age_days: Optional[int]
    median_age_days: Optional[int]
    items_with_valid_date: int
    items_total: int
    unique_title_count: int
    unique_pubdate_count: int
    distinct_url_hosts: int
    self_host_count: int
    # Cross-source same-wire detection result
    wire_origin_indicator_count: int  # titles with >=5 content-words overlap with another source
    decision: RegistryDecision
    reason: str

    @property
    def placeholder_ratio(self) -> float:
        n_placeholder = self.content_distribution.get("PLACEHOLDER", 0.0)
        return n_placeholder / 100.0

    @property
    def event_oriented_ratio(self) -> float:
        """PRESS + NEWS + REGULATORY_NOTICE share. Per Radar-5B definition."""
        return (
            self.content_distribution.get("PRESS", 0.0)
            + self.content_distribution.get("NEWS", 0.0)
            + self.content_distribution.get("REGULATORY_NOTICE", 0.0)
        ) / 100.0

    @property
    def non_news_ratio(self) -> float:
        """TENDER + HR + ADMIN_NOTICE + CORPORATE + PLACEHOLDER share."""
        return (
            self.content_distribution.get("TENDER", 0.0)
            + self.content_distribution.get("HR", 0.0)
            + self.content_distribution.get("ADMIN_NOTICE", 0.0)
            + self.content_distribution.get("CORPORATE", 0.0)
            + self.content_distribution.get("PLACEHOLDER", 0.0)
        ) / 100.0

    def to_dict(self) -> dict:
        """Stable JSON-serializable representation."""
        return {
            "source_name": self.source_name,
            "url": self.url,
            "freshness": self.freshness.value,
            "newest_age_days": self.newest_age_days,
            "median_age_days": self.median_age_days,
            "items_with_valid_date": self.items_with_valid_date,
            "items_total": self.items_total,
            "unique_title_count": self.unique_title_count,
            "unique_pubdate_count": self.unique_pubdate_count,
            "distinct_url_hosts": self.distinct_url_hosts,
            "self_host_count": self.self_host_count,
            "content_distribution": self.content_distribution,
            "placeholder_ratio": round(self.placeholder_ratio, 4),
            "event_oriented_ratio": round(self.event_oriented_ratio, 4),
            "non_news_ratio": round(self.non_news_ratio, 4),
            "wire_origin_indicator_count": self.wire_origin_indicator_count,
            "all_fetch_ok": self.probe.all_ok,
            "all_parse_ok": self.probe.parse_succeeds,
            "sha_identical_across_fetches": self.probe.all_sha_identical,
            "item_count_stable": self.probe.all_item_counts_equal,
            "decision": self.decision.value,
            "reason": self.reason,
        }


# ============================================================================
# Decision rules (per spec section 13 + section 14)
# ============================================================================

def decide_registry_decision(review: SourceReview) -> RegistryDecision:
    """Apply the three-rule decision tree.

    A source is REMOVED only when its underlying reliability has failed:
      - 1+ of 3 fetches failed (not reachable), OR
      - any fetched content was a placeholder, OR
      - all fetched items are now non-news and the feed is dormant.

    A source is NEEDS_REVIEW when the evidence is ambiguous:
      - feed is reachable + parses + is fresh, but content distribution
        has shifted (non-news > 70%) and freshness has degraded.

    Otherwise KEEP_TIER_B. Per spec section 14, do NOT flag for low item
    counts alone. Do NOT penalize a source for a single empty fetch when
    other fetches succeed.
    """
    # Hard fail: connectivity or content is fundamentally broken
    if not review.probe.all_ok:
        return RegistryDecision.REMOVE_FROM_REGISTRY, \
            f"1+ of {len(review.probe.fetches)} fetches failed (probe.all_ok={review.probe.all_ok})"

    if not review.probe.parse_succeeds:
        return RegistryDecision.REMOVE_FROM_REGISTRY, \
            "feed parse failure across all 3 fetches"

    if review.placeholder_ratio >= 0.5:
        return RegistryDecision.REMOVE_FROM_REGISTRY, \
            f"{review.placeholder_ratio*100:.1f}% of items are placeholders"

    if review.freshness == FreshnessVerdict.DORMANT:
        return RegistryDecision.REMOVE_FROM_REGISTRY, \
            f"feed is DORMANT (newest item {review.newest_age_days} days old)"

    # Soft fail: needs human review (don't auto-remove on these)
    if review.freshness == FreshnessVerdict.STALE:
        return RegistryDecision.NEEDS_REVIEW, \
            f"feed is STALE (newest item {review.newest_age_days} days old)"

    if review.non_news_ratio > 0.7 and review.freshness in (
        FreshnessVerdict.ACTIVE, FreshnessVerdict.FRESH
    ):
        # Active feed but mostly tenders / HR / corporate PR.
        # This is a "scope drift" signal but not an automatic removal.
        return RegistryDecision.NEEDS_REVIEW, \
            f"{review.non_news_ratio*100:.1f}% of items are non-news (tender/HR/admin/corporate)"

    # OK
    return RegistryDecision.KEEP_TIER_B, \
        f"stable feed ({review.probe.item_count} items/fetch, all fetch+parse OK), " \
        f"freshness={review.freshness.value}, event_oriented={review.event_oriented_ratio*100:.1f}%"


def attach_decision(review: SourceReview) -> SourceReview:
    """Compute and attach the registry decision + reason to a review."""
    decision, reason = decide_registry_decision(review)
    review.decision = decision
    review.reason = reason
    return review


# ============================================================================
# Cross-source wire-origin detection (per spec section 10)
# ============================================================================

# Common stopwords (English + Malay) for content-word extraction
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "by", "with", "is", "are", "was", "were", "be", "been", "has", "have", "had",
    "this", "that", "these", "those", "it", "its", "as", "from", "into",
    "i", "you", "he", "she", "we", "they", "them", "their", "my", "your",
    "akan", "yang", "dan", "di", "ini", "itu", "untuk", "dengan", "tidak",
    "kata", "kerana", "pada", "oleh", "malah", "juga", "sudah", "telah",
    "lebih", "kurang", "antara", "lain", "beliau", "belia", "belum",
}


def _normalize_title_words(title: str) -> set:
    """Lowercase + strip HTML + strip stopwords + strip short words."""
    import re
    t = title.lower()
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return {w for w in t.split() if w and w not in _STOPWORDS and len(w) > 2}


def count_cross_source_wire_indicators(
    all_samples_by_source: dict,
    min_overlap_words: int = 5,
) -> dict:
    """For each source, count titles whose content-word bag overlaps >=N words
    with a title from another source.

    Args:
        all_samples_by_source: {source_name: [ContentSample, ...]}
        min_overlap_words: threshold for "looks like same wire"

    Returns:
        {source_name: indicator_count}. Zero is the expected outcome for
        genuinely independent sources. A non-zero count is evidence of
        potential wire-dependence that warrants review.
    """
    # Flatten with source labels
    all_items = []
    for src, samples in all_samples_by_source.items():
        for s in samples:
            all_items.append((src, _normalize_title_words(s.title)))

    counts = {src: 0 for src in all_samples_by_source}
    for i, (src_a, words_a) in enumerate(all_items):
        for src_b, words_b in all_items[i + 1:]:
            if src_a == src_b:
                continue
            if len(words_a & words_b) >= min_overlap_words:
                counts[src_a] += 1
                counts[src_b] += 1
    return counts
