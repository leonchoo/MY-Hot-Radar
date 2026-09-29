"""
Performance Intelligence — Android Bridge (P3-A.5 / pre-P3-B design).

This module defines the wire contract that a separate "android-collector"
agent must produce for MY Hot Radar to consume. It does NOT contain
any Android / ADB / Facebook / Instagram / YouTube integration code.

What this module IS:

  * The agreed shape of a single Android observation that an external
    android-collector agent will hand to MY Hot Radar.
  * A translation layer from that shape to P3-A's AdapterObservation.
  * Quality checks specific to Android-collected observations.
  * Evidence reference types and validation rules.

What this module IS NOT:

  * It does NOT implement any Android UI observation.
  * It does NOT make any assumption that Facebook / Instagram /
    YouTube / TikTok / X exposes any specific engagement metric.
  * It does NOT log in, scrape, or extract credentials on behalf
    of any platform.
  * It does NOT modify Radar / Candidate / Website / politics /
    scheduler / source registry.

Strict data semantics (inherited from P3-A):

  * None  = unknown / not observed by the human-visible page
  * 0     = explicitly observed as zero
  * The two cases are NEVER conflated. There is no path that
    coerces a None into a 0 anywhere in this module.

  * Engagement metrics (likes / comments / shares / views /
    reposts) are independently Optional. Missing is per-metric.

  * Unknown image features (has_face / face_count / etc.) stay
    None. They are NEVER coerced to False.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

from .enums import Platform
from .validation import ValidationError, is_valid_url, parse_timestamp_any


# ============================================================================
# Evidence reference types
# ============================================================================

class EvidenceType(str, Enum):
    """How the observation was captured on-device.

    Evidence is METADATA ONLY. Reference paths point to files on the
    android-collector host; binary content is never embedded in
    Performance JSON.
    """
    SCREENSHOT = "SCREENSHOT"     # bitmap of the device screen
    UI_TEXT = "UI_TEXT"           # text extracted via uiautomator / similar
    UI_NODE = "UI_NODE"           # structured UI hierarchy dump
    OCR = "OCR"                   # OCR-extracted text from a screenshot
    COMPOSITE = "COMPOSITE"       # multiple evidence types combined


# ============================================================================
# Evidence dataclass
# ============================================================================

@dataclass
class Evidence:
    """A reference to the on-device evidence backing an observation.

    This is metadata, not content. The ``reference`` field points to
    a file path on the android-collector host. The actual binary
    (PNG screenshot, UI dump XML, OCR text) lives at that path; it
    is NEVER inlined in Performance JSON.

    Fields:
        evidence_type      what kind of evidence this is
        reference          path or URL where the evidence artifact lives
        captured_at        when the artifact was captured on-device
        screen_width       device screen width in pixels (when relevant)
        screen_height      device screen height in pixels (when relevant)
        device_model       device model identifier (when known)
        os_version         Android version (when known)
        notes              free-text notes (no fabricated metrics here)
    """
    evidence_type: EvidenceType
    reference: str
    captured_at: str
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None
    device_model: Optional[str] = None
    os_version: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evidence_type"] = self.evidence_type.value
        return d


# ============================================================================
# Android observation input (the wire format from android-collector)
# ============================================================================

@dataclass
class AndroidObservationInput:
    """The wire shape android-collector hands to MY Hot Radar.

    This is the AGREED contract. The android-collector Agent is
    responsible for producing rows in this shape. MY Hot Radar
    translates this into ``AdapterObservation`` via
    ``to_adapter_observation()``.

    Every field is documented below. Anything not provided by the
    android-collector MUST be left as None — it must NOT be guessed
    or filled with 0.

    Required fields:
        observation_id    unique id of THIS observation (separate from
                          the post's content_id — one post can have
                          many observations over time)
        platform          which platform the post was observed on
        observed_at       when the observation was recorded (UTC ISO)
        publisher         the page / account / channel name as seen
                          on the public page
        post_url          URL of the specific post (or story / reel /
                          video page)

    Optional content fields:
        page_url          URL of the page / account (if different
                          from post_url)
        title             title of the post (when one is shown)
        caption           post body / caption text (when present)
        published_at      timestamp on the post itself (if visible)

    Engagement metrics (each independently Optional):
        views, likes, comments, shares, reposts

    Evidence (optional but strongly recommended):
        evidence          an Evidence record describing how this
                          observation was captured

    Diagnostics:
        retrieval_status  outcome of the capture attempt
        unavailable_reason  explanation when retrieval_status is
                          not AVAILABLE
        notes             free-text notes — observations about the
                          page state ("post removed", "not signed in
                          account", "scroll position 2 of 5"). NOT
                          a metric.
    """
    observation_id: str
    platform: Platform
    observed_at: str
    publisher: str
    post_url: str
    retrieval_status: str = "AVAILABLE"
    unavailable_reason: Optional[str] = None
    page_url: Optional[str] = None
    title: Optional[str] = None
    caption: Optional[str] = None
    published_at: Optional[str] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    reposts: Optional[int] = None
    evidence: Optional[Evidence] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["platform"] = self.platform.value
        if self.evidence is not None:
            d["evidence"] = self.evidence.to_dict()
        return d


# ============================================================================
# Validation
# ============================================================================

@dataclass
class AndroidValidationIssue:
    """A single issue found while validating an Android observation."""
    field_name: str
    issue: str
    observation_id: Optional[str] = None


def validate_android_observation(
    obs: AndroidObservationInput,
) -> List[AndroidValidationIssue]:
    """Run quality checks against one Android observation input.

    Rules (mirror P3-A's check_observation_quality, plus Android-specific):

      * observation_id is non-empty
      * platform is a known Platform enum value
      * observed_at is a parseable timestamp
      * publisher is a non-empty string
      * post_url is a safe URL
      * published_at, if present, is parseable AND <= observed_at
      * each metric must be None or a non-negative int
      * retrieval_status, when set, must be one of the known values
      * evidence, when present, must have a valid EvidenceType and
        a non-empty reference + parseable captured_at
      * observation_id may be reused across observations of the SAME
        post at different observed_at timestamps — this is expected
        and supported (delta computation)
    """
    issues: List[AndroidValidationIssue] = []
    oid = obs.observation_id if obs.observation_id else None

    if not obs.observation_id or not isinstance(obs.observation_id, str):
        issues.append(AndroidValidationIssue(
            "observation_id", "must be a non-empty string", oid))
    if not isinstance(obs.platform, Platform):
        issues.append(AndroidValidationIssue(
            "platform", f"must be a Platform enum, got {type(obs.platform).__name__}", oid))
    if parse_timestamp_any(obs.observed_at) is None:
        issues.append(AndroidValidationIssue(
            "observed_at", f"not a valid ISO 8601 timestamp: {obs.observed_at!r}", oid))
    if not obs.publisher or not isinstance(obs.publisher, str):
        issues.append(AndroidValidationIssue(
            "publisher", "must be a non-empty string", oid))
    if not obs.post_url or not is_valid_url(obs.post_url):
        issues.append(AndroidValidationIssue(
            "post_url", f"must be a safe URL: {obs.post_url!r}", oid))
    if obs.page_url is not None and not is_valid_url(obs.page_url):
        issues.append(AndroidValidationIssue(
            "page_url", f"must be a safe URL: {obs.page_url!r}", oid))
    if obs.published_at is not None:
        if parse_timestamp_any(obs.published_at) is None:
            issues.append(AndroidValidationIssue(
                "published_at", f"not a valid ISO 8601 timestamp: {obs.published_at!r}", oid))
        else:
            t_pub = parse_timestamp_any(obs.published_at)
            t_obs = parse_timestamp_any(obs.observed_at)
            if t_pub is not None and t_obs is not None and t_pub > t_obs:
                issues.append(AndroidValidationIssue(
                    "published_at",
                    f"published_at {obs.published_at} is after observed_at {obs.observed_at}",
                    oid))
    for fname in ("views", "likes", "comments", "shares", "reposts"):
        v = getattr(obs, fname)
        if v is not None and (not isinstance(v, int) or v < 0):
            issues.append(AndroidValidationIssue(
                fname, f"must be None or non-negative int, got {v!r}", oid))
    valid_statuses = {"AVAILABLE", "PARTIAL", "UNAVAILABLE",
                      "RATE_LIMITED", "NOT_SUPPORTED",
                      "INVALID_SOURCE", "ERROR"}
    if obs.retrieval_status not in valid_statuses:
        issues.append(AndroidValidationIssue(
            "retrieval_status",
            f"unknown status: {obs.retrieval_status!r}", oid))
    if obs.evidence is not None:
        ev = obs.evidence
        if not isinstance(ev.evidence_type, EvidenceType):
            issues.append(AndroidValidationIssue(
                "evidence.evidence_type",
                f"must be an EvidenceType enum, got {type(ev.evidence_type).__name__}",
                oid))
        if not ev.reference or not isinstance(ev.reference, str):
            issues.append(AndroidValidationIssue(
                "evidence.reference",
                "must be a non-empty string", oid))
        if parse_timestamp_any(ev.captured_at) is None:
            issues.append(AndroidValidationIssue(
                "evidence.captured_at",
                f"not a valid ISO 8601 timestamp: {ev.captured_at!r}", oid))
        for dim in ("screen_width", "screen_height"):
            v = getattr(ev, dim)
            if v is not None and (not isinstance(v, int) or v <= 0):
                issues.append(AndroidValidationIssue(
                    f"evidence.{dim}",
                    f"must be None or positive int, got {v!r}", oid))
    return issues


def validate_android_batch(
    observations: List[AndroidObservationInput],
) -> List[AndroidValidationIssue]:
    """Validate a batch; also check for duplicate observation_id."""
    issues: List[AndroidValidationIssue] = []
    for obs in observations:
        issues.extend(validate_android_observation(obs))
    # Per-batch: same observation_id may appear multiple times ONLY
    # if observed_at differs. Otherwise it's a duplicate.
    by_id: Dict[str, List[AndroidObservationInput]] = {}
    for obs in observations:
        by_id.setdefault(obs.observation_id, []).append(obs)
    for oid, group in by_id.items():
        if len(group) > 1:
            timestamps = {g.observed_at for g in group}
            if len(timestamps) != len(group):
                issues.append(AndroidValidationIssue(
                    "observation_id",
                    f"duplicate observation_id {oid!r} with same observed_at",
                    oid))
    return issues


# ============================================================================
# Translation to P3-A AdapterObservation
# ============================================================================

# Public constant that android-collector writes into AdapterObservation.source
ANDROID_BRIDGE_SOURCE_PREFIX = "android_bridge"


def derive_content_id(post_url: str) -> str:
    """Derive a deterministic content_id from the post URL.

    This MUST match the form used elsewhere so P1 dedup works
    correctly. Different observations of the SAME post (same URL)
    MUST produce the same content_id; the observation_id is what
    distinguishes the individual capture event.
    """
    import hashlib
    payload = {"kind": "android_bridge_content_id_v1", "post_url": post_url}
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"))
    return "ci_" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]


def to_adapter_observation(
    obs: AndroidObservationInput,
) -> Dict[str, Any]:
    """Translate an Android observation input to a P3-A
    ``AdapterObservation`` shape (returned as dict so this module
    stays decoupled from the runtime shape of P3-A's dataclass).

    Mapping rules:

      * content_id  = derive_content_id(post_url)
      * platform    = obs.platform (preserved per-row)
      * observed_at = obs.observed_at
      * source      = ANDROID_BRIDGE_SOURCE_PREFIX + "::" + observation_id
                       (so a single batch can be traced back to the
                       exact android-collector observation)
      * source_url  = post_url
      * url         = post_url
      * page_url    = stored in extra["page_url"] if present
      * publisher   = stored in extra["publisher"] (P3-A does not
                       have a publisher field; we keep it in extra
                       until P3-B formalizes it)
      * title / caption / published_at map directly
      * metrics map directly (None preserved; never coerced)
      * retrieval_status maps directly
      * unavailable_reason maps directly
      * evidence, when present, is stored in extra["evidence"] as a
        dict (no binary content embedded)

    The returned dict has the exact key names P3-A's
    ``AdapterObservation`` expects (minus the dataclass instance).
    Callers construct the dataclass from this dict.
    """
    content_id = derive_content_id(obs.post_url)
    source = f"{ANDROID_BRIDGE_SOURCE_PREFIX}::{obs.observation_id}"
    extra: Dict[str, Any] = {"publisher": obs.publisher}
    if obs.page_url is not None:
        extra["page_url"] = obs.page_url
    if obs.caption is not None:
        extra["caption"] = obs.caption
    if obs.evidence is not None:
        extra["evidence"] = obs.evidence.to_dict()
    if obs.notes is not None:
        extra["notes"] = obs.notes
    return {
        "content_id": content_id,
        "platform": obs.platform,
        "observed_at": obs.observed_at,
        "retrieval_status": obs.retrieval_status,
        "source": source,
        "source_url": obs.post_url,
        "title": obs.title or "",
        "published_at": obs.published_at,
        "url": obs.post_url,
        "views": obs.views,
        "likes": obs.likes,
        "comments": obs.comments,
        "shares": obs.shares,
        "reposts": obs.reposts,
        "unavailable_reason": obs.unavailable_reason,
        "extra": extra,
    }


def batch_to_adapter_dicts(
    observations: List[AndroidObservationInput],
) -> List[Dict[str, Any]]:
    """Translate a whole batch."""
    return [to_adapter_observation(o) for o in observations]


def build_adapter_result_from_android_batch(
    source_name: str,
    platform: Platform,
    started_at: str,
    finished_at: str,
    observations: List[AndroidObservationInput],
) -> Dict[str, Any]:
    """Build a P3-A AdapterResult-shaped dict from an Android batch.

    Computes the overall retrieval_status from per-row statuses
    (mirrors SyntheticAdapter's logic in P3-A):

      * all AVAILABLE           -> AVAILABLE
      * some AVAILABLE, others  -> PARTIAL
      * any RATE_LIMITED        -> RATE_LIMITED
      * any ERROR               -> ERROR
      * all unavailable/etc.    -> UNAVAILABLE
      * empty batch             -> UNAVAILABLE
    """
    obs_dicts = batch_to_adapter_dicts(observations)
    statuses = {o.retrieval_status for o in observations}
    if not observations:
        overall = "UNAVAILABLE"
    elif statuses == {"AVAILABLE"}:
        overall = "AVAILABLE"
    elif "AVAILABLE" in statuses:
        overall = "PARTIAL"
    elif "RATE_LIMITED" in statuses:
        overall = "RATE_LIMITED"
    elif "ERROR" in statuses:
        overall = "ERROR"
    else:
        overall = "UNAVAILABLE"
    return {
        "source_name": source_name,
        "platform": platform,
        "started_at": started_at,
        "finished_at": finished_at,
        "retrieval_status": overall,
        "observations": obs_dicts,
        "errors": [],
    }


# ============================================================================
# Public re-exports
# ============================================================================

__all__ = [
    "EvidenceType",
    "Evidence",
    "AndroidObservationInput",
    "AndroidValidationIssue",
    "ANDROID_BRIDGE_SOURCE_PREFIX",
    "validate_android_observation",
    "validate_android_batch",
    "derive_content_id",
    "to_adapter_observation",
    "batch_to_adapter_dicts",
    "build_adapter_result_from_android_batch",
]
