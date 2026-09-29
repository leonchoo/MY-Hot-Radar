"""
Article Candidate Pipeline — Phase 2 Batch 3B-2.

Important principle (per spec §4):

    publishable ≠ article-ready ≠ published

This module introduces an INDEPENDENT Article Candidate layer above
the Radar output. A topic being ``publishable`` (Radar's gating)
does NOT make it ``article_ready``. This module evaluates whether a
publishable topic deserves to enter the future article-review
pipeline, using a separate set of rules.

States (spec §5):
    CANDIDATE          - meets basic eligibility; in the pool
    BLOCKED            - blocked by an explicit rule
    READY_FOR_REVIEW   - data complete, sources verified, ready for
                         future human/rule review (NOT yet approved
                         and NOT yet published)

The Candidate layer:
  - Does NOT modify Radar engine files.
  - Does NOT generate article bodies.
  - Does NOT publish to website, Facebook, or any channel.
  - Does NOT execute git operations.
  - Reads Radar output and produces structured candidate records.

Candidate persistence (spec §12):

    radar_data/candidates/
        latest.json
        YYYY-MM-DD/
            <candidate_id>.json

All candidate data stays under /radar_data/ which is gitignored
(see .gitignore). NO candidate file is committed to Git.

Candidate identity (spec §10-11):

    candidate_id is deterministic: stable hash of (content_key +
    schema_version). Same Radar topic -> same candidate_id across
    all scans. Updated scans DO NOT create duplicates; they update
    the existing candidate's verification / momentum / sources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .public_output import is_safe_url


# ============================================================================
# Constants
# ============================================================================

CANDIDATE_SCHEMA_VERSION = 1

# Default freshness: a topic whose last_seen is older than this is
# considered stale and NOT eligible for a fresh candidate.
# Conservative default; configurable per-call.
DEFAULT_FRESHNESS_HOURS = 48

# Conservative cap on how many candidates we track per scan. The
# runtime typically emits ~90 publishable topics; we don't need to
# candidate ALL of them. Editorial decision: cap at 50 most-recent.
MAX_CANDIDATES_PER_SCAN = 50

# Default paths.
DEFAULT_INTERNAL_OUTPUT = Path("radar_data/output/latest.json")
DEFAULT_CANDIDATE_DIR = Path("radar_data/candidates")


# ============================================================================
# States & reasons
# ============================================================================

class CandidateState(str, Enum):
    """Three states per spec §5."""
    CANDIDATE = "CANDIDATE"
    BLOCKED = "BLOCKED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"


class BlockingReason(str, Enum):
    """Explicit machine-stable reasons a candidate is blocked.

    Per spec §21: these are enum values, not free-form strings.
    """
    MISSING_TITLE = "missing_title"
    MISSING_SOURCE = "missing_source"
    INVALID_SOURCE_URL = "invalid_source_url"
    UNVERIFIED = "unverified"
    RUMOUR = "rumour"
    SOCIAL_BUZZ_ONLY = "social_buzz_only"
    TIER_F_ONLY = "tier_f_only"
    POLITICAL_NON_NEUTRAL = "political_non_neutral"
    TIER_A_DENIAL = "tier_a_denial"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    INVALID_TOPIC = "invalid_topic"
    STALE = "stale_topic"
    LOW_CONFIDENCE = "low_confidence"  # only used in stricter modes
    NOT_PUBLISHABLE = "not_publishable"  # publishable=False at Radar layer


class EligibilityReason(str, Enum):
    """Positive reasons a candidate passes eligibility."""
    PUBLISHABLE = "publishable"
    VALID_TITLE = "valid_title"
    VALID_SOURCE = "valid_source"
    VALID_SOURCE_URL = "valid_source_url"
    NOT_RUMOUR = "not_rumour"
    NOT_UNVERIFIED = "not_unverified"
    HAS_INDEPENDENT_SOURCES = "has_independent_sources"
    NO_BLOCKING_COUNTER_SIGNAL = "no_blocking_counter_signal"
    POLITICALLY_NEUTRAL = "politically_neutral"
    REPORTED_OR_CONFIRMED = "reported_or_confirmed"
    CONFIRMED_EVIDENCE = "confirmed_evidence"
    NOT_OPINION = "not_opinion"


# ============================================================================
# URL safety (mirror radar.public_output.is_safe_url)
# ============================================================================

def _is_safe_url(url: str) -> bool:
    """Mirror of radar.public_output.is_safe_url.

    Same algorithm. Kept as a thin wrapper so this module does NOT
    depend on radar.public_output's broader namespace.
    """
    return is_safe_url(url)


def has_dangerous_scheme(url: str) -> bool:
    """Return True iff url starts with a known dangerous scheme.

    Used in test isolation. Does NOT use .lower() / strip() — strict.
    """
    if not isinstance(url, str) or not url:
        return False
    lower = url.lower()
    for scheme in ("javascript:", "data:", "file:", "vbscript:",
                    "blob:", "ftp:"):
        if lower.startswith(scheme):
            return True
    return False


# ============================================================================
# Candidate model
# ============================================================================

@dataclass
class CandidateSource:
    """One source-evidence row on a candidate.

    Persisted verbatim from the Radar topic's source evidence.
    No field is fabricated; if the Radar output has empty URL or
    missing title, the candidate reflects that.
    """
    source_name: str
    source_tier: str       # A / B / C / D / E / F
    source_type: str
    country: Optional[str]
    url: str
    title: str
    published_at: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CandidateEligibility:
    """Audit record of why a candidate is or is not eligible.

    Per spec §20: machine-stable enums, not free-form prose.
    """
    eligible: bool
    reasons: List[str] = field(default_factory=list)        # positive reasons
    blocking_reasons: List[str] = field(default_factory=list)  # blocking reasons

    def to_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "reasons": list(self.reasons),
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass
class ArticleCandidate:
    """A Radar topic that has been evaluated for article-readiness.

    IMPORTANT: this is a CANDIDATE, not an article. It does NOT carry
    a body, byline, slug, SEO metadata, hero image, or anything
    that would imply "this is real published content". It is a
    structured record of Radar evidence + the eligibility decision.
    """
    schema_version: int
    candidate_id: str
    content_key: str
    state: str
    created_at: str
    updated_at: str
    headline: str
    headline_origin: str = "RADAR_TOPIC"  # always RADAR_TOPIC in v1
    category: str = ""
    language: str = ""
    radar_status: str = "WATCH"
    verification_status: str = "REPORTED"
    confidence_label: str = "MEDIUM"
    source_count: int = 0
    sources: List[CandidateSource] = field(default_factory=list)
    claim_kind: str = "NOT_POLITICAL"
    is_political: bool = False
    political_neutral: bool = True
    first_seen: str = ""
    last_seen: str = ""
    mention_count: int = 0
    momentum: dict = field(default_factory=dict)
    counter_signals: list = field(default_factory=list)  # serialized list
    eligibility: CandidateEligibility = field(
        default_factory=lambda: CandidateEligibility(eligible=False)
    )

    def to_dict(self) -> dict:
        d = {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "content_key": self.content_key,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "headline": self.headline,
            "headline_origin": self.headline_origin,
            "category": self.category,
            "language": self.language,
            "radar_status": self.radar_status,
            "verification_status": self.verification_status,
            "confidence_label": self.confidence_label,
            "source_count": self.source_count,
            "sources": [s.to_dict() for s in self.sources],
            "claim_kind": self.claim_kind,
            "is_political": self.is_political,
            "political_neutral": self.political_neutral,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "mention_count": self.mention_count,
            "momentum": dict(self.momentum),
            "counter_signals": list(self.counter_signals),
            "eligibility": self.eligibility.to_dict(),
        }
        return d


# ============================================================================
# Candidate ID (spec §10)
# ============================================================================

def make_candidate_id(content_key: str, schema_version: int = CANDIDATE_SCHEMA_VERSION) -> str:
    """Return a deterministic candidate_id.

    Same content_key + same schema_version -> same candidate_id.
    """
    if not content_key:
        raise ValueError("content_key must be non-empty")
    payload = f"{schema_version}|{content_key}".encode("utf-8")
    h = hashlib.sha256(payload).hexdigest()
    return f"cand_{h[:24]}"


# ============================================================================
# Time helpers
# ============================================================================

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(iso: str) -> Optional[datetime]:
    """Parse an ISO8601 string with trailing 'Z'. Returns None on failure."""
    if not iso or not isinstance(iso, str):
        return None
    try:
        s = iso.rstrip("Z")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _parse_rfc2822(s: str) -> Optional[datetime]:
    """Parse RFC 2822 (e.g. 'Mon, 28 Sep 2026 18:37:15 GMT').

    Returns None on failure. The current Radar engine emits RFC 2822
    timestamps in source-evidence published_at fields. We accept both
    ISO and RFC 2822 so the candidate layer does not care which the
    upstream emits.
    """
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    # Try the standard email.utils parser first.
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError, ImportError):
        return None


def _parse_any_timestamp(s: str) -> Optional[datetime]:
    """Parse a timestamp in either ISO 8601 or RFC 2822."""
    dt = _parse_iso(s)
    if dt is not None:
        return dt
    return _parse_rfc2822(s)


def _is_stale(timestamp_iso: str, *, freshness_hours: int) -> bool:
    """Return True iff timestamp is older than freshness_hours, or unparseable.

    Per spec §23: configurable, testable. Conservative: unparseable
    timestamps are treated as stale (we don't pretend an old or
    malformed timestamp means fresh content).
    """
    dt = _parse_any_timestamp(timestamp_iso)
    if dt is None:
        return True
    age = datetime.now(timezone.utc) - dt
    return age > timedelta(hours=freshness_hours)


# ============================================================================
# Source sanitization (per spec §16 + §35)
# ============================================================================

def _candidate_source_from_topic_source(raw: dict) -> Optional[CandidateSource]:
    """Build a CandidateSource from a Radar topic source-evidence row.

    Returns None if the row is unsafe (missing URL, dangerous scheme,
    missing name, invalid tier). The caller must DROP such rows
    silently — we do NOT keep unsafe sources on a candidate.
    """
    if not isinstance(raw, dict):
        return None
    name = (raw.get("source_name") or "")
    if not name.strip():
        return None
    tier = (raw.get("source_tier") or "")
    tier = tier.strip().upper()
    if tier not in {"A", "B", "C", "D", "E", "F"}:
        return None
    # IMPORTANT: do NOT strip() the URL before the safety check.
    # The safety check rejects URLs with leading/trailing whitespace;
    # stripping would let a malicious "   javascript:..." URL pass
    # through if the safety check used .lower()/.startswith(). We
    # use _is_safe_url directly which rejects embedded whitespace.
    url_raw = raw.get("url")
    url = url_raw if isinstance(url_raw, str) else ""
    if not _is_safe_url(url):
        return None
    stype = (raw.get("source_type") or "").strip()
    country = raw.get("country") or None
    title = raw.get("title") or ""
    # Clamp title for safety (control chars, length)
    title = "".join(ch for ch in title if 32 <= ord(ch) < 127 or ord(ch) >= 160)
    if len(title) > 500:
        title = title[:500]
    published_at = raw.get("published_at") or None

    return CandidateSource(
        source_name=name.strip(),
        source_tier=tier,
        source_type=stype,
        country=country,
        url=url,
        title=title,
        published_at=published_at,
    )


def _sanitize_title(raw: str, max_len: int = 400) -> str:
    """Make a Radar title safe for persistence.

    Strips control characters and clamps length. Does NOT change
    the headline's semantic content (per spec §15: headline = topic.title;
    we do not auto-rewrite).
    """
    if not raw:
        return ""
    # Keep printable + extended unicode; drop control chars
    cleaned = "".join(
        ch for ch in raw if (32 <= ord(ch) < 127) or (160 <= ord(ch) < 0x10000)
    )
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


# ============================================================================
# Eligibility evaluation (spec §6 + §7)
# ============================================================================

def _has_blocking_tier_a_denial(counter_signals: list) -> bool:
    """True iff any counter-signal has source_tier A and stance DENIAL/CORRECTION."""
    for sig in counter_signals or []:
        if not isinstance(sig, dict):
            continue
        tier = (sig.get("source_tier") or "").upper()
        stance = (sig.get("stance") or "").upper()
        if tier == "A" and stance in {"DENIAL", "CORRECTION"}:
            return True
    return False


def _all_sources_tier_f(sources: List[CandidateSource]) -> bool:
    """True iff there is at least one source AND all are Tier-F."""
    if not sources:
        return False
    return all(s.source_tier == "F" for s in sources)


def evaluate_eligibility(
    topic_output: dict,
    *,
    freshness_hours: int = DEFAULT_FRESHNESS_HOURS,
    existing_candidate_ids: Optional[set] = None,
) -> Tuple[bool, List[str], List[str]]:
    """Evaluate whether a Radar topic should become a Candidate.

    Returns (eligible, reasons, blocking_reasons).

    Per spec §7:
      Auto-eligible when:
        - publishable=True
        - valid title
        - >=1 valid source
        - >=1 valid source URL
        - not RUMOUR
        - not UNVERIFIED
        - no blocking Tier-A counter-signal
        - politically neutral OR non-political
        - not stale

      Auto-blocked on:
        - RUMOUR / UNVERIFIED / SOCIAL_BUZZ-only
        - missing source / URL
        - missing title
        - political non-neutral (OPINION)
        - Tier-A denial
        - Tier-F only (insufficient independent)
        - stale
        - not publishable (Radar-layer gate)

    NOTE on LOW confidence: per spec §21, low confidence is NOT a
    default blocker. The Radar publishability layer already handles
    confidence adequacy. We do not re-block on it.

    NOTE on REPORTED: per spec §7, REPORTED + publishable=True is
    allowed to become CANDIDATE. We do NOT silently convert to
    CONFIRMED.
    """
    existing_candidate_ids = existing_candidate_ids or set()

    content_key = topic_output.get("content_key") or ""
    blocking: List[str] = []
    positive: List[str] = []

    if not content_key:
        blocking.append(BlockingReason.INVALID_TOPIC.value)
        return False, [], blocking

    # 1. Radar-layer gate: publishable must be True.
    if not topic_output.get("publishable"):
        blocking.append(BlockingReason.NOT_PUBLISHABLE.value)
        return False, [], blocking
    positive.append(EligibilityReason.PUBLISHABLE.value)

    # 2. Title validity.
    title_raw = topic_output.get("title") or ""
    title_clean = _sanitize_title(title_raw)
    if not title_clean.strip():
        blocking.append(BlockingReason.MISSING_TITLE.value)
    else:
        positive.append(EligibilityReason.VALID_TITLE.value)

    # 3. Sources.
    raw_sources = topic_output.get("sources") or []
    cand_sources: List[CandidateSource] = []
    if not isinstance(raw_sources, list) or len(raw_sources) == 0:
        blocking.append(BlockingReason.MISSING_SOURCE.value)
    else:
        for rs in raw_sources:
            cs = _candidate_source_from_topic_source(rs)
            if cs is not None:
                cand_sources.append(cs)
        if not cand_sources:
            blocking.append(BlockingReason.MISSING_SOURCE.value)
            blocking.append(BlockingReason.INVALID_SOURCE_URL.value)
        else:
            positive.append(EligibilityReason.VALID_SOURCE.value)
            # All sources have at least one valid URL (sanity, given
            # _candidate_source_from_topic_source requires it).
            positive.append(EligibilityReason.VALID_SOURCE_URL.value)

    # 4. Verification status.
    vs = (topic_output.get("verification_status") or "").upper()
    if vs == "RUMOUR":
        blocking.append(BlockingReason.RUMOUR.value)
    elif vs == "UNVERIFIED":
        blocking.append(BlockingReason.UNVERIFIED.value)
    elif vs == "SOCIAL_BUZZ" or vs == "SOCIAL BUZZ":
        blocking.append(BlockingReason.SOCIAL_BUZZ_ONLY.value)
    else:
        positive.append(EligibilityReason.NOT_RUMOUR.value)
        positive.append(EligibilityReason.NOT_UNVERIFIED.value)
        if vs == "CONFIRMED":
            positive.append(EligibilityReason.CONFIRMED_EVIDENCE.value)
        elif vs == "REPORTED":
            positive.append(EligibilityReason.REPORTED_OR_CONFIRMED.value)

    # 5. Counter-signals (Tier-A denial override).
    if _has_blocking_tier_a_denial(topic_output.get("counter_signals") or []):
        blocking.append(BlockingReason.TIER_A_DENIAL.value)
    else:
        positive.append(EligibilityReason.NO_BLOCKING_COUNTER_SIGNAL.value)

    # 6. Political neutrality.
    is_political = bool(topic_output.get("is_political"))
    political_neutral = bool(topic_output.get("political_neutral"))
    if is_political and not political_neutral:
        # Per spec §18: political OPINION is blocked by default.
        blocking.append(BlockingReason.POLITICAL_NON_NEUTRAL.value)
    else:
        positive.append(EligibilityReason.POLITICALLY_NEUTRAL.value)

    # 7. Tier-F-only check (independent sources).
    if cand_sources and _all_sources_tier_f(cand_sources):
        blocking.append(BlockingReason.TIER_F_ONLY.value)
    elif cand_sources:
        positive.append(EligibilityReason.HAS_INDEPENDENT_SOURCES.value)

    # 8. Claim kind: OPINION blocked when politically non-neutral.
    claim_kind = (topic_output.get("claim_kind") or "").upper()
    if claim_kind == "OPINION":
        blocking.append(BlockingReason.POLITICAL_NON_NEUTRAL.value)
    else:
        positive.append(EligibilityReason.NOT_OPINION.value)

    # 9. Staleness (spec §23).
    last_seen = topic_output.get("last_seen") or topic_output.get("first_seen") or ""
    if _is_stale(last_seen, freshness_hours=freshness_hours):
        blocking.append(BlockingReason.STALE.value)

    # 10. Candidate dedup (spec §11). The caller passes the set of
    # already-existing candidate IDs from the same candidate_id-
    # domain. We DON'T check here — that's an artifact-level concern.
    # The pipeline uses CandidateStore to detect duplicates. This
    # function only handles per-topic eligibility.

    eligible = not blocking
    return eligible, positive, blocking


# ============================================================================
# Candidate construction (spec §9)
# ============================================================================

def build_candidate_from_topic(
    topic_output: dict,
    *,
    freshness_hours: int = DEFAULT_FRESHNESS_HOURS,
    existing_candidate_ids: Optional[set] = None,
    now_iso: Optional[str] = None,
    existing_created_at: Optional[str] = None,
) -> Tuple[ArticleCandidate, bool]:
    """Build an ArticleCandidate from a Radar topic_output dict.

    Returns (candidate, is_new) where is_new is True if the
    candidate has no prior record (caller should call
    ``created_at = now``), False if it's an update (preserve
    created_at, refresh updated_at).

    Per spec §11: same content_key -> same candidate_id. Caller is
    responsible for looking up the existing record and passing
    ``existing_created_at`` (and not incrementing created_at).
    """
    now = now_iso or _utcnow_iso()
    content_key = topic_output.get("content_key") or ""
    cand_id = make_candidate_id(content_key)

    eligible, reasons, blocking = evaluate_eligibility(
        topic_output,
        freshness_hours=freshness_hours,
        existing_candidate_ids=existing_candidate_ids,
    )

    # Build sanitized source list.
    cand_sources: List[CandidateSource] = []
    for rs in (topic_output.get("sources") or []):
        cs = _candidate_source_from_topic_source(rs)
        if cs is not None:
            cand_sources.append(cs)

    # State decision.
    if not eligible:
        state = CandidateState.BLOCKED.value
    elif cand_sources and topic_output.get("title"):
        # Eligible + sources + title = READY_FOR_REVIEW.
        # Per spec §22: this means "data complete, ready for
        # future review". It does NOT mean "approved for
        # publishing".
        state = CandidateState.READY_FOR_REVIEW.value
    else:
        state = CandidateState.CANDIDATE.value

    # is_new: caller passes existing_created_at if this is an update.
    is_new = existing_created_at is None
    created_at = existing_created_at if existing_created_at else now

    candidate = ArticleCandidate(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        candidate_id=cand_id,
        content_key=content_key,
        state=state,
        created_at=created_at,
        updated_at=now,
        headline=_sanitize_title(topic_output.get("title") or ""),
        headline_origin="RADAR_TOPIC",
        category=(topic_output.get("category") or "").strip(),
        language=(topic_output.get("language") or "").strip(),
        radar_status=(topic_output.get("status") or "WATCH").strip(),
        verification_status=(topic_output.get("verification_status") or "REPORTED").strip(),
        confidence_label=(topic_output.get("confidence_label") or "MEDIUM").strip(),
        source_count=len(cand_sources),
        sources=cand_sources,
        claim_kind=(topic_output.get("claim_kind") or "NOT_POLITICAL").strip(),
        is_political=bool(topic_output.get("is_political")),
        political_neutral=bool(topic_output.get("political_neutral", True)),
        first_seen=(topic_output.get("first_seen") or "").strip(),
        last_seen=(topic_output.get("last_seen") or "").strip(),
        mention_count=int(topic_output.get("mention_count") or 0),
        momentum=dict(topic_output.get("momentum") or {}),
        counter_signals=list(topic_output.get("counter_signals") or []),
        eligibility=CandidateEligibility(
            eligible=eligible,
            reasons=reasons,
            blocking_reasons=blocking,
        ),
    )
    return candidate, is_new


# ============================================================================
# Validation (spec §31)
# ============================================================================

_VALID_RADAR_STATUS = {"BREAKING", "RISING", "HOT", "WATCH", "COOLING"}
_VALID_VERIFICATION = {"CONFIRMED", "REPORTED", "SOCIAL_BUZZ", "SOCIAL BUZZ",
                        "UNVERIFIED", "RUMOUR"}
_VALID_CLAIM_KINDS = {"EVENT", "CLAIM", "OPINION", "NOT_POLITICAL"}
_VALID_TIERS = {"A", "B", "C", "D", "E", "F"}
_VALID_STATES = {s.value for s in CandidateState}


def validate_candidate(c: dict) -> List[str]:
    """Return a list of error strings. Empty list = valid.

    Per spec §31.
    """
    errs: List[str] = []
    if not isinstance(c, dict):
        return ["candidate is not a dict"]

    if c.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        errs.append(f"schema_version must be {CANDIDATE_SCHEMA_VERSION}")

    for k in ("candidate_id", "content_key", "state", "created_at",
              "updated_at", "headline", "category", "verification_status",
              "confidence_label", "eligibility"):
        if k not in c:
            errs.append(f"missing key: {k}")

    cid = c.get("candidate_id")
    if not isinstance(cid, str) or not cid:
        errs.append("candidate_id must be a non-empty string")

    ck = c.get("content_key")
    if not isinstance(ck, str) or not ck:
        errs.append("content_key must be a non-empty string")

    state = c.get("state")
    if state not in _VALID_STATES:
        errs.append(f"invalid state: {state!r}")

    if not isinstance(c.get("created_at"), str) or not c.get("created_at"):
        errs.append("created_at must be a non-empty string")
    if not isinstance(c.get("updated_at"), str) or not c.get("updated_at"):
        errs.append("updated_at must be a non-empty string")

    headline = c.get("headline") or ""
    if not isinstance(headline, str) or not headline.strip():
        errs.append("headline must be a non-empty string")

    rs = c.get("radar_status")
    if rs is not None and rs not in _VALID_RADAR_STATUS:
        errs.append(f"invalid radar_status: {rs!r}")

    vs = c.get("verification_status")
    if vs is not None and vs not in _VALID_VERIFICATION:
        errs.append(f"invalid verification_status: {vs!r}")

    cl = c.get("confidence_label")
    if cl is not None and cl not in {"VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"}:
        errs.append(f"invalid confidence_label: {cl!r}")

    ck_kind = c.get("claim_kind")
    if ck_kind is not None and ck_kind not in _VALID_CLAIM_KINDS:
        errs.append(f"invalid claim_kind: {ck_kind!r}")

    sources = c.get("sources")
    if not isinstance(sources, list):
        errs.append("sources must be a list")
    elif not sources:
        errs.append("sources must be non-empty")
    else:
        for i, s in enumerate(sources):
            prefix = f"sources[{i}]"
            if not isinstance(s, dict):
                errs.append(f"{prefix}: not a dict")
                continue
            if not s.get("source_name"):
                errs.append(f"{prefix}: missing source_name")
            if s.get("source_tier") not in _VALID_TIERS:
                errs.append(f"{prefix}: invalid source_tier")
            if not _is_safe_url(s.get("url", "")):
                errs.append(f"{prefix}: unsafe url")

    eligibility = c.get("eligibility")
    if not isinstance(eligibility, dict):
        errs.append("eligibility must be a dict")
    else:
        if not isinstance(eligibility.get("eligible"), bool):
            errs.append("eligibility.eligible must be a boolean")
        if not isinstance(eligibility.get("reasons"), list):
            errs.append("eligibility.reasons must be a list")
        if not isinstance(eligibility.get("blocking_reasons"), list):
            errs.append("eligibility.blocking_reasons must be a list")
        # Consistency: eligible=True with blocking_reasons is wrong.
        if (eligibility.get("eligible") is True
                and eligibility.get("blocking_reasons")):
            errs.append(
                "eligibility.eligible=True but blocking_reasons present"
            )

    # Political consistency: political_neutral=False implies
    # claim_kind=OPINION (the only non-neutral kind in v1).
    if c.get("is_political") and not c.get("political_neutral"):
        if c.get("claim_kind") != "OPINION":
            errs.append(
                "political_neutral=False requires claim_kind=OPINION"
            )

    # State consistency: BLOCKED iff eligibility.eligible=False.
    if state == "BLOCKED":
        if isinstance(eligibility, dict) and eligibility.get("eligible") is True:
            errs.append("state=BLOCKED but eligibility.eligible=True")

    # State consistency: READY_FOR_REVIEW implies eligible=True.
    if state == "READY_FOR_REVIEW":
        if isinstance(eligibility, dict) and eligibility.get("eligible") is False:
            errs.append("state=READY_FOR_REVIEW but eligibility.eligible=False")

    # JSON serializability.
    try:
        json.dumps(c, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        errs.append(f"not JSON-serializable: {e}")

    return errs


# ============================================================================
# Persistence (spec §12 + §30)
# ============================================================================

def _atomic_write_json(target: Path, payload: dict) -> None:
    """Atomic JSON write: temp + flush + fsync + os.replace.

    On failure, previous target file is unchanged.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            try:
                f.flush()
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass
        os.replace(tmp_str, target)
    except Exception:
        try:
            os.unlink(tmp_str)
        except OSError:
            pass
        raise


class CandidateStore:
    """Persistent store of Article Candidates on disk.

    Layout (per spec §12):

        radar_data/candidates/
            latest.json          # current snapshot
            YYYY-MM-DD/
                <candidate_id>.json  # per-candidate persistent file

    Behavior:
        - add_or_update() is idempotent on (content_key): the same
          content_key produces the same candidate_id and updates the
          existing record (preserving created_at, refreshing updated_at).
        - On any write failure, the previous on-disk state is preserved.
        - Atomic write via temp + os.replace.
        - read_all() returns the full list of currently-persisted
          candidates.
        - latest.json is rebuilt from the on-disk per-candidate files
          on each persist cycle.
    """

    def __init__(self, candidate_dir: Path = DEFAULT_CANDIDATE_DIR):
        self.candidate_dir = Path(candidate_dir)
        self.daily_dir = self.candidate_dir / "by_day"
        self.latest_path = self.candidate_dir / "latest.json"

    def ensure_dirs(self) -> None:
        self.candidate_dir.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)

    def _candidate_file(self, candidate_id: str) -> Path:
        # File names are sanitized to ASCII-ish path-safe form.
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", candidate_id):
            raise ValueError(f"unsafe candidate_id for filesystem: {candidate_id!r}")
        return self.daily_dir / f"{candidate_id}.json"

    def read_all(self) -> List[dict]:
        """Read all currently-persisted candidates.

        Reads the per-candidate files (NOT latest.json). Skips files
        that fail to parse so a single corrupt file does not lose
        the whole store.
        """
        if not self.daily_dir.exists():
            return []
        out: List[dict] = []
        for p in sorted(self.daily_dir.glob("*.json")):
            try:
                raw = p.read_text(encoding="utf-8")
                obj = json.loads(raw)
                if isinstance(obj, dict) and "candidate_id" in obj:
                    out.append(obj)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
        return out

    def get(self, candidate_id: str) -> Optional[dict]:
        """Read a single candidate by id, or None if absent."""
        path = self._candidate_file(candidate_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def get_existing_candidate_ids(self) -> set:
        return {c["candidate_id"] for c in self.read_all()
                if isinstance(c, dict) and "candidate_id" in c}

    def get_existing_created_at_by_id(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for c in self.read_all():
            if isinstance(c, dict) and "candidate_id" in c and "created_at" in c:
                out[c["candidate_id"]] = c["created_at"]
        return out

    def upsert(self, candidate_dict: dict) -> None:
        """Atomically write (insert or replace) a candidate.

        Validates first; raises OutputValidationError on failure.
        On any I/O failure, the previous file is preserved.
        """
        errs = validate_candidate(candidate_dict)
        if errs:
            raise OutputValidationError(
                "candidate failed validation: "
                + "; ".join(errs[:5])
                + (f" (+{len(errs)-5} more)" if len(errs) > 5 else "")
            )
        cid = candidate_dict["candidate_id"]
        path = self._candidate_file(cid)
        # Backup existing content so we can restore on failure.
        prev_text: Optional[str] = None
        if path.exists():
            try:
                prev_text = path.read_text(encoding="utf-8")
            except OSError:
                pass
        try:
            _atomic_write_json(path, candidate_dict)
        except Exception:
            # Try to restore previous content if we got partial write.
            if prev_text is not None:
                try:
                    path.write_text(prev_text, encoding="utf-8")
                except OSError:
                    pass
            raise

    def rebuild_latest(self) -> Path:
        """Rebuild latest.json from the per-candidate files.

        Atomic. Returns the path written.
        """
        self.ensure_dirs()
        all_cands = self.read_all()
        payload = build_latest_payload(all_cands)
        _atomic_write_json(self.latest_path, payload)
        return self.latest_path


def build_latest_payload(candidates: List[dict]) -> dict:
    """Build the latest.json content from a list of candidate dicts."""
    summary = {
        "candidate_count": len(candidates),
        "by_state": {},
        "by_verification": {},
        "by_claim_kind": {},
    }
    for c in candidates:
        st = c.get("state") or "UNKNOWN"
        summary["by_state"][st] = summary["by_state"].get(st, 0) + 1
        vs = c.get("verification_status") or "UNKNOWN"
        summary["by_verification"][vs] = summary["by_verification"].get(vs, 0) + 1
        ck = c.get("claim_kind") or "NOT_POLITICAL"
        summary["by_claim_kind"][ck] = summary["by_claim_kind"].get(ck, 0) + 1

    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "generated_at": _utcnow_iso(),
        "summary": summary,
        "candidates": candidates,
    }


# ============================================================================
# OutputValidationError
# ============================================================================

class OutputValidationError(Exception):
    """Raised when a candidate fails structural validation."""


# ============================================================================
# Pipeline (spec §5 + §11 + §23 + §25)
# ============================================================================

def run_candidate_pipeline(
    *,
    internal_output_path: Path = DEFAULT_INTERNAL_OUTPUT,
    candidate_dir: Path = DEFAULT_CANDIDATE_DIR,
    freshness_hours: int = DEFAULT_FRESHNESS_HOURS,
    max_candidates: int = MAX_CANDIDATES_PER_SCAN,
) -> Dict[str, Any]:
    """End-to-end: read internal latest.json, build candidates,
    upsert into the candidate store, rebuild latest.

    Returns a summary dict (NOT the full candidate list). Always
    returns; never raises on per-topic errors. The store is
    per-candidate atomic, so a topic failure does not corrupt
    existing records.
    """
    summary: Dict[str, Any] = {
        "topics_seen": 0,
        "candidates_built": 0,
        "candidates_updated": 0,
        "candidates_unchanged": 0,
        "candidates_blocked": 0,
        "candidates_ready": 0,
        "candidates_in_pool": 0,
        "errors": [],
    }
    if not internal_output_path.exists():
        summary["errors"].append(f"internal output not found: {internal_output_path}")
        return summary

    try:
        internal = json.loads(internal_output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        summary["errors"].append(f"could not parse internal output: {e}")
        return summary

    if not isinstance(internal, dict):
        summary["errors"].append("internal output root must be a dict")
        return summary

    topics = internal.get("topics") or []
    summary["topics_seen"] = len(topics)

    # Cap topics for this scan.
    if max_candidates > 0 and len(topics) > max_candidates:
        # Sort by last_seen descending (most recent first).
        topics = sorted(
            topics,
            key=lambda t: (t.get("last_seen") or t.get("first_seen") or ""),
            reverse=True,
        )[:max_candidates]

    store = CandidateStore(candidate_dir=candidate_dir)
    store.ensure_dirs()
    existing_created_at = store.get_existing_created_at_by_id()

    new_records: List[dict] = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        try:
            ck = topic.get("content_key") or ""
            cid = make_candidate_id(ck) if ck else None
            prev_created = existing_created_at.get(cid) if cid else None
            candidate, is_new = build_candidate_from_topic(
                topic,
                freshness_hours=freshness_hours,
                now_iso=_utcnow_iso(),
                existing_created_at=prev_created,
            )
            cd = candidate.to_dict()
            store.upsert(cd)
            new_records.append(cd)
            if is_new:
                summary["candidates_built"] += 1
            elif prev_created != cd["created_at"]:
                summary["candidates_unchanged"] += 1
            else:
                summary["candidates_updated"] += 1
            if cd["state"] == "BLOCKED":
                summary["candidates_blocked"] += 1
            elif cd["state"] == "READY_FOR_REVIEW":
                summary["candidates_ready"] += 1
            else:
                summary["candidates_in_pool"] += 1
        except OutputValidationError as e:
            summary["errors"].append(f"validation: {e}")
        except Exception as e:
            summary["errors"].append(
                f"topic={topic.get('content_key')!r}: {type(e).__name__}: {e}"
            )

    # Rebuild latest.json (atomic).
    try:
        all_now = store.read_all()
        store.rebuild_latest()
        summary["total_candidates_on_disk"] = len(all_now)
    except (OSError, ValueError) as e:
        summary["errors"].append(f"rebuild_latest: {type(e).__name__}: {e}")

    return summary


# ============================================================================
# CLI
# ============================================================================

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="radar.candidate",
        description="Article Candidate Pipeline (Phase 2 B3B-2). "
                    "Reads internal radar output and produces audit-grade "
                    "Article Candidate records. Never publishes.",
    )
    parser.add_argument(
        "--internal", type=str, default=str(DEFAULT_INTERNAL_OUTPUT),
        help="Path to internal latest.json (default: %(default)s)",
    )
    parser.add_argument(
        "--candidate-dir", type=str, default=str(DEFAULT_CANDIDATE_DIR),
        help="Path to candidate directory (default: %(default)s)",
    )
    parser.add_argument(
        "--freshness-hours", type=int, default=DEFAULT_FRESHNESS_HOURS,
        help="Max age of last_seen for a fresh candidate (default: %(default)s)",
    )
    parser.add_argument(
        "--max-candidates", type=int, default=MAX_CANDIDATES_PER_SCAN,
        help="Cap candidates processed per scan (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build + validate but do not write to disk",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Validate existing candidates on disk; do not rebuild",
    )
    args = parser.parse_args(argv)

    if args.check:
        store = CandidateStore(candidate_dir=Path(args.candidate_dir))
        all_cands = store.read_all()
        err_count = 0
        for c in all_cands:
            errs = validate_candidate(c)
            if errs:
                err_count += 1
                for e in errs[:3]:
                    print(f"  ERR candidate={c.get('candidate_id')!r}: {e}",
                          file=sys.stderr)
        print(json.dumps({
            "candidate_count": len(all_cands),
            "invalid_count": err_count,
            "valid": err_count == 0,
        }, indent=2))
        return 0 if err_count == 0 else 1

    if args.dry_run:
        internal_path = Path(args.internal)
        if not internal_path.exists():
            print(f"ERROR: internal output not found: {internal_path}",
                  file=sys.stderr)
            return 1
        try:
            internal = json.loads(internal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: could not parse {internal_path}: {e}",
                  file=sys.stderr)
            return 1
        topics = internal.get("topics") or []
        # Don't write; just compute eligibility summary.
        elig_count = 0
        block_count = 0
        for t in topics:
            if not isinstance(t, dict):
                continue
            ok, _, blocking = evaluate_eligibility(
                t, freshness_hours=args.freshness_hours,
            )
            if ok:
                elig_count += 1
            else:
                block_count += 1
        print(json.dumps({
            "dry_run": True,
            "topics": len(topics),
            "eligible": elig_count,
            "blocked": block_count,
            "freshness_hours": args.freshness_hours,
            "would_write_to": args.candidate_dir,
        }, indent=2))
        return 0

    summary = run_candidate_pipeline(
        internal_output_path=Path(args.internal),
        candidate_dir=Path(args.candidate_dir),
        freshness_hours=args.freshness_hours,
        max_candidates=args.max_candidates,
    )
    # Exit 0 = success; exit 1 = errors (caller decides what to do).
    # We do NOT raise — the candidate pipeline is best-effort, like
    # the output layer in Phase 2 B3A.
    print(json.dumps(summary, indent=2))
    return 0 if not summary.get("errors") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
