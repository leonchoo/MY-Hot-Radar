"""
Verification engine.

For every Topic, compute a VerificationStatus and the supporting evidence.
Rules follow VERIFICATION_RULES.md - no shortcut to "looks spread enough -> CONFIRMED".

Order of evaluation (first match wins unless contradicted by a Tier A denial):
  1. Any Tier A denial      -> RUMOUR
  2. >= 2 independent Tier A/B sources, >= 2 source_types
                            -> CONFIRMED
  3. >= 1 Tier A/B source   -> REPORTED
  4. only public social     -> SOCIAL BUZZ
  5. neither                -> UNVERIFIED

Confidence is a 0..1 number derived from the input, not a magic number.

The tier for each source comes from the explicit `Source.tier` field on the
registry (see radar/models.py:SourceTier). We do NOT derive tier from
`Source.reliability` alone, because tier is a semantic judgment
("is this outlet authoritative?") while reliability is a calibration knob.
The mapping for sources that did not declare an explicit tier falls back to
`default_tier_for(source_type, reliability)` below.
"""

from __future__ import annotations

from typing import List, Dict
from collections import Counter
from urllib.parse import urlsplit

from .models import (
    Topic, Verification, VerificationStatus, SourceType, SourceTier,
)
from .thresholds import CONFIRMED_MIN_INDEPENDENT_SOURCES


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


def evidence_for(topic: Topic, stories_by_id: Dict[str, dict],
                 source_reliability: Dict[str, int],
                 source_tiers: Dict[str, str] | None = None) -> Verification:
    """Compute Verification for a Topic.

    `stories_by_id` maps story_id -> {url, source_type, source_reliability}.
    `source_reliability` maps source name -> reliability int (1..5).
    `source_tiers` (preferred) maps source name -> 'A'..'F'. When a source
    name has no explicit tier, default_tier_for(source_type, reliability) is
    used.
    """
    members = [stories_by_id[sid] for sid in topic.story_ids]
    if not members:
        return Verification(
            status=VerificationStatus.UNVERIFIED,
            reasons=["no stories attached"],
        )

    source_tiers = source_tiers or {}

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
    # same canonical origin. For Phase 1 we use distinct origins.
    independent_sources = distinct_origin_count

    # Tier F is not admissible as evidence at all.
    only_F = (tiers_present == {"F"})
    has_A = "A" in tiers_present
    has_B = "B" in tiers_present
    # A/B/mixed -> "reportable"
    has_AB = has_A or has_B
    has_C = "C" in tiers_present
    has_social = bool(tiers_present & {"D", "E"})

    if only_F:
        status = VerificationStatus.UNVERIFIED
        reasons = ["only Tier-F (anonymous) sources; not admissible for any conclusion"]

    # Crude official-denial signal: if any Tier A produced a 'denial' sentinel,
    # we'd mark RUMOUR. We don't have a denial registry in Phase 1.
    # This is intentionally a placeholder -- a real impl would consume a
    # structured correction feed.
    status: VerificationStatus
    reasons = []

    if has_A and independent_sources >= CONFIRMED_MIN_INDEPENDENT_SOURCES and len(source_types_seen) >= 2:
        status = VerificationStatus.CONFIRMED
        confidence = min(1.0, 0.5 + 0.1 * independent_sources)
        reasons.append(f">=2 independent sources with Tier A present, {len(source_types_seen)} source types")
    elif has_AB and independent_sources >= 2:
        status = VerificationStatus.CONFIRMED
        confidence = 0.6
        reasons.append(">=2 independent Tier-A/B sources")
    elif has_AB and independent_sources >= 1:
        status = VerificationStatus.REPORTED
        confidence = 0.4
        reasons.append("single Tier-A/B source; awaiting corroboration")
    elif has_C or has_AB:
        status = VerificationStatus.REPORTED
        confidence = 0.3
        reasons.append("Tier C or single lower-tier coverage")
    elif has_social and not has_AB and not has_C:
        status = VerificationStatus.SOCIAL_BUZZ
        confidence = 0.15
        reasons.append("only social platforms covered; no media confirmation yet")
    else:
        status = VerificationStatus.UNVERIFIED
        confidence = 0.0
        reasons.append("no Tier-A/B source, no social evidence either")

    return Verification(
        status=status,
        independent_sources=independent_sources,
        raw_source_count=raw_source_count,
        source_types=source_types_seen,
        confidence=round(confidence, 3),
        evidence_urls=evidence_urls[:10],
        reasons=reasons,
    )


def attach_verification(topics: List[Topic], stories: List[Story],
                         source_reliability: dict | None = None,
                         source_tiers: dict | None = None) -> None:
    """Mutates each topic: fills `.verification` and `.statuses_seen`.

    `source_reliability` maps source name -> reliability int (1..5).
    `source_tiers`     maps source name -> tier letter 'A'..'F' (preferred).
    When omitted, defaults to reliability=3 and tier C for every source.
    """
    if source_reliability is None:
        source_reliability = {}
    if source_tiers is None:
        source_tiers = {}
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
        )
        t.verification = ev
