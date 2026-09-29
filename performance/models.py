"""
Data models for Performance Intelligence.

All models are frozen dataclass-shaped objects. They have
to_dict() / from_dict() helpers for JSON serialization, and
a dedicated validate() function (in models_validate.py).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from .enums import (
    InsightScope,
    Platform,
    SourceType,
)


# ============================================================================
# ContentIdentity
# ============================================================================

@dataclass
class ContentIdentity:
    """A piece of content under observation (own or market)."""
    content_id: str
    source_type: SourceType
    publisher: str
    platform: Platform
    url: str
    title: str
    category: str
    topic_type: str
    language: str
    published_at: str  # ISO 8601 (Z or offset) or RFC 2822

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        d["platform"] = self.platform.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ContentIdentity":
        return cls(
            content_id=d["content_id"],
            source_type=SourceType(d["source_type"]),
            platform=Platform(d["platform"]),
            publisher=d["publisher"],
            url=d["url"],
            title=d["title"],
            category=d["category"],
            topic_type=d["topic_type"],
            language=d["language"],
            published_at=d["published_at"],
        )


# ============================================================================
# PerformanceSnapshot
# ============================================================================

@dataclass
class PerformanceSnapshot:
    """A single point-in-time observation of public metrics.

    Each metric is either:
      * None  — unknown / not observable for this platform
      * int   — the observed public count

    The two cases are intentionally distinct: a snapshot of views=0
    is different from views=None.
    """
    content_id: str
    captured_at: str
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    reposts: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerformanceSnapshot":
        return cls(
            content_id=d["content_id"],
            captured_at=d["captured_at"],
            views=d.get("views"),
            likes=d.get("likes"),
            comments=d.get("comments"),
            shares=d.get("shares"),
            reposts=d.get("reposts"),
        )


# ============================================================================
# PerformanceObservation
# ============================================================================

@dataclass
class PerformanceObservation:
    """Change between two snapshots, plus derived velocity metrics."""
    content_id: str
    from_captured_at: str
    to_captured_at: str
    elapsed_seconds: int
    views_delta: Optional[int]
    likes_delta: Optional[int]
    comments_delta: Optional[int]
    shares_delta: Optional[int]
    views_per_hour: Optional[float]
    likes_per_hour: Optional[float]
    comments_per_hour: Optional[float]
    shares_per_hour: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerformanceObservation":
        return cls(
            content_id=d["content_id"],
            from_captured_at=d["from_captured_at"],
            to_captured_at=d["to_captured_at"],
            elapsed_seconds=d["elapsed_seconds"],
            views_delta=d.get("views_delta"),
            likes_delta=d.get("likes_delta"),
            comments_delta=d.get("comments_delta"),
            shares_delta=d.get("shares_delta"),
            views_per_hour=d.get("views_per_hour"),
            likes_per_hour=d.get("likes_per_hour"),
            comments_per_hour=d.get("comments_per_hour"),
            shares_per_hour=d.get("shares_per_hour"),
        )


# ============================================================================
# ContentFeatureSnapshot
# ============================================================================

@dataclass
class ContentFeatureSnapshot:
    """Stored features of a content item, frozen at observation time.

    These are *characteristics*, not *judgements*. They never reach
    back into the Radar to modify it.
    """
    content_id: str
    captured_at: str
    # Topic
    category: str
    topic_type: str
    local_relevance: str  # "LOCAL" | "NATIONAL" | "REGIONAL" | "GLOBAL"
    geographic_scope: str
    # Headline
    headline_length: int
    has_person_name: bool
    has_location: bool
    has_number: bool
    has_question: bool
    has_quote: bool
    has_time_reference: bool
    has_exclamation: bool
    headline_style: str  # "INFORMATIVE" | "QUESTION" | "EXCLAMATORY" | "QUOTE"
    # Publication
    published_at: str
    publication_hour: int  # 0..23 UTC
    publication_weekday: int  # 0=Mon..6=Sun
    # Radar context (only if content came from MY Hot Radar Radar)
    radar_status: Optional[str] = None
    radar_verification_status: Optional[str] = None
    radar_confidence_label: Optional[str] = None
    radar_momentum: Optional[float] = None
    radar_source_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# MarketObservation
# ============================================================================

@dataclass
class MarketObservation:
    """A competitor / market content observation.

    P1 only defines the schema. The collector (future P2) is
    responsible for populating this.
    """
    observation_id: str
    publisher: str
    platform: Platform
    content_url: str
    title: str
    published_at: str
    captured_at: str
    category: str
    topic_type: str
    metrics: Dict[str, Optional[int]]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["platform"] = self.platform.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MarketObservation":
        return cls(
            observation_id=d["observation_id"],
            publisher=d["publisher"],
            platform=Platform(d["platform"]),
            content_url=d["content_url"],
            title=d["title"],
            published_at=d["published_at"],
            captured_at=d["captured_at"],
            category=d["category"],
            topic_type=d["topic_type"],
            metrics=d.get("metrics", {}),
        )


# ============================================================================
# Insight
# ============================================================================

@dataclass
class Insight:
    """A derived finding (future P3).

    P1 only defines the schema. P1 MUST NOT produce real Insights from
    fake / synthetic data — the storage layer rejects insights that
    carry the synthetic flag.
    """
    insight_id: str
    generated_at: str
    scope: InsightScope
    observation_window: Dict[str, str]  # {"from": iso, "to": iso}
    sample_size: int
    finding: str
    evidence: List[str]
    limitations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["scope"] = self.scope.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Insight":
        return cls(
            insight_id=d["insight_id"],
            generated_at=d["generated_at"],
            scope=InsightScope(d["scope"]),
            observation_window=d["observation_window"],
            sample_size=d["sample_size"],
            finding=d["finding"],
            evidence=d.get("evidence", []),
            limitations=d.get("limitations", []),
        )
