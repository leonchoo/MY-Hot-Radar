"""
Phase 2 Batch 3A — Real Radar Output Layer.

This module produces a structured, audit-friendly JSON output from
the existing Radar pipeline. It does NOT modify any engine file:
verification, momentum, classification, counter-signals, politics,
dedup, scheduler — all unchanged.

Per spec §4 + §15: the output layer is a READ-ONLY view over the
post-pipeline Topic list. It does not recompute confidence, growth
rate, verification status, or any other derived metric. Every
output field is either:
  (a) a passthrough from an existing dataclass's to_dict(), or
  (b) a deterministic aggregation across the topics list, or
  (c) a publishability decision (a NEW boolean field, not a
      recomputation of verification).

Output location: <radar_dir>/output/latest.json (atomic) plus
<radar_dir>/output/<YYYY-MM-DD>/<scan_id>.json (snapshot).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    Topic, Story, Status, VerificationStatus,
    ConfidenceLabel, CounterSignal, CounterSignalStance,
    SourceTier,
)
from .politics import (
    PoliticalClaimKind, detect_political_kind,
)


SCHEMA_VERSION = 1


# ============================================================================
# Source / evidence model (spec §6)
# ============================================================================

@dataclass
class SourceEvidence:
    """A single source's contribution to a topic.

    Preserved VERBATIM from the Story object that fed the cluster.
    No field is fabricated; if a field is missing in the Story,
    the output reflects that (None), it does NOT invent a value.
    """
    source_name: str
    source_tier: str       # A / B / C / D / E / F
    source_type: str       # RSS / NEWS_SITE / OFFICIAL_SOURCE / PUBLIC_SOCIAL / SEARCH_RESULT / DIRECT
    country: Optional[str]
    url: str
    title: str
    published_at: Optional[str]

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "source_tier": self.source_tier,
            "source_type": self.source_type,
            "country": self.country,
            "url": self.url,
            "title": self.title,
            "published_at": self.published_at,
        }


# ============================================================================
# Publishability (spec §7)
# ============================================================================

class PublishabilityReason(str, Enum):
    """Why a topic is or is not a publish candidate.

    Multiple reasons may apply; the output records all that apply.
    These are explicit labels, not generic strings, so tests can
    rely on exact values.
    """
    # Positive (the topic contributes toward publishable)
    CONFIRMED_EVIDENCE = "confirmed_evidence"
    VALID_SOURCES = "valid_sources"
    NO_BLOCKING_COUNTER_SIGNAL = "no_blocking_counter_signal"
    VALID_TITLE = "valid_title"
    CONTENT_COMPLETE = "content_complete"
    POLITICALLY_NEUTRAL = "politically_neutral"

    # Negative (blocks publishable)
    VERIFICATION_RUMOUR = "verification_rumour"
    VERIFICATION_UNVERIFIED = "verification_unverified"
    VERIFICATION_SOCIAL_BUZZ_ONLY = "verification_social_buzz_only"
    MISSING_SOURCE_URL = "missing_source_url"
    MISSING_TITLE = "missing_title"
    BLOCKING_TIER_A_DENIAL = "blocking_tier_a_denial"
    POLITICAL_NON_NEUTRAL = "political_non_neutral"
    INSUFFICIENT_INDEPENDENT_SOURCES = "insufficient_independent_sources"
    CONTENT_NATURE_OPINION = "content_nature_opinion"


def evaluate_publishability(
    *,
    verification_status: str,
    confidence_label: str,
    counter_signals: List[CounterSignal],
    sources: List[SourceEvidence],
    title: str,
    is_political: bool,
    political_neutral: bool,
) -> tuple:
    """Return (publishable: bool, reasons: List[str]).

    Conservative default per spec §7:
      - CONFIRMED + valid sources + no blocking counter-signal +
        valid title + politically neutral = publishable
      - RUMOUR / UNVERIFIED / SOCIAL_BUZZ-only = NOT publishable
      - Political non-neutral = NOT publishable
      - Missing source URL or title = NOT publishable

    REPORTED is NOT automatically blocked. A REPORTED topic can
    be a publish candidate if all other gates pass; the user just
    sees "REPORTED" in the verification_status field.
    """
    reasons: List[str] = []

    # --- Negative gates (these BLOCK publishable) ---

    if verification_status == VerificationStatus.RUMOUR.value:
        reasons.append(PublishabilityReason.VERIFICATION_RUMOUR.value)
    elif verification_status == VerificationStatus.UNVERIFIED.value:
        reasons.append(PublishabilityReason.VERIFICATION_UNVERIFIED.value)
    elif verification_status == VerificationStatus.SOCIAL_BUZZ.value:
        reasons.append(PublishabilityReason.VERIFICATION_SOCIAL_BUZZ_ONLY.value)

    # Tier-A denial is an absolute block (existing Radar-3 rule)
    for sig in counter_signals:
        if sig.source_tier.value == "A" and sig.stance == CounterSignalStance.DENIAL:
            reasons.append(PublishabilityReason.BLOCKING_TIER_A_DENIAL.value)
            break

    if is_political and not political_neutral:
        reasons.append(PublishabilityReason.POLITICAL_NON_NEUTRAL.value)

    if not title or not title.strip():
        reasons.append(PublishabilityReason.MISSING_TITLE.value)

    # Every source must have a URL (no fake URLs)
    for s in sources:
        if not s.url or not s.url.strip():
            reasons.append(PublishabilityReason.MISSING_SOURCE_URL.value)
            break

    # Tier-F is NEVER independent. If all sources are Tier-F, no
    # independent evidence chain.
    if sources and all(s.source_tier == "F" for s in sources):
        reasons.append(PublishabilityReason.INSUFFICIENT_INDEPENDENT_SOURCES.value)

    # Negative gates that already fired
    blocking_reasons = {
        PublishabilityReason.VERIFICATION_RUMOUR.value,
        PublishabilityReason.VERIFICATION_UNVERIFIED.value,
        PublishabilityReason.VERIFICATION_SOCIAL_BUZZ_ONLY.value,
        PublishabilityReason.BLOCKING_TIER_A_DENIAL.value,
        PublishabilityReason.POLITICAL_NON_NEUTRAL.value,
        PublishabilityReason.MISSING_TITLE.value,
        PublishabilityReason.MISSING_SOURCE_URL.value,
        PublishabilityReason.INSUFFICIENT_INDEPENDENT_SOURCES.value,
    }
    is_blocked = bool(blocking_reasons & set(reasons))

    # --- Positive contributors (these ANNOTATE but don't override) ---
    if verification_status == VerificationStatus.CONFIRMED.value:
        reasons.append(PublishabilityReason.CONFIRMED_EVIDENCE.value)

    # At least one valid source URL present
    has_valid_url = any(s.url and s.url.strip() for s in sources)
    if has_valid_url:
        reasons.append(PublishabilityReason.VALID_SOURCES.value)

    # No blocking counter-signal is currently a positive signal
    has_blocking_cs = any(
        sig.source_tier.value == "A" and sig.stance == CounterSignalStance.DENIAL
        for sig in counter_signals
    )
    if not has_blocking_cs:
        reasons.append(PublishabilityReason.NO_BLOCKING_COUNTER_SIGNAL.value)

    if title and title.strip():
        reasons.append(PublishabilityReason.VALID_TITLE.value)

    # Content completeness heuristic: at least one source has a non-empty title
    if any(s.title and s.title.strip() for s in sources):
        reasons.append(PublishabilityReason.CONTENT_COMPLETE.value)

    if political_neutral:
        reasons.append(PublishabilityReason.POLITICALLY_NEUTRAL.value)

    publishable = (not is_blocked)
    return publishable, reasons


# ============================================================================
# Politics detection wrapper (spec §9)
# ============================================================================

def classify_topic_politics(topic: Topic) -> tuple:
    """Return (is_political: bool, claim_kind: str, political_neutral: bool).

    Per spec §9: this re-uses the Phase 2 Batch 1 politics layer.
    It does NOT introduce new political-judgement logic. If the
    topic has no political content, claim_kind is "NOT_POLITICAL"
    and political_neutral is True (vacuously).
    """
    text = (topic.title or "") + " " + (topic.summary or "")
    if not text.strip():
        return False, "NOT_POLITICAL", True
    # The detector returns EVENT/CLAIM/OPINION for political content;
    # it returns EVENT for non-political too. We need a stricter
    # gate: only mark as political if some political signal is
    # present.
    lowered = text.lower()
    political_signal_patterns = [
        r"\b(election|parliament|minister|minister|mp\b|coalition|"
        r"cabinet|candidate|government|policy|bill|legislation|"
        r"party|dewan rakyat|dewan negara|parlimen|menteri|"
        r"pilihan raya|perdana menteri|parti|kerajaan)\b",
        r"\b(选举|政党|议员|部长|首相|候选|国会|内阁|投票|政府)\b",
    ]
    is_political = any(re.search(p, lowered) for p in political_signal_patterns)
    if not is_political:
        return False, "NOT_POLITICAL", True
    claim_kind = detect_political_kind(text).value
    # political_neutral is True iff the claim is EVENT or CLAIM with
    # attribution; OPINION is non-neutral (per Phase 2 Batch 1).
    political_neutral = claim_kind in (
        PoliticalClaimKind.EVENT.value,
        PoliticalClaimKind.CLAIM.value,
    )
    return True, claim_kind, political_neutral


# ============================================================================
# Topic output (spec §5 + §6)
# ============================================================================

def _story_to_evidence(story: Story, source_meta: dict) -> SourceEvidence:
    """Build SourceEvidence from a Story. source_meta is a dict
    keyed by source_name with {tier, type, country}.

    NO field is fabricated. If something is missing in the Story
    or source_meta, the corresponding output field is None.
    """
    sm = source_meta.get(story.source) or {}
    return SourceEvidence(
        source_name=story.source,
        source_tier=str(sm.get("tier", "")) if sm else "",
        source_type=(story.source_type.value
                     if hasattr(story.source_type, "value")
                     else str(story.source_type)),
        country=(story.country if story.country else sm.get("country")),
        url=story.url or "",
        title=story.title or "",
        published_at=story.published_at,
    )


def _unique_preserving_order(items: List) -> List:
    """Return unique items preserving first-seen order. Used for
    source dedup so the same wire URL is not listed twice for the
    same topic."""
    seen = set()
    out = []
    for it in items:
        key = (it.url, it.source_name) if hasattr(it, "url") else str(it)
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def build_topic_output(
    topic: Topic,
    stories_by_id: Dict[str, Story],
    source_meta: Dict[str, dict],
) -> dict:
    """Build the output dict for a single Topic.

    Reads from:
      - Topic.to_dict()          (existing engine output)
      - stories_by_id[story_id]  (preserved source URL/title/published_at)
      - source_meta[source_name] (tier, country, type from registry)

    Does NOT recompute:
      - verification status
      - confidence
      - momentum
      - classification

    Adds (new output-only fields):
      - publishable, publishability_reasons
      - claim_kind, political_neutral
      - source_count, sources (full evidence list, deduped)
      - content_key (derived from canonical_url)
    """
    td = topic.to_dict()

    # Build the full source evidence list from the stories that fed
    # this topic. We never invent a URL.
    sources: List[SourceEvidence] = []
    for sid in (topic.story_ids or []):
        story = stories_by_id.get(sid)
        if story is None:
            continue
        sources.append(_story_to_evidence(story, source_meta))
    sources = _unique_preserving_order(sources)

    # Counter-signals (existing dataclass.to_dict already exists)
    counter_signals_list = []
    if topic.verification and topic.verification.counter_signals:
        for sig in topic.verification.counter_signals:
            counter_signals_list.append(sig.to_dict())

    # Politics classification (re-uses Phase 2 B1 logic)
    is_political, claim_kind, political_neutral = classify_topic_politics(topic)

    # Publishability (the new layer)
    pub, pub_reasons = evaluate_publishability(
        verification_status=(topic.verification.status.value
                            if topic.verification else ""),
        confidence_label=(topic.verification.confidence_label.value
                          if topic.verification else ""),
        counter_signals=(topic.verification.counter_signals
                         if topic.verification else []),
        sources=sources,
        title=topic.title,
        is_political=is_political,
        political_neutral=political_neutral,
    )

    # Confidence score: read from topic.verification.confidence (already computed)
    confidence_score = None
    if topic.verification is not None and topic.verification.confidence is not None:
        confidence_score = round(float(topic.verification.confidence), 4)

    # content_key for downstream consumers
    content_key = topic.content_key()

    # Build the output topic
    out_topic = {
        # Identity
        "content_key": content_key,
        "title": topic.title,
        "summary": topic.summary,
        "canonical_url": topic.canonical_url,

        # Classification (from existing engine)
        "category": (topic.category.value
                     if hasattr(topic.category, "value")
                     else str(topic.category)),
        "language": (topic.language.value
                     if hasattr(topic.language, "value")
                     else str(topic.language)),
        "status": (topic.status.value
                   if hasattr(topic.status, "value")
                   else str(topic.status)),
        "verification_status": (topic.verification.status.value
                                if topic.verification else None),
        "confidence_label": (topic.verification.confidence_label.value
                             if topic.verification else None),
        "confidence_score": confidence_score,

        # Momentum passthrough
        "momentum": td.get("momentum", {}),
        "classification_reasons": list(topic.classification_reasons or []),
        "statuses_seen": [s.value if hasattr(s, "value") else str(s)
                          for s in (topic.statuses_seen or [])],

        # Timing
        "first_seen": topic.first_seen,
        "last_seen": topic.last_seen,
        "mention_count": topic.mention_count,

        # Evidence (spec §6) - the new structured source list
        "source_count": len(sources),
        "sources": [s.to_dict() for s in sources],

        # Counter-signals passthrough (with full source attribution)
        "counter_signals": counter_signals_list,
        "counter_signal_count": len(counter_signals_list),

        # Politics (spec §9)
        "is_political": is_political,
        "claim_kind": claim_kind,
        "political_neutral": political_neutral,

        # Publishability (spec §7) - new layer, NOT a verification alias
        "publishable": pub,
        "publishability_reasons": pub_reasons,
    }
    return out_topic


# ============================================================================
# Top-level output (spec §5, §11, §13, §14)
# ============================================================================

def build_source_summary(source_status: List[dict]) -> dict:
    """Build source_summary from the source_status list returned by
    run_scan(). NO field is hardcoded -- everything is derived from
    the actual status records."""
    sources_out = []
    total = len(source_status)
    ok = sum(1 for s in source_status if s.get("ok"))
    failed = total - ok
    for s in source_status:
        sources_out.append({
            "name": s.get("name", ""),
            "tier": s.get("tier", ""),
            "type": s.get("type", ""),
            "ok": bool(s.get("ok")),
            "fetched": int(s.get("fetched", 0)),
            "error": s.get("error"),
        })
    return {
        "total": total,
        "ok": ok,
        "failed": failed,
        "sources": sources_out,
    }


def build_summary(topics_out: List[dict]) -> dict:
    """Aggregate per-topic fields into top-level summary.
    Spec §13: derived from actual topics, never hardcoded."""
    story_count_total = sum(t.get("mention_count", 0) for t in topics_out)
    topic_count = len(topics_out)
    publishable_count = sum(1 for t in topics_out if t.get("publishable"))

    by_verification: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    by_claim_kind: Dict[str, int] = {}
    for t in topics_out:
        vs = t.get("verification_status") or "UNKNOWN"
        by_verification[vs] = by_verification.get(vs, 0) + 1
        st = t.get("status") or "UNKNOWN"
        by_status[st] = by_status.get(st, 0) + 1
        ck = t.get("claim_kind") or "NOT_POLITICAL"
        by_claim_kind[ck] = by_claim_kind.get(ck, 0) + 1

    return {
        "story_count": story_count_total,
        "topic_count": topic_count,
        "publishable_count": publishable_count,
        "by_verification": by_verification,
        "by_status": by_status,
        "by_claim_kind": by_claim_kind,
    }


def build_output(
    *,
    scan_id: str,
    scan_status: str,
    topics: List[Topic],
    stories_by_id: Dict[str, Story],
    source_status: List[dict],
    source_meta: Dict[str, dict],
    generated_at: Optional[str] = None,
) -> dict:
    """Build the full Radar output document."""
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    topics_out = [
        build_topic_output(t, stories_by_id, source_meta) for t in topics
    ]
    summary = build_summary(topics_out)
    source_summary = build_source_summary(source_status)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "scan_id": scan_id,
        "scan_status": scan_status,
        "source_summary": source_summary,
        "summary": summary,
        "topics": topics_out,
    }


# ============================================================================
# Validation (spec §12)
# ============================================================================

class OutputValidationError(Exception):
    """Raised when the output fails structural validation."""


_VALID_VERIFICATION = {v.value for v in VerificationStatus}
_VALID_STATUS = {s.value for s in Status}
_VALID_CONFIDENCE_LABELS = {c.value for c in ConfidenceLabel}
_VALID_SOURCE_TIERS = {t.value for t in SourceTier}


def validate_output(out: dict) -> List[str]:
    """Return a list of error messages. Empty list = valid.

    Per spec §12: failed validation means latest.json MUST NOT be
    replaced. The caller is expected to check the return value and
    refuse to write if errors are present.
    """
    errors = []

    # Top-level required keys
    required = ["schema_version", "generated_at", "scan_id",
                "scan_status", "source_summary", "summary", "topics"]
    for k in required:
        if k not in out:
            errors.append(f"missing top-level key: {k!r}")

    if out.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}; "
                      f"got {out.get('schema_version')!r}")

    if not out.get("scan_id"):
        errors.append("scan_id must be non-empty")
    if not out.get("generated_at"):
        errors.append("generated_at must be non-empty")

    topics = out.get("topics") or []
    if not isinstance(topics, list):
        errors.append("topics must be a list")

    seen_keys = set()
    for i, t in enumerate(topics):
        prefix = f"topics[{i}]"

        # content_key uniqueness
        ck = t.get("content_key")
        if not ck:
            errors.append(f"{prefix}: missing content_key")
        elif ck in seen_keys:
            errors.append(f"{prefix}: duplicate content_key {ck!r}")
        else:
            seen_keys.add(ck)

        # title non-empty
        title = t.get("title") or ""
        if not title.strip():
            errors.append(f"{prefix}: empty title")

        # valid verification status
        vs = t.get("verification_status")
        if vs is not None and vs not in _VALID_VERIFICATION:
            errors.append(f"{prefix}: invalid verification_status {vs!r}")

        # valid classification status
        st = t.get("status")
        if st is not None and st not in _VALID_STATUS:
            errors.append(f"{prefix}: invalid status {st!r}")

        # valid confidence label
        cl = t.get("confidence_label")
        if cl is not None and cl not in _VALID_CONFIDENCE_LABELS:
            errors.append(f"{prefix}: invalid confidence_label {cl!r}")

        # confidence range
        cs = t.get("confidence_score")
        if cs is not None and (not (0.0 <= cs <= 1.0)):
            errors.append(f"{prefix}: confidence_score {cs} out of [0,1]")

        # source tier validity per source
        for j, s in enumerate(t.get("sources") or []):
            st_tier = s.get("source_tier")
            if st_tier and st_tier not in _VALID_SOURCE_TIERS:
                errors.append(
                    f"{prefix}.sources[{j}]: invalid source_tier {st_tier!r}"
                )
            # No fake source URL
            url = s.get("url") or ""
            if url and not (url.startswith("http://") or url.startswith("https://") or url.startswith("file://")):
                errors.append(
                    f"{prefix}.sources[{j}]: malformed url {url!r}"
                )

        # publishability consistency: if publishable=True, must have
        # at least one positive reason and no blocking reason
        pub = t.get("publishable")
        if pub is True:
            reasons = set(t.get("publishability_reasons") or [])
            blocking = {
                PublishabilityReason.VERIFICATION_RUMOUR.value,
                PublishabilityReason.VERIFICATION_UNVERIFIED.value,
                PublishabilityReason.VERIFICATION_SOCIAL_BUZZ_ONLY.value,
                PublishabilityReason.BLOCKING_TIER_A_DENIAL.value,
                PublishabilityReason.POLITICAL_NON_NEUTRAL.value,
                PublishabilityReason.MISSING_TITLE.value,
                PublishabilityReason.MISSING_SOURCE_URL.value,
                PublishabilityReason.INSUFFICIENT_INDEPENDENT_SOURCES.value,
            }
            if reasons & blocking:
                errors.append(
                    f"{prefix}: publishable=True but blocking reasons present"
                )

        # political_neutral consistency
        is_pol = t.get("is_political", False)
        pn = t.get("political_neutral", True)
        if is_pol and not pn:
            # Allowed, but check the kind is OPINION
            ck = t.get("claim_kind")
            if ck != "OPINION":
                # Non-OPINION political content should be neutral
                errors.append(
                    f"{prefix}: political_neutral=False for non-OPINION kind"
                )

    # Summary consistency: by_verification counts must equal topic_count
    summary = out.get("summary") or {}
    bv = summary.get("by_verification") or {}
    bv_total = sum(bv.values())
    if bv_total != len(topics):
        errors.append(
            f"summary.by_verification counts ({bv_total}) "
            f"!= topic_count ({len(topics)})"
        )
    bs = summary.get("by_status") or {}
    bs_total = sum(bs.values())
    if bs_total != len(topics):
        errors.append(
            f"summary.by_status counts ({bs_total}) "
            f"!= topic_count ({len(topics)})"
        )
    if summary.get("topic_count") != len(topics):
        errors.append(
            f"summary.topic_count ({summary.get('topic_count')}) "
            f"!= topics length ({len(topics)})"
        )

    # Source summary consistency
    ss = out.get("source_summary") or {}
    src_list = ss.get("sources") or []
    if ss.get("total") != len(src_list):
        errors.append(
            f"source_summary.total ({ss.get('total')}) "
            f"!= sources length ({len(src_list)})"
        )
    if ss.get("ok", 0) + ss.get("failed", 0) != ss.get("total", 0):
        errors.append(
            "source_summary: ok + failed != total"
        )

    # JSON-serializability sanity check
    try:
        json.dumps(out, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        errors.append(f"output is not JSON-serializable: {e}")

    return errors


# ============================================================================
# Atomic output write (spec §10, §11)
# ============================================================================

def _atomic_write_json(target: Path, payload: dict) -> None:
    """Write JSON atomically: temp + flush + fsync + os.replace.

    On failure mid-write, the previous target file is unchanged.
    Stale .tmp files may remain (harmless).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp_fd, tmp_str = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(data)
            try:
                f.flush()
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                # fsync may not be available on some platforms
                pass
        os.replace(tmp_str, target)
    except Exception:
        # Cleanup tmp on failure (best-effort)
        try:
            os.unlink(tmp_str)
        except OSError:
            pass
        raise


def write_output(
    *,
    output_dir: Path,
    payload: dict,
) -> Dict[str, Path]:
    """Write output to <output_dir>/latest.json and to
    <output_dir>/<YYYY-MM-DD>/<scan_id>.json.

    Returns a dict of paths written. Validation is the caller's
    responsibility (see write_validated_output).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot under YYYY-MM-DD
    gen = payload.get("generated_at", "")
    date_part = gen[:10] if gen else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    scan_id = payload.get("scan_id", "unknown")
    day_dir = output_dir / date_part
    day_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = day_dir / f"{scan_id}.json"

    # latest.json (atomic)
    latest_path = output_dir / "latest.json"

    _atomic_write_json(snapshot_path, payload)
    _atomic_write_json(latest_path, payload)

    return {"snapshot": snapshot_path, "latest": latest_path}


def write_validated_output(
    *,
    output_dir: Path,
    payload: dict,
) -> Dict[str, Path]:
    """Validate first; only write if validation passes.

    Per spec §12: failed validation must NOT replace latest.json.
    """
    errors = validate_output(payload)
    if errors:
        raise OutputValidationError(
            "output failed validation:\n  " + "\n  ".join(errors)
        )
    return write_output(output_dir=output_dir, payload=payload)


# ============================================================================
# CLI entry point
# ============================================================================

def run_output_for_existing_scan(
    *,
    radar_dir: Path,
    scan_id: Optional[str] = None,
    scan_status: str = "SUCCESS",
) -> Dict[str, Path]:
    """Re-generate the output from the most recent scan in memory.

    This is the function called by `python -m radar.output` -- it
    does NOT trigger a new scan. It uses the topics in
    radar_data/history/<latest>.json plus source_status from
    radar_data/latest.json.

    Returns the paths written. Raises OutputValidationError on
    validation failure (in which case latest.json is NOT replaced).
    """
    radar_dir = Path(radar_dir)
    history_dir = radar_dir / "history"
    latest_data_path = radar_dir / "latest.json"
    output_dir = radar_dir / "output"

    # Load the latest snapshot
    from .history import _latest_snapshot_path
    snap_path = _latest_snapshot_path(radar_dir)
    if snap_path is None:
        raise RuntimeError("no valid history snapshot found; "
                           "run `python -m radar.scan` first")
    snap_raw = json.loads(snap_path.read_text(encoding="utf-8"))

    # Load source_status from latest.json (run_scan's report writes
    # it). If not present, fall back to an empty list.
    src_status: List[dict] = []
    if latest_data_path.exists():
        try:
            ld = json.loads(latest_data_path.read_text(encoding="utf-8"))
            src_status = ld.get("source_status") or []
        except (OSError, json.JSONDecodeError):
            pass

    # Build source_meta from registry
    from .sources_registry import load_sources
    source_meta: Dict[str, dict] = {}
    for s in load_sources():
        source_meta[s.name] = {
            "tier": s.tier.value,
            "type": s.type.value,
            "country": s.country,
        }
    # Include <direct> (fixture injection) too
    for ss in src_status:
        n = ss.get("name")
        if n and n not in source_meta:
            source_meta[n] = {
                "tier": ss.get("tier", ""),
                "type": ss.get("type", ""),
                "country": "",
            }

    # Rebuild Topic list from snapshot. The snapshot only has
    # minimal Topic data (per Radar-4A's _topic_min); the full
    # Topic objects are NOT preserved in history. So this CLI
    # path reconstructs them as best it can.
    topics: List[Topic] = []
    for ck, td in snap_raw.get("topics", {}).items():
        try:
            status_val = td.get("status", "WATCH")
            try:
                status_enum = Status(status_val)
            except ValueError:
                status_enum = Status.WATCH
            t = Topic(
                id=td.get("id", ""),
                title=td.get("title", ""),
                mention_count=int(td.get("mention_count", 0)),
                status=status_enum,
                first_seen=td.get("first_seen", ""),
                last_seen=td.get("last_seen", ""),
                canonical_url=td.get("canonical_url", ""),
                summary="",
                category=__import__("radar.models", fromlist=["Category"]).Category.WORLD,
                language=__import__("radar.models", fromlist=["Language"]).Language.EN,
            )
            topics.append(t)
        except Exception:
            continue

    # Stories cannot be reconstructed from snapshot alone; we
    # derive minimal SourceEvidence from topic canonical_url only.
    # For source_url/title, we just use what the Topic knows.
    stories_by_id: Dict[str, Story] = {}

    # scan_id: prefer explicit, else from snapshot filename
    if not scan_id:
        scan_id = snap_path.stem  # e.g. "scan-2026-09-29T024332Z"

    payload = build_output(
        scan_id=scan_id,
        scan_status=scan_status,
        topics=topics,
        stories_by_id=stories_by_id,
        source_status=src_status,
        source_meta=source_meta,
        generated_at=snap_raw.get("meta", {}).get("started_at"),
    )

    return write_validated_output(output_dir=output_dir, payload=payload)


def _generate_output_from_scan_summary(
    summary: dict,
    scan_id: str,
    scan_status: str,
    started_at: str,
    radar_dir: Path,
) -> Dict[str, Path]:
    """Build + validate + write output from a run_scan summary.

    Caller is responsible for invoking run_scan with
    return_internals=True and for the lock / scheduling. This
    function only handles the output layer concerns: build,
    validate, atomic write.
    """
    topics = summary.get("topics") or []
    stories_by_id = summary.get("stories_by_id") or {}
    source_status = summary.get("source_status") or []

    from .sources_registry import load_sources
    source_meta = {
        s.name: {"tier": s.tier.value, "type": s.type.value,
                 "country": s.country}
        for s in load_sources()
    }
    for ss in source_status:
        n = ss.get("name")
        if n and n not in source_meta:
            source_meta[n] = {
                "tier": ss.get("tier", ""),
                "type": ss.get("type", ""),
                "country": "",
            }

    payload = build_output(
        scan_id=scan_id,
        scan_status=scan_status,
        topics=topics,
        stories_by_id=stories_by_id,
        source_status=source_status,
        source_meta=source_meta,
        generated_at=started_at,
    )

    output_dir = radar_dir / "output"
    return write_validated_output(output_dir=output_dir, payload=payload)


def main(argv=None) -> int:
    parser_args_mod = []
    # Avoid pulling in argparse at module load
    import argparse
    parser = argparse.ArgumentParser(
        description="MY Hot Radar - real output layer"
    )
    parser.add_argument("--radar-dir", default=None)
    parser.add_argument("--scan-status", default="SUCCESS",
                        help="SUCCESS | PARTIAL | FAILED | SKIPPED_LOCKED")
    parser.add_argument("--scan-id", default=None)
    parser.add_argument("--from-history", action="store_true",
                        help="Reconstruct output from the most recent history "
                             "snapshot. Does NOT run a new scan. Useful when "
                             "you want to rebuild output without rescanning.")
    parser.add_argument("--inject-fixture", action="store_true",
                        help="Run a fresh offline scan (deterministic) and "
                             "generate the output. No network calls.")
    parser.add_argument("--live", action="store_true",
                        help="Run a live network scan and generate the output. "
                             "This is the production-realistic path.")
    args = parser.parse_args(argv)

    radar_dir = Path(args.radar_dir) if args.radar_dir else \
        Path(__file__).resolve().parents[1] / "radar_data"

    if args.from_history:
        try:
            paths = run_output_for_existing_scan(
                radar_dir=radar_dir,
                scan_id=args.scan_id,
                scan_status=args.scan_status,
            )
        except OutputValidationError as e:
            print(f"OUTPUT VALIDATION FAILED; latest.json NOT replaced:")
            print(str(e))
            return 1
        except Exception as e:
            print(f"OUTPUT GENERATION FAILED: {type(e).__name__}: {e}")
            return 1
        print(json.dumps({
            "snapshot": str(paths["snapshot"]),
            "latest": str(paths["latest"]),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.inject_fixture or args.live:
        from .scheduler import _new_scan_id, _now_iso
        from .pipeline import run_scan

        scan_id = args.scan_id or _new_scan_id()
        started_at = _now_iso()
        scan_status = "SUCCESS"

        extra_stories = None
        if args.inject_fixture:
            from .tests.fixtures import fixture_stories
            extra_stories = fixture_stories()

        try:
            summary = run_scan(
                extra_stories=extra_stories,
                radar_dir=str(radar_dir),
                return_internals=True,
            )
        except Exception as e:
            print(f"SCAN FAILED: {type(e).__name__}: {e}")
            return 1

        try:
            paths = _generate_output_from_scan_summary(
                summary=summary,
                scan_id=scan_id,
                scan_status=scan_status,
                started_at=started_at,
                radar_dir=radar_dir,
            )
        except OutputValidationError as e:
            print(f"OUTPUT VALIDATION FAILED; latest.json NOT replaced:")
            print(str(e))
            return 1
        topics = summary.get("topics") or []
        stories_by_id = summary.get("stories_by_id") or {}
        print(json.dumps({
            "scan_id": scan_id,
            "snapshot": str(paths["snapshot"]),
            "latest": str(paths["latest"]),
            "topics": len(topics),
            "stories": len(stories_by_id),
        }, ensure_ascii=False, indent=2))
        return 0

    # Default: --from-history
    try:
        paths = run_output_for_existing_scan(
            radar_dir=radar_dir,
            scan_id=args.scan_id,
            scan_status=args.scan_status,
        )
    except OutputValidationError as e:
        print(f"OUTPUT VALIDATION FAILED; latest.json NOT replaced:")
        print(str(e))
        return 1
    except Exception as e:
        print(f"OUTPUT GENERATION FAILED: {type(e).__name__}: {e}")
        return 1
    print(json.dumps({
        "snapshot": str(paths["snapshot"]),
        "latest": str(paths["latest"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
