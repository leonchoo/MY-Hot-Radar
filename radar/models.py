"""
Story, Topic, Verification, Momentum, Classification data classes.

A Story is a single observed item from one source. Many Stories can map to one
Topic. Status, verification, momentum, and classification are computed on
Topic, not Story.

Field names are deliberately boring (snake_case) so the radar output JSON
is easy to inspect by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any
import uuid


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --- enums ---


class SourceType(str, Enum):
    RSS = "RSS"
    NEWS_SITE = "NEWS_SITE"
    OFFICIAL_SOURCE = "OFFICIAL_SOURCE"
    PUBLIC_SOCIAL = "PUBLIC_SOCIAL"
    SEARCH_RESULT = "SEARCH_RESULT"


class SourceTier(str, Enum):
    """Source credibility tiers. See VERIFICATION_RULES.md.

    A - Official / authoritative (govt press releases, national wire, royal,
        statutory bodies).
    B - Established outlet with documented corrections record.
    C - Secondary or niche outlet with weaker corrections history.
    D - Social primary (first-hand from a verifiable individual).
    E - Social echo / forward (shares, quotes, comments).
    F - Anonymous / unaccountable.

    Tier F is NOT admissible as evidence for any CONFIRMED claim. It may be
    used as a discovery input only.
    """
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


class Category(str, Enum):
    MALAYSIA = "MALAYSIA"
    VIRAL = "VIRAL"
    CELEBRITY = "CELEBRITY"
    FOOD = "FOOD"
    WORLD = "WORLD"
    SOCIAL = "SOCIAL"


class Status(str, Enum):
    """Radar momentum classification. See radar/classification.py."""
    BREAKING = "BREAKING"
    RISING = "RISING"
    HOT = "HOT"
    WATCH = "WATCH"
    COOLING = "COOLING"


class VerificationStatus(str, Enum):
    """See VERIFICATION_RULES.md - epistemic state of the underlying claim."""
    CONFIRMED = "CONFIRMED"
    REPORTED = "REPORTED"
    SOCIAL_BUZZ = "SOCIAL BUZZ"
    UNVERIFIED = "UNVERIFIED"
    RUMOUR = "RUMOUR"


class ConfidenceLabel(str, Enum):
    """Coarse qualitative bucket for the heuristic confidence score.

    IMPORTANT: this is NOT a probability. It is a coarse ordinal bucket for
    human inspection. See VERIFICATION_RULES.md and radar/verification.py
    for the explicit heuristic definition. The numeric `Verification.confidence`
    field is documented as heuristic and is NOT a calibrated probability.
    """
    VERY_LOW = "VERY_LOW"      # ~ 0.00..0.20  - unverified / only-Tier-F / social-only weak
    LOW = "LOW"                # ~ 0.20..0.40  - single Tier-B, Tier-C alone
    MEDIUM = "MEDIUM"          # ~ 0.40..0.60  - 2+ Tier-B independent
    HIGH = "HIGH"              # ~ 0.60..0.85  - Tier A present + multi-source
    VERY_HIGH = "VERY_HIGH"    # ~ 0.85..1.00  - Tier A + multi independent + corroboration


class CounterSignalStance(str, Enum):
    """A stance a counter-signal source can take on a topic.

    Per VERIFICATION_RULES.md: a credible counter-signal (especially from a
    Tier-A source) drops the topic at least one status rung. A confirmed
    official denial = RUMOUR.
    """
    DENIAL = "DENIAL"          # explicit "the claim is false"
    CORRECTION = "CORRECTION"  # partial correction / clarification
    CONTRADICTION = "CONTRADICTION"  # competing credible account
    DOWNPLAY = "DOWNPLAY"      # reduces importance without denying


@dataclass
class CounterSignal:
    """A documented counter-signal against a topic.

    Used by verification to demote or flag topics that an authoritative
    source has contested. The signal is keyed by the Topic it contests
    via a `topic_content_key` (Topic.content_key() of the contested topic).
    """
    topic_content_key: str
    source_name: str
    source_tier: SourceTier
    stance: CounterSignalStance
    evidence_url: str
    summary: str
    observed_at: str = field(default_factory=_utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source_tier"] = self.source_tier.value
        d["stance"] = self.stance.value
        return d


class Language(str, Enum):
    EN = "en"
    ZH = "zh"
    MS = "ms"


# --- dataclasses ---


@dataclass
class Source:
    name: str
    type: SourceType
    url: str
    reliability: int                       # 1..5
    country: str = "MY"
    languages: List[Language] = field(default_factory=lambda: [Language.EN])
    tier: SourceTier = SourceTier.C        # credibility tier per VERIFICATION_RULES.md
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["tier"] = self.tier.value
        d["languages"] = [l.value for l in self.languages]
        return d


@dataclass
class Story:
    """One observed item from one source about one underlying thing.
    Many Stories describe the same Topic."""
    id: str = field(default_factory=lambda: _new_id("s"))
    title: str = ""
    summary: str = ""
    url: str = ""
    source: str = ""
    source_type: SourceType = SourceType.NEWS_SITE
    published_at: Optional[str] = None         # ISO8601 UTC, best-effort
    discovered_at: str = field(default_factory=_utcnow_iso)
    category: Category = Category.MALAYSIA
    language: Language = Language.EN
    country: str = "MY"

    # signals for dedup (filled by normalize stage)
    normalized_title: str = ""
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        d["category"] = self.category.value
        d["language"] = self.language.value
        return d


@dataclass
class Verification:
    """Reasoned state for a Topic. Always carries evidence, never just a label.

    IMPORTANT on `confidence`: this is a HEURISTIC value, not a calibrated
    probability. The docstring at the top of radar/verification.py explains
    exactly how it's computed. Use `confidence_label` for a coarse bucket.
    """
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    independent_sources: int = 0        # = distinct canonical origins
    raw_source_count: int = 0           # = sum of stories per origin (pre-independence)
    source_types: List[SourceType] = field(default_factory=list)
    confidence: float = 0.0             # HEURISTIC, 0..1, NOT a probability
    confidence_label: ConfidenceLabel = ConfidenceLabel.VERY_LOW
    evidence_urls: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    counter_signals: List[Dict[str, Any]] = field(default_factory=list)  # serialized CounterSignals

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["source_types"] = [s.value for s in self.source_types]
        d["confidence_label"] = self.confidence_label.value
        return d


@dataclass
class Momentum:
    current_mentions: int = 0
    previous_mentions: int = 0
    growth: int = 0                    # current - previous
    growth_rate: Optional[float] = None  # % change; None when previous == 0
    is_new: bool = False               # True when previous == 0 and current > 0
    window_label: str = "vs previous scan"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Topic:
    """Cluster of Stories that describe the same underlying event."""
    id: str = field(default_factory=lambda: _new_id("t"))
    title: str = ""
    summary: str = ""
    category: Category = Category.MALAYSIA
    language: Language = Language.EN

    story_ids: List[str] = field(default_factory=list)
    related_urls: List[str] = field(default_factory=list)
    canonical_url: str = ""             # stable content-keyed identifier; first
                                         # related_url after canonicalization. Used
                                         # by history/momentum to match topics
                                         # across consecutive scans.

    first_seen: str = field(default_factory=_utcnow_iso)
    last_seen: str = field(default_factory=_utcnow_iso)

    mention_count: int = 0
    statuses_seen: List[SourceType] = field(default_factory=list)

    verification: Verification = field(default_factory=Verification)
    momentum: Momentum = field(default_factory=Momentum)
    status: Status = Status.WATCH      # set by classification stage

    # explainability: why this topic got the status it got
    classification_reasons: List[str] = field(default_factory=list)

    def content_key(self) -> str:
        """Stable content-derived identifier for cross-scan matching.

        Prefer canonical_url; fall back to normalized title. Random
        ids are NOT used here because they change every scan.
        """
        if self.canonical_url:
            return f"u:{self.canonical_url}"
        if self.title:
            return f"t:{self.title.strip().lower()}"
        return f"i:{self.id}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["language"] = self.language.value
        d["status"] = self.status.value
        d["verification"] = self.verification.to_dict()
        d["momentum"] = self.momentum.to_dict()
        d["statuses_seen"] = [s.value for s in self.statuses_seen]
        return d
