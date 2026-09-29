"""
Android Bridge tests (pre-P3-B design contract).

These tests verify the wire contract that the future
android-collector Agent will use to hand observations to MY Hot
Radar. They cover:

  1. complete observation
  2. missing likes
  3. missing comments
  4. missing shares
  5. missing views
  6. None != 0
  7. invalid negative metrics
  8. invalid timestamp
  9. evidence metadata
 10. screenshot reference (path, no binary)
 11. platform separation
 12. deterministic observation_id / content_id
 13. duplicate observation protection
 14. political observation remains descriptive-only
 15. synthetic observation cannot enter production storage

P3-A contract rules must continue to hold for Android observations.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from performance import (
    AdapterObservation,
    ANDROID_BRIDGE_SOURCE_PREFIX,
    AndroidObservationInput,
    AndroidValidationIssue,
    Evidence,
    EvidenceType,
    Platform,
    RetrievalStatus,
    batch_to_adapter_dicts,
    build_adapter_result_from_android_batch,
    derive_content_id,
    to_adapter_observation,
    validate_android_batch,
    validate_android_observation,
)
from performance.android_bridge import AndroidObservationInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(year=2026, month=9, day=29, hour=10, minute=0, second=0):
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"


def _ok_observation(**overrides):
    """Build a baseline valid AndroidObservationInput for tests."""
    base = dict(
        observation_id="obs_001",
        platform=Platform.FACEBOOK,
        observed_at=_ts(2026, 9, 29, 10),
        publisher="Free Malaysia Today",
        post_url="https://facebook.com/FMT/posts/123456",
        retrieval_status="AVAILABLE",
        unavailable_reason=None,
        page_url="https://facebook.com/FreeMalaysiaToday",
        title="PM Anwar announces subsidy review",
        caption="Full story text here...",
        published_at=_ts(2026, 9, 29, 8),
        views=15000,
        likes=320,
        comments=42,
        shares=15,
        reposts=None,
        evidence=Evidence(
            evidence_type=EvidenceType.SCREENSHOT,
            reference="/tmp/android_bridge/obs_001.png",
            captured_at=_ts(2026, 9, 29, 10),
            screen_width=1080,
            screen_height=2400,
            device_model="Pixel 7",
            os_version="14",
            notes="Public post, not signed in",
        ),
        notes="page state OK",
    )
    base.update(overrides)
    return AndroidObservationInput(**base)


# ---------------------------------------------------------------------------
# 1. Complete observation
# ---------------------------------------------------------------------------

def test_android_observation_complete_round_trip():
    obs = _ok_observation()
    issues = validate_android_observation(obs)
    assert issues == [], f"unexpected issues: {issues}"
    d = to_adapter_observation(obs)
    # All required AdapterObservation fields populated
    assert d["content_id"].startswith("ci_")
    assert d["platform"] == Platform.FACEBOOK
    assert d["observed_at"] == obs.observed_at
    assert d["retrieval_status"] == "AVAILABLE"
    assert d["source"] == f"{ANDROID_BRIDGE_SOURCE_PREFIX}::obs_001"
    assert d["source_url"] == obs.post_url
    assert d["title"] == obs.title
    assert d["published_at"] == obs.published_at
    assert d["url"] == obs.post_url
    # Metrics preserved exactly
    assert d["views"] == 15000
    assert d["likes"] == 320
    assert d["comments"] == 42
    assert d["shares"] == 15
    assert d["reposts"] is None
    # extra carries publisher + caption + page_url + evidence + notes
    assert d["extra"]["publisher"] == "Free Malaysia Today"
    assert d["extra"]["caption"] == "Full story text here..."
    assert d["extra"]["page_url"] == obs.page_url
    assert d["extra"]["evidence"]["evidence_type"] == "SCREENSHOT"
    assert d["extra"]["notes"] == "page state OK"


# ---------------------------------------------------------------------------
# 2-5. Missing metrics: each independently None
# ---------------------------------------------------------------------------

def test_android_missing_likes_kept_none():
    obs = _ok_observation(likes=None)
    issues = validate_android_observation(obs)
    assert issues == []
    d = to_adapter_observation(obs)
    assert d["likes"] is None
    # Other metrics still present (None != 0)
    assert d["views"] == 15000


def test_android_missing_comments_kept_none():
    obs = _ok_observation(comments=None)
    issues = validate_android_observation(obs)
    assert issues == []
    d = to_adapter_observation(obs)
    assert d["comments"] is None
    assert d["likes"] == 320


def test_android_missing_shares_kept_none():
    obs = _ok_observation(shares=None)
    d = to_adapter_observation(obs)
    assert d["shares"] is None
    assert d["likes"] == 320


def test_android_missing_views_kept_none():
    obs = _ok_observation(views=None)
    d = to_adapter_observation(obs)
    assert d["views"] is None
    assert d["likes"] == 320


def test_android_all_metrics_missing_is_valid():
    """A post that the page shows no metrics on is valid."""
    obs = _ok_observation(
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    issues = validate_android_observation(obs)
    assert issues == []
    d = to_adapter_observation(obs)
    for f in ("views", "likes", "comments", "shares", "reposts"):
        assert d[f] is None


# ---------------------------------------------------------------------------
# 6. None != 0
# ---------------------------------------------------------------------------

def test_android_none_not_coerced_to_zero():
    """Spec #6 / §F: missing metric must NEVER become 0."""
    obs = _ok_observation(likes=None)
    d = to_adapter_observation(obs)
    assert d["likes"] is None
    assert d["likes"] != 0


def test_android_observed_zero_preserved():
    """A page showing '0 likes' must record 0, not None."""
    obs = _ok_observation(likes=0, comments=0)
    issues = validate_android_observation(obs)
    assert issues == []
    d = to_adapter_observation(obs)
    assert d["likes"] == 0
    assert d["comments"] == 0


# ---------------------------------------------------------------------------
# 7. Invalid negative metrics
# ---------------------------------------------------------------------------

def test_android_negative_metric_rejected():
    obs = _ok_observation(likes=-5)
    issues = validate_android_observation(obs)
    assert any(i.field_name == "likes" for i in issues)


def test_android_wrong_type_metric_rejected():
    obs = _ok_observation()
    # Sneak in a string-typed value
    object.__setattr__(obs, "likes", "320")
    issues = validate_android_observation(obs)
    assert any(i.field_name == "likes" for i in issues)


# ---------------------------------------------------------------------------
# 8. Invalid timestamps
# ---------------------------------------------------------------------------

def test_android_invalid_observed_at_rejected():
    obs = _ok_observation(observed_at="not-a-timestamp")
    issues = validate_android_observation(obs)
    assert any(i.field_name == "observed_at" for i in issues)


def test_android_published_after_observed_rejected():
    """Cannot have post-published-at > observation time."""
    obs = _ok_observation(
        published_at=_ts(2026, 9, 29, 12),  # 2 hours after observation
        observed_at=_ts(2026, 9, 29, 10),
    )
    issues = validate_android_observation(obs)
    assert any(i.field_name == "published_at" for i in issues)


def test_android_invalid_evidence_captured_at_rejected():
    obs = _ok_observation()
    obs.evidence.captured_at = "garbage"
    issues = validate_android_observation(obs)
    assert any(i.field_name == "evidence.captured_at" for i in issues)


# ---------------------------------------------------------------------------
# 9. Evidence metadata
# ---------------------------------------------------------------------------

def test_android_evidence_metadata_no_binary():
    """Evidence is metadata only — reference is a path, not bytes."""
    obs = _ok_observation()
    ev = obs.evidence
    assert ev.evidence_type == EvidenceType.SCREENSHOT
    assert ev.reference.startswith("/tmp/")
    assert ev.reference.endswith(".png")
    # The reference is a string, not bytes.
    assert isinstance(ev.reference, str)
    # to_dict produces a JSON-safe dict (no binary blobs).
    ev_d = ev.to_dict()
    s = json.dumps(ev_d)
    assert "PNG" not in s  # no encoded binary markers
    assert "/tmp/android_bridge/obs_001.png" in s


def test_android_evidence_types_accepted():
    for et in (EvidenceType.SCREENSHOT, EvidenceType.UI_TEXT,
                EvidenceType.UI_NODE, EvidenceType.OCR, EvidenceType.COMPOSITE):
        obs = _ok_observation(
            evidence=Evidence(
                evidence_type=et,
                reference=f"/tmp/ref_{et.value}",
                captured_at=_ts(2026, 9, 29, 10),
            )
        )
        issues = validate_android_observation(obs)
        assert issues == [], f"{et.value}: {issues}"


def test_android_unknown_evidence_type_rejected():
    obs = _ok_observation(
        evidence=Evidence(
            evidence_type="SOMETHING_NEW",  # type: ignore[arg-type]
            reference="/tmp/x",
            captured_at=_ts(2026, 9, 29, 10),
        )
    )
    issues = validate_android_observation(obs)
    assert any(i.field_name == "evidence.evidence_type" for i in issues)


# ---------------------------------------------------------------------------
# 10. Screenshot reference (path only)
# ---------------------------------------------------------------------------

def test_android_screenshot_reference_is_path_not_binary():
    """Reference must be a path / URI; no binary content embedded."""
    obs = _ok_observation()
    d = to_adapter_observation(obs)
    ev = d["extra"]["evidence"]
    assert ev["evidence_type"] == "SCREENSHOT"
    assert ev["reference"] == "/tmp/android_bridge/obs_001.png"
    # Metadata fields present
    assert ev["screen_width"] == 1080
    assert ev["screen_height"] == 2400
    assert ev["device_model"] == "Pixel 7"
    assert ev["os_version"] == "14"
    # No 'data' / 'base64' / 'bytes' keys
    assert "data" not in ev
    assert "base64" not in ev
    assert "bytes" not in ev


def test_android_evidence_reference_must_be_non_empty():
    obs = _ok_observation()
    obs.evidence.reference = ""
    issues = validate_android_observation(obs)
    assert any(i.field_name == "evidence.reference" for i in issues)


# ---------------------------------------------------------------------------
# 11. Platform separation
# ---------------------------------------------------------------------------

def test_android_platform_identity_preserved_per_row():
    fb = _ok_observation(observation_id="obs_fb", platform=Platform.FACEBOOK,
                         post_url="https://facebook.com/FMT/posts/1")
    ig = _ok_observation(observation_id="obs_ig", platform=Platform.INSTAGRAM,
                         post_url="https://instagram.com/p/X",
                         publisher="Some IG Page")
    yt = _ok_observation(observation_id="obs_yt", platform=Platform.YOUTUBE,
                         post_url="https://youtube.com/watch?v=Z",
                         publisher="Some YT Channel")
    batch = [fb, ig, yt]
    issues = validate_android_batch(batch)
    assert issues == [], f"unexpected issues: {issues}"
    result = build_adapter_result_from_android_batch(
        source_name="android_collector",
        platform=Platform.FACEBOOK,  # batch source platform; rows still per-row
        started_at=_ts(2026, 9, 29, 10),
        finished_at=_ts(2026, 9, 29, 10, 5),
        observations=batch,
    )
    # Each row carries its own platform — never collapsed.
    platforms_seen = {row["platform"] for row in result["observations"]}
    assert platforms_seen == {Platform.FACEBOOK, Platform.INSTAGRAM, Platform.YOUTUBE}


def test_android_no_cross_platform_aggregation_in_bridge():
    """The bridge does not combine Facebook + Instagram + YouTube into
    a single number. Each row is independent."""
    obs_fb = _ok_observation(observation_id="fb", platform=Platform.FACEBOOK,
                               post_url="https://facebook.com/x/post/1",
                               views=100, likes=10)
    obs_ig = _ok_observation(observation_id="ig", platform=Platform.INSTAGRAM,
                               post_url="https://instagram.com/p/Y",
                               views=200, likes=20)
    obs_yt = _ok_observation(observation_id="yt", platform=Platform.YOUTUBE,
                               post_url="https://youtube.com/watch?v=Z",
                               views=300, likes=30)
    rows = batch_to_adapter_dicts([obs_fb, obs_ig, obs_yt])
    # Verify per-row metrics preserved exactly
    views = [r["views"] for r in rows]
    assert views == [100, 200, 300]
    # No "total_views" / "combined" fields
    for r in rows:
        assert "total_views" not in r
        assert "combined" not in r
        assert "aggregate" not in r


# ---------------------------------------------------------------------------
# 12. Deterministic IDs
# ---------------------------------------------------------------------------

def test_derive_content_id_deterministic_for_same_url():
    a = derive_content_id("https://facebook.com/x/posts/1")
    b = derive_content_id("https://facebook.com/x/posts/1")
    assert a == b
    assert a.startswith("ci_")


def test_derive_content_id_differs_for_different_url():
    a = derive_content_id("https://facebook.com/x/posts/1")
    b = derive_content_id("https://facebook.com/x/posts/2")
    assert a != b


def test_android_observation_source_includes_observation_id():
    """source field ties the row back to its android-collector input."""
    obs = _ok_observation(observation_id="obs_XYZ")
    d = to_adapter_observation(obs)
    assert d["source"] == "android_bridge::obs_XYZ"


def test_same_post_url_yields_same_content_id_across_observations():
    """Two observations of the SAME post (different observation_id)
    must share content_id."""
    obs1 = _ok_observation(observation_id="obs_t1",
                             post_url="https://facebook.com/x/posts/1",
                             observed_at=_ts(2026, 9, 29, 10))
    obs2 = _ok_observation(observation_id="obs_t2",
                             post_url="https://facebook.com/x/posts/1",
                             observed_at=_ts(2026, 9, 29, 11))
    d1 = to_adapter_observation(obs1)
    d2 = to_adapter_observation(obs2)
    assert d1["content_id"] == d2["content_id"]
    assert d1["source"] != d2["source"]  # different observation_id -> different source
    assert d1["observed_at"] != d2["observed_at"]


# ---------------------------------------------------------------------------
# 13. Duplicate observation protection
# ---------------------------------------------------------------------------

def test_duplicate_observation_id_same_observed_at_rejected():
    a = _ok_observation(observation_id="dup", observed_at=_ts(2026, 9, 29, 10))
    b = _ok_observation(observation_id="dup", observed_at=_ts(2026, 9, 29, 10))
    issues = validate_android_batch([a, b])
    assert any(i.field_name == "observation_id" and "duplicate" in i.issue
                for i in issues)


def test_same_observation_id_different_observed_at_allowed():
    """The same observation_id MAY be reused across time; that's how
    we compute deltas (P1 compute_observation across two snapshots
    of the same post)."""
    a = _ok_observation(observation_id="dup", observed_at=_ts(2026, 9, 29, 10),
                         likes=10)
    b = _ok_observation(observation_id="dup", observed_at=_ts(2026, 9, 29, 11),
                         likes=15)
    issues = validate_android_batch([a, b])
    assert issues == [], f"unexpected: {issues}"


# ---------------------------------------------------------------------------
# 14. Political observation remains descriptive-only
# ---------------------------------------------------------------------------

def test_android_political_observation_descriptive_only():
    """Spec #8: political engagement metrics are recorded as numbers,
    not as political support signals."""
    obs = _ok_observation(
        observation_id="pol_1",
        platform=Platform.FACEBOOK,
        publisher="Outlet A",
        post_url="https://facebook.com/OutletA/posts/999",
        title="Politician X statement",
        caption="Full post text",
        likes=1500,
        comments=320,
        shares=80,
        views=12000,
    )
    d = to_adapter_observation(obs)
    # The dict MUST NOT contain political-inference keys.
    forbidden = ("support", "voter", "approval", "election", "winner",
                  "best", "rank", "more_popular")
    for k in d:
        for f in forbidden:
            assert f not in k.lower(), f"forbidden key {k!r} in {d}"
    for k in d["extra"]:
        for f in forbidden:
            assert f not in k.lower(), f"forbidden extra key {k!r} in {d['extra']}"


def test_android_political_batch_no_aggregate_signal():
    """A batch of political posts must not produce any aggregate
    ranking signal at the bridge level."""
    a = _ok_observation(observation_id="pol_A",
                         publisher="Outlet A",
                         post_url="https://facebook.com/A/posts/1",
                         likes=2000)
    b = _ok_observation(observation_id="pol_B",
                         publisher="Outlet B",
                         post_url="https://facebook.com/B/posts/1",
                         likes=500)
    result = build_adapter_result_from_android_batch(
        source_name="android_collector",
        platform=Platform.FACEBOOK,
        started_at=_ts(2026, 9, 29, 10),
        finished_at=_ts(2026, 9, 29, 10, 5),
        observations=[a, b],
    )
    forbidden = ("winner", "best", "rank", "more_popular",
                  "support_rate", "voter_preference")
    for key in result:
        for f in forbidden:
            assert f not in key.lower(), f"forbidden top-level key {key!r}"


# ---------------------------------------------------------------------------
# 15. Synthetic observation cannot enter production storage
# ---------------------------------------------------------------------------

def test_synthetic_observation_path_unchanged_by_bridge():
    """The Android Bridge is for ANDROID inputs. A synthetic (test)
    observation must NOT be silently treated as production. The
    bridge never produces SYNTHETIC-tagged rows; callers using
    SyntheticAdapter separately control that flag.
    """
    obs = _ok_observation()  # this is NOT synthetic
    d = to_adapter_observation(obs)
    # Bridge output does not carry the synthetic flag.
    assert d["extra"].get("_synthetic") is None or \
        d["extra"].get("_synthetic") is False


def test_android_bridge_does_not_write_to_performance_data():
    """The bridge module is purely a translation layer. It must not
    touch the PerformanceStore.
    """
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "performance_data"
        # Bridge code paths (validate, translate, build result) do
        # not import or call PerformanceStore. We verify the data
        # dir stays empty.
        from performance import PerformanceStore
        store = PerformanceStore(data_dir=data_dir)
        # Run a bridge pipeline purely in-memory.
        obs = _ok_observation()
        issues = validate_android_observation(obs)
        assert issues == []
        d = to_adapter_observation(obs)
        result = build_adapter_result_from_android_batch(
            source_name="android_collector",
            platform=Platform.FACEBOOK,
            started_at=_ts(2026, 9, 29, 10),
            finished_at=_ts(2026, 9, 29, 10, 5),
            observations=[obs],
        )
        # Result is a dict, not a store write.
        assert isinstance(result, dict)
        # The store dir is still empty (no implicit write).
        assert not any(data_dir.iterdir()) if data_dir.exists() else True


# ---------------------------------------------------------------------------
# AdapterResult overall status computation (mirror of P3-A SyntheticAdapter)
# ---------------------------------------------------------------------------

def test_android_batch_overall_available():
    batch = [
        _ok_observation(observation_id="a"),
        _ok_observation(observation_id="b", post_url="https://facebook.com/x/posts/2"),
    ]
    r = build_adapter_result_from_android_batch(
        "android_collector", Platform.FACEBOOK,
        _ts(2026, 9, 29, 10), _ts(2026, 9, 29, 10, 5), batch,
    )
    assert r["retrieval_status"] == "AVAILABLE"


def test_android_batch_overall_partial_when_mixed():
    batch = [
        _ok_observation(observation_id="a", retrieval_status="AVAILABLE"),
        _ok_observation(observation_id="b",
                         post_url="https://facebook.com/x/posts/2",
                         retrieval_status="UNAVAILABLE",
                         unavailable_reason="post_removed"),
    ]
    r = build_adapter_result_from_android_batch(
        "android_collector", Platform.FACEBOOK,
        _ts(2026, 9, 29, 10), _ts(2026, 9, 29, 10, 5), batch,
    )
    assert r["retrieval_status"] == "PARTIAL"


def test_android_batch_overall_unavailable_when_empty():
    r = build_adapter_result_from_android_batch(
        "android_collector", Platform.FACEBOOK,
        _ts(2026, 9, 29, 10), _ts(2026, 9, 29, 10, 5), [],
    )
    assert r["retrieval_status"] == "UNAVAILABLE"


def test_android_batch_overall_rate_limited():
    batch = [
        _ok_observation(observation_id="a", retrieval_status="RATE_LIMITED"),
    ]
    r = build_adapter_result_from_android_batch(
        "android_collector", Platform.FACEBOOK,
        _ts(2026, 9, 29, 10), _ts(2026, 9, 29, 10, 5), batch,
    )
    assert r["retrieval_status"] == "RATE_LIMITED"


def test_android_batch_overall_error():
    batch = [
        _ok_observation(observation_id="a", retrieval_status="ERROR"),
    ]
    r = build_adapter_result_from_android_batch(
        "android_collector", Platform.FACEBOOK,
        _ts(2026, 9, 29, 10), _ts(2026, 9, 29, 10, 5), batch,
    )
    assert r["retrieval_status"] == "ERROR"


# ---------------------------------------------------------------------------
# Translation sanity: each Android input produces exactly one AdapterObservation
# ---------------------------------------------------------------------------

def test_android_translation_yields_one_observation_per_input():
    batch = [
        _ok_observation(observation_id=f"obs_{i}",
                         post_url=f"https://facebook.com/x/posts/{i}")
        for i in range(5)
    ]
    dicts = batch_to_adapter_dicts(batch)
    assert len(dicts) == 5
    assert {d["source"] for d in dicts} == {
        f"android_bridge::obs_{i}" for i in range(5)
    }


def test_android_translation_json_serializable():
    """Bridge output must be JSON-safe for store round-trip."""
    obs = _ok_observation()
    d = to_adapter_observation(obs)
    # Platform is an enum; serializable
    d["platform"] = d["platform"].value
    s = json.dumps(d)
    parsed = json.loads(s)
    assert parsed["content_id"] == d["content_id"]
    assert parsed["likes"] == 320


# ---------------------------------------------------------------------------
# No addition of new capabilities or status values
# ---------------------------------------------------------------------------

def test_android_bridge_does_not_introduce_new_status_values():
    """The Android Bridge uses the same RetrievalStatus enum from P3-A.
    It does not invent its own."""
    obs = _ok_observation()
    issues = validate_android_observation(obs)
    assert issues == []
    # Translate and inspect retrieval_status is one of the 7 known values.
    d = to_adapter_observation(obs)
    assert d["retrieval_status"] in {
        "AVAILABLE", "PARTIAL", "UNAVAILABLE", "RATE_LIMITED",
        "NOT_SUPPORTED", "INVALID_SOURCE", "ERROR",
    }


def test_android_bridge_does_not_invent_metrics():
    """Metrics list is exactly views/likes/comments/shares/reposts —
    nothing else. No 'followers', 'reach', 'impressions', 'historical'.
    """
    obs = _ok_observation()
    d = to_adapter_observation(obs)
    metric_keys = {k for k in d if k in {
        "views", "likes", "comments", "shares", "reposts",
    }}
    assert metric_keys == {"views", "likes", "comments", "shares", "reposts"}
    # No follower / reach / impression fields anywhere.
    forbidden_metrics = ("followers", "reach", "impressions", "historical")
    full_text = json.dumps(d)
    for fm in forbidden_metrics:
        assert fm not in full_text, f"forbidden metric {fm} leaked into {d}"

if __name__ == "__main__":
    import sys
    test_funcs = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    passed = 0
    failed = []
    for name, fn in test_funcs:
        try:
            fn()
            passed += 1
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append((name, str(e)))
            print(f"FAIL {name}: {e}")
        except Exception as e:
            import traceback
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"ERROR {name}: {e}")
            traceback.print_exc()
    print()
    print(f"{passed} passed, {len(failed)} failed of {len(test_funcs)} tests")
    if failed:
        for n, e in failed:
            print(f"  {n}: {e}")
        sys.exit(1)
    else:
        print(f"ALL {len(test_funcs)} ANDROID BRIDGE TESTS PASSED")
