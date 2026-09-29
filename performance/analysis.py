"""
Analysis primitives for Performance Intelligence.

All functions are pure: same input -> same output, no I/O.

Key design rules (per spec):

  * null != 0. A missing metric stays None throughout the math.
  * Negative deltas are NOT silently coerced to 0; they signal data
    inconsistency and the helper returns None for that field.
  * Engagement rate is engagements / views, only when views is a
    positive int. Components are kept separately so the breakdown is
    inspectable.
  * Classification is conservative: small samples / large windows /
    missing metrics all yield INSUFFICIENT_DATA.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional

from .enums import PerformanceClass
from .models import (
    ContentFeatureSnapshot,
    PerformanceObservation,
    PerformanceSnapshot,
)
from .validation import parse_timestamp_any, utcnow, iso_utc
from .ids import observation_id_for


# ============================================================================
# Observation math
# ============================================================================

def _safe_delta(prev, curr):
    """Delta between two metric observations.

    None  if either side is None.
    None  if either side is negative.
    None  if the value is not int-shaped.

    Negative deltas (curr < prev) are NOT silently coerced to 0.
    They are a data-integrity signal: a later snapshot showing fewer
    views than an earlier one is suspicious and must be flagged, not
    hidden. Returning None forces the downstream layer to refuse to
    use the metric.
    """
    if prev is None or curr is None:
        return None
    if isinstance(prev, bool) or isinstance(curr, bool):
        return None
    if not isinstance(prev, int) or not isinstance(curr, int):
        return None
    if prev < 0 or curr < 0:
        return None
    delta = curr - prev
    if delta < 0:
        return None
    return delta


def _per_hour(delta, elapsed_seconds):
    if delta is None or elapsed_seconds <= 0:
        return None
    return delta * 3600.0 / elapsed_seconds


def compute_observation(snap_old, snap_new):
    """Compute an observation between two snapshots.

    Returns None if the two snapshots don't form a valid ordered pair
    (different content_id, non-monotonic timestamps, or unparseable
    timestamps).
    """
    if snap_old.content_id != snap_new.content_id:
        return None
    t_old = parse_timestamp_any(snap_old.captured_at)
    t_new = parse_timestamp_any(snap_new.captured_at)
    if t_old is None or t_new is None:
        return None
    if t_new < t_old:
        return None
    elapsed = int((t_new - t_old).total_seconds())
    if elapsed < 0:
        return None
    vd = _safe_delta(snap_old.views, snap_new.views)
    ld = _safe_delta(snap_old.likes, snap_new.likes)
    cd = _safe_delta(snap_old.comments, snap_new.comments)
    sd = _safe_delta(snap_old.shares, snap_new.shares)
    # P3-B-4: stamp a deterministic observation_id. Same content
    # with same (from, to) timestamps -> same id. Different
    # timestamps -> different ids. This is the basis for the
    # repeated-snapshot scheduler's history integrity.
    obs_id = observation_id_for(
        content_id=snap_new.content_id,
        from_captured_at=snap_old.captured_at,
        to_captured_at=snap_new.captured_at,
    )
    return PerformanceObservation(
        content_id=snap_new.content_id,
        from_captured_at=snap_old.captured_at,
        to_captured_at=snap_new.captured_at,
        elapsed_seconds=elapsed,
        views_delta=vd,
        likes_delta=ld,
        comments_delta=cd,
        shares_delta=sd,
        views_per_hour=_per_hour(vd, elapsed),
        likes_per_hour=_per_hour(ld, elapsed),
        comments_per_hour=_per_hour(cd, elapsed),
        shares_per_hour=_per_hour(sd, elapsed),
        observation_id=obs_id,
    )


# ============================================================================
# Engagement
# ============================================================================

def engagement_breakdown(snap):
    """Return the components used to compute engagement rate.

    None values are preserved as None. The caller must not silently
    coerce None to 0.
    """
    return {
        "views": snap.views,
        "likes": snap.likes,
        "comments": snap.comments,
        "shares": snap.shares,
        "reposts": snap.reposts,
    }


def engagement_total(snap):
    """Sum of known engagement metrics (likes/comments/shares/reposts).

    None if NO component is known. If at least one is known, the
    others are treated as 0 for the sum; the breakdown is exposed
    via engagement_breakdown() so the caller can distinguish.
    """
    parts = [snap.likes, snap.comments, snap.shares, snap.reposts]
    if all(p is None for p in parts):
        return None
    return sum(p or 0 for p in parts)


def engagement_rate(snap):
    """engagements / views, only when views is a positive int.

    Returns None if:
      * views is None
      * views == 0
      * all engagement components are None
    """
    if snap.views is None or snap.views <= 0:
        return None
    total = engagement_total(snap)
    if total is None:
        return None
    return total / snap.views


# ============================================================================
# Classification thresholds
# ============================================================================

# Minimum elapsed time required to attempt any classification.
MIN_ELAPSED_FOR_CLASSIFY_SECONDS = 600  # 10 min
# Maximum elapsed time under which EARLY_SPIKE applies.
EARLY_SPIKE_MAX_ELAPSED_SECONDS = 3600  # 1 h
# Views-per-hour under EARLY_SPIKE to qualify (very strong).
EARLY_SPIKE_MIN_VIEWS_PER_HOUR = 1000
# Views-per-hour under FAST_GROWTH (strong but not "early spike").
FAST_GROWTH_MIN_VIEWS_PER_HOUR = 200
# Slow-start upper bound for LATE_BREAKOUT (per-hour in first window).
LATE_BREAKOUT_MAX_EARLY_VPH = 50
# LATE_BREAKOUT acceleration: late-window vph must be >= this.
LATE_BREAKOUT_MIN_LATE_VPH = 300
# Steady growth floor.
STEADY_GROWTH_MIN_VPH = 20
# Cooling: views_per_hour below this but delta still > 0.
COOLING_MAX_VPH = 5
# Stable band: |delta| <= this and vph below steady-growth floor.
STABLE_DELTA_RANGE = 5


def classify_performance(observation):
    """Classify an observation into a descriptive performance class.

    Conservative: small samples, large windows with no growth, or
    missing metrics all return INSUFFICIENT_DATA. The classification
    describes what was OBSERVED, not what will happen next.
    """
    if observation.elapsed_seconds < MIN_ELAPSED_FOR_CLASSIFY_SECONDS:
        return PerformanceClass.INSUFFICIENT_DATA
    vph = observation.views_per_hour
    vdelta = observation.views_delta
    if vph is None or vdelta is None:
        return PerformanceClass.INSUFFICIENT_DATA
    # STABLE: literally zero change
    if vdelta == 0:
        return PerformanceClass.STABLE
    # COOLING: very small positive growth (still grew, but barely)
    if vph < COOLING_MAX_VPH and vdelta > 0:
        return PerformanceClass.COOLING
    # EARLY_SPIKE: huge in < 1h
    if (
        observation.elapsed_seconds <= EARLY_SPIKE_MAX_ELAPSED_SECONDS
        and vph >= EARLY_SPIKE_MIN_VIEWS_PER_HOUR
    ):
        return PerformanceClass.EARLY_SPIKE
    # FAST_GROWTH: strong but not "early spike" timing
    if vph >= FAST_GROWTH_MIN_VIEWS_PER_HOUR:
        return PerformanceClass.FAST_GROWTH
    # STEADY_GROWTH: positive but moderate
    if vph >= STEADY_GROWTH_MIN_VPH:
        return PerformanceClass.STEADY_GROWTH
    # Anything else (e.g. vph between COOLING and STEADY_GROWTH, or
    # very flat) is conservatively STABLE.
    return PerformanceClass.STABLE


def classify_late_breakout(early, late):
    """Test if `late` shows breakout acceleration after a slow start.

    Returns True iff the early observation's views_per_hour is below
    LATE_BREAKOUT_MAX_EARLY_VPH, AND the late observation's
    views_per_hour is at or above LATE_BREAKOUT_MIN_LATE_VPH, AND
    both observations share the same content_id and the late window
    starts at or after the early window's to_captured_at.

    This is a strict, conservative test. It is one of several
    candidate signals; it does not by itself classify the content
    as LATE_BREAKOUT (callers must use classify_performance with a
    properly-windowed late observation, plus this accelerator test,
    plus sample size).
    """
    if early.content_id != late.content_id:
        return False
    if early.views_per_hour is None or late.views_per_hour is None:
        return False
    if early.views_per_hour > LATE_BREAKOUT_MAX_EARLY_VPH:
        return False
    if late.views_per_hour < LATE_BREAKOUT_MIN_LATE_VPH:
        return False
    t_early_end = parse_timestamp_any(early.to_captured_at)
    t_late_start = parse_timestamp_any(late.from_captured_at)
    if t_early_end is None or t_late_start is None:
        return False
    return t_late_start >= t_early_end


# ============================================================================
# Feature extraction
# ============================================================================

# Heuristic headline features. None of these are authoritative. They
# describe what was OBSERVED in the title, not facts about the
# underlying news. P1 does not implement entity recognition.

_PERSON_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b")
_NUMBER_RE = re.compile(r"\d")
_QUESTION_RE = re.compile(r"[?？]\s*$")
_QUOTE_RE = re.compile(r"[\"\u201c\u201d]")
_TIME_REF_RE = re.compile(
    r"\b(today|yesterday|tomorrow|tonight|just|breaking|"
    r"今天|昨天|明天|今晚|刚刚|突发|最新|今日)\b",
    re.IGNORECASE,
)
_EXCLAMATION_RE = re.compile(r"!|！")


def _detect_headline_style(title: str) -> str:
    if _QUESTION_RE.search(title):
        return "QUESTION"
    if _EXCLAMATION_RE.search(title):
        return "EXCLAMATORY"
    if _QUOTE_RE.search(title):
        return "QUOTE"
    return "INFORMATIVE"


def extract_features(
    *,
    content_id: str,
    title: str,
    category: str,
    topic_type: str,
    local_relevance: str,
    geographic_scope: str,
    published_at: str,
    radar_status=None,
    radar_verification_status=None,
    radar_confidence_label=None,
    radar_momentum=None,
    radar_source_count=None,
) -> ContentFeatureSnapshot:
    """Build a ContentFeatureSnapshot from a title + metadata.

    The headline features are heuristic, not authoritative. They are
    features of the OBSERVED title, not facts about the underlying
    news. P1 does not implement entity recognition.
    """
    t = parse_timestamp_any(published_at)
    if t is None:
        raise ValueError(f"published_at not valid: {published_at!r}")
    t_utc = t.astimezone(timezone.utc)
    return ContentFeatureSnapshot(
        content_id=content_id,
        captured_at=iso_utc(utcnow()),
        category=category,
        topic_type=topic_type,
        local_relevance=local_relevance,
        geographic_scope=geographic_scope,
        headline_length=len(title),
        has_person_name=bool(_PERSON_NAME_RE.search(title)),
        has_location=False,  # no NER in P1
        has_number=bool(_NUMBER_RE.search(title)),
        has_question=title.rstrip().endswith(("?", "？")),
        has_quote=bool(_QUOTE_RE.search(title)),
        has_time_reference=bool(_TIME_REF_RE.search(title)),
        has_exclamation=bool(_EXCLAMATION_RE.search(title)),
        headline_style=_detect_headline_style(title),
        published_at=published_at,
        publication_hour=t_utc.hour,
        publication_weekday=t_utc.weekday(),
        radar_status=radar_status,
        radar_verification_status=radar_verification_status,
        radar_confidence_label=radar_confidence_label,
        radar_momentum=radar_momentum,
        radar_source_count=radar_source_count,
    )
