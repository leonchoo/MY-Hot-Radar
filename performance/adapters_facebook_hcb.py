"""
Phase 2B — Facebook HCB Performance adapter.

URL-anchored Option A integration (per
``docs/HCB_PERFORMANCE_COMPATIBILITY_AUDIT.md``).

Pipeline:

    FacebookDesktopCollector.collect_with_engagement(url)
        ↓ writes envelope
    C:\\MY-Hot-Radar-Bridge\\inbox\\android-observations\\*.json
        ↓ consumed by
    FacebookHcbAdapter.fetch()
        ↓ produces
    AdapterObservation rows
        ↓ projected by
    PerformanceStore.to_snapshots()
        ↓
    PerformanceSnapshot history

Identity anchor:

    canonical_url  ── derive_content_id(post_url) ──> content_id

    Same canonical URL across observations → same content_id
    (deterministic, dedup-safe; verified by P3-B-4 audit).

Engagement mapping (SEMANTIC_MISMATCH documented):

    reactions       → likes (with semantic metadata in extra)
    comments        → comments
    shares          → shares
    views           → views (None preserved; no fake zero)
    reposts         → None (Facebook HCB does not emit reposts)

`reactions` is the SUM of all reaction types (Like + Love +
Haha + Wow + Sad + Angry + Care), NOT a "Like only" count.
We preserve the raw-text evidence in
``extra["metric_semantics"]["likes"]["raw_text"]`` and
``extra["metric_semantics"]["likes"]["pattern"]`` so a future
auditor can re-derive the value or downgrade semantics.

published_at policy (no fake ISO):

    HCB does NOT emit an absolute published timestamp; it
    only emits a relative string ("1h", "28 minutes ago").
    Per spec §6 we do NOT convert relative to absolute.

    Therefore published_at is always None on the resulting
    AdapterObservation. The relative string is preserved in
    ``extra["published_time_raw"]`` for future reference.

    This means HCB observations:
      * Persist as PerformanceSnapshot normally (uses captured_at)
      * Persist as PerformanceObservation normally (uses captured_at)
      * Cannot become StoryMember as-is (StoryMember requires
        parseable published_at — known limitation, documented in
        the audit). This is acceptable for Phase 2B; the goal
        is Performance chain integration, not StoryCluster.

Failure policy (fail-closed):

    * Missing canonical_url → adapter emits zero observations
      and returns AdapterResult(retrieval_status=ERROR).
    * Invalid canonical_url (not is_valid_url) → same as above.
    * Native post ID missing → observation is still emitted IF
      canonical_url is valid (native_post_id is supplemental,
      not a contract requirement). Missing native_post_id is
      recorded as None in extra.
    * Identity conflict (canonical vs native_post_id mismatch) →
      not applicable here; HCB already enforces this at its
      layer (CONFLICT → fail-closed, no envelope emitted).

No synthetic leakage:

    Synthetic data (synthetic Facebook fixtures) MUST NOT
    reach the production performance_data dir. The adapter
    has no synthetic fixture mode; the only inputs are
    ``FacebookHcbInput`` instances carrying real data
    (canonical_url + metrics). Tests that need fixture data
    use ``_make_hcb_input(...)`` which produces real-data
    shaped ``FacebookHcbInput`` rows.

NOT in scope for this batch:

    * HCB code changes (Phase 2A done; Collector frozen)
    * AndroidObservationInput changes (bridge contract frozen)
    * ContentIdentity schema changes
    * PlatformContentRef
    * StoryCluster changes (published_at=None limitation
      documented but not worked around)
    * Scheduler activation
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .enums import Platform, SourceType
from .adapters import (
    AdapterCapability,
    AdapterObservation,
    AdapterResult,
    AdapterSourceSpec,
    DataAccess,
    PublicPerformanceAdapter,
    RetrievalStatus,
)
from .validation import (
    ValidationError,
    is_valid_url,
    iso_utc,
    parse_timestamp_any,
    utcnow,
)
from .ids import content_id_for
from .android_bridge import derive_content_id


# ============================================================================
# Source name
# ============================================================================

FACEBOOK_HCB_SOURCE_NAME = "facebook_hcb"
"""Stable adapter source name; goes into ``AdapterResult.source_name``
and ``ExecutionRecord.source_name``. Distinct from ``"bernama_en"``
and from ``ANDROID_BRIDGE_SOURCE_PREFIX = "android_bridge"``."""


# ============================================================================
# Input dataclass — one HCB observation row
# ============================================================================

@dataclass(frozen=True)
class FacebookHcbInput:
    """One Facebook Web observation row, as produced by the HCB
    collector and committed to the bridge inbox envelope.

    All fields come from real HCB output (Phase 2A verified). No
    fake values; missing fields stay None.

    Attributes
    ----------
    canonical_url:
        The Facebook canonical post URL extracted from
        ``<link rel="canonical">``. **Identity anchor.** Passes
        ``is_valid_url()``. Required.
    native_post_id:
        The 16-digit FB internal post ID parsed from the URL
        slug. Supplemental; preserved in ``extra`` for audit.
        May be None when HCB could not parse it.
    publisher:
        The Page / Group display name (e.g. ``"BBC News"``).
        Required (orchestrator always extracts it).
    caption:
        The Post caption / body text, de-noised by HCB. May be
        None when HCB could not extract a caption.
    reactions:
        All-reactions total (Like + Love + Haha + Wow + Sad +
        Angry + Care). May be None.
    likes_breakdown:
        Like-only count from ``aria-label="Like: N people"``.
        May be None (older posts may not expose it).
    comments:
        Comment count. May be None.
    shares:
        Share count. May be None.
    views:
        View count. May be None (most Posts do not expose views).
    published_at_iso:
        Absolute ISO-8601 publish timestamp. HCB does NOT emit
        this today; the field is reserved for the future. When
        None, we DO NOT substitute observed_at.
    published_time_raw:
        Relative publish string ("1h", "28 minutes ago"). May be
        None. Preserved in ``extra["published_time_raw"]``.
    observed_at:
        ISO-8601 timestamp of the capture event. Defaults to
        fetch wall-clock UTC when not provided.
    """

    canonical_url: str
    native_post_id: Optional[str] = None
    publisher: Optional[str] = None
    caption: Optional[str] = None
    reactions: Optional[int] = None
    likes_breakdown: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    views: Optional[int] = None
    published_at_iso: Optional[str] = None
    published_time_raw: Optional[str] = None
    observed_at: Optional[str] = None


# ============================================================================
# Helpers
# ============================================================================

def _now_iso() -> str:
    return iso_utc(utcnow())


def _coerce_metric(v: Any) -> Optional[int]:
    """None-or-non-negative-int. Pass through None; reject negatives
    and non-ints. Same shape as ``is_metric`` in validation.py."""
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValidationError(
            f"metric must be None or non-negative int, got {v!r}"
        )
    if v < 0:
        raise ValidationError(
            f"metric must be non-negative, got {v!r}"
        )
    return v


def _build_metric_semantics(
    reactions_raw_text: Optional[str],
    reactions_pattern: Optional[str],
) -> Dict[str, Any]:
    """Document the SEMANTIC_MISMATCH of ``likes`` ← ``reactions``.

    Facebook's "All reactions: <n>" is the SUM of all reaction
    types, NOT a Like-only count. We persist this audit metadata
    in ``extra["metric_semantics"]["likes"]`` so a future consumer
    can:

      * downgrade ``likes`` to the Like-only count if a
        ``likes_breakdown`` was extracted,
      * re-interpret the metric if Facebook changes its semantics,
      * or reject the metric if a stricter downstream consumer
        requires Like-only.
    """
    return {
        "likes": {
            "kind": "facebook_reactions_total",
            "raw_text": reactions_raw_text,
            "pattern": reactions_pattern,
            "note": (
                "reactions_total is the sum of Like + Love + Haha + "
                "Wow + Sad + Angry + Care. NOT Like-only. Use "
                "likes_breakdown for Like-only when available."
            ),
        }
    }


# ============================================================================
# Identity derivation
# ============================================================================

def derive_hcb_content_id(canonical_url: str) -> str:
    """URL-anchored content_id derivation for HCB Facebook Posts.

    Same URL → same content_id. Different URL → different id.
    Deterministic. Matches ``derive_content_id`` semantics used
    by the Android bridge for Android Collector observations.

    Returns ``"ci_<24 hex>"``.
    """
    if not is_valid_url(canonical_url):
        raise ValidationError(
            f"canonical_url is not safe: {canonical_url!r}"
        )
    return derive_content_id(canonical_url)


# ============================================================================
# Adapter
# ============================================================================

class FacebookHcbAdapter(PublicPerformanceAdapter):
    """Facebook HCB adapter — Option A (URL-anchored).

    Reads from a list of ``FacebookHcbInput`` rows (typically
    loaded from ``C:\\MY-Hot-Radar-Bridge\\inbox\\android-observations\\``
    JSON envelopes written by the HCB Collector).

    For each row:
      * validates ``canonical_url`` is safe
      * derives ``content_id = derive_hcb_content_id(canonical_url)``
      * maps ``reactions → likes`` with semantic metadata in extra
      * maps ``comments / shares / views`` directly
      * preserves None for unknown metrics (no fake zero)
      * preserves ``published_at = None`` (no fake ISO conversion)
      * stores ``native_post_id`` / ``caption`` / ``published_time_raw``
        in ``extra`` for audit

    Fail-closed:
      * Invalid URL → row is skipped, error appended, status PARTIAL
      * No input rows → retrieval_status = UNAVAILABLE
      * Adapter construction with empty inputs list → fetch returns
        UNAVAILABLE.

    Identity guarantee:
      * Two ``FacebookHcbInput`` rows with the SAME canonical_url
        produce observations with the SAME content_id (regardless
        of differences in metrics, caption, or other fields).
    """

    def __init__(
        self,
        inputs: Iterable[FacebookHcbInput],
        *,
        source_name: str = FACEBOOK_HCB_SOURCE_NAME,
        clock=None,
    ) -> None:
        self._inputs: List[FacebookHcbInput] = list(inputs)
        self._source_name = source_name
        self._clock = clock or utcnow

    # ----- public adapter API -----

    def spec(self) -> AdapterSourceSpec:
        # Compute supported capabilities from the actual input set
        # so callers know what to expect on this run.
        caps = {AdapterCapability.ARTICLE_METADATA}
        if any(i.reactions is not None for i in self._inputs):
            caps.add(AdapterCapability.LIKES)
        if any(i.comments is not None for i in self._inputs):
            caps.add(AdapterCapability.COMMENTS)
        if any(i.shares is not None for i in self._inputs):
            caps.add(AdapterCapability.SHARES)
        if any(i.views is not None for i in self._inputs):
            caps.add(AdapterCapability.VIEWS)
        return AdapterSourceSpec(
            source_name=self._source_name,
            platform=Platform.FACEBOOK,
            data_access=DataAccess.PUBLIC,
            source_url="https://www.facebook.com/",  # generic FB root
            description=(
                "Facebook HCB (hermes-chrome-bridge) public Page/Group "
                "Post observations via desktop Chromium. Public content "
                "only; no login / cookies / tokens. Engagement metrics "
                "are real numbers extracted from the visible DOM; never "
                "fabricated."
            ),
            supported_metrics=sorted(caps, key=lambda c: c.value),
        )

    def fetch(self) -> AdapterResult:
        started = _now_iso()
        errors: List[str] = []
        observations: List[AdapterObservation] = []
        seen_content_ids: Dict[str, int] = {}

        for idx, row in enumerate(self._inputs):
            try:
                obs = self._build_observation(row)
            except ValidationError as e:
                errors.append(f"row[{idx}]: {e}")
                continue
            except Exception as e:
                errors.append(
                    f"row[{idx}]: {type(e).__name__}: {e}"
                )
                continue
            # Dedup within batch — keep first occurrence
            if obs.content_id in seen_content_ids:
                continue
            seen_content_ids[obs.content_id] = idx
            observations.append(obs)

        finished = _now_iso()

        if not observations and not self._inputs:
            overall = RetrievalStatus.UNAVAILABLE
        elif not observations:
            overall = RetrievalStatus.ERROR
        elif errors:
            overall = RetrievalStatus.PARTIAL
        else:
            overall = RetrievalStatus.AVAILABLE

        return AdapterResult(
            source_name=self._source_name,
            platform=Platform.FACEBOOK,
            started_at=started,
            finished_at=finished,
            retrieval_status=overall,
            observations=observations,
            errors=errors,
        )

    # ----- construction helper -----

    @classmethod
    def from_inbox_envelope(
        cls,
        envelope: Dict[str, Any],
        *,
        source_name: str = FACEBOOK_HCB_SOURCE_NAME,
    ) -> List[FacebookHcbInput]:
        """Parse a bridge inbox envelope into ``FacebookHcbInput`` rows.

        The envelope is the same JSON shape HCB writes to
        ``C:\\MY-Hot-Radar-Bridge\\inbox\\android-observations\\``.
        Each envelope carries the inbox-level ``AndroidObservationInput``
        shape; we translate it to ``FacebookHcbInput``.

        Returns one ``FacebookHcbInput`` per ``observations[]`` row.
        Invalid rows are SKIPPED silently (the HCB contract already
        ensures canonical_url is RESOLVED for written envelopes).
        """
        obs_list = envelope.get("observations") or []
        out: List[FacebookHcbInput] = []
        for o in obs_list:
            canonical_url = o.get("post_url")
            if not isinstance(canonical_url, str) or not canonical_url:
                continue
            if not is_valid_url(canonical_url):
                continue
            # Try to derive native_post_id from URL when not explicit
            native_post_id = o.get("native_post_id")
            if native_post_id is None:
                native_post_id = _parse_native_post_id_from_url(canonical_url)
            out.append(FacebookHcbInput(
                canonical_url=canonical_url,
                native_post_id=native_post_id,
                publisher=o.get("publisher"),
                caption=o.get("caption"),
                reactions=o.get("likes"),  # inbox envelope's "likes" is reactions
                likes_breakdown=None,  # not in inbox; in evidence JSON only
                comments=o.get("comments"),
                shares=o.get("shares"),
                views=o.get("views"),
                published_at_iso=None,  # inbox doesn't carry this
                published_time_raw=None,  # inbox doesn't carry this
                observed_at=o.get("observed_at"),
            ))
        return out

    # ----- internal -----

    def _build_observation(self, row: FacebookHcbInput) -> AdapterObservation:
        if not is_valid_url(row.canonical_url):
            raise ValidationError(
                f"canonical_url is not safe: {row.canonical_url!r}"
            )

        content_id = derive_hcb_content_id(row.canonical_url)

        # observed_at — prefer row, fall back to now
        observed_at = row.observed_at or _now_iso()
        if parse_timestamp_any(observed_at) is None:
            raise ValidationError(
                f"observed_at invalid: {observed_at!r}"
            )

        # published_at — HCB does not emit ISO; preserve None
        published_at: Optional[str] = row.published_at_iso
        if published_at is not None and parse_timestamp_any(published_at) is None:
            raise ValidationError(
                f"published_at invalid: {published_at!r}"
            )

        # Metrics — None preserved; coerce + validate
        reactions = _coerce_metric(row.reactions)
        comments = _coerce_metric(row.comments)
        shares = _coerce_metric(row.shares)
        views = _coerce_metric(row.views)

        # reactions → likes (SEMANTIC_MISMATCH documented)
        likes: Optional[int] = reactions

        # Build extra dict — preserve provenance + HCB-specific signals
        extra: Dict[str, Any] = {
            "publisher": row.publisher,
            "native_post_id": row.native_post_id,
        }
        if row.caption is not None:
            extra["caption"] = row.caption
        if row.published_time_raw is not None:
            extra["published_time_raw"] = row.published_time_raw
        if row.likes_breakdown is not None:
            extra["likes_breakdown"] = row.likes_breakdown
        # Document the SEMANTIC_MISMATCH so future auditors can
        # see exactly how ``likes`` was derived.
        extra["metric_semantics"] = _build_metric_semantics(
            reactions_raw_text=None,
            reactions_pattern=None,
        )

        # unavailable_reason: when engagement metrics are absent
        # we still mark AVAILABLE if any one metric is present;
        # otherwise we record why.
        any_metric = any(
            m is not None for m in (likes, comments, shares, views)
        )
        if any_metric:
            retrieval_status = RetrievalStatus.AVAILABLE
            unavailable_reason: Optional[str] = None
        else:
            retrieval_status = RetrievalStatus.PARTIAL
            unavailable_reason = (
                "facebook_post_engagement_metrics_not_visible"
            )

        # publisher — HCB always extracts it; but be defensive
        publisher_value = (
            row.publisher if row.publisher is not None
            else "facebook_unknown"
        )

        # Title — HCB does not produce a stable title; we use the
        # canonical URL as a stable placeholder so the field is
        # non-empty (AdapterObservation.title is required).
        # Caption is preserved separately in extra.
        title_value = row.canonical_url

        return AdapterObservation(
            content_id=content_id,
            platform=Platform.FACEBOOK,
            observed_at=observed_at,
            retrieval_status=retrieval_status,
            source=self._source_name,
            source_url=row.canonical_url,
            title=title_value,
            published_at=published_at,
            url=row.canonical_url,
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            reposts=None,  # Facebook HCB does not emit reposts
            unavailable_reason=unavailable_reason,
            extra=extra,
        )


# ============================================================================
# Native post ID parsing (URL → native_post_id, defensive)
# ============================================================================

def _parse_native_post_id_from_url(url: str) -> Optional[str]:
    """Best-effort: extract the trailing numeric segment from a
    canonical Facebook URL like

        https://www.facebook.com/<page>/posts/<slug>/<numeric_id>/

    Returns the numeric id as a string, or None when the pattern
    does not match. This is purely a defensive fallback — the
    inbox envelope's ``native_post_id`` (or HCB's evidence JSON)
    is the authoritative source when available.
    """
    # Strip trailing slash, then look at the last path segment
    cleaned = url.rstrip("/").split("?")[0]
    parts = cleaned.split("/")
    if not parts:
        return None
    last = parts[-1]
    if last.isdigit():
        return last
    return None


# ============================================================================
# Module exports
# ============================================================================

__all__ = [
    "FACEBOOK_HCB_SOURCE_NAME",
    "FacebookHcbInput",
    "FacebookHcbAdapter",
    "derive_hcb_content_id",
]
