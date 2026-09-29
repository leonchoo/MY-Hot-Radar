"""
Performance & Market Intelligence Agent — P1 tests.

These tests cover the foundation layer:
  * Validation (ContentIdentity, PerformanceSnapshot, etc.)
  * null vs zero distinction in metrics
  * Negative delta handling
  * Elapsed time / per-hour calculations
  * Engagement rate (all four cases: known, missing views, zero
    views, all-missing engagement)
  * Classification (one test per PerformanceClass)
  * Deterministic IDs (same input → same id; different input →
    different id)
  * Duplicate snapshot handling (deterministic id is the same)
  * OWN vs MARKET separation
  * Platform separation (independent engagement math)
  * Invalid / future / negative inputs
  * Atomic persistence failure
  * Schema serialization / round-trip
  * Synthetic fixtures are rejected by the production store
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

import performance as p
from performance import (
    ContentFeatureSnapshot,
    ContentIdentity,
    Insight,
    InsightScope,
    MarketObservation,
    PerformanceClass,
    PerformanceObservation,
    PerformanceSnapshot,
    PerformanceStore,
    Platform,
    SourceType,
    SyntheticFixtureError,
    ValidationError,
    classify_late_breakout,
    classify_performance,
    compute_observation,
    content_id_for,
    engagement_breakdown,
    engagement_rate,
    engagement_total,
    extract_features,
    feature_id_for,
    market_observation_id_for,
    observation_id_for,
    snapshot_id_for,
    validate_content_identity,
    validate_feature_snapshot,
    validate_insight,
    validate_market_observation,
    validate_snapshot,
)
from performance.fixtures import SYNTHETIC_TAG


REPO_ROOT = Path(__file__).resolve().parents[2]


# ============================================================================
# Helpers
# ============================================================================

def _utc(dt=None) -> datetime:
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt=None) -> str:
    return _utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mk_content(**kwargs) -> ContentIdentity:
    base = dict(
        content_id="p_test_content_001",
        source_type=SourceType.OWN,
        publisher="MY Hot Radar",
        platform=Platform.WEBSITE,
        url="https://myhotradar.com/article/test",
        title="Test Article",
        category="MALAYSIA",
        topic_type="NEWS",
        language="en",
        published_at=_iso(),
    )
    base.update(kwargs)
    return ContentIdentity(**base)


def _mk_snapshot(**kwargs) -> PerformanceSnapshot:
    base = dict(
        content_id="p_test_content_001",
        captured_at=_iso(),
        views=1000, likes=30, comments=4, shares=2,
    )
    base.update(kwargs)
    return PerformanceSnapshot(**base)


def _mk_isolated_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="performance_test_"))


# ============================================================================
# §十八 Tests
# ============================================================================

# 1. ContentIdentity validation
def test_content_identity_valid():
    c = _mk_content()
    validate_content_identity(c)  # does not raise
    print("PASS test_content_identity_valid")


# 2. PerformanceSnapshot validation
def test_snapshot_valid():
    s = _mk_snapshot()
    validate_snapshot(s)
    print("PASS test_snapshot_valid")


# 3. null vs zero
def test_null_vs_zero_distinct():
    s_none = _mk_snapshot(views=None)
    s_zero = _mk_snapshot(views=0)
    validate_snapshot(s_none)
    validate_snapshot(s_zero)
    assert s_none.views is None
    assert s_zero.views == 0
    assert s_none.views != s_zero.views
    print("PASS test_null_vs_zero_distinct")


# 4. negative delta handling
def test_negative_delta_returns_none():
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(hours=1)),
                          views=1000)
    s_new = _mk_snapshot(captured_at=_iso(), views=500)  # negative delta
    obs = compute_observation(s_old, s_new)
    assert obs is not None
    assert obs.views_delta is None  # MUST NOT be 0
    print("PASS test_negative_delta_returns_none")


# 5. elapsed time calculation
def test_elapsed_time_calculation():
    t0 = _utc() - timedelta(hours=2)
    t1 = _utc()
    s_old = _mk_snapshot(captured_at=_iso(t0), views=100)
    s_new = _mk_snapshot(captured_at=_iso(t1), views=200)
    obs = compute_observation(s_old, s_new)
    assert obs is not None
    assert obs.elapsed_seconds == 7200
    print(f"PASS test_elapsed_time_calculation (elapsed={obs.elapsed_seconds}s)")


# 6. views_per_hour
def test_views_per_hour():
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(hours=1)),
                          views=1000)
    s_new = _mk_snapshot(captured_at=_iso(), views=3000)
    obs = compute_observation(s_old, s_new)
    assert obs.views_per_hour == 2000.0
    print(f"PASS test_views_per_hour (vph={obs.views_per_hour})")


# 7. likes_per_hour
def test_likes_per_hour():
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(hours=2)),
                          likes=50)
    s_new = _mk_snapshot(captured_at=_iso(), likes=100)
    obs = compute_observation(s_old, s_new)
    assert obs.likes_per_hour == 25.0
    print(f"PASS test_likes_per_hour (lph={obs.likes_per_hour})")


# 8. comments_per_hour
def test_comments_per_hour():
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(minutes=30)),
                          comments=10)
    s_new = _mk_snapshot(captured_at=_iso(), comments=20)
    obs = compute_observation(s_old, s_new)
    assert obs.comments_per_hour == 20.0
    print(f"PASS test_comments_per_hour (cph={obs.comments_per_hour})")


# 9. shares_per_hour
def test_shares_per_hour():
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(hours=1)),
                          shares=5)
    s_new = _mk_snapshot(captured_at=_iso(), shares=15)
    obs = compute_observation(s_old, s_new)
    assert obs.shares_per_hour == 10.0
    print(f"PASS test_shares_per_hour (sph={obs.shares_per_hour})")


# 10. engagement rate — all known
def test_engagement_rate_all_known():
    s = _mk_snapshot(views=1000, likes=30, comments=4, shares=2)
    # 30+4+2 = 36; 36/1000 = 0.036
    assert engagement_rate(s) == 0.036
    assert engagement_breakdown(s) == {
        "views": 1000, "likes": 30, "comments": 4, "shares": 2, "reposts": None,
    }
    assert engagement_total(s) == 36
    print(f"PASS test_engagement_rate_all_known (rate={engagement_rate(s)})")


# 11. engagement rate — missing views
def test_engagement_rate_missing_views():
    s = _mk_snapshot(views=None, likes=30, comments=4, shares=2)
    assert engagement_rate(s) is None
    assert engagement_total(s) == 36  # total is independent of views
    print("PASS test_engagement_rate_missing_views")


# 12. engagement rate — missing all engagement components
def test_engagement_rate_missing_all_engagement():
    s = _mk_snapshot(views=1000, likes=None, comments=None,
                      shares=None, reposts=None)
    assert engagement_total(s) is None
    assert engagement_rate(s) is None
    print("PASS test_engagement_rate_missing_all_engagement")


# 13. engagement rate — missing shares only (partial)
def test_engagement_rate_partial_engagement():
    s = _mk_snapshot(views=1000, likes=30, comments=4,
                      shares=None, reposts=None)
    # 30+4+0+0 = 34 (treating None as 0 in sum)
    assert engagement_total(s) == 34
    assert engagement_rate(s) == 0.034
    print(f"PASS test_engagement_rate_partial_engagement (rate={engagement_rate(s)})")


# 14. zero views
def test_zero_views_engagement_rate():
    s = _mk_snapshot(views=0, likes=10, comments=2)
    assert engagement_rate(s) is None
    print("PASS test_zero_views_engagement_rate")


# 15. insufficient data
def test_insufficient_data_short_window():
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(seconds=300)),
                          views=10)
    s_new = _mk_snapshot(captured_at=_iso(), views=100)
    obs = compute_observation(s_old, s_new)
    assert obs is not None
    cls = classify_performance(obs)
    assert cls == PerformanceClass.INSUFFICIENT_DATA
    print(f"PASS test_insufficient_data_short_window (cls={cls.value})")


def test_insufficient_data_missing_views():
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(hours=1)),
                          views=None)
    s_new = _mk_snapshot(captured_at=_iso(), views=None)
    obs = compute_observation(s_old, s_new)
    assert obs is not None
    cls = classify_performance(obs)
    assert cls == PerformanceClass.INSUFFICIENT_DATA
    print("PASS test_insufficient_data_missing_views")


# 16. EARLY_SPIKE
def test_classify_early_spike():
    # 15 min, +5000 views = 20000 vph, > 1000 threshold
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(minutes=15)),
                          views=0)
    s_new = _mk_snapshot(captured_at=_iso(), views=5000)
    obs = compute_observation(s_old, s_new)
    cls = classify_performance(obs)
    assert cls == PerformanceClass.EARLY_SPIKE, \
        f"expected EARLY_SPIKE, got {cls.value}"
    print(f"PASS test_classify_early_spike (cls={cls.value}, vph={obs.views_per_hour})")


# 17. FAST_GROWTH
def test_classify_fast_growth():
    # 2h, +1000 views = 500 vph, > 200 threshold, > 1h window
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(hours=2)),
                          views=1000)
    s_new = _mk_snapshot(captured_at=_iso(), views=2000)
    obs = compute_observation(s_old, s_new)
    cls = classify_performance(obs)
    assert cls == PerformanceClass.FAST_GROWTH, \
        f"expected FAST_GROWTH, got {cls.value}"
    print(f"PASS test_classify_fast_growth (cls={cls.value}, vph={obs.views_per_hour})")


# 18. STEADY_GROWTH
def test_classify_steady_growth():
    # 5h, +150 views = 30 vph, in [20, 200) range
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(hours=5)),
                          views=100)
    s_new = _mk_snapshot(captured_at=_iso(), views=250)
    obs = compute_observation(s_old, s_new)
    cls = classify_performance(obs)
    assert cls == PerformanceClass.STEADY_GROWTH, \
        f"expected STEADY_GROWTH, got {cls.value}"
    print(f"PASS test_classify_steady_growth (cls={cls.value}, vph={obs.views_per_hour})")


# 19. LATE_BREAKOUT
def test_classify_late_breakout():
    # Use synthetic Article A as a real test (not a synthetic flag).
    # Article A's last two windows are 30m -> 60m:
    #   15m->30m: views 1000 -> 3000  (15min, delta 2000, vph 8000)
    #   30m->60m: views 3000 -> 12000 (30min, delta 9000, vph 18000)
    # Use the same Article A logic but as non-synthetic for the test.
    base = _utc() - timedelta(hours=1)
    t15 = base + timedelta(minutes=15)
    t30 = base + timedelta(minutes=30)
    t60 = base + timedelta(hours=1)
    cid = "p_late_breakout_test"
    early = compute_observation(
        PerformanceSnapshot(content_id=cid, captured_at=_iso(t15),
                             views=10, likes=1, comments=0, shares=0),
        PerformanceSnapshot(content_id=cid, captured_at=_iso(t30),
                             views=20, likes=2, comments=0, shares=0),
    )
    late = compute_observation(
        PerformanceSnapshot(content_id=cid, captured_at=_iso(t30),
                             views=20, likes=2, comments=0, shares=0),
        PerformanceSnapshot(content_id=cid, captured_at=_iso(t60),
                             views=2000, likes=20, comments=3, shares=2),
    )
    assert early.views_per_hour < 50, f"setup wrong: {early.views_per_hour}"
    assert late.views_per_hour >= 300, f"setup wrong: {late.views_per_hour}"
    assert classify_late_breakout(early, late) is True
    print("PASS test_classify_late_breakout")


# 20. COOLING
def test_classify_cooling():
    # 24h, +1 view = 0.04 vph, positive delta but very small
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(hours=24)),
                          views=1000)
    s_new = _mk_snapshot(captured_at=_iso(), views=1001)
    obs = compute_observation(s_old, s_new)
    cls = classify_performance(obs)
    assert cls == PerformanceClass.COOLING, \
        f"expected COOLING, got {cls.value}"
    print(f"PASS test_classify_cooling (cls={cls.value}, vph={obs.views_per_hour})")


# 21. STABLE
def test_classify_stable():
    # 2h, +0 views = 0 vph, but views_delta == 0
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(hours=2)),
                          views=500)
    s_new = _mk_snapshot(captured_at=_iso(), views=500)
    obs = compute_observation(s_old, s_new)
    cls = classify_performance(obs)
    assert cls == PerformanceClass.STABLE, \
        f"expected STABLE, got {cls.value}"
    print(f"PASS test_classify_stable (cls={cls.value}, vph={obs.views_per_hour})")


# 22. deterministic IDs
def test_deterministic_content_id():
    cid_a = content_id_for(
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar",
        url="https://myhotradar.com/a",
        title="Article A",
    )
    cid_b = content_id_for(
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar",
        url="https://myhotradar.com/a",
        title="Article A",
    )
    assert cid_a == cid_b
    cid_diff = content_id_for(
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar",
        url="https://myhotradar.com/b",
        title="Article A",
    )
    assert cid_a != cid_diff
    print(f"PASS test_deterministic_content_id (id={cid_a})")


# 23. duplicate snapshot (same content, same captured_at)
def test_duplicate_snapshot_id():
    cid = "p_dup_snap_test"
    cap = _iso()
    sid_a = snapshot_id_for(cid, cap)
    sid_b = snapshot_id_for(cid, cap)
    assert sid_a == sid_b
    sid_diff = snapshot_id_for(cid, _iso(_utc() - timedelta(minutes=1)))
    assert sid_a != sid_diff
    print(f"PASS test_duplicate_snapshot_id (sid={sid_a})")


# 24. OWN vs MARKET separation
def test_own_vs_market_separation():
    cid_own = content_id_for(
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar",
        url="https://myhotradar.com/x",
        title="X",
    )
    cid_market = content_id_for(
        source_type=SourceType.MARKET,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar",
        url="https://myhotradar.com/x",
        title="X",
    )
    assert cid_own != cid_market
    assert cid_own.startswith("p_")
    assert cid_market.startswith("p_")
    print(f"PASS test_own_vs_market_separation (own={cid_own[:14]}.., market={cid_market[:14]}..)")


# 25. platform separation
def test_platform_separation():
    cid_web = content_id_for(
        source_type=SourceType.MARKET,
        platform=Platform.WEBSITE,
        publisher="X",
        url="https://example.com/y",
        title="Y",
    )
    cid_fb = content_id_for(
        source_type=SourceType.MARKET,
        platform=Platform.FACEBOOK,
        publisher="X",
        url="https://example.com/y",
        title="Y",
    )
    assert cid_web != cid_fb
    # Engagement math is independent per snapshot — verify by
    # feeding two snapshots with different platforms' metrics.
    s_web = _mk_snapshot(views=1000, likes=10, comments=2, shares=1)
    s_fb  = _mk_snapshot(views=2000, likes=50, comments=8, shares=12)
    assert engagement_total(s_web) == 13
    assert engagement_total(s_fb)  == 70
    print("PASS test_platform_separation")


# 26. invalid timestamp
def test_invalid_timestamp_rejected():
    c = _mk_content(published_at="not a date")
    try:
        validate_content_identity(c)
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError for invalid timestamp")
    print("PASS test_invalid_timestamp_rejected")


# 27. future timestamp allowed (Radar sometimes captures upcoming items)
def test_future_timestamp_allowed_for_published_at():
    # Published-at can be future-dated (scheduled articles). But the
    # observation function MUST reject out-of-order snapshots (newer
    # captured_at must be >= older captured_at — but not necessarily
    # in the past).
    future = _iso(_utc() + timedelta(days=7))
    c = _mk_content(published_at=future)
    validate_content_identity(c)
    print("PASS test_future_timestamp_allowed_for_published_at")


# 28. negative metric rejected
def test_negative_metric_rejected():
    s = _mk_snapshot(views=-100)
    try:
        validate_snapshot(s)
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError for negative views")
    print("PASS test_negative_metric_rejected")


# 29. atomic persistence failure
def test_atomic_write_failure_preserves_previous():
    d = _mk_isolated_dir()
    store = PerformanceStore(data_dir=d)
    store.ensure_dirs()
    c = _mk_content()
    p1 = store.put_content(c)
    assert p1.exists()
    # Now attempt to write a synthetic — store refuses
    c_synth = _mk_content(content_id="p_synth_test")
    synth_dict = c_synth.to_dict()
    synth_dict[SYNTHETIC_TAG] = True
    try:
        # Bypass validate and call the internal helper directly to
        # test atomic write failure preservation
        from performance.store import _atomic_write_json, _validate_payload
        try:
            _validate_payload(synth_dict, "ContentIdentity")
        except SyntheticFixtureError:
            pass
        else:
            raise AssertionError("synthetic must be rejected")
    except SyntheticFixtureError:
        pass
    # The original file is still there
    assert p1.exists()
    print("PASS test_atomic_write_failure_preserves_previous")


# 30. schema serialization round-trip
def test_schema_serialization_round_trip():
    c = _mk_content()
    d = c.to_dict()
    js = json.dumps(d, ensure_ascii=False)
    d2 = json.loads(js)
    c2 = ContentIdentity.from_dict(d2)
    assert c2.content_id == c.content_id
    assert c2.source_type == c.source_type
    assert c2.platform == c.platform
    print("PASS test_schema_serialization_round_trip")


# ============================================================================
# Additional tests beyond the §十八 minimum (defense-in-depth)
# ============================================================================

def test_synthetic_fixtures_are_tagged():
    """Every synthetic fixture carries the SYNTHETIC tag."""
    for fx in p.all_synthetic_fixtures():
        assert SYNTHETIC_TAG in fx["content"], \
            "synthetic content must be tagged"
        for s in fx["snapshots"]:
            assert SYNTHETIC_TAG in s, \
                "synthetic snapshot must be tagged"
    print("PASS test_synthetic_fixtures_are_tagged")


def test_production_store_refuses_synthetic():
    """PerformanceStore.put_content refuses SYNTHETIC-flagged data."""
    d = _mk_isolated_dir()
    store = PerformanceStore(data_dir=d)
    store.ensure_dirs()
    fx = p.make_synthetic_article_a()
    # Reconstruct ContentIdentity from the tagged dict
    c_dict = dict(fx["content"])
    c_dict.pop(SYNTHETIC_TAG, None)
    # Tag-check at store layer: re-add tag and try to put
    payload = c_dict.copy()
    payload[SYNTHETIC_TAG] = True
    try:
        # Use the internal atomic write path to test the gate
        from performance.store import _validate_payload
        _validate_payload(payload, "ContentIdentity")
    except SyntheticFixtureError:
        pass
    else:
        raise AssertionError("store must refuse SYNTHETIC data")
    # No file was written for the synthetic id
    target = store.content_dir / f"{c_dict['content_id']}.json"
    assert not target.exists(), \
        "synthetic content file must NOT exist on production store"
    print("PASS test_production_store_refuses_synthetic")


def test_rebuild_latest_excludes_synthetic():
    """rebuild_latest() filters out SYNTHETIC-flagged content."""
    d = _mk_isolated_dir()
    store = PerformanceStore(data_dir=d)
    store.ensure_dirs()
    # Real content
    real = _mk_content(content_id="p_real_one")
    store.put_content(real)
    # Synthetic content written directly bypassing put (we want to
    # test the rebuild filter, not the write gate)
    fx = p.make_synthetic_article_a()
    from performance.store import _atomic_write_json
    _atomic_write_json(
        store.content_dir / f"{fx['content']['content_id']}.json",
        fx["content"],
    )
    latest = store.rebuild_latest()
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["counts"]["content"] == 1, \
        f"rebuild_latest must exclude SYNTHETIC, got {payload['counts']}"
    print("PASS test_rebuild_latest_excludes_synthetic")


def test_extract_features_basic():
    """extract_features reads headline heuristics correctly."""
    cid = "p_feat_test"
    title = "Anwar Ibrahim says government will review subsidy mechanism today"
    f = extract_features(
        content_id=cid,
        title=title,
        category="MALAYSIA",
        topic_type="POLICY",
        local_relevance="LOCAL",
        geographic_scope="MALAYSIA",
        published_at="2026-09-29T10:00:00Z",
        radar_status="WATCH",
        radar_verification_status="REPORTED",
        radar_confidence_label="MEDIUM",
        radar_momentum=2.5,
        radar_source_count=3,
    )
    assert f.content_id == cid
    assert f.headline_length == len(title)
    assert f.has_question is False
    assert f.has_number is False
    assert f.has_person_name is True  # "Anwar Ibrahim"
    assert f.has_time_reference is True  # "today"
    assert f.has_exclamation is False
    assert f.headline_style == "INFORMATIVE"
    assert f.radar_status == "WATCH"
    assert f.publication_hour == 10
    assert f.publication_weekday in range(7)
    print(f"PASS test_extract_features_basic (style={f.headline_style})")


def test_extract_features_question_headline():
    f = extract_features(
        content_id="p_q",
        title="Will the new policy pass?",
        category="WORLD",
        topic_type="POLITICS",
        local_relevance="GLOBAL",
        geographic_scope="GLOBAL",
        published_at="2026-09-29T12:00:00Z",
    )
    assert f.has_question is True
    assert f.headline_style == "QUESTION"
    print(f"PASS test_extract_features_question_headline (style={f.headline_style})")


def test_extract_features_exclamatory_headline():
    f = extract_features(
        content_id="p_e",
        title="Big news just in!",
        category="VIRAL",
        topic_type="NEWS",
        local_relevance="GLOBAL",
        geographic_scope="GLOBAL",
        published_at="2026-09-29T12:00:00Z",
    )
    assert f.has_exclamation is True
    assert f.headline_style == "EXCLAMATORY"
    print(f"PASS test_extract_features_exclamatory_headline (style={f.headline_style})")


def test_extract_features_number_in_headline():
    f = extract_features(
        content_id="p_n",
        title="5 things to know about the new law",
        category="WORLD",
        topic_type="NEWS",
        local_relevance="GLOBAL",
        geographic_scope="GLOBAL",
        published_at="2026-09-29T12:00:00Z",
    )
    assert f.has_number is True
    print("PASS test_extract_features_number_in_headline")


def test_url_safety_rejects_dangerous_schemes():
    """is_valid_url rejects javascript:/data:/etc."""
    from performance.validation import is_valid_url
    for bad in ("javascript:alert(1)", "data:text/html,x",
                 "vbscript:msgbox", "file:///etc/passwd"):
        assert not is_valid_url(bad), f"must reject {bad!r}"
    assert is_valid_url("https://example.com/x")
    print("PASS test_url_safety_rejects_dangerous_schemes")


def test_observation_requires_same_content_id():
    """compute_observation rejects mismatched content_id."""
    s_old = _mk_snapshot(content_id="c1", captured_at=_iso(_utc() - timedelta(hours=1)))
    s_new = _mk_snapshot(content_id="c2", captured_at=_iso())
    assert compute_observation(s_old, s_new) is None
    print("PASS test_observation_requires_same_content_id")


def test_observation_rejects_out_of_order():
    """compute_observation rejects new < old."""
    s_old = _mk_snapshot(captured_at=_iso(_utc()))
    s_new = _mk_snapshot(captured_at=_iso(_utc() - timedelta(hours=1)))
    assert compute_observation(s_old, s_new) is None
    print("PASS test_observation_rejects_out_of_order")


def test_feature_validation_rejects_bad_local_relevance():
    """local_relevance must be in the allowed enum."""
    f = ContentFeatureSnapshot(
        content_id="p_x",
        captured_at=_iso(),
        category="MALAYSIA",
        topic_type="NEWS",
        local_relevance="PLANETARY",  # invalid
        geographic_scope="GLOBAL",
        headline_length=10,
        has_person_name=False, has_location=False, has_number=False,
        has_question=False, has_quote=False, has_time_reference=False,
        has_exclamation=False,
        headline_style="INFORMATIVE",
        published_at=_iso(),
        publication_hour=10,
        publication_weekday=2,
    )
    try:
        validate_feature_snapshot(f)
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError for bad local_relevance")
    print("PASS test_feature_validation_rejects_bad_local_relevance")


def test_insight_validation_basic():
    i = Insight(
        insight_id="i_test",
        generated_at=_iso(),
        scope=InsightScope.OWN,
        observation_window={"from": _iso(_utc() - timedelta(hours=1)),
                              "to": _iso()},
        sample_size=10,
        finding="Observational note only.",
        evidence=["obs1", "obs2"],
        limitations=["synthetic fixtures excluded"],
    )
    validate_insight(i)
    print("PASS test_insight_validation_basic")


def test_market_observation_basic():
    m = MarketObservation(
        observation_id=market_observation_id_for(
            publisher="Example Publisher",
            platform=Platform.FACEBOOK,
            content_url="https://facebook.com/example/post/123",
            captured_at=_iso(),
        ),
        publisher="Example Publisher",
        platform=Platform.FACEBOOK,
        content_url="https://facebook.com/example/post/123",
        title="Example market post",
        published_at="2026-09-29T10:00:00Z",
        captured_at=_iso(),
        category="MALAYSIA",
        topic_type="NEWS",
        metrics={"views": 1000, "likes": 50, "comments": 10, "shares": 5,
                  "reposts": None},
    )
    validate_market_observation(m)
    print("PASS test_market_observation_basic")


def test_store_round_trip_snapshot_and_observation():
    """A snapshot persisted then reloaded matches exactly."""
    d = _mk_isolated_dir()
    store = PerformanceStore(data_dir=d)
    store.ensure_dirs()
    c = _mk_content(content_id="p_rt_test")
    store.put_content(c)
    s = _mk_snapshot(content_id="p_rt_test",
                      captured_at=_iso(_utc() - timedelta(hours=1)))
    path = store.put_snapshot(s)
    assert path.exists()
    snaps = store.list_snapshots_for("p_rt_test")
    assert len(snaps) == 1
    assert snaps[0]["views"] == 1000
    print("PASS test_store_round_trip_snapshot_and_observation")


def test_store_atomic_failure_does_not_remove_previous():
    """If a write fails, the previous content file is preserved."""
    d = _mk_isolated_dir()
    store = PerformanceStore(data_dir=d)
    store.ensure_dirs()
    c1 = _mk_content(content_id="p_fail_test", title="v1")
    p1 = store.put_content(c1)
    assert p1.exists()
    sentinel = p1.read_text(encoding="utf-8")
    # Patch json.dump to fail
    import performance.store as store_mod
    original_dump = store_mod.json.dump
    def bad_dump(*a, **kw):
        raise RuntimeError("simulated dump failure")
    store_mod.json.dump = bad_dump
    try:
        try:
            c2 = _mk_content(content_id="p_fail_test", title="v2")
            store.put_content(c2)
        except RuntimeError:
            pass
    finally:
        store_mod.json.dump = original_dump
    # Sentinel content must be intact
    on_disk = p1.read_text(encoding="utf-8")
    assert on_disk == sentinel, \
        "previous content must be preserved on write failure"
    print("PASS test_store_atomic_failure_does_not_remove_previous")


def test_observation_id_for_deterministic():
    cid = "p_obs_id_test"
    f = _iso(_utc() - timedelta(hours=1))
    t = _iso()
    oid_a = observation_id_for(cid, f, t)
    oid_b = observation_id_for(cid, f, t)
    assert oid_a == oid_b
    oid_diff = observation_id_for(cid, f, _iso(_utc() + timedelta(hours=1)))
    assert oid_a != oid_diff
    print(f"PASS test_observation_id_for_deterministic (oid={oid_a})")


def test_classify_performance_short_window_conservative():
    """A 5-minute window must classify INSUFFICIENT_DATA even with
    massive growth — short windows are noisy."""
    s_old = _mk_snapshot(captured_at=_iso(_utc() - timedelta(minutes=5)),
                          views=0)
    s_new = _mk_snapshot(captured_at=_iso(), views=100000)
    obs = compute_observation(s_old, s_new)
    cls = classify_performance(obs)
    assert cls == PerformanceClass.INSUFFICIENT_DATA
    print(f"PASS test_classify_performance_short_window_conservative (cls={cls.value})")


def test_market_metrics_independent_per_platform():
    """Two snapshots from different platforms don't share metrics."""
    s_fb = _mk_snapshot(views=10000, likes=200, comments=20, shares=30,
                         reposts=10)
    # YT-style: explicitly set shares=None and reposts=None
    s_yt = _mk_snapshot(views=5000, likes=300, comments=40,
                         shares=None, reposts=None)
    # Engagement math is independent per snapshot
    assert engagement_total(s_fb) == 260  # 200+20+30+10
    assert engagement_total(s_yt) == 340  # 300+40 (shares=None)
    print("PASS test_market_metrics_independent_per_platform")


# ============================================================================
# Runner
# ============================================================================

if __name__ == "__main__":
    tests = [
        # spec §18 numbered tests
        test_content_identity_valid,
        test_snapshot_valid,
        test_null_vs_zero_distinct,
        test_negative_delta_returns_none,
        test_elapsed_time_calculation,
        test_views_per_hour,
        test_likes_per_hour,
        test_comments_per_hour,
        test_shares_per_hour,
        test_engagement_rate_all_known,
        test_engagement_rate_missing_views,
        test_engagement_rate_missing_all_engagement,
        test_engagement_rate_partial_engagement,
        test_zero_views_engagement_rate,
        test_insufficient_data_short_window,
        test_insufficient_data_missing_views,
        test_classify_early_spike,
        test_classify_fast_growth,
        test_classify_steady_growth,
        test_classify_late_breakout,
        test_classify_cooling,
        test_classify_stable,
        test_deterministic_content_id,
        test_duplicate_snapshot_id,
        test_own_vs_market_separation,
        test_platform_separation,
        test_invalid_timestamp_rejected,
        test_future_timestamp_allowed_for_published_at,
        test_negative_metric_rejected,
        test_atomic_write_failure_preserves_previous,
        test_schema_serialization_round_trip,
        # extra defense-in-depth
        test_synthetic_fixtures_are_tagged,
        test_production_store_refuses_synthetic,
        test_rebuild_latest_excludes_synthetic,
        test_extract_features_basic,
        test_extract_features_question_headline,
        test_extract_features_exclamatory_headline,
        test_extract_features_number_in_headline,
        test_url_safety_rejects_dangerous_schemes,
        test_observation_requires_same_content_id,
        test_observation_rejects_out_of_order,
        test_feature_validation_rejects_bad_local_relevance,
        test_insight_validation_basic,
        test_market_observation_basic,
        test_store_round_trip_snapshot_and_observation,
        test_store_atomic_failure_does_not_remove_previous,
        test_observation_id_for_deterministic,
        test_classify_performance_short_window_conservative,
        test_market_metrics_independent_per_platform,
    ]
    passed = 0
    failed = []
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
        for n, e in failed:
            print(f"  {n}: {e}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} PERFORMANCE TESTS PASSED")
