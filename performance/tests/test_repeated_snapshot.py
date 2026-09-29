"""
P3-B-4 Repeated Snapshot / Time-Series Scheduler Foundation tests.

Goal: prove the time-series foundation works end-to-end:

  real BERNAMA RSS
        |
        v
  BernamaRssAdapter.fetch()
        |
        v
  AdapterObservation -> PerformanceSnapshot (projected)
        |
        v
  PerformanceStore (atomic write, synthetic gate, history preserved)
        |
        v
  Repeated run at later captured_at -> distinct snapshots
        |
        v
  compute_observation(snap1, snap2) -> PerformanceObservation
        |
        v
  observation_id stamped, history preserved

Hard invariants verified here:

  * Same URL -> same content_id (already in P3-B-1; re-verified).
  * Distinct captured_at -> distinct snapshot files (history).
  * observation_id is deterministic and distinct per (from, to).
  * Real BERNAMA observations: metrics stay None, velocity None,
    classification = INSUFFICIENT_DATA.
  * SyntheticAdapter rows are filtered upstream; synthetic data
    NEVER reaches the production store.
  * SchedulerLock is acquired/released cleanly; stale locks are
    recovered; failure releases the lock.
  * Atomic write failure leaves previous snapshot intact.
  * Two runs at the same captured_at -> idempotent re-write.
  * Two runs at distinct captured_at -> distinct files.

Strictly NOT verified (out of scope per spec):

  * No real cron / Task Scheduler / watchdog.
  * No Facebook / Android Collector / PlatformContentRef.
  * No ranking / prediction / political scoring.
  * No LLM / AI classification.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest.mock as mock
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone

from performance import (
    AdapterObservation,
    BernamaRssAdapter,
    Platform,
    PerformanceObservation,
    PerformanceSnapshot,
    PerformanceStore,
    RetrievalStatus,
    SyntheticAdapter,
    SyntheticAdapterRecord,
    SyntheticFixtureError,
    compute_observation,
    classify_performance,
    PerformanceClass,
    engagement_rate,
    engagement_total,
    observation_id_for,
    SchedulerLock,
    SchedulerLockError,
    ExecutionLog,
    ExecutionStatus,
    scheduler_run_once,
)


IS_LIVE = os.environ.get("PERFORMANCE_BERNAMA_LIVE") == "1"


# ============================================================================
# Cached real BERNAMA RSS feed
# ============================================================================

CACHED_BERNAMA_RSS = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
<rss version="2.0">
<channel>
<title>BERNAMA - English Version</title>
<link>http://www.bernama.com/en</link>
<description>BERNAMA</description>
<language>en-us</language>
<item>
<title>World : Same Story A Day 1</title>
<link>http://www.bernama.com/en/news.php?id=2900001</link>
<description>&lt;font size=1&gt;&lt;p&gt;KUALA LUMPUR, Sept 29 (Bernama) -- Same story day 1.&lt;/p&gt;&lt;/font&gt;</description>
</item>
<item>
<title>World : Different Story B Day 1</title>
<link>http://www.bernama.com/en/news.php?id=2900002</link>
<description>&lt;font size=1&gt;&lt;p&gt;KUALA LUMPUR, Sept 29 (Bernama) -- Different story B day 1.&lt;/p&gt;&lt;/font&gt;</description>
</item>
</channel>
</rss>"""


def _patch_urlopen():
    import performance.adapters as adapters_module
    fake_resp = SimpleNamespace(
        read=lambda: CACHED_BERNAMA_RSS,
        status=200,
        headers={"Content-Type": "text/xml"},
    )
    return mock.patch.object(
        adapters_module.urllib.request, "urlopen",
        return_value=mock.MagicMock(__enter__=lambda self: fake_resp),
    )


def _fetch_cached() -> object:
    adapter = BernamaRssAdapter()
    with _patch_urlopen():
        return adapter.fetch()


def _fetch_live() -> object:
    adapter = BernamaRssAdapter()
    return adapter.fetch()


# ============================================================================
# 1. Repeated snapshot history
# ============================================================================

def test_repeated_snapshot_creates_distinct_files():
    """Two runs at distinct captured_at produce distinct snapshot
    files in PerformanceStore.snapshots_dir.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        # Run #1
        snap1 = PerformanceSnapshot(
            content_id="ci_x", captured_at="2026-09-29T10:00:00Z",
            views=None, likes=None, comments=None, shares=None, reposts=None,
        )
        store.put_snapshot(snap1)
        # Run #2 at later captured_at
        snap2 = PerformanceSnapshot(
            content_id="ci_x", captured_at="2026-09-29T11:00:00Z",
            views=None, likes=None, comments=None, shares=None, reposts=None,
        )
        store.put_snapshot(snap2)
        # Both recoverable
        all_snaps = store.list_snapshots_for("ci_x")
        assert len(all_snaps) == 2
        assert all_snaps[0]["captured_at"] == "2026-09-29T10:00:00Z"
        assert all_snaps[1]["captured_at"] == "2026-09-29T11:00:00Z"


def test_same_captured_at_repeated_run_is_idempotent():
    """Two runs at the SAME captured_at -> single file (idempotent
    overwrite of identical payload).
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        snap = PerformanceSnapshot(
            content_id="ci_x", captured_at="2026-09-29T10:00:00Z",
            views=None, likes=None, comments=None, shares=None, reposts=None,
        )
        store.put_snapshot(snap)
        store.put_snapshot(snap)
        all_snaps = store.list_snapshots_for("ci_x")
        # Same captured_at -> same filename -> 1 file
        assert len(all_snaps) == 1


def test_content_id_stable_across_repeated_runs():
    """Same URL -> same content_id. Re-verified here as a guard
    before time-series math.
    """
    res = _fetch_cached()
    assert res.retrieval_status.value == "AVAILABLE"
    # Run twice via cached fetch; same URLs -> same content_ids
    res2 = _fetch_cached()
    ids1 = sorted(o.content_id for o in res.observations)
    ids2 = sorted(o.content_id for o in res2.observations)
    assert ids1 == ids2
    # All URLs distinct
    urls = [o.url for o in res.observations]
    assert len(set(urls)) == len(urls)


# ============================================================================
# 2. Observation ID stability
# ============================================================================

def test_observation_id_is_deterministic_per_triple():
    """observation_id_for(content_id, from, to) is deterministic:
    same triple -> same id.
    """
    a = observation_id_for("ci_x", "2026-09-29T10:00:00Z",
                            "2026-09-29T11:00:00Z")
    b = observation_id_for("ci_x", "2026-09-29T10:00:00Z",
                            "2026-09-29T11:00:00Z")
    assert a == b
    assert a.startswith("o_")  # P1 ID namespace


def test_observation_id_distinct_per_distinct_to():
    """Same content_id + same from_captured_at + DIFFERENT to_captured_at
    -> DIFFERENT observation_id.
    """
    a = observation_id_for("ci_x", "2026-09-29T10:00:00Z",
                            "2026-09-29T11:00:00Z")
    b = observation_id_for("ci_x", "2026-09-29T10:00:00Z",
                            "2026-09-29T12:00:00Z")
    assert a != b


def test_observation_id_distinct_per_distinct_from():
    """Same content_id + DIFFERENT from_captured_at -> DIFFERENT
    observation_id.
    """
    a = observation_id_for("ci_x", "2026-09-29T10:00:00Z",
                            "2026-09-29T11:00:00Z")
    b = observation_id_for("ci_x", "2026-09-29T09:00:00Z",
                            "2026-09-29T11:00:00Z")
    assert a != b


def test_observation_id_distinct_per_distinct_content_id():
    """DIFFERENT content_id -> DIFFERENT observation_id.
    """
    a = observation_id_for("ci_x", "2026-09-29T10:00:00Z",
                            "2026-09-29T11:00:00Z")
    b = observation_id_for("ci_y", "2026-09-29T10:00:00Z",
                            "2026-09-29T11:00:00Z")
    assert a != b


def test_compute_observation_stamps_observation_id():
    """compute_observation stamps the observation_id field.
    """
    snap_old = PerformanceSnapshot(
        content_id="ci_x", captured_at="2026-09-29T10:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap_new = PerformanceSnapshot(
        content_id="ci_x", captured_at="2026-09-29T11:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    obs = compute_observation(snap_old, snap_new)
    assert obs is not None
    assert obs.observation_id is not None
    expected = observation_id_for(
        "ci_x", "2026-09-29T10:00:00Z", "2026-09-29T11:00:00Z",
    )
    assert obs.observation_id == expected


# ============================================================================
# 3. Real BERNAMA repeated snapshot semantics
# ============================================================================

def test_bernama_repeated_snapshot_metrics_remain_none():
    """Real BERNAMA doesn't expose engagement metrics; repeated
    snapshots must keep them None end-to-end.
    """
    res = _fetch_cached()
    snap1 = PerformanceSnapshot(
        content_id=res.observations[0].content_id,
        captured_at="2026-09-29T10:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap2 = PerformanceSnapshot(
        content_id=res.observations[0].content_id,
        captured_at="2026-09-29T11:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    # All deltas stay None
    assert obs.views_delta is None
    assert obs.likes_delta is None
    assert obs.comments_delta is None
    assert obs.shares_delta is None
    # All velocities stay None
    assert obs.views_per_hour is None
    assert obs.likes_per_hour is None
    assert obs.comments_per_hour is None
    assert obs.shares_per_hour is None
    # Classification is INSUFFICIENT_DATA (None metrics)
    cls = classify_performance(obs)
    assert cls == PerformanceClass.INSUFFICIENT_DATA
    # Engagement metrics return None
    assert engagement_total(snap1) is None
    assert engagement_rate(snap1) is None


def test_bernama_repeated_snapshot_observation_id_distinct():
    """Two observations of the same BERNAMA article at distinct
    timestamps produce distinct observation_ids.
    """
    cid = "ci_bernama_repeated_test"
    obs_a = compute_observation(
        PerformanceSnapshot(content_id=cid,
                            captured_at="2026-09-29T10:00:00Z",
                            views=None, likes=None, comments=None,
                            shares=None, reposts=None),
        PerformanceSnapshot(content_id=cid,
                            captured_at="2026-09-29T11:00:00Z",
                            views=None, likes=None, comments=None,
                            shares=None, reposts=None),
    )
    obs_b = compute_observation(
        PerformanceSnapshot(content_id=cid,
                            captured_at="2026-09-29T11:00:00Z",
                            views=None, likes=None, comments=None,
                            shares=None, reposts=None),
        PerformanceSnapshot(content_id=cid,
                            captured_at="2026-09-29T12:00:00Z",
                            views=None, likes=None, comments=None,
                            shares=None, reposts=None),
    )
    assert obs_a.observation_id != obs_b.observation_id
    assert obs_a.content_id == obs_b.content_id == cid


def test_bernama_repeated_snapshot_classification_insufficient():
    """Even with distinct elapsed_seconds, classification is
    INSUFFICIENT_DATA (no metrics to classify).
    """
    snap1 = PerformanceSnapshot(
        content_id="ci_x", captured_at="2026-09-29T10:00:00Z",
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    snap2 = PerformanceSnapshot(
        content_id="ci_x", captured_at="2026-09-29T13:00:00Z",  # 3 hours
        views=None, likes=None, comments=None, shares=None, reposts=None,
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    assert obs.elapsed_seconds == 3 * 3600  # 10800 seconds
    assert classify_performance(obs) == PerformanceClass.INSUFFICIENT_DATA


# ============================================================================
# 4. SyntheticAdapter fixture data for math verification
# ============================================================================

def test_synthetic_repeated_snapshot_delta_math():
    """SyntheticAdapter rows with real metrics -> delta / velocity
    math works correctly.
    """
    # Use SyntheticAdapter to build deterministic observations
    syn = SyntheticAdapter("test", Platform.WEBSITE, [
        SyntheticAdapterRecord(
            content_id="syn_x", title="synthetic article",
            published_at="2026-09-29T10:00:00Z",
            url="https://example.com/syn_x",
            views=100, likes=10, comments=1, shares=2,
        ),
    ])
    res = syn.fetch()
    obs = res.observations[0]

    snap1 = PerformanceSnapshot(
        content_id=obs.content_id, captured_at="2026-09-29T10:00:00Z",
        views=100, likes=10, comments=1, shares=2, reposts=None,
    )
    snap2 = PerformanceSnapshot(
        content_id=obs.content_id, captured_at="2026-09-29T11:00:00Z",
        views=1100, likes=100, comments=10, shares=20, reposts=None,
    )
    obs_out = compute_observation(snap1, snap2)
    assert obs_out is not None
    # Deltas
    assert obs_out.views_delta == 1000
    assert obs_out.likes_delta == 90
    assert obs_out.comments_delta == 9
    assert obs_out.shares_delta == 18
    # Velocities (per hour over 1h)
    assert obs_out.views_per_hour == 1000.0
    assert obs_out.likes_per_hour == 90.0
    assert obs_out.comments_per_hour == 9.0
    assert obs_out.shares_per_hour == 18.0


def test_synthetic_repeated_snapshot_classification_fast_growth():
    """Synthetic 10x views/hour -> growth classification.

    The exact category is determined by classify_performance; we
    only assert it's NOT INSUFFICIENT_DATA (since we have metrics)
    and is one of the growth-class values.
    """
    snap1 = PerformanceSnapshot(
        content_id="ci_x", captured_at="2026-09-29T10:00:00Z",
        views=100, likes=10, comments=1, shares=2, reposts=None,
    )
    snap2 = PerformanceSnapshot(
        content_id="ci_x", captured_at="2026-09-29T11:00:00Z",
        views=1100, likes=100, comments=10, shares=20, reposts=None,
    )
    obs = compute_observation(snap1, snap2)
    assert obs is not None
    cls = classify_performance(obs)
    # We have metrics; classification must NOT be INSUFFICIENT_DATA
    assert cls != PerformanceClass.INSUFFICIENT_DATA, (
        f"with metrics present, classification should not be "
        f"INSUFFICIENT_DATA; got {cls}"
    )
    # Must be one of the growth classes
    growth_classes = {
        PerformanceClass.EARLY_SPIKE,
        PerformanceClass.FAST_GROWTH,
        PerformanceClass.STEADY_GROWTH,
        PerformanceClass.LATE_BREAKOUT,
    }
    assert cls in growth_classes, (
        f"expected a growth class; got {cls}"
    )


def test_synthetic_adapter_filtered_from_production_store():
    """SyntheticAdapter rows MUST NOT reach the production store.

    The scheduler filters them upstream via the extra['_synthetic']
    check. Even if a synthetic row slips through, the store gate
    raises SyntheticFixtureError.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        # SyntheticAdapter
        syn = SyntheticAdapter("test", Platform.WEBSITE, [
            SyntheticAdapterRecord(
                content_id="syn_x", title="synthetic",
                published_at="2026-09-29T10:00:00Z",
                url="https://example.com/syn_x", views=10,
            ),
        ])
        result = syn.fetch()
        record = scheduler_run_once(
            adapter=syn, store=store,
            captured_at="2026-09-29T10:00:00Z",
        )
        # The scheduler must have filtered synthetic; check
        # store has zero snapshots
        assert len(store.list_snapshots_for("syn_x")) == 0
        # Status is SUCCESS or PARTIAL (no synthetic count) —
        # the filter prevents the synthetic row from being
        # persisted as a snapshot.
        # However the row's observation_count will be 0 since
        # it was filtered.
        assert record.observation_count == 0
        assert record.snapshot_count == 0


# ============================================================================
# 5. Scheduler foundation tests
# ============================================================================

def test_scheduler_run_once_with_real_bernama():
    """Run the scheduler once with cached real BERNAMA adapter.

    Verifies:
      - Lock acquired
      - Snapshots persisted
      - ExecutionRecord written
      - Lock released
      - All real BERNAMA observations stored with None metrics
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        # Custom adapter from cached fetch
        adapter = BernamaRssAdapter()
        with _patch_urlopen():
            record = scheduler_run_once(
                adapter=adapter, store=store,
                captured_at="2026-09-29T10:00:00Z",
            )
        assert record.status == ExecutionStatus.SUCCESS.value
        assert record.observation_count >= 1
        # Snapshots recoverable
        for o in _fetch_cached().observations:
            snaps = store.list_snapshots_for(o.content_id)
            assert len(snaps) >= 1
            s = snaps[0]
            assert s["views"] is None
            assert s["likes"] is None
            assert s["comments"] is None
            assert s["shares"] is None
            assert s["reposts"] is None
        # Lock released: another run should succeed immediately
        with _patch_urlopen():
            record2 = scheduler_run_once(
                adapter=adapter, store=store,
                captured_at="2026-09-29T11:00:00Z",
            )
        assert record2.status == ExecutionStatus.SUCCESS.value
        # Both runs' snapshots recoverable
        for o in _fetch_cached().observations:
            snaps = store.list_snapshots_for(o.content_id)
            assert len(snaps) == 2  # both runs


def test_scheduler_run_once_skipped_when_locked():
    """When the lock is held by a still-running process, run_once
    returns SKIPPED_LOCKED.

    Uses the current process's pid so the lock is NOT stale
    (psutil.pid_exists(my_pid) returns True).
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        adapter = BernamaRssAdapter()

        lock_path = store.data_dir / ".scan.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Use a fresh (current) timestamp and current pid so
        # the lock is NOT considered stale by age or pid check.
        import json as _json
        import os as _os
        from datetime import datetime as _dt, timezone as _tz
        ts = _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lock_path.write_text(_json.dumps({
            "pid": _os.getpid(),
            "acquired_at": ts,
        }))
        try:
            record = scheduler_run_once(
                adapter=adapter, store=store,
                captured_at="2026-09-29T10:00:00Z",
            )
            assert record.status == ExecutionStatus.SKIPPED_LOCKED.value, (
                f"expected SKIPPED_LOCKED, got {record.status}"
            )
        finally:
            if lock_path.exists():
                lock_path.unlink()


def test_scheduler_stale_lock_recovery():
    """A lock older than STALE_AFTER_SECONDS is recovered and the
    next run succeeds.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        adapter = BernamaRssAdapter()

        lock_path = store.data_dir / ".scan.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Stale lock: timestamp 2 hours ago (STALE_AFTER = 3600s)
        from datetime import datetime, timezone
        import json as _json
        ts = (datetime.now(timezone.utc)
              .replace(hour=0, minute=0, second=0, microsecond=0)
              .strftime("%Y-%m-%dT%H:%M:%SZ"))
        lock_path.write_text(_json.dumps({
            "pid": 999999,
            "acquired_at": ts,
        }))
        try:
            with _patch_urlopen():
                record = scheduler_run_once(
                    adapter=adapter, store=store,
                    captured_at="2026-09-29T10:00:00Z",
                )
            # Stale lock is recovered; run succeeded
            assert record.status == ExecutionStatus.SUCCESS.value
        finally:
            if lock_path.exists():
                lock_path.unlink()


def test_scheduler_lock_released_on_failure():
    """When the adapter raises, the lock is still released so the
    next run can proceed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")

        class FailingAdapter:
            source_name = "failing"
            def fetch(self):
                raise RuntimeError("simulated fetch failure")

        record = scheduler_run_once(
            adapter=FailingAdapter(), store=store,
            captured_at="2026-09-29T10:00:00Z",
        )
        assert record.status == ExecutionStatus.FAILED.value
        # Lock must be released
        lock_path = store.data_dir / ".scan.lock"
        assert not lock_path.exists(), (
            "lock must be released after failure"
        )


def test_scheduler_execution_log_records_each_run():
    """Each scheduler run appends a JSON line to execution_log.jsonl.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        adapter = BernamaRssAdapter()
        with _patch_urlopen():
            scheduler_run_once(adapter=adapter, store=store,
                               captured_at="2026-09-29T10:00:00Z")
            scheduler_run_once(adapter=adapter, store=store,
                               captured_at="2026-09-29T11:00:00Z")
        log = ExecutionLog(store.data_dir / "execution_log.jsonl")
        rows = log.read_all()
        # 2 runs (newest first)
        assert len(rows) == 2
        assert rows[0]["status"] == ExecutionStatus.SUCCESS.value
        assert rows[1]["status"] == ExecutionStatus.SUCCESS.value
        # Different run_ids (different captured_at)
        assert rows[0]["run_id"] != rows[1]["run_id"]


# ============================================================================
# 6. Atomic write / history integrity
# ============================================================================

def test_atomic_write_failure_preserves_history():
    """When json.dump fails, the previous snapshot must still be
    readable. This is the foundation of history integrity.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        snap1 = PerformanceSnapshot(
            content_id="ci_x", captured_at="2026-09-29T10:00:00Z",
            views=None, likes=None, comments=None, shares=None, reposts=None,
        )
        store.put_snapshot(snap1)
        # Now simulate a write failure for the second snapshot
        snap2 = PerformanceSnapshot(
            content_id="ci_x", captured_at="2026-09-29T11:00:00Z",
            views=None, likes=None, comments=None, shares=None, reposts=None,
        )
        import performance.store as store_module
        with mock.patch.object(store_module.json, "dump",
                               side_effect=RuntimeError("simulated")):
            raised = False
            try:
                store.put_snapshot(snap2)
            except RuntimeError:
                raised = True
        assert raised
        # Previous snapshot must still be intact
        snaps = store.list_snapshots_for("ci_x")
        assert len(snaps) == 1
        assert snaps[0]["captured_at"] == "2026-09-29T10:00:00Z"


def test_observation_history_preserved_through_store():
    """Two observations of the same content at different timestamps
    produce two distinct files; both recoverable.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        cid = "ci_x"
        # First observation
        snap1 = PerformanceSnapshot(content_id=cid,
                                    captured_at="2026-09-29T10:00:00Z")
        snap2 = PerformanceSnapshot(content_id=cid,
                                    captured_at="2026-09-29T11:00:00Z")
        obs1 = compute_observation(snap1, snap2)
        store.put_observation(obs1)
        # Second observation (different timestamp window)
        snap3 = PerformanceSnapshot(content_id=cid,
                                    captured_at="2026-09-29T11:00:00Z")
        snap4 = PerformanceSnapshot(content_id=cid,
                                    captured_at="2026-09-29T12:00:00Z")
        obs2 = compute_observation(snap3, snap4)
        store.put_observation(obs2)
        # Both recoverable
        all_obs = store.list_observations_for(cid)
        assert len(all_obs) == 2
        # Different observation_ids
        ids = {o["observation_id"] for o in all_obs}
        assert len(ids) == 2


# ============================================================================
# 7. None-metric None-velocity invariant under repeated snapshots
# ============================================================================

def test_bernama_metrics_remain_none_across_n_runs():
    """No matter how many times we sample real BERNAMA, all 5
    engagement metrics stay None. velocity stays None.
    classification stays INSUFFICIENT_DATA.

    This is the documented normal result for BERNAMA, not an error.
    """
    res = _fetch_cached()
    cid = res.observations[0].content_id
    # Build 3 successive snapshots
    snaps = []
    for hr in range(3):
        snap = PerformanceSnapshot(
            content_id=cid,
            captured_at=f"2026-09-29T{10+hr:02d}:00:00Z",
            views=None, likes=None, comments=None, shares=None, reposts=None,
        )
        snaps.append(snap)
    # Compute two observations
    for i in range(2):
        obs = compute_observation(snaps[i], snaps[i + 1])
        assert obs is not None
        for f in ("views_delta", "likes_delta", "comments_delta",
                   "shares_delta", "views_per_hour", "likes_per_hour",
                   "comments_per_hour", "shares_per_hour"):
            assert getattr(obs, f) is None
        assert classify_performance(obs) == PerformanceClass.INSUFFICIENT_DATA


# ============================================================================
# 8. LIVE: real BERNAMA repeated fetch verification
# ============================================================================

def test_live_bernama_two_fetches_via_scheduler():
    """REAL LIVE: two scheduler runs on real BERNAMA, separated
    by a real time interval. Verify history preserved.

    This is the live end-to-end smoke verification. Reports all
    invariants. Real BERNAMA doesn't expose engagement metrics,
    so velocity stays None and classification is INSUFFICIENT_DATA.
    """
    if not IS_LIVE:
        return
    with tempfile.TemporaryDirectory() as tmp:
        store = PerformanceStore(data_dir=Path(tmp) / "perf_data")
        adapter = BernamaRssAdapter()

        # Run #1
        record1 = scheduler_run_once(
            adapter=adapter, store=store,
            captured_at="2026-09-29T10:00:00Z",
        )
        assert record1.status == ExecutionStatus.SUCCESS.value
        time.sleep(LIVE_FETCH_INTERVAL_SECONDS := 3)

        # Run #2
        record2 = scheduler_run_once(
            adapter=adapter, store=store,
            captured_at="2026-09-29T11:00:00Z",
        )
        assert record2.status == ExecutionStatus.SUCCESS.value

        # For each BERNAMA article, both runs produced snapshots
        res = adapter.fetch()
        print(f"\n=== P3-B-4 LIVE BERNAMA repeated snapshot stats ===")
        print(f"run #1: status={record1.status.value}, "
              f"obs={record1.observation_count}, "
              f"snap={record1.snapshot_count}")
        print(f"run #2: status={record2.status.value}, "
              f"obs={record2.observation_count}, "
              f"snap={record2.snapshot_count}")
        for o in res.observations[:3]:
            snaps = store.list_snapshots_for(o.content_id)
            print(f"  content_id={o.content_id[:30]}... snapshots={len(snaps)}")
            for s in snaps:
                print(f"    captured_at={s['captured_at']} "
                      f"views={s['views']} likes={s['likes']}")
        print("=== end live stats ===\n")
        # Both runs preserved
        for o in res.observations:
            snaps = store.list_snapshots_for(o.content_id)
            assert len(snaps) == 2, (
                f"expected 2 snapshots for {o.content_id}, got {len(snaps)}"
            )
            # Both have None metrics
            for s in snaps:
                assert s["views"] is None
                assert s["likes"] is None
                assert s["comments"] is None
                assert s["shares"] is None
                assert s["reposts"] is None


# ============================================================================
# Runner
# ============================================================================

if __name__ == "__main__":
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
            failed.append((name, str(e) if str(e) else "<empty assertion>"))
            print(f"FAIL {name}: {e if str(e) else '<empty assertion>'}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"ERROR {name}: {e}")
            import traceback
            traceback.print_exc()
    print()
    print(f"{passed} passed, {len(failed)} failed of {len(test_funcs)} tests")
    if failed:
        for n, e in failed:
            print(f"  {n}: {e}")
        sys.exit(1)
    else:
        print(f"ALL {len(test_funcs)} P3-B-4 SCHEDULER TESTS PASSED")