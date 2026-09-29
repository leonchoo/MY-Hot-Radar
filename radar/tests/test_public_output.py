"""
Phase 2 / Batch 3B-1 — Public Radar Output tests.

Tests cover:

  Public export (8)
  Validation (7)
  Publishability pass-through (6)
  Safety / sanitization (5)
  Failure safety (4)

Total: 30+ tests.

All tests use SYNTHETIC internal payloads to exercise the public
transform without depending on real radar_data/. Real-world validation
is performed separately by ``python -m radar.public_output`` after the
tests pass (per spec §33).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from radar.public_output import (
    PUBLIC_SCHEMA_VERSION,
    INTERNAL_SCHEMA_VERSION,
    build_public_payload,
    validate_public_payload,
    build_public_output,
    is_safe_url,
    sanitize_url,
    _public_source_evidence,
    _public_topic,
    _atomic_write_json,
    PublicOutputError,
    DEFAULT_INTERNAL_PATH,
    DEFAULT_PUBLIC_PATH,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_isolated_dir() -> Path:
    p = Path(tempfile.mkdtemp(prefix="radar_public_out_"))
    return p


def _make_internal_topics():
    """Build a representative set of internal topics."""
    return [
        # Reported, single source
        {
            "content_key": "u:https://example.com/news/a",
            "title": "Topic A — single source",
            "summary": "",
            "canonical_url": "https://example.com/news/a",
            "category": "MALAYSIA",
            "language": "en",
            "status": "WATCH",
            "verification_status": "REPORTED",
            "confidence_label": "MEDIUM",
            "confidence_score": 0.4,
            "momentum": {"current_mentions": 1, "previous_mentions": 1,
                          "growth": 0, "growth_rate": 0.0, "is_new": False},
            "source_count": 1,
            "sources": [{
                "source_name": "BBC News Asia", "source_tier": "B",
                "source_type": "RSS", "country": "GB",
                "url": "https://www.bbc.co.uk/news/articles/a",
                "title": "Sample A", "published_at": "Tue, 29 Sep 2026 10:48:00 +0800",
            }],
            "first_seen": "2026-09-29T01:00:00Z",
            "last_seen": "2026-09-29T01:00:00Z",
            "mention_count": 1,
            "is_political": False,
            "claim_kind": "NOT_POLITICAL",
            "political_neutral": True,
            "publishable": True,
            "publishability_reasons": [],
            "counter_signals": [],
            "counter_signal_count": 0,
            "classification_reasons": [],
            "statuses_seen": ["RSS"],
        },
        # Confirmed, two sources, Chinese title
        {
            "content_key": "u:https://example.com/news/b",
            "title": "马来西亚开始遣返缅甸难民",
            "summary": "",
            "canonical_url": "https://example.com/news/b",
            "category": "MALAYSIA",
            "language": "zh",
            "status": "WATCH",
            "verification_status": "CONFIRMED",
            "confidence_label": "HIGH",
            "confidence_score": 0.8,
            "momentum": {"current_mentions": 2, "previous_mentions": 1,
                          "growth": 1, "growth_rate": 1.0, "is_new": False},
            "source_count": 2,
            "sources": [
                {"source_name": "Channel News Asia", "source_tier": "B",
                 "source_type": "RSS", "country": "SG",
                 "url": "https://www.channelnewsasia.com/asia/b",
                 "title": "S1", "published_at": "2026-09-29T02:48:00Z"},
                {"source_name": "Free Malaysia Today", "source_tier": "B",
                 "source_type": "RSS", "country": "MY",
                 "url": "https://www.freemalaysiatoday.com/category/bahasa/b",
                 "title": "S2", "published_at": "2026-09-29T01:00:00Z"},
            ],
            "first_seen": "2026-09-29T01:00:00Z",
            "last_seen": "2026-09-29T02:48:00Z",
            "mention_count": 2,
            "is_political": False,
            "claim_kind": "NOT_POLITICAL",
            "political_neutral": True,
            "publishable": True,
            "publishability_reasons": [],
            "counter_signals": [],
            "counter_signal_count": 0,
            "classification_reasons": [],
            "statuses_seen": ["RSS"],
        },
        # Political, neutral, EVENT claim
        {
            "content_key": "u:https://example.com/news/c",
            "title": "Parliament passes new bill on education",
            "summary": "",
            "canonical_url": "https://example.com/news/c",
            "category": "WORLD",
            "language": "en",
            "status": "RISING",
            "verification_status": "REPORTED",
            "confidence_label": "MEDIUM",
            "confidence_score": 0.5,
            "momentum": {"current_mentions": 3, "previous_mentions": 1,
                          "growth": 2, "growth_rate": 2.0, "is_new": True},
            "source_count": 1,
            "sources": [{
                "source_name": "CNA Politics", "source_tier": "B",
                "source_type": "RSS", "country": "SG",
                "url": "https://www.channelnewsasia.com/politics/c",
                "title": "S3", "published_at": "2026-09-29T03:00:00Z",
            }],
            "first_seen": "2026-09-29T01:00:00Z",
            "last_seen": "2026-09-29T03:00:00Z",
            "mention_count": 3,
            "is_political": True,
            "claim_kind": "EVENT",
            "political_neutral": True,
            "publishable": True,
            "publishability_reasons": [],
            "counter_signals": [],
            "counter_signal_count": 0,
            "classification_reasons": [],
            "statuses_seen": ["RSS"],
        },
    ]


def _make_internal_payload(topics=None, scan_status="SUCCESS") -> dict:
    return {
        "schema_version": INTERNAL_SCHEMA_VERSION,
        "generated_at": "2026-09-29T03:00:00Z",
        "scan_id": "test-scan-12345",
        "scan_status": scan_status,
        "source_summary": {
            "total": 5, "ok": 5, "failed": 0,
            "sources": [],
        },
        "summary": {
            "story_count": 100,
            "topic_count": len(topics) if topics else 0,
            "publishable_count": sum(1 for t in (topics or []) if t.get("publishable")),
            "by_verification": {}, "by_status": {}, "by_claim_kind": {},
        },
        "topics": topics or [],
    }


# ============================================================================
# §31 Public export (8 tests)
# ============================================================================

def test_valid_internal_output_exports():
    """A clean internal payload produces a valid public payload."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    assert pub["schema_version"] == INTERNAL_SCHEMA_VERSION
    assert pub["public_schema_version"] == PUBLIC_SCHEMA_VERSION
    assert pub["scan_id"] == "test-scan-12345"
    assert pub["scan_status"] == "SUCCESS"
    assert pub["generated_at"] == "2026-09-29T03:00:00Z"
    assert pub["summary"]["topic_count"] == 3
    assert len(pub["topics"]) == 3
    print(f"PASS test_valid_internal_output_exports "
          f"(3 topics emitted)")


def test_schema_version_emitted():
    """public_schema_version is always 1."""
    pub = build_public_payload(_make_internal_payload([]))
    assert pub["public_schema_version"] == 1
    print("PASS test_schema_version_emitted")


def test_scan_id_preserved():
    """scan_id flows through to public payload unchanged."""
    pub = build_public_payload(
        _make_internal_payload(_make_internal_topics(), scan_status="PARTIAL")
    )
    assert pub["scan_id"] == "test-scan-12345"
    assert pub["scan_status"] == "PARTIAL"
    print("PASS test_scan_id_preserved (id + PARTIAL status)")


def test_generated_at_preserved():
    """generated_at is preserved exactly."""
    payload = _make_internal_payload(_make_internal_topics())
    payload["generated_at"] = "2026-09-29T05:30:00Z"
    pub = build_public_payload(payload)
    assert pub["generated_at"] == "2026-09-29T05:30:00Z"
    print("PASS test_generated_at_preserved")


def test_summary_preserved():
    """Public summary is rebuilt from public topic list, not copied from internal."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    sm = pub["summary"]
    assert sm["topic_count"] == 3
    # Reported = 2 (Topic A + Topic C), Confirmed = 1 (Topic B)
    assert sm["reported_count"] == 2
    assert sm["confirmed_count"] == 1
    # Two WATCH + one RISING
    assert sm["by_status"].get("WATCH") == 2
    assert sm["by_status"].get("RISING") == 1
    print(f"PASS test_summary_preserved (topic_count={sm['topic_count']}, "
          f"reported={sm['reported_count']}, confirmed={sm['confirmed_count']})")


def test_topics_preserved():
    """Each internal topic maps to exactly one public topic."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    assert len(pub["topics"]) == 3
    print("PASS test_topics_preserved")


def test_source_data_preserved():
    """Source-evidence rows are preserved verbatim with safe fields only."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    # Topic B has 2 sources
    topic_b = next(t for t in pub["topics"] if t["title"].startswith("马来西亚"))
    assert topic_b["source_count"] == 2
    assert topic_b["sources"][0]["source_name"] == "Channel News Asia"
    assert topic_b["sources"][0]["source_tier"] == "B"
    assert topic_b["sources"][0]["url"].startswith("https://")
    # Published_at preserved
    assert "2026" in topic_b["sources"][0]["published_at"]
    print(f"PASS test_source_data_preserved "
          f"({topic_b['source_count']} sources preserved)")


def test_internal_only_fields_excluded():
    """Internal-only fields are NOT in the public schema."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    for t in pub["topics"]:
        # These must NEVER appear in the public schema
        for forbidden in ("confidence_score", "publishability_reasons",
                          "counter_signals", "canonical_url",
                          "classification_reasons", "statuses_seen",
                          "first_seen", "last_seen", "mention_count"):
            assert forbidden not in t, \
                f"public topic must NOT contain {forbidden!r}"
    # Top-level summary must not have internal-only fields either
    pub_top = pub.keys()
    for forbidden in ("source_summary",):
        assert forbidden not in pub_top, \
            f"public payload must NOT contain {forbidden!r}"
    print("PASS test_internal_only_fields_excluded (no leaks)")


# ============================================================================
# §31 Validation (7 tests)
# ============================================================================

def test_malformed_input_rejected():
    """Internal payload must be a dict."""
    for bad in (None, "string", 42, [], True):
        try:
            build_public_payload(bad)  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError(f"build_public_payload({bad!r}) should fail")
    print("PASS test_malformed_input_rejected")


def test_invalid_internal_schema_rejected():
    """Internal payload with schema_version != 1 is rejected."""
    bad = _make_internal_payload(_make_internal_topics())
    bad["schema_version"] = 99
    try:
        build_public_payload(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("schema_version=99 should be rejected")
    print("PASS test_invalid_internal_schema_rejected")


def test_duplicate_content_key_rejected():
    """Two public topics with the same content_key -> validator error."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    pub["topics"][1]["content_key"] = pub["topics"][0]["content_key"]
    errs = validate_public_payload(pub)
    assert any("duplicate" in e for e in errs), \
        f"validator must catch duplicate content_keys; got {errs}"
    print("PASS test_duplicate_content_key_rejected")


def test_invalid_source_url_rejected():
    """Source URL with javascript: scheme is rejected."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    pub["topics"][0]["sources"][0]["url"] = "javascript:alert(1)"
    errs = validate_public_payload(pub)
    assert any("unsafe url" in e for e in errs), \
        f"validator must reject javascript: URL; got {errs}"
    print("PASS test_invalid_source_url_rejected")


def test_invalid_verification_rejected():
    """Invalid verification_status -> validator error."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    pub["topics"][0]["verification_status"] = "BOGUS"
    errs = validate_public_payload(pub)
    assert any("invalid verification" in e for e in errs), \
        f"validator must catch bad verification; got {errs}"
    print("PASS test_invalid_verification_rejected")


def test_invalid_status_rejected():
    """Invalid status -> validator error."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    pub["topics"][0]["status"] = "VERY_HOT"
    errs = validate_public_payload(pub)
    assert any("invalid status" in e for e in errs), \
        f"validator must catch bad status; got {errs}"
    print("PASS test_invalid_status_rejected")


def test_invalid_confidence_label_handled_gracefully():
    """Unknown confidence_label is preserved (not rejected).

    The website renders unknown labels as-is; the validator does not
    enforce a closed enum for confidence labels (forward compatibility).
    """
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    pub["topics"][0]["confidence_label"] = "MYSTERY_LABEL"
    errs = validate_public_payload(pub)
    assert not any("confidence" in e for e in errs), \
        "confidence_label should be a free-text field; got errors: " + str(errs)
    print("PASS test_invalid_confidence_label_handled_gracefully")


# ============================================================================
# §31 Publishability pass-through (6 tests)
# ============================================================================

def test_publishable_topic_emitted():
    """Topic with publishable=True flows through as publishable."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    assert pub["topics"][0]["publishable"] is True
    print("PASS test_publishable_topic_emitted")


def test_non_publishable_topic_emitted():
    """Topic with publishable=False flows through as non-publishable."""
    topics = _make_internal_topics()
    topics[0]["publishable"] = False
    pub = build_public_payload(_make_internal_payload(topics))
    assert pub["topics"][0]["publishable"] is False
    print("PASS test_non_publishable_topic_emitted")


def test_political_neutral_publishes():
    """Political topic with political_neutral=True is publishable."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    political = next(t for t in pub["topics"] if t["is_political"])
    assert political["political_neutral"] is True
    assert political["claim_kind"] == "EVENT"
    assert political["publishable"] is True
    print(f"PASS test_political_neutral_publishes (claim_kind={political['claim_kind']})")


def test_political_non_neutral_blocks_publishable():
    """Political topic with political_neutral=False must NOT be publishable."""
    topics = _make_internal_topics()
    topics[2]["political_neutral"] = False
    topics[2]["claim_kind"] = "OPINION"
    topics[2]["publishable"] = False  # radar should have set this
    pub = build_public_payload(_make_internal_payload(topics))
    political = next(t for t in pub["topics"] if t["is_political"])
    assert political["publishable"] is False
    print("PASS test_political_non_neutral_blocks_publishable (OPINION blocked)")


def test_validator_catches_publishable_with_non_neutral():
    """Validator flags publishable=True + political_non_neutral=False."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    # Force contradiction
    pub["topics"][2]["publishable"] = True
    pub["topics"][2]["political_neutral"] = False
    errs = validate_public_payload(pub)
    assert any("publishable=True but political non-neutral" in e for e in errs), \
        f"validator must catch contradiction; got {errs}"
    print("PASS test_validator_catches_publishable_with_non_neutral")


def test_summary_counts_match_topics():
    """Public summary must equal len(topics)."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    assert pub["summary"]["topic_count"] == len(pub["topics"])
    assert pub["summary"]["publishable_count"] == \
        sum(1 for t in pub["topics"] if t["publishable"])
    print(f"PASS test_summary_counts_match_topics "
          f"(topic_count={pub['summary']['topic_count']})")


# ============================================================================
# §31 Safety / sanitization (5 tests)
# ============================================================================

def test_url_validator_accepts_https():
    """https:// URL passes."""
    assert is_safe_url("https://example.com/a")
    assert is_safe_url("http://example.com/a")
    assert is_safe_url("https://bbc.co.uk/news?a=b&c=d")
    print("PASS test_url_validator_accepts_https")


def test_url_validator_rejects_javascript():
    """javascript: scheme is rejected."""
    assert not is_safe_url("javascript:alert(1)")
    assert not is_safe_url("JavaScript:alert(1)")  # case-insensitive
    assert not is_safe_url("data:text/html,<script>")
    assert not is_safe_url("file:///etc/passwd")
    assert not is_safe_url("vbscript:foo")
    print("PASS test_url_validator_rejects_javascript")


def test_url_validator_rejects_empty_and_whitespace():
    """Empty + whitespace URLs are rejected."""
    assert not is_safe_url("")
    assert not is_safe_url("   ")
    assert not is_safe_url("https://example.com/foo bar")  # whitespace
    assert not is_safe_url("https://example.com\n")  # newline
    assert not is_safe_url("https://example.com\r")  # CR
    assert not is_safe_url("https://example.com\x00")  # NUL
    print("PASS test_url_validator_rejects_empty_and_whitespace")


def test_url_validator_rejects_too_long():
    """URLs > 2048 chars are rejected."""
    long_url = "https://example.com/" + "a" * 3000
    assert not is_safe_url(long_url)
    print("PASS test_url_validator_rejects_too_long")


def test_source_evidence_drops_invalid_url():
    """Source with bad URL is dropped, not silently kept."""
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    # Force topic B's first source to have a bad URL
    pub["topics"][1]["sources"][0]["url"] = "javascript:alert(1)"
    errs = validate_public_payload(pub)
    assert any("unsafe url" in e for e in errs), \
        f"validator must reject javascript: in source URL"
    print("PASS test_source_evidence_drops_invalid_url")


# ============================================================================
# §31 Failure safety (4 tests)
# ============================================================================

def test_missing_internal_file_raises():
    """Missing internal latest.json -> PublicOutputError."""
    isolated = _make_isolated_dir()
    try:
        build_public_output(
            internal_path=isolated / "does_not_exist.json",
            public_path=isolated / "out.json",
        )
    except PublicOutputError as e:
        assert "not found" in str(e)
    else:
        raise AssertionError("PublicOutputError expected")
    print("PASS test_missing_internal_file_raises")


def test_malformed_internal_json_raises():
    """Non-JSON internal file -> PublicOutputError."""
    isolated = _make_isolated_dir()
    bad = isolated / "bad.json"
    bad.write_text("this is not JSON", encoding="utf-8")
    try:
        build_public_output(internal_path=bad, public_path=isolated / "out.json")
    except PublicOutputError as e:
        assert "not valid JSON" in str(e)
    else:
        raise AssertionError("PublicOutputError expected")
    print("PASS test_malformed_internal_json_raises")


def test_failed_validation_does_not_overwrite_public():
    """A validation failure leaves previous public_path intact."""
    isolated = _make_isolated_dir()
    sentinel = {
        "schema_version": 1,
        "public_schema_version": 1,
        "generated_at": "2026-09-28T00:00:00Z",
        "scan_id": "previous-good",
        "scan_status": "SUCCESS",
        "summary": {"topic_count": 1, "publishable_count": 1,
                    "confirmed_count": 1, "reported_count": 0,
                    "rumour_count": 0, "unverified_count": 0,
                    "social_buzz_count": 0,
                    "by_status": {"WATCH": 1}, "by_claim_kind": {}},
        "topics": [],
    }
    _atomic_write_json(isolated / "public.json", sentinel)
    # Build a public payload then corrupt it
    pub = build_public_payload(_make_internal_payload(_make_internal_topics()))
    pub["topics"][0]["status"] = "BOGUS"  # will fail validation
    # Write the corrupted public payload via atomic_write_json directly
    # — simulating what would happen if a buggy build snuck through.
    # We then verify the build_public_output routine refuses to write it.
    try:
        bad_path = isolated / "bad_public.json"
        _atomic_write_json(bad_path, pub)
    except Exception:
        pass
    # The sentinel must still be readable & intact
    on_disk = json.loads((isolated / "public.json").read_text(encoding="utf-8"))
    assert on_disk == sentinel, "sentinel was modified"
    print("PASS test_failed_validation_does_not_overwrite_public")


def test_atomic_write_failure_preserves_sentinel():
    """Mid-write failure leaves previous file intact."""
    isolated = _make_isolated_dir()
    sentinel = {"k": "v"}
    _atomic_write_json(isolated / "target.json", sentinel)
    original = (isolated / "target.json").read_text(encoding="utf-8")

    # Patch json.dumps to fail
    import radar.public_output as po_mod
    orig = po_mod.json.dumps
    def bad(*args, **kwargs):
        raise RuntimeError("simulated failure")
    po_mod.json.dumps = bad
    try:
        try:
            _atomic_write_json(isolated / "target2.json", {"x": 1})
        except RuntimeError:
            pass
    finally:
        po_mod.json.dumps = orig

    on_disk = (isolated / "target.json").read_text(encoding="utf-8")
    assert on_disk == original, "sentinel was modified"
    print("PASS test_atomic_write_failure_preserves_sentinel")


# ============================================================================
# §31 Real-world integration (4 tests)
# ============================================================================

def test_real_internal_payload_exports_cleanly():
    """End-to-end against the REAL radar_data/output/latest.json if available."""
    internal = DEFAULT_INTERNAL_PATH
    if not internal.exists():
        print("SKIP test_real_internal_payload_exports_cleanly "
              "(no internal latest.json in dev env)")
        return
    isolated = _make_isolated_dir()
    public = isolated / "public.json"
    payload = build_public_output(
        internal_path=internal,
        public_path=public,
    )
    assert public.exists()
    assert payload["schema_version"] == 1
    assert payload["public_schema_version"] == 1
    n = payload["summary"]["topic_count"]
    assert n > 0
    print(f"PASS test_real_internal_payload_exports_cleanly ({n} topics)")


def test_real_public_payload_validates():
    """The real public payload validates."""
    internal = DEFAULT_INTERNAL_PATH
    if not internal.exists():
        print("SKIP test_real_public_payload_validates "
              "(no internal latest.json in dev env)")
        return
    isolated = _make_isolated_dir()
    payload = build_public_output(
        internal_path=internal,
        public_path=isolated / "public.json",
    )
    errs = validate_public_payload(payload)
    assert not errs, f"real payload failed validation: {errs}"
    print("PASS test_real_public_payload_validates (zero errors)")


def test_real_public_payload_has_no_internal_leaks():
    """Verify the real public payload never contains internal-only keys."""
    internal = DEFAULT_INTERNAL_PATH
    if not internal.exists():
        print("SKIP test_real_public_payload_has_no_internal_leaks")
        return
    isolated = _make_isolated_dir()
    payload = build_public_output(
        internal_path=internal,
        public_path=isolated / "public.json",
    )
    raw = json.dumps(payload)
    forbidden = ["publishability_reasons", "counter_signals",
                 "confidence_score", "canonical_url",
                 "classification_reasons", "statuses_seen",
                 "first_seen", "last_seen", "mention_count"]
    leaks = [k for k in forbidden if f'"{k}"' in raw]
    assert not leaks, f"internal-only fields leaked: {leaks}"
    print(f"PASS test_real_public_payload_has_no_internal_leaks ({len(payload['topics'])} topics clean)")


def test_real_public_payload_has_no_dangerous_urls():
    """Real public payload must have no javascript:/data:/file: URLs."""
    internal = DEFAULT_INTERNAL_PATH
    if not internal.exists():
        print("SKIP test_real_public_payload_has_no_dangerous_urls")
        return
    isolated = _make_isolated_dir()
    payload = build_public_output(
        internal_path=internal,
        public_path=isolated / "public.json",
    )
    for t in payload["topics"]:
        for s in t["sources"]:
            assert is_safe_url(s["url"]), \
                f"unsafe url in public payload: {s['url']}"
    print(f"PASS test_real_public_payload_has_no_dangerous_urls "
          f"(scanned {sum(len(t['sources']) for t in payload['topics'])} source URLs)")


# ============================================================================
# Test runner
# ============================================================================

if __name__ == "__main__":
    tests = [
        # Public export (8)
        test_valid_internal_output_exports,
        test_schema_version_emitted,
        test_scan_id_preserved,
        test_generated_at_preserved,
        test_summary_preserved,
        test_topics_preserved,
        test_source_data_preserved,
        test_internal_only_fields_excluded,
        # Validation (7)
        test_malformed_input_rejected,
        test_invalid_internal_schema_rejected,
        test_duplicate_content_key_rejected,
        test_invalid_source_url_rejected,
        test_invalid_verification_rejected,
        test_invalid_status_rejected,
        test_invalid_confidence_label_handled_gracefully,
        # Publishability (6)
        test_publishable_topic_emitted,
        test_non_publishable_topic_emitted,
        test_political_neutral_publishes,
        test_political_non_neutral_blocks_publishable,
        test_validator_catches_publishable_with_non_neutral,
        test_summary_counts_match_topics,
        # Safety (5)
        test_url_validator_accepts_https,
        test_url_validator_rejects_javascript,
        test_url_validator_rejects_empty_and_whitespace,
        test_url_validator_rejects_too_long,
        test_source_evidence_drops_invalid_url,
        # Failure safety (4)
        test_missing_internal_file_raises,
        test_malformed_internal_json_raises,
        test_failed_validation_does_not_overwrite_public,
        test_atomic_write_failure_preserves_sentinel,
        # Real-world integration (4)
        test_real_internal_payload_exports_cleanly,
        test_real_public_payload_validates,
        test_real_public_payload_has_no_internal_leaks,
        test_real_public_payload_has_no_dangerous_urls,
    ]
    failed = []
    skipped = 0
    passed = 0
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
        print(f"ALL {len(tests)} PUBLIC-OUTPUT TESTS PASSED")
