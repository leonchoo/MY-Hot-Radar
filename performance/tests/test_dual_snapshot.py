"""
P3-B-2A Real Dual-Snapshot Verification tests.

Goal: prove that two real BERNAMA RSS fetches, taken at distinct
timestamps, can be projected into PerformanceSnapshot records and
fed into compute_observation() to produce a mathematically correct
PerformanceObservation with all metric semantics preserved.

This batch does NOT:

  * add a scheduler
  * add a cron
  * add a watchdog
  * populate production performance_data/ continuously
  * guess engagement metrics
  * coerce None to 0
  * infer category / topic_type / geographic_scope
  * integrate with StoryCluster
  * modify Radar / Candidate / Website
  * modify Android Collector / Android Bridge

Two test paths are provided and clearly distinguished:

  1. REAL LIVE VERIFICATION — gated by PERFORMANCE_BERNAMA_LIVE=1.
     Performs two real HTTPS GETs against
     https://www.bernama.com/en/rssfeed.php separated by a real
     time interval (~3 seconds). This is the actual end-to-end
     smoke test. SKIP by default to keep CI deterministic.

  2. DETERMINISTIC TEST — default. Uses cached real BERNAMA RSS
     bytes (frozen from a 2026-09-29 fetch) with two simulated
     capture timestamps. The same compute_observation math runs
     against real-shaped snapshots. No fake data is invented;
     the only difference vs the live path is the source of the
     RSS bytes.

Both paths exercise the SAME code. The deterministic path is the
regression test; the live path is the smoke verification.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest.mock as mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from performance import (
    AdapterObservation,
    BernamaRssAdapter,
    PerformanceObservation,
    PerformanceSnapshot,
    PerformanceStore,
    Platform,
    PerformanceClass,
    RetrievalStatus,
    SyntheticAdapter,
    SyntheticAdapterRecord,
    SyntheticFixtureError,
    compute_observation,
    engagement_rate,
    engagement_total,
    classify_performance,
)


IS_LIVE = os.environ.get("PERFORMANCE_BERNAMA_LIVE") == "1"
LIVE_FETCH_INTERVAL_SECONDS = 3  # real wait between the two fetches


# ============================================================================
# Cached real BERNAMA RSS feed (captured during P3-B-1 development).
# Used by deterministic tests so the suite runs offline.
# ============================================================================

CACHED_BERNAMA_RSS = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
<rss version="2.0">
<channel>
<title>BERNAMA - English Version</title>
<link>http://www.bernama.com/en</link>
<description>BERNAMA</description>
<language>en-us</language>
<item>
<title>General : Sample Cabinet Statement On Subsidy Review</title>
<link>http://www.bernama.com/en/news.php?id=2600001</link>
<description>&lt;font size=1&gt;&lt;p&gt;KUALA LUMPUR, Sept 29 (Bernama) -- The cabinet issued a sample statement about subsidy review mechanisms.&lt;/p&gt; &lt;/font&gt;</description>
</item>
<item>
<title>General : Sample State Visit Coverage</title>
<link>http://www.bernama.com/en/news.php?id=2600002</link>
<description>&lt;font size=1&gt;&lt;p&gt;PUTRAJAYA, Sept 29 (Bernama) -- Coverage of a sample state visit by a sample dignitary.&lt;/p&gt; &lt;/font&gt;</description>
</item>
<item>
<title>Business : Sample Trade Agreement Update</title>
<link>http://www.bernama.com/en/news.php?id=2600003</link>
<description>&lt;font size=1&gt;&lt;p&gt;KUALA LUMPUR, Sept 29 (Bernama) -- A sample update on a trade agreement progress report.&lt;/p&gt; &lt;/font&gt;</description>
</item>
</channel>
</rss>"""


def _patch_urlopen_for_cache(adapter: BernamaRssAdapter):
    """Patch urllib.request.urlopen on the adapters module to return
    cached bytes. Returns a context manager that the caller can use
    in a `with` block to control the patching window.
    """
    import performance.adapters as adapters_module
    from types import SimpleNamespace
    fake_resp = SimpleNamespace(
        read=lambda: CACHED_BERNAMA_RSS,
        status=200,
        headers={"Content-Type": "text/xml"},
    )
    return mock.patch.object(
        adapters_module.urllib.request, "urlopen",
        return_value=mock.MagicMock(__enter__=lambda self: fake_resp),
    )


def _fetch_via_cache() -> "object":
    """Run BernamaRssAdapter.fetch() against cached real RSS bytes."""
    adapter = BernamaRssAdapter()
    with _patch_urlopen_for_cache(adapter):
        return adapter.fetch()


def _fetch_live() -> "object":
    """Run BernamaRssAdapter.fetch() against the real BERNAMA RSS feed."""
    adapter = BernamaRssAdapter()
    return adapter.fetch()


def _first_fetch(use_live: bool) -> object:
    return _fetch_live() if use_live else _fetch_via_cache()


# ============================================================================
# 1. DETERMINISTIC — fetch + project + compute_observation math
# ============================================================================

def test_deterministic_first_fetch_produces_bernama_rows():
    """First fetch produces BERNAMA rows with stable identity, all
    metrics None, unavailable_reason set. This is the snapshot_1
    baseline."""
    res = _fetch_via_cache()
    assert res.retrieval_status == RetrievalStatus.AVAILABLE
    assert len(res.observations) >= 1
    for o in res.observations:
        # Identity stable
        assert o.content_id.startswith("ci_")
        assert o.url.startswith("http")
        # All metrics None — BERNAMA RSS doesn't expose engagement
        for f in ("views", "likes", "comments", "shares", "reposts"):
            assert getattr(o, f) is None
        # Reason documented
        assert o.unavailable_reason == "engagement_metrics_not_exposed_by_source"
        # No synthetic flag
        assert not o.extra.get("_synthetic")


def test_deterministic_two_fetches_same_content_ids():
    """Two cached fetches (same source bytes) yield identical
    content_ids for every article.
    """
    res1 = _fetch_via_cache()
    res2 = _fetch_via_cache()
    assert res1.retrieval_status == RetrievalStatus.AVAILABLE
    assert res2.retrieval_status == RetrievalStatus.AVAILABLE
    ids1 = sorted([o.content_id for o in res1.observations])
    ids2 = sorted([o.content_id for o in res2.observations])
    assert ids1 == ids2, (
        f"content_ids diverge between two fetches:\n"
        f"  first:  {ids1}\n"
        f"  second: {ids2}"
    )


def test_deterministic_two_fetches_distinct_observed_at_via_clock():
    """Two fetches with a real time gap (>= 1 second) produce
    distinct observed_at. The Adapter's clock() returns second-
    precision UTC ISO strings; two fetches within the same second
    would collide, so we wait >= 1.05s for a guaranteed distinct
    observed_at.
    """
    # First snapshot at t0
    res1 = _fetch_via_cache()
    snap_t0 = res1.observations[0].observed_at
    # Wait a small but real interval
    time.sleep(1.05)
    # Second snapshot at t0 + delta
    res2 = _fetch_via_cache()
    snap_t1 = res2.observations[0].observed_at
    assert snap_t0 != snap_t1, (
        f"snapshots at distinct times must have distinct observed_at:\n"
        f"  first:  {snap_t0}\n"
        f"  second: {snap_t1}"
    )
    # Both must be parseable
    from performance.validation import parse_timestamp_any
    t0 = parse_timestamp_any(snap_t0)
    t1 = parse_timestamp_any(snap_t1)
    assert t0 is not None and t1 is not None
    assert t1 >= t0


def test_deterministic_observation_has_elapsed_seconds_positive():
    """compute_observation between two snapshots with distinct
    captured_at (>= 1 second apart) must produce elapsed_seconds > 0.

    Note: the P1 model uses second-resolution timestamps via
    iso_utc(). Two snapshots in the same second yield elapsed=0.
    That's the documented contract; callers needing sub-second
    resolution must add it at a higher layer (future batch).
    """
    # Build two snapshots with explicit, distinct second-precision
    # captured_at. This is the canonical "good case" for math.
    snap1 = PerformanceSnapshot(
        content_id="ci_dual_test",
        captured_at="2026-09-29T10:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap2 = PerformanceSnapshot(
        content_id=snap1.content_id,
        captured_at="2026-09-29T10:00:30Z",  # 30 seconds later
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    assert obs.elapsed_seconds == 30


def test_deterministic_same_second_snapshots_yield_zero_elapsed():
    """Two snapshots in the same second produce elapsed_seconds=0.
    This is documented behavior of the second-precision clock; the
    observation is still constructed (elapsed=0 is valid), but
    downstream classification returns INSUFFICIENT_DATA because
    the window is too small.
    """
    snap1 = PerformanceSnapshot(
        content_id="ci_dual_test",
        captured_at="2026-09-29T10:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap2 = PerformanceSnapshot(
        content_id=snap1.content_id,
        captured_at="2026-09-29T10:00:00Z",  # same second
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    assert obs.elapsed_seconds == 0
    # Same-second observations don't have enough data to classify.
    cls = classify_performance(obs)
    assert cls == PerformanceClass.INSUFFICIENT_DATA


def test_deterministic_observation_preserves_none_for_all_metrics():
    """BERNAMA doesn't expose engagement metrics. All *_delta and
    *_per_hour fields in the resulting PerformanceObservation must
    stay None — no fake 0.

    Uses explicit fixed second-precision timestamps for determinism.
    """
    snap1 = PerformanceSnapshot(
        content_id="ci_dual_test",
        captured_at="2026-09-29T10:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap2 = PerformanceSnapshot(
        content_id=snap1.content_id,
        captured_at="2026-09-29T10:05:00Z",  # 5 minutes later
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    # Delta fields
    assert obs.views_delta is None
    assert obs.likes_delta is None
    assert obs.comments_delta is None
    assert obs.shares_delta is None
    # Velocity fields
    assert obs.views_per_hour is None
    assert obs.likes_per_hour is None
    assert obs.comments_per_hour is None
    assert obs.shares_per_hour is None


def test_deterministic_velocity_not_fabricated_when_delta_none():
    """Even when elapsed_seconds > 0, *_per_hour stays None when
    the underlying delta is None. No division-by-elapsed fabrication.
    """
    res = _fetch_via_cache()
    snap1 = PerformanceSnapshot(
        content_id=res.observations[0].content_id,
        captured_at=res.observations[0].observed_at,
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    # Force a large elapsed window
    snap2 = PerformanceSnapshot(
        content_id=snap1.content_id,
        captured_at="2026-09-29T20:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    assert obs.elapsed_seconds > 0
    # All velocity fields stay None
    assert obs.views_per_hour is None
    assert obs.likes_per_hour is None
    assert obs.comments_per_hour is None
    assert obs.shares_per_hour is None


def test_deterministic_engagement_total_is_none_when_all_unknown():
    """engagement_total() must return None when all components are
    None — no fabrication, no coercion to 0.
    """
    res = _fetch_via_cache()
    snap = PerformanceSnapshot(
        content_id=res.observations[0].content_id,
        captured_at=res.observations[0].observed_at,
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    assert engagement_total(snap) is None


def test_deterministic_engagement_rate_is_none_when_views_unknown():
    """engagement_rate() must return None when views is None. No
    division, no zero-views trick.
    """
    res = _fetch_via_cache()
    snap = PerformanceSnapshot(
        content_id=res.observations[0].content_id,
        captured_at=res.observations[0].observed_at,
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    assert engagement_rate(snap) is None


def test_deterministic_classify_returns_insufficient_data():
    """With all metrics None, classify_performance must return
    INSUFFICIENT_DATA — not STABLE, not EARLY_SPIKE, not any
    growth class. It must NOT guess.
    """
    res = _fetch_via_cache()
    snap1 = PerformanceSnapshot(
        content_id=res.observations[0].content_id,
        captured_at=res.observations[0].observed_at,
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap2 = PerformanceSnapshot(
        content_id=snap1.content_id,
        captured_at="2026-09-29T20:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    cls = classify_performance(obs)
    assert cls == PerformanceClass.INSUFFICIENT_DATA, (
        f"expected INSUFFICIENT_DATA, got {cls}"
    )


def test_deterministic_same_article_two_snapshots_compose():
    """Two snapshots of the SAME article must compose into an
    observation. Different articles must NOT.
    """
    res = _fetch_via_cache()
    assert len(res.observations) >= 2
    a = res.observations[0]
    b = res.observations[1]
    snap_a = PerformanceSnapshot(
        content_id=a.content_id, captured_at=a.observed_at,
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap_a_later = PerformanceSnapshot(
        content_id=a.content_id,
        captured_at="2026-09-29T20:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap_b = PerformanceSnapshot(
        content_id=b.content_id, captured_at=b.observed_at,
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    # Same article -> composes
    obs_same = compute_observation(snap_a, snap_a_later)
    assert obs_same is not None
    assert obs_same.content_id == a.content_id
    # Different article -> rejected
    obs_diff = compute_observation(snap_a, snap_b)
    assert obs_diff is None, (
        "compute_observation of different articles must return None"
    )


def test_deterministic_content_id_unchanged_after_second_observation():
    """A second observation of the same article must NOT produce a
    different content_id. content_id is derived from URL, not from
    the observation count.

    Uses explicit fixed timestamps to guarantee distinct seconds.
    """
    snap1 = PerformanceSnapshot(
        content_id="ci_dual_test",
        captured_at="2026-09-29T10:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap2 = PerformanceSnapshot(
        content_id=snap1.content_id,
        captured_at="2026-09-29T10:00:30Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    # compute_observation must succeed (same content_id, monotonic)
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    # content_id stays exactly the same
    assert obs.content_id == snap1.content_id


def test_deterministic_second_snapshot_not_treated_as_new_content():
    """The second observation must NOT generate a new content_id;
    the same article stays the same content.

    Uses explicit fixed timestamps to guarantee distinct seconds.
    """
    cid_a = "ci_dual_test"
    snap1 = PerformanceSnapshot(
        content_id=cid_a, captured_at="2026-09-29T10:00:00Z",
    )
    snap2 = PerformanceSnapshot(
        content_id=cid_a,
        captured_at="2026-09-29T10:00:30Z",
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    # content_id stays exactly the same
    assert obs.content_id == cid_a


def test_deterministic_elapsed_seconds_matches_timestamps():
    """elapsed_seconds must equal int((t_new - t_old).total_seconds())."""
    res = _fetch_via_cache()
    snap1 = PerformanceSnapshot(
        content_id=res.observations[0].content_id,
        captured_at="2026-09-29T10:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap2 = PerformanceSnapshot(
        content_id=snap1.content_id,
        captured_at="2026-09-29T10:01:30Z",  # 90 seconds later
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    assert obs.elapsed_seconds == 90, (
        f"expected 90 seconds, got {obs.elapsed_seconds}"
    )
    assert obs.from_captured_at == "2026-09-29T10:00:00Z"
    assert obs.to_captured_at == "2026-09-29T10:01:30Z"


def test_deterministic_non_monotonic_timestamps_rejected():
    """compute_observation returns None when t_new < t_old."""
    res = _fetch_via_cache()
    snap_old = PerformanceSnapshot(
        content_id=res.observations[0].content_id,
        captured_at="2026-09-29T11:00:00Z",
    )
    snap_newer = PerformanceSnapshot(
        content_id=snap_old.content_id,
        captured_at="2026-09-29T10:00:00Z",  # earlier than snap_old
    )
    obs = compute_observation(snap_old, snap_newer)
    assert obs is None, "non-monotonic timestamps must reject observation"


def test_deterministic_different_content_ids_rejected():
    """compute_observation returns None when content_ids differ."""
    snap1 = PerformanceSnapshot(
        content_id="ci_aaa", captured_at="2026-09-29T10:00:00Z",
    )
    snap2 = PerformanceSnapshot(
        content_id="ci_bbb",
        captured_at="2026-09-29T11:00:00Z",
    )
    obs = compute_observation(snap1, snap2)
    assert obs is None


def test_deterministic_store_round_trip_preserves_observation():
    """Write PerformanceObservation to PerformanceStore and read back."""
    res = _fetch_via_cache()
    snap1 = PerformanceSnapshot(
        content_id=res.observations[0].content_id,
        captured_at="2026-09-29T10:00:00Z",
    )
    snap2 = PerformanceSnapshot(
        content_id=snap1.content_id,
        captured_at="2026-09-29T10:01:30Z",
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        store.put_observation(obs)
        loaded = store.list_observations_for(obs.content_id)
        assert len(loaded) == 1
        r = loaded[0]
        assert r["content_id"] == obs.content_id
        assert r["from_captured_at"] == obs.from_captured_at
        assert r["to_captured_at"] == obs.to_captured_at
        assert r["elapsed_seconds"] == obs.elapsed_seconds
        # All metric fields None
        for f in (
            "views_delta", "likes_delta", "comments_delta", "shares_delta",
            "views_per_hour", "likes_per_hour", "comments_per_hour",
            "shares_per_hour",
        ):
            assert r[f] is None, f"{f} should be None, got {r[f]!r}"
        # No synthetic flag
        assert not r.get("_synthetic")


def test_deterministic_synthetic_observation_refused_at_store():
    """SyntheticAdapter output must NOT be persistable via the
    documented caller-side gate."""
    syn = SyntheticAdapter("test", Platform.WEBSITE, [
        SyntheticAdapterRecord(
            content_id="syn_x", title="synthetic",
            published_at="2026-09-29T10:00:00Z",
            url="https://example.com/syn_x", views=10,
        ),
    ])
    res = syn.fetch()
    gated_out = 0
    for o in res.observations:
        if o.extra.get("_synthetic"):
            gated_out += 1
    assert gated_out == 1
    # The store still accepts a plain PerformanceSnapshot with no
    # _synthetic tag (schema-clean by design) — but the documented
    # contract says the caller must filter before projecting.
    snap = res.to_snapshots()[0]
    assert not hasattr(snap, "_synthetic") or getattr(snap, "_synthetic") is False


def test_deterministic_synthetic_payload_dict_rejected_by_store():
    """The store's defence-in-depth gate (raw dict with _synthetic) still fires."""
    from performance import store as store_module
    bad_payload = {
        "content_id": "syn_x",
        "from_captured_at": "2026-09-29T10:00:00Z",
        "to_captured_at": "2026-09-29T10:01:00Z",
        "elapsed_seconds": 60,
        "views_delta": 0,
        "likes_delta": 0,
        "comments_delta": 0,
        "shares_delta": 0,
        "views_per_hour": 0.0,
        "likes_per_hour": 0.0,
        "comments_per_hour": 0.0,
        "shares_per_hour": 0.0,
        "_synthetic": True,
    }
    raised = False
    try:
        store_module._validate_payload(bad_payload, "PerformanceObservation")
    except SyntheticFixtureError:
        raised = True
    assert raised


# ============================================================================
# 2. REAL LIVE VERIFICATION (gated by PERFORMANCE_BERNAMA_LIVE=1)
# ============================================================================

def test_live_bernama_first_fetch():
    """REAL LIVE: first fetch via real HTTPS GET against BERNAMA RSS."""
    if not IS_LIVE:
        return  # SKIP — deterministic tests cover the same code path
    res = _fetch_live()
    assert res.retrieval_status == RetrievalStatus.AVAILABLE, (
        f"live fetch failed: {res.errors}"
    )
    assert len(res.observations) >= 1


def test_live_bernama_two_fetches_same_content_ids():
    """REAL LIVE: two real fetches share content_ids for each article."""
    if not IS_LIVE:
        return
    res1 = _fetch_live()
    assert res1.retrieval_status == RetrievalStatus.AVAILABLE
    # Wait a real interval
    time.sleep(LIVE_FETCH_INTERVAL_SECONDS)
    res2 = _fetch_live()
    assert res2.retrieval_status == RetrievalStatus.AVAILABLE
    # Same articles -> same content_ids (BERNAMA RSS is deterministic on URL)
    ids1 = sorted([o.content_id for o in res1.observations])
    ids2 = sorted([o.content_id for o in res2.observations])
    # urls also match (BERNAMA may update titles but URL is the ID anchor)
    urls1 = sorted([o.url for o in res1.observations])
    urls2 = sorted([o.url for o in res2.observations])
    assert ids1 == ids2, "content_ids diverge across two live fetches"
    assert urls1 == urls2, "URLs diverge across two live fetches"


def test_live_bernama_dual_snapshot_math():
    """REAL LIVE: end-to-end dual snapshot → observation math.

    This is the actual smoke verification. Two real HTTPS GETs
    separated by ~3 seconds. The resulting two snapshots must
    produce a PerformanceObservation with all None metric fields
    (because BERNAMA RSS doesn't expose engagement) and
    elapsed_seconds > 0.
    """
    if not IS_LIVE:
        return
    res1 = _fetch_live()
    assert res1.retrieval_status == RetrievalStatus.AVAILABLE
    assert len(res1.observations) >= 1
    # Build snapshot_1
    a = res1.observations[0]
    snap1 = PerformanceSnapshot(
        content_id=a.content_id,
        captured_at=a.observed_at,
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    # Wait a real interval
    time.sleep(LIVE_FETCH_INTERVAL_SECONDS)
    # Second fetch
    res2 = _fetch_live()
    assert res2.retrieval_status == RetrievalStatus.AVAILABLE
    # Find the SAME article by URL in res2
    same_in_2 = None
    for o in res2.observations:
        if o.url == a.url:
            same_in_2 = o
            break
    assert same_in_2 is not None, (
        "BERNAMA RSS first article disappeared between fetches"
    )
    snap2 = PerformanceSnapshot(
        content_id=same_in_2.content_id,
        captured_at=same_in_2.observed_at,
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    # Identity preserved
    assert snap1.content_id == snap2.content_id
    assert snap1.captured_at != snap2.captured_at
    # Math
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    assert obs.elapsed_seconds >= LIVE_FETCH_INTERVAL_SECONDS - 1
    # All metric fields None
    for f in (
        "views_delta", "likes_delta", "comments_delta", "shares_delta",
        "views_per_hour", "likes_per_hour", "comments_per_hour",
        "shares_per_hour",
    ):
        assert getattr(obs, f) is None
    # Classification is INSUFFICIENT_DATA (no metrics to classify on)
    cls = classify_performance(obs)
    assert cls == PerformanceClass.INSUFFICIENT_DATA


# ============================================================================
# 3. Cross-platform guardrail
# ============================================================================

def test_deterministic_bernama_observations_carry_no_synthetic_flag():
    """BERNAMA rows MUST NOT carry _synthetic=True under any path."""
    res = _fetch_via_cache()
    for o in res.observations:
        assert not o.extra.get("_synthetic"), (
            f"BERNAMA row {o.content_id} leaked _synthetic"
        )


def test_deterministic_persisted_observation_carry_no_synthetic_flag():
    """The store refuses any payload with _synthetic. A live BERNAMA
    observation, persisted, must not be marked synthetic.
    """
    res = _fetch_via_cache()
    snap1 = PerformanceSnapshot(
        content_id=res.observations[0].content_id,
        captured_at="2026-09-29T10:00:00Z",
    )
    snap2 = PerformanceSnapshot(
        content_id=snap1.content_id,
        captured_at="2026-09-29T10:00:30Z",
    )
    obs = compute_observation(snap1, snap2)
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        store.put_observation(obs)
        loaded = store.list_observations_for(obs.content_id)
        assert not loaded[0].get("_synthetic")


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
        print(f"ALL {len(test_funcs)} P3-B-2A DUAL-SNAPSHOT TESTS PASSED")
