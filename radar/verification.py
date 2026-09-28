"""
Verification engine.

For every Topic, compute a VerificationStatus and the supporting evidence.
Rules follow VERIFICATION_RULES.md - no shortcut to "looks spread enough -> CONFIRMED".

Order of evaluation (first match wins):

  Step 1. Tier-F-only            -> UNVERIFIED (Tier F is not admissible).
  Step 2. Counter-signal check   -> apply demotion rules from active denials.
  Step 3. CONFIRMED promotion    -> Tier A present + >= 2 independent sources
                                   + >= 2 source_types
                                   OR  >= 2 independent Tier-A/B sources.
  Step 4. REPORTED promotion     -> single Tier-A/B source.
  Step 5. Tier-C / fallback      -> Tier C coverage.
  Step 6. SOCIAL_BUZZ             -> only social sources.
  Step 7. UNVERIFIED              -> nothing reportable.

Counter-signal rules (applied AFTER base status is decided, but before
recording the final status):
  - Tier-A DENIAL                -> RUMOUR, regardless of how viral the claim ran.
  - Tier-A CORRECTION            -> demote one rung; minimum UNVERIFIED.
  - Tier-A CONTRADICTION/DOWNPLAY-> demote one rung; minimum REPORTED (cannot
                                   end up as CONFIRMED over a Tier-A objection).
  - Tier-B DENIAL                -> demote one rung.
  - Tier-B CORRECTION / etc.     -> no demotion (B is not strong enough to
                                   override), but we record the signal.

Confidence is a HEURISTIC value in [0.0, 1.0]. It is NOT a calibrated
probability. It reflects evidence STRUCTURE, not raw mention count.
Confidence_LABEL is the coarse ordinal bucket for human inspection.

The tier for each source comes from the explicit `Source.tier` field on the
registry (see radar/models.py:SourceTier). We do NOT derive tier from
`Source.reliability` alone, because tier is a semantic judgment
("is this outlet authoritative?") while reliability is a calibration knob.
The mapping for sources that did not declare an explicit tier falls back to
`default_tier_for(source_type, reliability)` below.
"""

from __future__ import annotations

from typing import List, Dict, Iterable
from collections import Counter
from urllib.parse import urlsplit

from .models import (
    Topic, Verification, VerificationStatus, SourceType, SourceTier,
    ConfidenceLabel, CounterSignal, CounterSignalStance,
)
from .thresholds import CONFIRMED_MIN_INDEPENDENT_SOURCES
from .counter_signals import CounterSignalRegistry, default_registry


# Confidence-label numeric bands. Heuristic, NOT a probability.
def confidence_to_label(c: float) -> ConfidenceLabel:
    if c >= 0.85:
        return ConfidenceLabel.VERY_HIGH
    if c >= 0.60:
        return ConfidenceLabel.HIGH
    if c >= 0.40:
        return ConfidenceLabel.MEDIUM
    if c >= 0.20:
        return ConfidenceLabel.LOW
    return ConfidenceLabel.VERY_LOW


# Fallback derivation for callers that still supply reliability only.
def default_tier_for(source_type: SourceType, reliability: int) -> SourceTier:
    """Default tier mapping when no explicit tier is provided.

    A: OFFICIAL_SOURCE (a property of source-type identity)
    B: NEWS_SITE / RSS with reliability >= 4
    C: NEWS_SITE / RSS with reliability 2..3
    D: PUBLIC_SOCIAL with reliability >= 3
    E: PUBLIC_SOCIAL with reliability 1..2
    F: SEARCH_RESULT (anonymous)
    """
    if source_type == SourceType.OFFICIAL_SOURCE:
        return SourceTier.A
    if source_type in (SourceType.NEWS_SITE, SourceType.RSS) and reliability >= 4:
        return SourceTier.B
    if source_type in (SourceType.NEWS_SITE, SourceType.RSS):
        return SourceTier.C
    if source_type == SourceType.PUBLIC_SOCIAL and reliability >= 3:
        return SourceTier.D
    if source_type == SourceType.PUBLIC_SOCIAL:
        return SourceTier.E
    if source_type == SourceType.SEARCH_RESULT:
        return SourceTier.F
    return SourceTier.E


def _canonical_origin(url: str) -> str:
    """A canonical origin: scheme+host. Two URLs that share origin may still
    trace to the same wire item; we treat them as same-origin."""
    if not url:
        return ""
    try:
        p = urlsplit(url)
        return f"{p.scheme}://{p.netloc}"
    except ValueError:
        return url


def _distinct_sources(members) -> Dict[str, int]:
    """Count members by canonical origin; identical-origin items are co-counted
    but we mark them as 'same origin' so the engine doesn't double-count a
    single wire reposted by N aggregators.

    Accepts either Story objects (with .url) or plain dicts (with 'url' key)."""
    counts: Dict[str, int] = {}
    for s in members:
        url = s["url"] if isinstance(s, dict) else getattr(s, "url", "")
        origin = _canonical_origin(url)
        counts[origin] = counts.get(origin, 0) + 1
    return counts


# Confidence heuristic. Returns a number in [0.0, 1.0] reflecting evidence
# STRUCTURE (tier mix, independence, source-type diversity), NOT raw mention
# count. A topic with 100 mentions all from the same wire scores the same as
# a topic with 1 mention from that wire.
def _heuristic_confidence(*, has_A: bool, has_B: bool, has_C: bool,
                          has_social: bool, has_F: bool,
                          independent_sources: int, source_type_count: int,
                          has_counter_signal: bool) -> float:
    """Confidence heuristic.

    Anchors:
      - Tier A present + 2+ independent + 2+ source_types    -> 0.85
      - Tier A present + 2+ independent                      -> 0.75
      - 2+ independent Tier A/B                              -> 0.60
      - Single Tier A/B                                       -> 0.40
      - Tier C alone                                          -> 0.30
      - Social only                                           -> 0.15
      - Only Tier F                                           -> 0.00
      - Anything contradicted by Tier A                       -> capped at 0.10
    """
    # Tier-F short-circuit
    if has_F and not (has_A or has_B or has_C):
        return 0.0
    if has_A and independent_sources >= CONFIRMED_MIN_INDEPENDENT_SOURCES and source_type_count >= 2:
        c = 0.85
    elif has_A and independent_sources >= 2:
        c = 0.75
    elif has_A and independent_sources >= 1:
        c = 0.55
    elif (has_A or has_B) and independent_sources >= 2:
        c = 0.60
    elif has_A or has_B:
        c = 0.40
    elif has_C:
        c = 0.30
    elif has_social:
        c = 0.15
    else:
        c = 0.0
    if has_counter_signal:
        c = min(c, 0.10)
    return c


def evidence_for(topic: Topic, stories_by_id: Dict[str, dict],
                 source_reliability: Dict[str, int],
                 source_tiers: Dict[str, str] | None = None,
                 counter_signal_registry: CounterSignalRegistry | None = None,
                 ) -> Verification:
    """Compute Verification for a Topic.

    `stories_by_id` maps story_id -> {url, source_type, source_reliability}.
    `source_reliability` maps source name -> reliability int (1..5).
    `source_tiers` (preferred) maps source name -> 'A'..'F'. When a source
    name has no explicit tier, default_tier_for(source_type, reliability) is
    used.

    `counter_signal_registry` is consulted for active denials/corrections
    keyed by topic.content_key(). Defaults to the process-wide registry.
    """
    members = [stories_by_id[sid] for sid in topic.story_ids]
    if not members:
        return Verification(
            status=VerificationStatus.UNVERIFIED,
            confidence=0.0,
            confidence_label=confidence_to_label(0.0),
            reasons=["no stories attached"],
        )

    source_tiers = source_tiers or {}
    if counter_signal_registry is None:
        counter_signal_registry = default_registry()

    # Pull active counter-signals for this topic
    signals = counter_signal_registry.for_topic(topic.content_key())
    active_signals = [
        s for s in signals
        if s.stance in (CounterSignalStance.DENIAL,
                        CounterSignalStance.CORRECTION,
                        CounterSignalStance.CONTRADICTION,
                        CounterSignalStance.DOWNPLAY)
    ]
    tier_a_signal = any(s.source_tier == SourceTier.A for s in active_signals)
    tier_b_signal = any(s.source_tier == SourceTier.B for s in active_signals)
    denial_a = any(s.source_tier == SourceTier.A and s.stance == CounterSignalStance.DENIAL
                   for s in active_signals)
    denial_b = any(s.source_tier == SourceTier.B and s.stance == CounterSignalStance.DENIAL
                   for s in active_signals)

    # Per-source-type tally
    type_counts: Counter = Counter()
    tiers_present = set()
    origins = _distinct_sources(members)
    distinct_origin_count = len(origins)
    raw_source_count = sum(origins.values())
    source_types_seen: List[SourceType] = []
    evidence_urls: List[str] = []

    for s in members:
        st = s["source_type"] if isinstance(s["source_type"], SourceType) else SourceType(s["source_type"])
        rel = int(source_reliability.get(s["source"], 3))
        # Prefer explicit tier from registry; fall back to derivation
        if s["source"] in source_tiers:
            t = source_tiers[s["source"]]
        else:
            t = default_tier_for(st, rel).value
        tiers_present.add(t)
        type_counts[t] = type_counts.get(t, 0) + 1
        if st not in source_types_seen:
            source_types_seen.append(st)
        if s["url"] not in evidence_urls:
            evidence_urls.append(s["url"])

    # An "independent source" counts distinct origin URLs that are not the
    # same canonical origin.
    independent_sources = distinct_origin_count

    # Tier F is not admissible as evidence at all.
    only_F = (tiers_present == {"F"})
    has_A = "A" in tiers_present
    has_B = "B" in tiers_present
    # A/B/mixed -> "reportable"
    has_AB = has_A or has_B
    has_C = "C" in tiers_present
    has_social = bool(tiers_present & {"D", "E"})

    reasons: List[str] = []

    # Step 1: Tier-F-only is UNVERIFIED
    if only_F:
        status = VerificationStatus.UNVERIFIED
        confidence = 0.0
        reasons.append("only Tier-F (anonymous) sources; not admissible for any conclusion")

    # Step 3-7: base status decision
    elif has_A and independent_sources >= CONFIRMED_MIN_INDEPENDENT_SOURCES and len(source_types_seen) >= 2:
        status = VerificationStatus.CONFIRMED
        reasons.append(f">=2 independent sources with Tier A present, {len(source_types_seen)} source types")
    elif has_AB and independent_sources >= 2:
        status = VerificationStatus.CONFIRMED
        reasons.append(">=2 independent Tier-A/B sources")
    elif has_AB and independent_sources >= 1:
        status = VerificationStatus.REPORTED
        reasons.append("single Tier-A/B source; awaiting corroboration")
    elif has_C or has_AB:
        status = VerificationStatus.REPORTED
        reasons.append("Tier C or single lower-tier coverage")
    elif has_social and not has_AB and not has_C:
        status = VerificationStatus.SOCIAL_BUZZ
        reasons.append("only social platforms covered; no media confirmation yet")
    else:
        status = VerificationStatus.UNVERIFIED
        reasons.append("no Tier-A/B source, no social evidence either")

    # Heuristic confidence BEFORE counter-signal demotion
    confidence = _heuristic_confidence(
        has_A=has_A, has_B=has_B, has_C=has_C,
        has_social=has_social, has_F=only_F,
        independent_sources=independent_sources,
        source_type_count=len(source_types_seen),
        has_counter_signal=bool(active_signals),
    )

    # Step 2: counter-signal demotion rules.
    # Tier-A DENIAL is the strongest signal -> RUMOUR regardless of how
    # popular the claim ran.
    if denial_a:
        status = VerificationStatus.RUMOUR
        reasons.append("Tier-A denial registered; demoted to RUMOUR")
    elif tier_a_signal:
        # Other Tier-A counter-signals (correction / contradiction / downplay)
        # demote one rung; CONFIRMED can no longer stand.
        if status == VerificationStatus.CONFIRMED:
            status = VerificationStatus.REPORTED
            reasons.append("Tier-A counter-signal; CONFIRMED demoted to REPORTED")
        else:
            reasons.append("Tier-A counter-signal recorded; status held")
    elif denial_b:
        # Tier-B denial demotes one rung
        if status == VerificationStatus.CONFIRMED:
            status = VerificationStatus.REPORTED
            reasons.append("Tier-B denial; CONFIRMED demoted to REPORTED")
        elif status == VerificationStatus.REPORTED:
            status = VerificationStatus.SOCIAL_BUZZ
            reasons.append("Tier-B denial; REPORTED demoted to SOCIAL BUZZ")
        else:
            reasons.append("Tier-B denial recorded; status held")
    elif tier_b_signal:
        reasons.append("Tier-B counter-signal recorded (no demotion: B is not strong enough to override)")

    confidence = round(confidence, 3)
    confidence_label = confidence_to_label(confidence)

    return Verification(
        status=status,
        independent_sources=independent_sources,
        raw_source_count=raw_source_count,
        source_types=source_types_seen,
        confidence=confidence,
        confidence_label=confidence_label,
        evidence_urls=evidence_urls[:10],
        reasons=reasons,
        counter_signals=[s.to_dict() for s in active_signals],
    )


def attach_verification(topics: List[Topic], stories: List[Story],
                         source_reliability: dict | None = None,
                         source_tiers: dict | None = None,
                         counter_signal_registry: CounterSignalRegistry | None = None) -> None:
    """Mutates each topic: fills `.verification` and `.statuses_seen`.

    `source_reliability` maps source name -> reliability int (1..5).
    `source_tiers`     maps source name -> tier letter 'A'..'F' (preferred).
    `counter_signal_registry` is consulted for denials; defaults to the
    process-wide registry.

    When omitted, defaults to reliability=3 and tier C for every source.
    """
    if source_reliability is None:
        source_reliability = {}
    if source_tiers is None:
        source_tiers = {}
    if counter_signal_registry is None:
        counter_signal_registry = default_registry()
    by_id = {s.id: s for s in stories}
    for t in topics:
        rel_for: Dict[str, int] = {}
        for sid in t.story_ids:
            s = by_id.get(sid)
            if not s:
                continue
            rel_for.setdefault(s.source, 3)
        ev = evidence_for(
            t,
            {sid: {"url": by_id[sid].url,
                   "source_type": by_id[sid].source_type,
                   "source": by_id[sid].source}
             for sid in t.story_ids if sid in by_id},
            rel_for,
            source_tiers,
            counter_signal_registry,
        )
        t.verification = ev
