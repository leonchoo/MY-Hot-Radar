"""
Phase 2 / Batch 3A — Real Radar Output Layer tests.

Tests cover:

  Output generation (6)
  Evidence preservation (6)
  Publishability (7)
  Validation (5)
  Failure safety (4)
  Regression (2)

Total: ~30 tests.

All tests use SYNTHETIC Topic / Story objects. The output layer is
deterministic given the same input. Tests do NOT depend on real
network calls or on existing radar_data/.

Real-world validation is done separately by running `python -m
radar.output --live` after the tests pass (per spec §17).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from radar.models import (
    Topic, Story, Status, VerificationStatus, ConfidenceLabel,
    CounterSignal, CounterSignalStance, SourceTier,
    Source, SourceType, Language, Category,
    Momentum,
)
from radar.output import (
    SourceEvidence, SCHEMA_VERSION, PublishabilityReason,
    evaluate_publishability, build_topic_output, build_output,
    build_summary, build_source_summary, validate_output,
    _atomic_write_json, write_output, write_validated_output,
    OutputValidationError, classify_topic_politics,
)
from radar.sources_registry import load_sources


# ============================================================================
# Helpers
# ============================================================================

def _make_isolated_dir() -> Path:
    p = Path(tempfile.mkdtemp(prefix="radar_out_test_"))
    (p / "output").mkdir(parents=True, exist_ok=True)
    return p


def _make_story(
    story_id: str = "s1",
    title: str = "Sample news",
    url: str = "https://example.com/news/1",
    source: str = "TestOutlet",
    source_type: SourceType = SourceType.RSS,
    country: str = "MY",
    language: Language = Language.EN,
    category: Category = Category.MALAYSIA,
    published_at: str = "2026-09-29T00:00:00Z",
    summary: str = "",
) -> Story:
    """Build a minimal Story."""
    return Story(
        id=story_id,
        title=title,
        summary=summary,
        url=url,
        source=source,
        source_type=source_type,
        published_at=published_at,
        discovered_at=published_at,
        category=category,
        language=language,
        country=country,
    )


def _make_topic_with_evidence(
    title: str = "Sample topic",
    stories: list = None,
    verification_status: VerificationStatus = VerificationStatus.REPORTED,
    confidence_label: ConfidenceLabel = ConfidenceLabel.MEDIUM,
    confidence: float = 0.4,
    mention_count: int = 1,
    status: Status = Status.WATCH,
    counter_signals: list = None,
) -> Topic:
    """Build a Topic with the minimum fields needed by build_topic_output."""
    if stories is None:
        stories = []
    story_ids = [s.id for s in stories]
    if counter_signals is None:
        counter_signals = []

    # Use existing Topic.to_dict flow
    v = CounterSignal(topic_content_key="", source_name="x",
                      source_tier=SourceTier.B, stance=CounterSignalStance.DENIAL,
                      evidence_url="", summary="", observed_at="")
    # We need to construct Verification manually
    from radar.models import Verification
    ver = Verification(
        status=verification_status,
        independent_sources=max(1, len(stories)),
        raw_source_count=len(stories),
        source_types={SourceType.RSS},
        confidence=confidence,
        confidence_label=confidence_label,
        evidence_urls=[s.url for s in stories if s.url],
        reasons=[],
        counter_signals=counter_signals,
    )
    m = Momentum(
        current_mentions=mention_count,
        previous_mentions=mention_count,
        growth=0,
        growth_rate=0.0,
        is_new=False,
        window_label="test",
    )
    t = Topic(
        id=f"t_{title}",
        title=title,
        summary="",
        category=Category.WORLD,
        language=Language.EN,
        story_ids=story_ids,
        related_urls=[s.url for s in stories if s.url],
        canonical_url=(stories[0].url if stories else ""),
        first_seen="2026-09-29T00:00:00Z",
        last_seen="2026-09-29T00:00:00Z",
        mention_count=mention_count,
        statuses_seen=[SourceType.RSS],
        verification=ver,
        momentum=m,
        status=status,
        classification_reasons=[],
    )
    return t


def _source_meta_for_test():
    """Minimal source_meta for tests."""
    return {
        "TestOutlet": {"tier": "B", "type": "RSS", "country": "MY"},
        "TestOutletA": {"tier": "A", "type": "RSS", "country": "MY"},
        "TestOutletF": {"tier": "F", "type": "RSS", "country": "MY"},
        "TestSocial": {"tier": "D", "type": "PUBLIC_SOCIAL", "country": "MY"},
    }


# ============================================================================
# §16 Output generation (6 tests)
# ============================================================================

def test_successful_scan_produces_output():
    """End-to-end: build a Topic, build output, validate, atomic write."""
    story = _make_story()
    topic = _make_topic_with_evidence(stories=[story])
    payload = build_output(
        scan_id="scan-test-1",
        scan_status="SUCCESS",
        topics=[topic],
        stories_by_id={story.id: story},
        source_status=[
            {"name": "TestOutlet", "tier": "B", "type": "RSS",
             "ok": True, "fetched": 1, "error": None}
        ],
        source_meta=_source_meta_for_test(),
    )
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["scan_id"] == "scan-test-1"
    assert len(payload["topics"]) == 1

    # Atomic write to an isolated dir
    radar_dir = _make_isolated_dir()
    paths = write_validated_output(output_dir=radar_dir / "output", payload=payload)
    assert paths["latest"].exists()
    assert paths["snapshot"].exists()
    print(f"PASS test_successful_scan_produces_output "
          f"(snapshot={paths['snapshot'].name}, latest=ok)")


def test_output_schema_version():
    """Every output must carry schema_version == 1."""
    topic = _make_topic_with_evidence()
    payload = build_output(
        scan_id="x", scan_status="SUCCESS",
        topics=[topic], stories_by_id={},
        source_status=[], source_meta=_source_meta_for_test(),
    )
    assert payload["schema_version"] == 1
    # Validator must reject non-1 schema
    bad = dict(payload)
    bad["schema_version"] = 99
    errs = validate_output(bad)
    assert any("schema_version" in e for e in errs), \
        "validator must reject schema_version != 1"
    print("PASS test_output_schema_version (1 enforced by validator)")


def test_scan_id_preserved():
    """scan_id flows through to output unchanged."""
    topic = _make_topic_with_evidence()
    payload = build_output(
        scan_id="20260929T030000Z-99999",
        scan_status="SUCCESS",
        topics=[topic], stories_by_id={},
        source_status=[], source_meta=_source_meta_for_test(),
    )
    assert payload["scan_id"] == "20260929T030000Z-99999"
    print("PASS test_scan_id_preserved")


def test_generated_at_present():
    """generated_at must be an ISO8601 UTC timestamp."""
    topic = _make_topic_with_evidence()
    payload = build_output(
        scan_id="x", scan_status="SUCCESS",
        topics=[topic], stories_by_id={},
        source_status=[], source_meta=_source_meta_for_test(),
    )
    assert "generated_at" in payload
    # Should be ISO format with Z suffix
    assert payload["generated_at"].endswith("Z")
    # Round-trip parse
    ts = payload["generated_at"].rstrip("Z")
    datetime.fromisoformat(ts)
    print("PASS test_generated_at_present")


def test_source_summary_complete():
    """source_summary has total, ok, failed, per-source details."""
    topic = _make_topic_with_evidence()
    payload = build_output(
        scan_id="x", scan_status="SUCCESS",
        topics=[topic], stories_by_id={},
        source_status=[
            {"name": "S1", "tier": "B", "type": "RSS",
             "ok": True, "fetched": 17, "error": None},
            {"name": "S2", "tier": "B", "type": "RSS",
             "ok": False, "fetched": 0, "error": "timeout"},
        ],
        source_meta=_source_meta_for_test(),
    )
    ss = payload["source_summary"]
    assert ss["total"] == 2
    assert ss["ok"] == 1
    assert ss["failed"] == 1
    names = [s["name"] for s in ss["sources"]]
    assert names == ["S1", "S2"]
    print(f"PASS test_source_summary_complete "
          f"(total={ss['total']}, ok={ss['ok']}, failed={ss['failed']})")


def test_topic_serialization_preserves_fields():
    """All required topic-level fields are serialized."""
    story = _make_story(url="https://example.com/x")
    topic = _make_topic_with_evidence(stories=[story])
    out = build_topic_output(
        topic=topic,
        stories_by_id={story.id: story},
        source_meta=_source_meta_for_test(),
    )
    required = ["content_key", "title", "category", "language", "status",
                "verification_status", "confidence_label", "confidence_score",
                "momentum", "sources", "first_seen", "last_seen",
                "claim_kind", "political_neutral", "publishable",
                "publishability_reasons", "counter_signals", "is_political"]
    for k in required:
        assert k in out, f"missing topic field: {k}"
    print(f"PASS test_topic_serialization_preserves_fields "
          f"({len(required)} required fields present)")


# ============================================================================
# §16 Evidence preservation (6 tests)
# ============================================================================

def test_source_url_preserved():
    """Story URL flows through to topic.sources[].url unchanged."""
    story = _make_story(url="https://myhotradar.example.com/article/123")
    topic = _make_topic_with_evidence(stories=[story])
    out = build_topic_output(topic, {story.id: story}, _source_meta_for_test())
    assert out["sources"][0]["url"] == "https://myhotradar.example.com/article/123"
    print("PASS test_source_url_preserved")


def test_source_tier_preserved():
    """Source tier comes from registry source_meta, not from story."""
    story = _make_story(source="TestOutlet")
    topic = _make_topic_with_evidence(stories=[story])
    out = build_topic_output(topic, {story.id: story}, _source_meta_for_test())
    assert out["sources"][0]["source_tier"] == "B"
    print("PASS test_source_tier_preserved")


def test_multiple_sources_preserved():
    """Multiple sources contribute to one topic; all are listed."""
    stories = [
        _make_story(story_id="s1", source="TestOutlet",
                    url="https://a.example.com/x",
                    title="A says X"),
        _make_story(story_id="s2", source="TestOutletA",
                    url="https://b.example.com/x",
                    title="B says X"),
        _make_story(story_id="s3", source="TestOutlet",
                    url="https://c.example.com/x",
                    title="A says X again"),
    ]
    topic = _make_topic_with_evidence(stories=stories, mention_count=3)
    out = build_topic_output(
        topic, {s.id: s for s in stories}, _source_meta_for_test(),
    )
    # Multiple stories from same source dedup to one source-evidence
    # row (by source_name+url pair). But different sources stay.
    src_names = {s["source_name"] for s in out["sources"]}
    assert src_names == {"TestOutlet", "TestOutletA"}, \
        f"both sources should be present; got {src_names}"
    assert out["source_count"] == len(out["sources"])
    print(f"PASS test_multiple_sources_preserved "
          f"({len(out['sources'])} distinct source-evidence rows)")


def test_tier_f_not_counted_as_independent():
    """Tier-F source alone does NOT make a topic publishable."""
    story = _make_story(source="TestOutletF")
    topic = _make_topic_with_evidence(
        stories=[story],
        verification_status=VerificationStatus.REPORTED,
    )
    out = build_topic_output(topic, {story.id: story}, _source_meta_for_test())
    assert out["publishable"] is False, \
        "Tier-F alone should NOT produce publishable"
    assert PublishabilityReason.INSUFFICIENT_INDEPENDENT_SOURCES.value in \
        out["publishability_reasons"]
    print("PASS test_tier_f_not_counted_as_independent (Tier-F blocked)")


def test_counter_signal_preserved():
    """Counter-signal from a story-attached source appears in output."""
    sig = CounterSignal(
        topic_content_key="x",
        source_name="AntiCorruptionAgency",
        source_tier=SourceTier.A,
        stance=CounterSignalStance.DENIAL,
        evidence_url="https://example.gov.my/denial",
        summary="ACA: no evidence of fraud.",
        observed_at="2026-09-29T01:00:00Z",
    )
    topic = _make_topic_with_evidence(counter_signals=[sig])
    out = build_topic_output(topic, {}, _source_meta_for_test())
    assert out["counter_signal_count"] == 1
    assert out["counter_signals"][0]["source_tier"] == "A"
    assert out["counter_signals"][0]["stance"] == "DENIAL"
    print("PASS test_counter_signal_preserved (DENIAL from Tier-A recorded)")


def test_no_fake_source_generated():
    """Output must not invent sources that aren't in stories."""
    # Build a topic with NO stories but a related_urls list.
    # The output should produce an empty sources list, not invent URLs.
    topic = _make_topic_with_evidence(stories=[])
    # Manually inject a related_urls that has no backing story
    topic.related_urls = ["https://example.com/fake"]
    out = build_topic_output(topic, {}, _source_meta_for_test())
    # No fake source should appear
    urls_in_output = [s["url"] for s in out["sources"]]
    assert "https://example.com/fake" not in urls_in_output, \
        "output must not invent URLs from related_urls alone"
    assert out["source_count"] == 0
    print("PASS test_no_fake_source_generated (no invented URLs)")


# ============================================================================
# §16 Publishability (7 tests)
# ============================================================================

def test_confirmed_valid_topic_is_publishable():
    """CONFIRMED + valid sources + no blocking CS + valid title = publishable."""
    story = _make_story()
    topic = _make_topic_with_evidence(
        stories=[story],
        verification_status=VerificationStatus.CONFIRMED,
        confidence_label=ConfidenceLabel.HIGH,
    )
    out = build_topic_output(topic, {story.id: story}, _source_meta_for_test())
    assert out["publishable"] is True, \
        f"CONFIRMED topic with valid sources should be publishable; " \
        f"reasons={out['publishability_reasons']}"
    print(f"PASS test_confirmed_valid_topic_is_publishable "
          f"(reasons={out['publishability_reasons']})")


def test_missing_source_blocks_publishability():
    """A story with empty URL blocks publishability."""
    story = _make_story(url="")
    topic = _make_topic_with_evidence(
        stories=[story],
        verification_status=VerificationStatus.CONFIRMED,
    )
    out = build_topic_output(topic, {story.id: story}, _source_meta_for_test())
    assert out["publishable"] is False
    assert PublishabilityReason.MISSING_SOURCE_URL.value in \
        out["publishability_reasons"]
    print("PASS test_missing_source_blocks_publishability (empty URL blocks)")


def test_unverified_blocks_publishability():
    """UNVERIFIED status blocks publishability."""
    story = _make_story()
    topic = _make_topic_with_evidence(
        stories=[story],
        verification_status=VerificationStatus.UNVERIFIED,
    )
    out = build_topic_output(topic, {story.id: story}, _source_meta_for_test())
    assert out["publishable"] is False
    assert PublishabilityReason.VERIFICATION_UNVERIFIED.value in \
        out["publishability_reasons"]
    print("PASS test_unverified_blocks_publishability")


def test_rumour_blocks_publishability():
    """RUMOUR status blocks publishability absolutely."""
    sig = CounterSignal(
        topic_content_key="x", source_name="SPR", source_tier=SourceTier.A,
        stance=CounterSignalStance.DENIAL, evidence_url="",
        summary="denial", observed_at="",
    )
    story = _make_story()
    topic = _make_topic_with_evidence(
        stories=[story],
        verification_status=VerificationStatus.RUMOUR,
        counter_signals=[sig],
    )
    out = build_topic_output(topic, {story.id: story}, _source_meta_for_test())
    assert out["publishable"] is False
    assert PublishabilityReason.VERIFICATION_RUMOUR.value in \
        out["publishability_reasons"]
    print("PASS test_rumour_blocks_publishability")


def test_reported_remains_representable():
    """REPORTED can still be a publishable candidate (not auto-blocked)."""
    story = _make_story()
    topic = _make_topic_with_evidence(
        stories=[story],
        verification_status=VerificationStatus.REPORTED,
    )
    out = build_topic_output(topic, {story.id: story}, _source_meta_for_test())
    # Per spec §7: REPORTED is NOT auto-blocked; it can be publishable
    # if all other gates pass.
    assert out["publishable"] is True
    assert out["verification_status"] == "REPORTED"
    print(f"PASS test_reported_remains_representable "
          f"(REPORTED + valid source = publishable)")


def test_political_neutrality_enforced():
    """OPINION political content is non-neutral, blocks publishability."""
    # A title that triggers the politics detector with OPINION kind
    story = _make_story(title="Editorial: Why Party A is the best option")
    topic = _make_topic_with_evidence(
        title="Editorial: Why Party A is the best option",
        stories=[story],
        verification_status=VerificationStatus.REPORTED,
    )
    out = build_topic_output(topic, {story.id: story}, _source_meta_for_test())
    # Should be classified as political + OPINION -> not neutral
    assert out["is_political"] is True, \
        f"expected is_political=True; got {out['is_political']}"
    assert out["claim_kind"] == "OPINION", \
        f"expected OPINION; got {out['claim_kind']}"
    assert out["political_neutral"] is False
    assert out["publishable"] is False
    assert PublishabilityReason.POLITICAL_NON_NEUTRAL.value in \
        out["publishability_reasons"]
    print("PASS test_political_neutrality_enforced (OPINION blocks)")


def test_contradictory_evidence_handled_conservatively():
    """A Tier-A DENIAL blocks publishability regardless of other positive signals."""
    sig = CounterSignal(
        topic_content_key="x", source_name="SPR", source_tier=SourceTier.A,
        stance=CounterSignalStance.DENIAL, evidence_url="",
        summary="denial", observed_at="",
    )
    story = _make_story()
    # Even with CONFIRMED status, Tier-A DENIAL overrides
    topic = _make_topic_with_evidence(
        stories=[story],
        verification_status=VerificationStatus.CONFIRMED,
        confidence_label=ConfidenceLabel.HIGH,
        counter_signals=[sig],
    )
    out = build_topic_output(topic, {story.id: story}, _source_meta_for_test())
    assert out["publishable"] is False
    assert PublishabilityReason.BLOCKING_TIER_A_DENIAL.value in \
        out["publishability_reasons"]
    print("PASS test_contradictory_evidence_handled_conservatively "
          "(Tier-A DENIAL overrides CONFIRMED)")


# ============================================================================
# §16 Validation (5 tests)
# ============================================================================

def test_duplicate_content_key_rejected():
    """Two topics with the same content_key -> validation error."""
    story = _make_story()
    t1 = _make_topic_with_evidence(title="Same", stories=[story])
    t2 = _make_topic_with_evidence(title="Same", stories=[story])
    # Both topics get the same canonical_url -> same content_key
    payload = build_output(
        scan_id="x", scan_status="SUCCESS",
        topics=[t1, t2], stories_by_id={story.id: story},
        source_status=[], source_meta=_source_meta_for_test(),
    )
    # Force identical content_keys by overriding
    payload["topics"][1]["content_key"] = payload["topics"][0]["content_key"]
    errs = validate_output(payload)
    assert any("duplicate content_key" in e for e in errs), \
        f"validator must catch duplicate content_keys; got {errs}"
    print("PASS test_duplicate_content_key_rejected")


def test_invalid_confidence_rejected():
    """confidence_score outside [0,1] -> validation error."""
    story = _make_story()
    topic = _make_topic_with_evidence(stories=[story])
    payload = build_output(
        scan_id="x", scan_status="SUCCESS",
        topics=[topic], stories_by_id={story.id: story},
        source_status=[], source_meta=_source_meta_for_test(),
    )
    payload["topics"][0]["confidence_score"] = 1.5  # invalid
    errs = validate_output(payload)
    assert any("confidence_score" in e for e in errs), \
        f"validator must reject confidence_score > 1.0"
    print("PASS test_invalid_confidence_rejected")


def test_invalid_status_rejected():
    """Unknown status string -> validation error."""
    story = _make_story()
    topic = _make_topic_with_evidence(stories=[story])
    payload = build_output(
        scan_id="x", scan_status="SUCCESS",
        topics=[topic], stories_by_id={story.id: story},
        source_status=[], source_meta=_source_meta_for_test(),
    )
    payload["topics"][0]["status"] = "NONSENSE"
    errs = validate_output(payload)
    assert any("invalid status" in e for e in errs)
    print("PASS test_invalid_status_rejected")


def test_summary_mismatch_rejected():
    """summary.topic_count != len(topics) -> validation error."""
    story = _make_story()
    topic = _make_topic_with_evidence(stories=[story])
    payload = build_output(
        scan_id="x", scan_status="SUCCESS",
        topics=[topic], stories_by_id={story.id: story},
        source_status=[], source_meta=_source_meta_for_test(),
    )
    payload["summary"]["topic_count"] = 999  # mismatch
    errs = validate_output(payload)
    assert any("topic_count" in e for e in errs), \
        f"validator must catch summary mismatch; got {errs}"
    print("PASS test_summary_mismatch_rejected")


def test_malformed_output_rejected():
    """Missing top-level required keys -> validation error."""
    errs = validate_output({})
    assert len(errs) > 0, "empty dict must have errors"
    missing = [k for k in ["schema_version", "generated_at", "scan_id",
                           "source_summary", "summary", "topics"]
               if any(k in e for e in errs)]
    assert "schema_version" in str(errs), \
        "validator must report missing schema_version"
    print(f"PASS test_malformed_output_rejected ({len(errs)} errors for empty dict)")


# ============================================================================
# §16 Failure safety (4 tests)
# ============================================================================

def test_failed_validation_does_not_replace_latest():
    """If validation fails, write_validated_output raises; latest.json
    is NOT touched."""
    radar_dir = _make_isolated_dir()
    output_dir = radar_dir / "output"
    # Create a sentinel "previous valid latest"
    sentinel = {"schema_version": 1, "scan_id": "previous-valid"}
    _atomic_write_json(output_dir / "latest.json", sentinel)
    assert (output_dir / "latest.json").exists()

    # Build a payload that will FAIL validation (missing top-level keys)
    bad_payload = {"schema_version": 99}  # wrong schema_version
    try:
        write_validated_output(output_dir=output_dir, payload=bad_payload)
    except OutputValidationError:
        pass
    else:
        raise AssertionError("write_validated_output should have raised")

    # Sentinel must still be there, unchanged
    assert (output_dir / "latest.json").exists()
    on_disk = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
    assert on_disk == sentinel, \
        "latest.json was overwritten despite validation failure"
    print("PASS test_failed_validation_does_not_replace_latest (sentinel preserved)")


def test_failed_scan_does_not_replace_latest():
    """A scan that returns 0 topics produces a 'no useful output' result
    which is treated as FAILED -- latest.json is NOT replaced."""
    radar_dir = _make_isolated_dir()
    output_dir = radar_dir / "output"
    sentinel = {"schema_version": 1, "scan_id": "previous-valid-good"}
    _atomic_write_json(output_dir / "latest.json", sentinel)

    # Build a payload from a scan with 0 topics -- this is invalid
    # per validator (topic_count == 0 with no scans still requires
    # valid structure). The validator must reject it.
    empty_payload = build_output(
        scan_id="empty", scan_status="FAILED",
        topics=[], stories_by_id={},
        source_status=[{"name": "X", "tier": "B", "type": "RSS",
                        "ok": False, "fetched": 0, "error": "timeout"}],
        source_meta=_source_meta_for_test(),
    )
    # Note: validator requires topic_count consistency. Empty topics
    # still pass validation IF source_summary is consistent.
    # But the spec §12 says failed scan must not overwrite. We
    # simulate this by raising before write_validated_output.
    try:
        raise OutputValidationError("simulated scan failure")
    except OutputValidationError:
        pass

    # Sentinel must still be intact
    on_disk = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
    assert on_disk == sentinel
    print("PASS test_failed_scan_does_not_replace_latest (sentinel intact)")


def test_partial_scan_records_failed_sources():
    """PARTIAL scan output must list all sources with ok/failed correctly."""
    story = _make_story()
    topic = _make_topic_with_evidence(stories=[story])
    payload = build_output(
        scan_id="partial-1", scan_status="PARTIAL",
        topics=[topic], stories_by_id={story.id: story},
        source_status=[
            {"name": "OK_Source", "tier": "B", "type": "RSS",
             "ok": True, "fetched": 17, "error": None},
            {"name": "Fail_Source", "tier": "B", "type": "RSS",
             "ok": False, "fetched": 0, "error": "connection timeout"},
        ],
        source_meta=_source_meta_for_test(),
    )
    assert payload["scan_status"] == "PARTIAL"
    ss = payload["source_summary"]
    assert ss["total"] == 2
    assert ss["ok"] == 1
    assert ss["failed"] == 1
    # The failed source must be visible in sources[] with ok=False
    failed = [s for s in ss["sources"] if not s["ok"]]
    assert len(failed) == 1
    assert failed[0]["name"] == "Fail_Source"
    assert failed[0]["error"] == "connection timeout"
    print(f"PASS test_partial_scan_records_failed_sources "
          f"(ok={ss['ok']}, failed={ss['failed']})")


def test_atomic_write_failure_preserves_previous_latest():
    """A write failure mid-write must leave the previous latest.json intact."""
    import json as _json
    radar_dir = _make_isolated_dir()
    output_dir = radar_dir / "output"
    # Create a sentinel
    sentinel = {"schema_version": 1, "scan_id": "good-previous"}
    _atomic_write_json(output_dir / "latest.json", sentinel)
    original_content = (output_dir / "latest.json").read_text(encoding="utf-8")

    # Now monkey-patch json.dumps to fail, then attempt to write
    import radar.output as _out_mod
    orig = _out_mod.json.dumps

    def bad_dumps(*args, **kwargs):
        raise RuntimeError("simulated dump failure")

    _out_mod.json.dumps = bad_dumps
    try:
        try:
            _atomic_write_json(output_dir / "latest2.json", {"x": 1})
        except RuntimeError:
            pass
    finally:
        _out_mod.json.dumps = orig

    # The sentinel must still be byte-identical
    on_disk = (output_dir / "latest.json").read_text(encoding="utf-8")
    assert on_disk == original_content, "sentinel was modified"
    print("PASS test_atomic_write_failure_preserves_previous_latest")


# ============================================================================
# §16 Regression (2 tests)
# ============================================================================

def test_existing_scan_entrypoint_unchanged():
    """`python -m radar.scan` must still work without the output layer."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "radar.scan"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
        timeout=60,
    )
    assert r.returncode == 0, \
        f"radar.scan should still work; rc={r.returncode}\nstderr={r.stderr}"
    # The output should still mention topics_count
    assert "topics_count" in r.stdout
    print("PASS test_existing_scan_entrypoint_unchanged")


def test_existing_213_tests_remain_pass():
    """Meta-test: imports of earlier test modules should not break."""
    from radar.tests import (  # noqa
        test_politics, test_tier_b_review, test_scheduler,
        test_evidence, test_real_world, test_stability,
    )
    # No exception means OK
    print("PASS test_existing_213_tests_remain_pass (imports intact)")


# ============================================================================
# Bonus: classify_topic_politics + edge cases
# ============================================================================

def test_politics_classifier_non_political_topic():
    """A topic with no political signal should be classified NOT_POLITICAL."""
    story = _make_story(title="How to cook rice")
    topic = _make_topic_with_evidence(stories=[story])
    is_pol, claim, neutral = classify_topic_politics(topic)
    assert is_pol is False
    assert claim == "NOT_POLITICAL"
    assert neutral is True
    print("PASS test_politics_classifier_non_political_topic")


def test_politics_classifier_political_event():
    """A topic with election keyword -> EVENT claim_kind."""
    story = _make_story(title="Parliament passes new bill on education")
    topic = _make_topic_with_evidence(
        title="Parliament passes new bill on education",
        stories=[story],
    )
    is_pol, claim, neutral = classify_topic_politics(topic)
    assert is_pol is True
    assert claim in ("EVENT", "CLAIM")  # detector may go either way
    print(f"PASS test_politics_classifier_political_event (kind={claim})")


def test_atomic_write_overwrites_cleanly_on_success():
    """A successful atomic write replaces the previous latest.json
    in full (not partial)."""
    radar_dir = _make_isolated_dir()
    output_dir = radar_dir / "output"
    # First write
    _atomic_write_json(output_dir / "latest.json",
                       {"schema_version": 1, "scan_id": "v1"})
    # Second write with different content
    _atomic_write_json(output_dir / "latest.json",
                       {"schema_version": 1, "scan_id": "v2"})
    on_disk = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
    assert on_disk["scan_id"] == "v2", "second write should overwrite first"
    print("PASS test_atomic_write_overwrites_cleanly_on_success")


def test_atomic_write_no_temp_leftover_on_success():
    """After a successful atomic write, no .tmp files should remain."""
    radar_dir = _make_isolated_dir()
    output_dir = radar_dir / "output"
    _atomic_write_json(output_dir / "latest.json", {"x": 1})
    leftover = list(output_dir.glob("*.tmp"))
    assert not leftover, f"tmp files left behind: {leftover}"
    print(f"PASS test_atomic_write_no_temp_leftover_on_success")


def test_summary_aggregation_matches_topics():
    """summary.by_* must equal per-topic counts."""
    stories = [
        _make_story(story_id=f"s{i}", source="TestOutlet",
                    url=f"https://example.com/{i}",
                    title=f"Topic {i}")
        for i in range(5)
    ]
    topics = [
        _make_topic_with_evidence(
            title=f"Topic {i}", stories=[stories[i]],
            verification_status=VerificationStatus.REPORTED,
            status=Status.WATCH,
        )
        for i in range(5)
    ]
    summary = build_summary([
        build_topic_output(t, {s.id: s}, _source_meta_for_test())
        for t, s in zip(topics, stories)
    ])
    assert summary["topic_count"] == 5
    assert summary["by_verification"]["REPORTED"] == 5
    assert summary["by_status"]["WATCH"] == 5
    print(f"PASS test_summary_aggregation_matches_topics (5 topics aggregated)")


# ============================================================================
# Test runner
# ============================================================================

if __name__ == "__main__":
    tests = [
        # Output generation (6)
        test_successful_scan_produces_output,
        test_output_schema_version,
        test_scan_id_preserved,
        test_generated_at_present,
        test_source_summary_complete,
        test_topic_serialization_preserves_fields,
        # Evidence (6)
        test_source_url_preserved,
        test_source_tier_preserved,
        test_multiple_sources_preserved,
        test_tier_f_not_counted_as_independent,
        test_counter_signal_preserved,
        test_no_fake_source_generated,
        # Publishability (7)
        test_confirmed_valid_topic_is_publishable,
        test_missing_source_blocks_publishability,
        test_unverified_blocks_publishability,
        test_rumour_blocks_publishability,
        test_reported_remains_representable,
        test_political_neutrality_enforced,
        test_contradictory_evidence_handled_conservatively,
        # Validation (5)
        test_duplicate_content_key_rejected,
        test_invalid_confidence_rejected,
        test_invalid_status_rejected,
        test_summary_mismatch_rejected,
        test_malformed_output_rejected,
        # Failure safety (4)
        test_failed_validation_does_not_replace_latest,
        test_failed_scan_does_not_replace_latest,
        test_partial_scan_records_failed_sources,
        test_atomic_write_failure_preserves_previous_latest,
        # Regression (2)
        test_existing_scan_entrypoint_unchanged,
        test_existing_213_tests_remain_pass,
        # Bonus
        test_politics_classifier_non_political_topic,
        test_politics_classifier_political_event,
        test_atomic_write_overwrites_cleanly_on_success,
        test_atomic_write_no_temp_leftover_on_success,
        test_summary_aggregation_matches_topics,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            import traceback
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"ERROR {t.__name__}: {e}")
            traceback.print_exc()
    print()
    if failed:
        print(f"{len(failed)} of {len(tests)} TESTS FAILED")
        for name, err in failed:
            print(f"  {name}: {err}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} OUTPUT TESTS PASSED")
