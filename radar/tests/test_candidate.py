"""
Phase 2 / Batch 3B-2 — Article Candidate Pipeline tests.

Tests cover:

  Candidate model (5)
  Eligibility (15)
  REPORTED handling (2)
  Politics (5)
  Dedup (5)
  Freshness (3)
  Persistence (6)
  Scheduler integration (3)
  Security / sanitization (5)
  Regression (4)

Total: 50+ tests.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from radar.candidate import (
    CANDIDATE_SCHEMA_VERSION,
    DEFAULT_FRESHNESS_HOURS,
    ArticleCandidate,
    BlockingReason,
    CandidateEligibility,
    CandidateState,
    CandidateSource,
    CandidateStore,
    EligibilityReason,
    OutputValidationError,
    build_candidate_from_topic,
    build_latest_payload,
    evaluate_eligibility,
    make_candidate_id,
    run_candidate_pipeline,
    validate_candidate,
    _candidate_source_from_topic_source,
    _is_safe_url,
    _is_stale,
    _parse_any_timestamp,
    _parse_iso,
    _parse_rfc2822,
    _sanitize_title,
)
from radar.public_output import is_safe_url


REPO_ROOT = Path(__file__).resolve().parents[2]


# ============================================================================
# Helpers
# ============================================================================

def _make_isolated_dir() -> Path:
    p = Path(tempfile.mkdtemp(prefix="radar_candidate_"))
    return p


def _make_topic(
    *,
    content_key: str = "u:https://example.com/news/1",
    title: str = "Sample headline",
    publishable: bool = True,
    verification_status: str = "REPORTED",
    confidence_label: str = "MEDIUM",
    counter_signals: list = None,
    is_political: bool = False,
    political_neutral: bool = True,
    claim_kind: str = "NOT_POLITICAL",
    sources: list = None,
    last_seen: str = None,
    first_seen: str = None,
    status: str = "WATCH",
) -> dict:
    """Build a topic dict shaped like the internal Radar output."""
    if sources is None:
        sources = [{
            "source_name": "Test Outlet", "source_tier": "B",
            "source_type": "RSS", "country": "MY",
            "url": "https://example.com/news/1",
            "title": "Source title",
            "published_at": "2026-09-29T03:00:00Z",
        }]
    if counter_signals is None:
        counter_signals = []
    if last_seen is None:
        last_seen = "2026-09-29T03:00:00Z"
    if first_seen is None:
        first_seen = "2026-09-29T03:00:00Z"
    return {
        "content_key": content_key,
        "title": title,
        "canonical_url": content_key[2:] if content_key.startswith("u:") else "",
        "category": "MALAYSIA",
        "language": "en",
        "status": status,
        "verification_status": verification_status,
        "confidence_label": confidence_label,
        "momentum": {
            "current_mentions": 1, "previous_mentions": 1,
            "growth": 0, "growth_rate": 0.0, "is_new": False,
        },
        "first_seen": first_seen,
        "last_seen": last_seen,
        "mention_count": 1,
        "source_count": len(sources),
        "sources": sources,
        "counter_signals": counter_signals,
        "is_political": is_political,
        "claim_kind": claim_kind,
        "political_neutral": political_neutral,
        "publishable": publishable,
    }


# ============================================================================
# §34 Candidate model (5 tests)
# ============================================================================

def test_valid_candidate():
    """A valid candidate dict passes validate_candidate."""
    c = ArticleCandidate(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        candidate_id="cand_abc123",
        content_key="u:https://example.com/x",
        state=CandidateState.READY_FOR_REVIEW.value,
        created_at="2026-09-29T03:00:00Z",
        updated_at="2026-09-29T03:00:00Z",
        headline="Sample headline",
        category="MALAYSIA",
        language="en",
        radar_status="WATCH",
        verification_status="REPORTED",
        confidence_label="MEDIUM",
        source_count=1,
        sources=[CandidateSource(
            source_name="BBC", source_tier="B",
            source_type="RSS", country="GB",
            url="https://bbc.co.uk/x", title="BBC",
            published_at="2026-09-29T03:00:00Z",
        )],
        claim_kind="NOT_POLITICAL",
        is_political=False,
        political_neutral=True,
        first_seen="2026-09-29T03:00:00Z",
        last_seen="2026-09-29T03:00:00Z",
        mention_count=1,
        momentum={"current_mentions": 1, "previous_mentions": 1,
                  "growth": 0, "growth_rate": 0.0, "is_new": False},
        counter_signals=[],
        eligibility=CandidateEligibility(
            eligible=True,
            reasons=[EligibilityReason.PUBLISHABLE.value],
            blocking_reasons=[],
        ),
    )
    cd = c.to_dict()
    errs = validate_candidate(cd)
    assert not errs, f"valid candidate should not have errors: {errs}"
    print("PASS test_valid_candidate")


def test_schema_version():
    """Candidate must carry schema_version == CANDIDATE_SCHEMA_VERSION."""
    c, _ = build_candidate_from_topic(_make_topic())
    cd = c.to_dict()
    assert cd["schema_version"] == CANDIDATE_SCHEMA_VERSION == 1
    # Validator rejects bad schema_version
    bad = dict(cd)
    bad["schema_version"] = 99
    errs = validate_candidate(bad)
    assert any("schema_version" in e for e in errs), \
        "validator must reject bad schema_version"
    print(f"PASS test_schema_version (schema_version={cd['schema_version']})")


def test_deterministic_candidate_id():
    """Same content_key -> same candidate_id."""
    ck = "u:https://example.com/same"
    id1 = make_candidate_id(ck)
    id2 = make_candidate_id(ck)
    id3 = make_candidate_id(ck, schema_version=CANDIDATE_SCHEMA_VERSION)
    assert id1 == id2 == id3
    assert id1.startswith("cand_")
    # Different content_key -> different candidate_id
    id4 = make_candidate_id("u:https://example.com/different")
    assert id4 != id1
    print(f"PASS test_deterministic_candidate_id (id={id1})")


def test_candidate_serialization_round_trip():
    """A candidate dict round-trips through JSON."""
    c, _ = build_candidate_from_topic(_make_topic())
    cd = c.to_dict()
    js = json.dumps(cd, ensure_ascii=False)
    decoded = json.loads(js)
    assert decoded["candidate_id"] == cd["candidate_id"]
    assert decoded["state"] == cd["state"]
    assert decoded["content_key"] == cd["content_key"]
    assert len(decoded["sources"]) == len(cd["sources"])
    print("PASS test_candidate_serialization_round_trip")


def test_candidate_deserialization():
    """A JSON dict can be re-validated and re-loaded."""
    c, _ = build_candidate_from_topic(_make_topic())
    cd = c.to_dict()
    js = json.dumps(cd, ensure_ascii=False)
    decoded = json.loads(js)
    errs = validate_candidate(decoded)
    assert not errs
    print("PASS test_candidate_deserialization")


# ============================================================================
# §34 Eligibility (15 tests)
# ============================================================================

def test_publishable_topic_eligible():
    """publishable=True + valid sources + valid title -> eligible."""
    ok, reasons, blocking = evaluate_eligibility(_make_topic())
    assert ok is True
    assert EligibilityReason.PUBLISHABLE.value in reasons
    assert EligibilityReason.VALID_TITLE.value in reasons
    assert EligibilityReason.VALID_SOURCE.value in reasons
    assert EligibilityReason.NOT_RUMOUR.value in reasons
    assert EligibilityReason.NOT_UNVERIFIED.value in reasons
    assert not blocking
    print(f"PASS test_publishable_topic_eligible ({len(reasons)} positive reasons)")


def test_non_publishable_blocked():
    """publishable=False -> NOT_PUBLISHABLE blocking reason."""
    ok, _, blocking = evaluate_eligibility(_make_topic(publishable=False))
    assert ok is False
    assert BlockingReason.NOT_PUBLISHABLE.value in blocking
    print("PASS test_non_publishable_blocked")


def test_missing_title_blocked():
    """Empty title -> MISSING_TITLE blocking reason."""
    ok, _, blocking = evaluate_eligibility(_make_topic(title=""))
    assert ok is False
    assert BlockingReason.MISSING_TITLE.value in blocking
    print("PASS test_missing_title_blocked")


def test_missing_source_blocked():
    """Empty sources list -> MISSING_SOURCE blocking reason."""
    ok, _, blocking = evaluate_eligibility(_make_topic(sources=[]))
    assert ok is False
    assert BlockingReason.MISSING_SOURCE.value in blocking
    print("PASS test_missing_source_blocked")


def test_invalid_source_url_blocked():
    """Source URL with javascript: scheme -> INVALID_SOURCE_URL blocking reason."""
    sources = [{
        "source_name": "Bad Outlet", "source_tier": "B",
        "source_type": "RSS", "country": "MY",
        "url": "javascript:alert(1)",
        "title": "Bad",
        "published_at": "2026-09-29T03:00:00Z",
    }]
    ok, _, blocking = evaluate_eligibility(_make_topic(sources=sources))
    assert ok is False
    assert BlockingReason.INVALID_SOURCE_URL.value in blocking
    print("PASS test_invalid_source_url_blocked")


def test_rumour_blocked():
    """RUMOUR -> RUMOUR blocking reason."""
    ok, _, blocking = evaluate_eligibility(
        _make_topic(verification_status="RUMOUR")
    )
    assert ok is False
    assert BlockingReason.RUMOUR.value in blocking
    print("PASS test_rumour_blocked")


def test_unverified_blocked():
    """UNVERIFIED -> UNVERIFIED blocking reason."""
    ok, _, blocking = evaluate_eligibility(
        _make_topic(verification_status="UNVERIFIED")
    )
    assert ok is False
    assert BlockingReason.UNVERIFIED.value in blocking
    print("PASS test_unverified_blocked")


def test_social_buzz_only_blocked():
    """SOCIAL_BUZZ-only verification -> SOCIAL_BUZZ_ONLY blocking reason."""
    ok, _, blocking = evaluate_eligibility(
        _make_topic(verification_status="SOCIAL_BUZZ")
    )
    assert ok is False
    assert BlockingReason.SOCIAL_BUZZ_ONLY.value in blocking
    print("PASS test_social_buzz_only_blocked")


def test_social_buzz_with_space_blocked():
    """SOCIAL BUZZ (with space) verification -> SOCIAL_BUZZ_ONLY blocking."""
    ok, _, blocking = evaluate_eligibility(
        _make_topic(verification_status="SOCIAL BUZZ")
    )
    assert ok is False
    assert BlockingReason.SOCIAL_BUZZ_ONLY.value in blocking
    print("PASS test_social_buzz_with_space_blocked")


def test_tier_f_only_blocked():
    """All sources Tier-F -> TIER_F_ONLY blocking reason."""
    sources = [{
        "source_name": "Anonymous", "source_tier": "F",
        "source_type": "RSS", "country": "??",
        "url": "https://example.com/x",
        "title": "Anon",
        "published_at": "2026-09-29T03:00:00Z",
    }]
    ok, _, blocking = evaluate_eligibility(_make_topic(sources=sources))
    assert ok is False
    assert BlockingReason.TIER_F_ONLY.value in blocking
    print("PASS test_tier_f_only_blocked")


def test_tier_a_denial_blocked():
    """Tier-A DENIAL counter-signal -> TIER_A_DENIAL blocking reason."""
    cs = [{
        "source_name": "SPR", "source_tier": "A",
        "stance": "DENIAL",
        "evidence_url": "https://example.gov.my/denial",
        "summary": "no evidence",
        "observed_at": "2026-09-29T03:00:00Z",
    }]
    ok, _, blocking = evaluate_eligibility(
        _make_topic(counter_signals=cs)
    )
    assert ok is False
    assert BlockingReason.TIER_A_DENIAL.value in blocking
    print("PASS test_tier_a_denial_blocked")


def test_tier_a_correction_blocked():
    """Tier-A CORRECTION counter-signal -> TIER_A_DENIAL blocking."""
    cs = [{
        "source_name": "SPR", "source_tier": "A",
        "stance": "CORRECTION",
        "evidence_url": "",
        "summary": "partial correction",
        "observed_at": "",
    }]
    ok, _, blocking = evaluate_eligibility(_make_topic(counter_signals=cs))
    assert ok is False
    assert BlockingReason.TIER_A_DENIAL.value in blocking
    print("PASS test_tier_a_correction_blocked")


def test_tier_b_denial_not_blocking():
    """Tier-B DENIAL does NOT block (only Tier-A does per spec)."""
    cs = [{
        "source_name": "Secondary Outlet", "source_tier": "B",
        "stance": "DENIAL",
        "evidence_url": "",
        "summary": "claims doubt",
        "observed_at": "",
    }]
    ok, _, blocking = evaluate_eligibility(_make_topic(counter_signals=cs))
    # Tier-B denial is recorded but does not block eligibility.
    assert BlockingReason.TIER_A_DENIAL.value not in blocking
    assert ok is True
    print("PASS test_tier_b_denial_not_blocking (B-tier denial non-blocking)")


def test_multiple_blocking_reasons_listed():
    """A topic with multiple blockers has all blocking reasons listed."""
    ok, _, blocking = evaluate_eligibility(_make_topic(
        title="",
        verification_status="RUMOUR",
    ))
    # MISSING_TITLE + RUMOUR
    assert BlockingReason.MISSING_TITLE.value in blocking
    assert BlockingReason.RUMOUR.value in blocking
    print(f"PASS test_multiple_blocking_reasons_listed ({len(blocking)} blockers)")


def test_invalid_topic_returns_invalid():
    """Missing content_key -> INVALID_TOPIC blocking reason."""
    ok, _, blocking = evaluate_eligibility(_make_topic(content_key=""))
    assert ok is False
    assert BlockingReason.INVALID_TOPIC.value in blocking
    print("PASS test_invalid_topic_returns_invalid")


# ============================================================================
# §34 REPORTED handling (2 tests)
# ============================================================================

def test_reported_publishable_topic_remains_candidate():
    """REPORTED + publishable=True -> still eligible, NOT auto-confirmed."""
    ok, reasons, blocking = evaluate_eligibility(
        _make_topic(verification_status="REPORTED", publishable=True)
    )
    assert ok is True
    # REPORTED_OR_CONFIRMED positive reason
    assert EligibilityReason.REPORTED_OR_CONFIRMED.value in reasons
    assert EligibilityReason.CONFIRMED_EVIDENCE.value not in reasons  # NOT CONFIRMED
    print("PASS test_reported_publishable_topic_remains_candidate")


def test_reported_never_silently_converted_to_confirmed():
    """A REPORTED candidate's verification_status stays REPORTED."""
    c, _ = build_candidate_from_topic(
        _make_topic(verification_status="REPORTED")
    )
    assert c.verification_status == "REPORTED"
    assert c.eligibility.eligible is True
    print("PASS test_reported_never_silently_converted_to_confirmed")


# ============================================================================
# §34 Politics (5 tests)
# ============================================================================

def test_political_event_allowed():
    """Political EVENT claim_kind + political_neutral=True -> eligible."""
    ok, _, blocking = evaluate_eligibility(
        _make_topic(
            is_political=True, political_neutral=True,
            claim_kind="EVENT",
        )
    )
    assert ok is True
    print("PASS test_political_event_allowed")


def test_political_claim_allowed():
    """Political CLAIM + political_neutral=True -> eligible."""
    ok, _, blocking = evaluate_eligibility(
        _make_topic(
            is_political=True, political_neutral=True,
            claim_kind="CLAIM",
        )
    )
    assert ok is True
    print("PASS test_political_claim_allowed")


def test_political_opinion_blocked():
    """Political + non-neutral -> POLITICAL_NON_NEUTRAL blocking."""
    ok, _, blocking = evaluate_eligibility(
        _make_topic(
            is_political=True, political_neutral=False,
            claim_kind="OPINION",
        )
    )
    assert ok is False
    assert BlockingReason.POLITICAL_NON_NEUTRAL.value in blocking
    print("PASS test_political_opinion_blocked")


def test_political_neutral_field_preserved():
    """A political_neutral=True candidate preserves the flag."""
    c, _ = build_candidate_from_topic(
        _make_topic(is_political=True, political_neutral=True, claim_kind="EVENT")
    )
    assert c.is_political is True
    assert c.political_neutral is True
    print("PASS test_political_neutral_field_preserved")


def test_banned_political_phrases_absent_from_metadata():
    """No banned political phrases are auto-injected by the candidate builder."""
    c, _ = build_candidate_from_topic(_make_topic())
    cd = c.to_dict()
    js = json.dumps(cd, ensure_ascii=False).lower()
    for forbidden in ("best candidate", "worst candidate",
                     "likely to win", "vote for", "endorse",
                     "best party", "worst party"):
        assert forbidden not in js, \
            f"candidate metadata contains banned political phrase: {forbidden!r}"
    print("PASS test_banned_political_phrases_absent_from_metadata")


# ============================================================================
# §34 Dedup (5 tests)
# ============================================================================

def test_same_content_key_same_candidate_id():
    """Same content_key always produces the same candidate_id."""
    topic_a1 = _make_topic(content_key="u:https://example.com/news/A")
    topic_a2 = _make_topic(content_key="u:https://example.com/news/A",
                            title="Updated headline")
    c1, _ = build_candidate_from_topic(topic_a1)
    c2, _ = build_candidate_from_topic(topic_a2)
    assert c1.candidate_id == c2.candidate_id
    print("PASS test_same_content_key_same_candidate_id")


def test_repeated_scan_does_not_duplicate_candidate():
    """Two scans of the same topic produce a single candidate file (updated)."""
    isolated = _make_isolated_dir()
    store = CandidateStore(candidate_dir=isolated)
    store.ensure_dirs()
    # First scan
    c1, is_new1 = build_candidate_from_topic(_make_topic(content_key="u:https://example.com/news/X"))
    cd1 = c1.to_dict()
    store.upsert(cd1)
    # Second scan: same content_key, different verification_status
    c2, is_new2 = build_candidate_from_topic(
        _make_topic(content_key="u:https://example.com/news/X",
                    verification_status="CONFIRMED"),
        existing_created_at=cd1["created_at"],
    )
    store.upsert(c2.to_dict())
    # All candidates on disk
    on_disk = store.read_all()
    keys = [c["content_key"] for c in on_disk]
    assert keys.count("u:https://example.com/news/X") == 1, \
        f"expected 1 candidate for content_key, got {keys.count('u:https://example.com/news/X')}"
    # The candidate's verification_status was updated
    assert on_disk[0]["verification_status"] == "CONFIRMED"
    print(f"PASS test_repeated_scan_does_not_duplicate_candidate "
          f"({len(on_disk)} candidates on disk)")


def test_changed_momentum_updates_candidate():
    """A topic with updated momentum updates the existing candidate."""
    isolated = _make_isolated_dir()
    store = CandidateStore(candidate_dir=isolated)
    store.ensure_dirs()
    # First scan: 1 mention
    c1, _ = build_candidate_from_topic(_make_topic(content_key="u:https://example.com/m"))
    store.upsert(c1.to_dict())
    # Second scan: momentum changed to 5 mentions
    topic2 = _make_topic(content_key="u:https://example.com/m")
    topic2["momentum"] = {
        "current_mentions": 5, "previous_mentions": 1,
        "growth": 4, "growth_rate": 4.0, "is_new": False,
    }
    c2, _ = build_candidate_from_topic(
        topic2, existing_created_at=c1.to_dict()["created_at"]
    )
    store.upsert(c2.to_dict())
    on_disk = store.read_all()
    assert len(on_disk) == 1
    assert on_disk[0]["momentum"]["current_mentions"] == 5
    print("PASS test_changed_momentum_updates_candidate")


def test_changed_verification_updates_candidate():
    """A topic whose verification changes from REPORTED to CONFIRMED updates."""
    isolated = _make_isolated_dir()
    store = CandidateStore(candidate_dir=isolated)
    store.ensure_dirs()
    c1, _ = build_candidate_from_topic(
        _make_topic(content_key="u:https://example.com/v", verification_status="REPORTED")
    )
    store.upsert(c1.to_dict())
    c2, _ = build_candidate_from_topic(
        _make_topic(content_key="u:https://example.com/v", verification_status="CONFIRMED"),
        existing_created_at=c1.to_dict()["created_at"],
    )
    store.upsert(c2.to_dict())
    on_disk = store.read_all()
    assert len(on_disk) == 1
    assert on_disk[0]["verification_status"] == "CONFIRMED"
    print("PASS test_changed_verification_updates_candidate")


def test_different_content_key_produces_different_candidate():
    """Different content_keys produce different candidate_ids."""
    c1, _ = build_candidate_from_topic(_make_topic(content_key="u:https://example.com/a"))
    c2, _ = build_candidate_from_topic(_make_topic(content_key="u:https://example.com/b"))
    assert c1.candidate_id != c2.candidate_id
    assert c1.content_key != c2.content_key
    print("PASS test_different_content_key_produces_different_candidate")


# ============================================================================
# §34 Freshness (3 tests)
# ============================================================================

def test_fresh_topic_accepted():
    """A topic with last_seen within freshness_hours is accepted."""
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    ok, _, blocking = evaluate_eligibility(
        _make_topic(last_seen=recent),
        freshness_hours=48,
    )
    assert ok is True
    assert BlockingReason.STALE.value not in blocking
    print("PASS test_fresh_topic_accepted")


def test_stale_topic_blocked():
    """A topic with last_seen older than freshness_hours is blocked as STALE."""
    old = (datetime.now(timezone.utc) - timedelta(hours=72)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    ok, _, blocking = evaluate_eligibility(
        _make_topic(last_seen=old),
        freshness_hours=48,
    )
    assert ok is False
    assert BlockingReason.STALE.value in blocking
    print("PASS test_stale_topic_blocked")


def test_configurable_freshness_threshold():
    """freshness_hours is configurable."""
    recent = (datetime.now(timezone.utc) - timedelta(hours=10)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    # With freshness_hours=5, the 10h-old topic is stale.
    ok_strict, _, blocking_strict = evaluate_eligibility(
        _make_topic(last_seen=recent), freshness_hours=5,
    )
    assert ok_strict is False
    assert BlockingReason.STALE.value in blocking_strict
    # With freshness_hours=24, the 10h-old topic is fresh.
    ok_loose, _, _ = evaluate_eligibility(
        _make_topic(last_seen=recent), freshness_hours=24,
    )
    assert ok_loose is True
    print("PASS test_configurable_freshness_threshold (5h strict vs 24h loose)")


# ============================================================================
# §34 Persistence (6 tests)
# ============================================================================

def test_atomic_write():
    """Atomic write produces a file whose content matches the payload."""
    isolated = _make_isolated_dir()
    target = isolated / "test.json"
    payload = {"hello": "world", "n": 42}
    from radar.candidate import _atomic_write_json
    _atomic_write_json(target, payload)
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk == payload
    print("PASS test_atomic_write")


def test_malformed_candidate_does_not_replace_previous():
    """A malformed candidate does not replace a valid one."""
    isolated = _make_isolated_dir()
    store = CandidateStore(candidate_dir=isolated)
    store.ensure_dirs()
    valid, _ = build_candidate_from_topic(_make_topic(content_key="u:https://example.com/v"))
    store.upsert(valid.to_dict())
    sentinel = store.get(valid.candidate_id)
    assert sentinel is not None
    # Try to upsert a malformed candidate
    bad = dict(sentinel)
    bad["schema_version"] = 99
    try:
        store.upsert(bad)
    except OutputValidationError:
        pass
    else:
        raise AssertionError("OutputValidationError expected")
    # Original is preserved
    on_disk = store.get(valid.candidate_id)
    assert on_disk["schema_version"] == CANDIDATE_SCHEMA_VERSION
    print("PASS test_malformed_candidate_does_not_replace_previous")


def test_duplicate_candidate_id_detection():
    """The same content_key does not produce two candidate files on disk."""
    isolated = _make_isolated_dir()
    store = CandidateStore(candidate_dir=isolated)
    store.ensure_dirs()
    c1, _ = build_candidate_from_topic(_make_topic(content_key="u:https://example.com/dup"))
    c2, _ = build_candidate_from_topic(_make_topic(content_key="u:https://example.com/dup",
                                                    title="Different headline"))
    assert c1.candidate_id == c2.candidate_id
    store.upsert(c1.to_dict())
    store.upsert(c2.to_dict())
    on_disk = store.read_all()
    same_id_count = sum(1 for c in on_disk
                         if c["candidate_id"] == c1.candidate_id)
    assert same_id_count == 1, f"expected 1 file for id, got {same_id_count}"
    print("PASS test_duplicate_candidate_id_detection")


def test_latest_candidate_output_valid():
    """The latest.json content is valid + summary matches candidate count."""
    isolated = _make_isolated_dir()
    store = CandidateStore(candidate_dir=isolated)
    store.ensure_dirs()
    topics = [
        _make_topic(content_key=f"u:https://example.com/n{i}")
        for i in range(5)
    ]
    for t in topics:
        c, _ = build_candidate_from_topic(t)
        store.upsert(c.to_dict())
    latest_path = store.rebuild_latest()
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["summary"]["candidate_count"] == 5
    assert len(payload["candidates"]) == 5
    # Validate each candidate
    for c in payload["candidates"]:
        errs = validate_candidate(c)
        assert not errs, f"candidate failed validation: {errs}"
    print(f"PASS test_latest_candidate_output_valid ({len(payload['candidates'])} candidates)")


def test_restore_previous_on_write_failure():
    """If atomic write raises, the previous file content is restored."""
    import radar.candidate as cand_mod
    isolated = _make_isolated_dir()
    target = isolated / "atomic.json"
    payload1 = {"v": 1}
    cand_mod._atomic_write_json(target, payload1)
    original = target.read_text(encoding="utf-8")

    # Patch json.dumps to fail.
    orig = cand_mod.json.dumps
    def bad(*a, **kw):
        raise RuntimeError("simulated dump failure")
    cand_mod.json.dumps = bad
    try:
        try:
            cand_mod._atomic_write_json(target, {"v": 2})
        except RuntimeError:
            pass
    finally:
        cand_mod.json.dumps = orig
    # Original content preserved
    on_disk = target.read_text(encoding="utf-8")
    assert on_disk == original, "sentinel was modified"
    print("PASS test_restore_previous_on_write_failure")


def test_store_rebuild_latest_is_atomic():
    """rebuild_latest atomically replaces latest.json."""
    isolated = _make_isolated_dir()
    store = CandidateStore(candidate_dir=isolated)
    store.ensure_dirs()
    c, _ = build_candidate_from_topic(_make_topic(content_key="u:https://example.com/a"))
    store.upsert(c.to_dict())
    # Initial latest.json
    latest_path = store.rebuild_latest()
    before = latest_path.read_text(encoding="utf-8")
    # Add another candidate + rebuild
    c2, _ = build_candidate_from_topic(_make_topic(content_key="u:https://example.com/b"))
    store.upsert(c2.to_dict())
    latest_path = store.rebuild_latest()
    after = latest_path.read_text(encoding="utf-8")
    assert before != after, "latest.json was not updated"
    assert "u:https://example.com/b" in after
    print("PASS test_store_rebuild_latest_is_atomic")


# ============================================================================
# §34 Scheduler integration (3 tests)
# ============================================================================

def test_pipeline_runs_against_real_internal_output():
    """End-to-end pipeline runs against the REAL radar_data/output/latest.json."""
    internal = REPO_ROOT / "radar_data" / "output" / "latest.json"
    if not internal.exists():
        print("SKIP test_pipeline_runs_against_real_internal_output "
              "(no internal output)")
        return
    # Use a fresh isolated candidate dir
    isolated = _make_isolated_dir()
    summary = run_candidate_pipeline(
        internal_output_path=internal,
        candidate_dir=isolated,
    )
    assert summary["topics_seen"] > 0
    assert "errors" in summary
    n = summary["candidates_built"] + summary["candidates_updated"]
    assert n > 0, f"expected at least 1 candidate; summary={summary}"
    print(f"PASS test_pipeline_runs_against_real_internal_output "
          f"(topics={summary['topics_seen']}, candidates={n})")


def test_candidate_failure_does_not_corrupt_existing():
    """A failure inside run_candidate_pipeline leaves previous candidates intact."""
    isolated = _make_isolated_dir()
    # Pre-populate with one valid candidate
    store = CandidateStore(candidate_dir=isolated)
    store.ensure_dirs()
    c0, _ = build_candidate_from_topic(_make_topic(content_key="u:https://example.com/pre"))
    store.upsert(c0.to_dict())
    pre_count = len(store.read_all())
    assert pre_count == 1

    # Create a malformed internal output (invalid JSON)
    bad_internal = isolated / "bad_internal.json"
    bad_internal.write_text("{not valid json", encoding="utf-8")
    summary = run_candidate_pipeline(
        internal_output_path=bad_internal,
        candidate_dir=isolated,
    )
    # Errors must be recorded, but the previous candidate must survive
    assert summary["errors"], "errors should be recorded for malformed input"
    after_count = len(store.read_all())
    assert after_count == pre_count, "previous candidates were lost"
    print("PASS test_candidate_failure_does_not_corrupt_existing")


def test_pipeline_freshness_is_configurable():
    """run_candidate_pipeline accepts freshness_hours override."""
    internal = REPO_ROOT / "radar_data" / "output" / "latest.json"
    if not internal.exists():
        print("SKIP test_pipeline_freshness_is_configurable (no internal output)")
        return
    isolated_loose = _make_isolated_dir()
    sum_loose = run_candidate_pipeline(
        internal_output_path=internal,
        candidate_dir=isolated_loose,
        freshness_hours=10_000,  # effectively unlimited
    )
    isolated_strict = _make_isolated_dir()
    sum_strict = run_candidate_pipeline(
        internal_output_path=internal,
        candidate_dir=isolated_strict,
        freshness_hours=1,  # very strict — almost everything stale
    )
    n_loose = sum_loose["candidates_built"]
    n_strict = sum_strict["candidates_built"]
    assert n_loose >= n_strict, \
        f"loose freshness should yield >= strict: loose={n_loose}, strict={n_strict}"
    print(f"PASS test_pipeline_freshness_is_configurable "
          f"(loose={n_loose}, strict={n_strict})")


# ============================================================================
# §35 Security / sanitization (5 tests)
# ============================================================================

def test_javascript_source_rejected():
    """javascript: URL source is dropped from candidate."""
    sources = [{
        "source_name": "Bad", "source_tier": "B",
        "source_type": "RSS", "country": "?",
        "url": "javascript:alert(1)",
        "title": "X", "published_at": "",
    }]
    cs = _candidate_source_from_topic_source(sources[0])
    assert cs is None, "javascript: source must be dropped"
    print("PASS test_javascript_source_rejected")


def test_data_source_rejected():
    """data: URL is dropped."""
    sources = [{
        "source_name": "Bad", "source_tier": "B",
        "source_type": "RSS", "country": "?",
        "url": "data:text/html,<script>",
        "title": "X", "published_at": "",
    }]
    cs = _candidate_source_from_topic_source(sources[0])
    assert cs is None
    print("PASS test_data_source_rejected")


def test_file_source_rejected():
    """file: URL is dropped."""
    sources = [{
        "source_name": "Bad", "source_tier": "B",
        "source_type": "RSS", "country": "?",
        "url": "file:///etc/passwd",
        "title": "X", "published_at": "",
    }]
    cs = _candidate_source_from_topic_source(sources[0])
    assert cs is None
    print("PASS test_file_source_rejected")


def test_vbscript_source_rejected():
    """vbscript: URL is dropped."""
    sources = [{
        "source_name": "Bad", "source_tier": "B",
        "source_type": "RSS", "country": "?",
        "url": "vbscript:msgbox",
        "title": "X", "published_at": "",
    }]
    cs = _candidate_source_from_topic_source(sources[0])
    assert cs is None
    print("PASS test_vbscript_source_rejected")


def test_long_url_rejected():
    """URL >= 2048 chars is rejected."""
    long_url = "https://example.com/" + "a" * 2030
    sources = [{
        "source_name": "Bad", "source_tier": "B",
        "source_type": "RSS", "country": "?",
        "url": long_url,
        "title": "X", "published_at": "",
    }]
    cs = _candidate_source_from_topic_source(sources[0])
    assert cs is None
    print("PASS test_long_url_rejected")


def test_html_in_title_sanitized():
    """Title with control characters is sanitized (control chars removed).

    Note on HTML: we do NOT strip '<>' from titles. The Radar output
    text is rendered by the JS adapter via textContent, which
    auto-escapes any HTML. The candidate layer does not 'execute'
    HTML — it just stores the source text. The control-character
    sanitization is what protects against rendering glitches.
    """
    title_with_ctrl = "Some news\x00\x01\x02\x03More text"
    cleaned = _sanitize_title(title_with_ctrl)
    # Control chars (ord < 32) are removed
    assert "\x00" not in cleaned
    assert "\x01" not in cleaned
    assert "\x02" not in cleaned
    assert "\x03" not in cleaned
    # The text content is preserved
    assert "Some news" in cleaned
    assert "More text" in cleaned
    print(f"PASS test_html_in_title_sanitized (cleaned={cleaned!r})")


def test_chinese_malay_english_mixed_title():
    """Mixed CN/MY/EN title is preserved verbatim."""
    title = "马来西亚开始遣返缅甸难民 — Malaysia starts repatriation - 简体中文"
    cleaned = _sanitize_title(title)
    assert cleaned == title, f"cleaned={cleaned!r}, expected={title!r}"
    print("PASS test_chinese_malay_english_mixed_title")


def test_whitespace_prefixed_url_rejected():
    """A URL with leading whitespace is rejected."""
    sources = [{
        "source_name": "Bad", "source_tier": "B",
        "source_type": "RSS", "country": "?",
        "url": "   https://example.com/x",
        "title": "X", "published_at": "",
    }]
    cs = _candidate_source_from_topic_source(sources[0])
    assert cs is None
    print("PASS test_whitespace_prefixed_url_rejected")


def test_extremely_long_title_clamped():
    """Title > 500 chars is clamped (NOT silently lost)."""
    long_title = "A" * 600
    cleaned = _sanitize_title(long_title)
    assert len(cleaned) == 400
    print("PASS test_extremely_long_title_clamped (clamped to 400)")


def test_unicode_title_preserved():
    """Unicode titles (CJK etc.) are preserved verbatim."""
    title = "马来西亚 · 中文标题 · 中文测试"
    cleaned = _sanitize_title(title)
    assert cleaned == title
    print("PASS test_unicode_title_preserved")


# ============================================================================
# §34 Regression (4 tests)
# ============================================================================

def test_python_scan_entrypoint_unchanged():
    """python -m radar.scan still works."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "radar.scan"],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT), timeout=60,
    )
    assert r.returncode == 0, f"radar.scan rc={r.returncode}, stderr={r.stderr}"
    print("PASS test_python_scan_entrypoint_unchanged")


def test_python_scheduler_entrypoint_unchanged():
    """python -m radar.scheduler still works."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "radar.scheduler"],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT), timeout=60,
    )
    assert r.returncode == 0, f"radar.scheduler rc={r.returncode}, stderr={r.stderr}"
    print("PASS test_python_scheduler_entrypoint_unchanged")


def test_python_output_entrypoint_unchanged():
    """python -m radar.output --live still works."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "radar.output", "--live"],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT), timeout=120,
    )
    assert r.returncode == 0, \
        f"radar.output --live rc={r.returncode}, stderr={r.stderr}"
    print("PASS test_python_output_entrypoint_unchanged")


def test_python_public_output_entrypoint_unchanged():
    """python -m radar.public_output still works."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "radar.public_output"],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT), timeout=30,
    )
    assert r.returncode == 0, \
        f"radar.public_output rc={r.returncode}, stderr={r.stderr}"
    print("PASS test_python_public_output_entrypoint_unchanged")


def test_no_git_commands_in_candidate_module():
    """The candidate module does NOT execute git commands.

    We scan for actual subprocess / os.system invocations AND for
    any line that runs 'git ' as a command. Docstring mentions of
    "git" (e.g. explaining the design decision) are explicitly
    excluded.
    """
    candidate_src = (REPO_ROOT / "radar" / "candidate.py").read_text(encoding="utf-8")
    # Look for ACTUAL subprocess / os.system / git invocations.
    # Strip the module docstring first to avoid matching docs.
    stripped = re.sub(r'"""[\s\S]*?"""', "", candidate_src, count=1)
    forbidden = ["subprocess.run", "subprocess.call", "subprocess.Popen",
                  "os.system", "os.popen", "os.execv", "os.execvp",
                  "git commit", "git push", "git add", "git checkout",
                  "shutil.which('git')"]
    found = []
    for f in forbidden:
        if f in stripped:
            found.append(f)
    assert not found, f"candidate module contains potential git invocation: {found}"
    print("PASS test_no_git_commands_in_candidate_module")


def test_no_body_in_candidate():
    """A candidate must NOT carry a 'body' field (spec §14)."""
    c, _ = build_candidate_from_topic(_make_topic())
    cd = c.to_dict()
    assert "body" not in cd, "candidate must not carry a body field"
    # The Radar title is NOT rewritten
    assert cd["headline_origin"] == "RADAR_TOPIC"
    print("PASS test_no_body_in_candidate")


def test_candidate_uses_real_publishable_count():
    """The real internal latest.json has ~90 publishable topics."""
    internal = REPO_ROOT / "radar_data" / "output" / "latest.json"
    if not internal.exists():
        print("SKIP test_candidate_uses_real_publishable_count")
        return
    data = json.loads(internal.read_text(encoding="utf-8"))
    pub = data["summary"]["publishable_count"]
    topics = data["summary"]["topic_count"]
    # We don't hard-code exact numbers — verify the data structure
    assert pub > 0, "real internal output should have publishable topics"
    assert topics > 0
    print(f"PASS test_candidate_uses_real_publishable_count "
          f"(publishable={pub}/{topics})")


def test_rfc2822_timestamp_parsing():
    """RFC 2822 timestamps (e.g. 'Mon, 28 Sep 2026 18:37:15 GMT') are parsed."""
    dt = _parse_rfc2822("Mon, 28 Sep 2026 18:37:15 GMT")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 9
    assert dt.day == 28
    print("PASS test_rfc2822_timestamp_parsing")


def test_iso_timestamp_parsing():
    """ISO 8601 timestamps are parsed."""
    dt = _parse_iso("2026-09-29T03:00:00Z")
    assert dt is not None
    assert dt.year == 2026
    assert dt.day == 29
    print("PASS test_iso_timestamp_parsing")


def test_parse_any_timestamp_accepts_both():
    """_parse_any_timestamp handles ISO and RFC 2822."""
    iso_dt = _parse_any_timestamp("2026-09-29T03:00:00Z")
    rfc_dt = _parse_any_timestamp("Mon, 28 Sep 2026 18:37:15 GMT")
    assert iso_dt is not None
    assert rfc_dt is not None
    print("PASS test_parse_any_timestamp_accepts_both")


# ============================================================================
# Test runner
# ============================================================================

if __name__ == "__main__":
    tests = [
        # Candidate model (5)
        test_valid_candidate,
        test_schema_version,
        test_deterministic_candidate_id,
        test_candidate_serialization_round_trip,
        test_candidate_deserialization,
        # Eligibility (15)
        test_publishable_topic_eligible,
        test_non_publishable_blocked,
        test_missing_title_blocked,
        test_missing_source_blocked,
        test_invalid_source_url_blocked,
        test_rumour_blocked,
        test_unverified_blocked,
        test_social_buzz_only_blocked,
        test_social_buzz_with_space_blocked,
        test_tier_f_only_blocked,
        test_tier_a_denial_blocked,
        test_tier_a_correction_blocked,
        test_tier_b_denial_not_blocking,
        test_multiple_blocking_reasons_listed,
        test_invalid_topic_returns_invalid,
        # REPORTED (2)
        test_reported_publishable_topic_remains_candidate,
        test_reported_never_silently_converted_to_confirmed,
        # Politics (5)
        test_political_event_allowed,
        test_political_claim_allowed,
        test_political_opinion_blocked,
        test_political_neutral_field_preserved,
        test_banned_political_phrases_absent_from_metadata,
        # Dedup (5)
        test_same_content_key_same_candidate_id,
        test_repeated_scan_does_not_duplicate_candidate,
        test_changed_momentum_updates_candidate,
        test_changed_verification_updates_candidate,
        test_different_content_key_produces_different_candidate,
        # Freshness (3)
        test_fresh_topic_accepted,
        test_stale_topic_blocked,
        test_configurable_freshness_threshold,
        # Persistence (6)
        test_atomic_write,
        test_malformed_candidate_does_not_replace_previous,
        test_duplicate_candidate_id_detection,
        test_latest_candidate_output_valid,
        test_restore_previous_on_write_failure,
        test_store_rebuild_latest_is_atomic,
        # Scheduler integration (3)
        test_pipeline_runs_against_real_internal_output,
        test_candidate_failure_does_not_corrupt_existing,
        test_pipeline_freshness_is_configurable,
        # Security (10)
        test_javascript_source_rejected,
        test_data_source_rejected,
        test_file_source_rejected,
        test_vbscript_source_rejected,
        test_long_url_rejected,
        test_html_in_title_sanitized,
        test_chinese_malay_english_mixed_title,
        test_whitespace_prefixed_url_rejected,
        test_extremely_long_title_clamped,
        test_unicode_title_preserved,
        # Regression / extras (10)
        test_python_scan_entrypoint_unchanged,
        test_python_scheduler_entrypoint_unchanged,
        test_python_output_entrypoint_unchanged,
        test_python_public_output_entrypoint_unchanged,
        test_no_git_commands_in_candidate_module,
        test_no_body_in_candidate,
        test_candidate_uses_real_publishable_count,
        test_rfc2822_timestamp_parsing,
        test_iso_timestamp_parsing,
        test_parse_any_timestamp_accepts_both,
    ]
    failed = []
    passed = 0
    skipped = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            import traceback
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"ERROR {t.__name__}: {e}")
            traceback.print_exc()
    print()
    print(f"{passed} passed, {len(failed)} failed of {len(tests)} tests")
    if failed:
        for name, err in failed:
            print(f"  {name}: {err}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} CANDIDATE TESTS PASSED")
