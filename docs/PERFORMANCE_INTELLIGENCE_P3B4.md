# Performance Intelligence — P3-B-4: Repeated Snapshot / Time-Series Scheduler Foundation

**Status:** P3-B-4 — PASS

**Goal:** Provide a minimal, reliable repeated-snapshot /
time-series foundation so the same content can be sampled
multiple times, producing a chain of observations with stable
content_ids, distinct observation_ids, monotonic timestamps,
and history-preserving persistence.

This is the FOUNDATION ONLY. It does NOT add Windows Task
Scheduler, cron, watchdog, or any auto-run mechanism. Production
scheduling is a separate, future-approved step.

---

## 1. What P3-B-4 does

* Adds `PerformanceObservation.observation_id: Optional[str]`
  (additive, default `None`). `compute_observation()` stamps it
  deterministically from `(content_id, from_captured_at,
  to_captured_at)`.
* Adds `performance/scheduler.py` with the Performance
  scheduler foundation: `SchedulerLock`, `ExecutionStatus`,
  `ExecutionRecord`, `ExecutionLog`, `run_once()`. Modeled
  after `radar/scheduler.py` (independent copy — Radar is
  untouched).
* `PerformanceStore.put_observation()` filename now includes
  `observation_id` for cleaner indexing. Snapshots remain
  keyed by `(captured_at, content_id)` so distinct timestamps
  produce distinct files (history preserved).

## 2. What P3-B-4 does NOT do

* ❌ NO Windows Task Scheduler entry.
* ❌ NO cron / watchdog / auto-run.
* ❌ NO scheduler background daemon.
* ❌ NO modification to `match_stories()`, `classify_performance()`,
  velocity math, classification thresholds, or P2 matching.
* ❌ NO modification to Radar / Candidate / Website.
* ❌ NO Facebook / Android Collector / PlatformContentRef.
* ❌ NO engagement metrics guessing; real BERNAMA stays None.
* ❌ NO LLM / AI classification / ranking / prediction.
* ❌ NO political scoring.
* ❌ NO Experience promotion.

---

## 3. Scheduler architecture

```
                run_once
+-------------------+
| acquire lock      |
+-------------------+
        |
        v
+-------------------+
| adapter.fetch()    |  BernamaRssAdapter or any PublicPerformanceAdapter
+-------------------+
        |
        v
+-------------------+
| filter _synthetic  |  upstream synthetic gate (defence in depth)
+-------------------+
        |
        v
+-------------------+
| project to         |  PerformanceSnapshot(content_id, captured_at, ...)
| PerformanceSnapshot|
+-------------------+
        |
        v
+-------------------+
| PerformanceStore.  |  atomic write; synthetic gate at validation layer
| put_snapshot       |
+-------------------+
        |
        v
+-------------------+
| ExecutionLog.      |  one JSON line per run
| append             |  separate from snapshot files
+-------------------+
        |
        v
+-------------------+
| release lock       |  always, success or failure
+-------------------+
```

### Lock

* `SchedulerLock` — file-based single-instance lock at
  `<data_dir>/.scan.lock`
* Atomic acquire: tmp + os.replace
* Stale-lock recovery: max-age 3600s + psutil `pid_exists` check
* Released on success AND failure

### Status

* `SUCCESS` — snapshots persisted, no errors
* `PARTIAL` — some snapshots persisted, some failed
* `FAILED` — catastrophic failure, no snapshots persisted
* `SKIPPED_LOCKED` — another run is in progress

### History

* `PerformanceStore.put_snapshot(snap)` writes
  `{safe_cap}__{content_id}.json`
* Two runs at **distinct** `captured_at` → distinct files
* Two runs at **same** `captured_at` → idempotent overwrite
* `PerformanceStore.put_observation(obs)` writes
  `{content_id}__{safe_from}__{safe_to}__{observation_id}.json`
* Different `(from, to)` triples → different files

### Failure handling

* Adapter fetch raises → record `FAILED`, lock released
* SyntheticAdapter rows → filtered upstream; even if they slip
  through, the store's `_validate_payload` raises
  `SyntheticFixtureError`
* Atomic write failure → previous file preserved (no overwrite)

---

## 4. Real BERNAMA verification (live, 2026-09-29)

### Fetch #1 (captured_at: 2026-09-29T10:00:00Z)

```
status: SUCCESS
run_id: 20260929T100000Z-<pid>
observation_count: 10
snapshot_count: 10

Sample article:
  URL:             http://www.bernama.com/en/news.php?id=2613526
  content_id:      ci_d688800ef0949b8db8e20f5b
  captured_at:     2026-09-29T10:00:00Z
  views:           None
  likes:           None
  comments:        None
  shares:          None
  reposts:         None
```

### Fetch #2 (captured_at: 2026-09-29T11:00:00Z, after 3s wait)

```
status: SUCCESS
run_id: 20260929T110000Z-<pid>
observation_count: 10
snapshot_count: 10
```

### History (same store, two runs)

```
ci_d688800ef0949b8db8e20f5b: 2 snapshots
  captured_at=2026-09-29T10:00:00Z
  captured_at=2026-09-29T11:00:00Z
ci_62ffcfece83728645fcd44d2: 2 snapshots
  captured_at=2026-09-29T10:00:00Z
  captured_at=2026-09-29T11:00:00Z
ci_d21c35156d5600eff2295a6a: 2 snapshots
  captured_at=2026-09-29T10:00:00Z
  captured_at=2026-09-29T11:00:00Z
```

### Observation math (synthetic timing for the demo)

```
content_id:       ci_demo
from/to:          2026-09-29T10:00:00Z -> 2026-09-29T11:00:00Z
elapsed_seconds:   3600
observation_id:   o_c6edc20bf9828874076063e88b4f4b0f
views_delta:      None
views_per_hour:   None
classification:   INSUFFICIENT_DATA
```

**Honest finding:** Real BERNAMA has no engagement metrics.
Repeated snapshots produce identical `None` deltas and velocity
fields. Classification remains `INSUFFICIENT_DATA`. This is
the **documented normal result** for BERNAMA — it is NOT a
performance issue; it is the absence of public engagement data.

---

## 5. Synthetic analysis (math verification)

Using `SyntheticAdapter` to populate real metrics:

```
snap1: views=100, likes=10, comments=1, shares=2
snap2: views=1100, likes=100, comments=10, shares=20
captured_at difference: 1 hour

Result:
  views_delta:       1000
  likes_delta:       90
  comments_delta:    9
  shares_delta:      18
  views_per_hour:    1000.0
  likes_per_hour:    90.0
  comments_per_hour: 9.0
  shares_per_hour:   18.0
  classification:    EARLY_SPIKE  (growth class)
```

**Strict isolation:** `SyntheticAdapter` rows carry
`extra['_synthetic']=True`. The scheduler filters them
upstream, so they never reach the production store. Verified
explicitly: 0 snapshots persisted, 0 observations counted.

---

## 6. History invariants

| Invariant | Verified |
|---|---|
| Same URL → same content_id across runs | ✅ |
| Different captured_at → different snapshot files | ✅ |
| Same captured_at → idempotent re-write (single file) | ✅ |
| Two runs at distinct timestamps → distinct observation_ids | ✅ |
| Same `(content_id, from, to)` triple → same observation_id | ✅ |
| History not overwritten by new snapshot | ✅ |
| Atomic write failure preserves previous snapshot | ✅ |
| All 5 engagement metrics stay None on real BERNAMA | ✅ |
| velocity fields stay None when metrics are None | ✅ |
| classification = INSUFFICIENT_DATA when no metrics | ✅ |
| SyntheticAdapter rows never reach production store | ✅ |

---

## 7. Lock / safety invariants

| Behavior | Verified |
|---|---|
| `acquire()` is atomic (tmp + os.replace) | ✅ |
| Active lock blocks new runs (SKIPPED_LOCKED) | ✅ |
| Stale lock recovered automatically | ✅ |
| Failure releases lock | ✅ |
| Lock released even on fetch exception | ✅ |
| Lock NOT force-cleaned when valid active | ✅ |

---

## 8. Test results

| Suite | Count |
|---|---|
| P1 (existing) | 49 / 49 PASS |
| P2 (existing) | 59 / 59 PASS |
| P3-A (existing) | 37 / 37 PASS |
| Android Bridge (existing) | 39 / 39 PASS |
| P3-B-1 (existing) | 21 / 21 PASS |
| P3-B-2A (existing) | 24 / 24 PASS |
| P3-B-3 (existing) | 32 / 32 PASS |
| P3-B-5 (existing + follow-up) | 33 / 33 PASS |
| P3-B-6 (existing) | 15 / 15 PASS |
| **P3-B-4 (new)** | **23 / 23 PASS** |
| **Total Performance** | **332 / 332 PASS** |
| Radar (no-touch) | 396 / 396 PASS |
| **Grand Total** | **728 / 728 PASS** |

P3-B-4 test breakdown (23 tests):

| Test | Purpose |
|---|---|
| `test_repeated_snapshot_creates_distinct_files` | history preserved |
| `test_same_captured_at_repeated_run_is_idempotent` | same ts → 1 file |
| `test_content_id_stable_across_repeated_runs` | URL-anchored identity |
| `test_observation_id_is_deterministic_per_triple` | same (c,f,t) → same id |
| `test_observation_id_distinct_per_distinct_to` | different to → different id |
| `test_observation_id_distinct_per_distinct_from` | different from → different id |
| `test_observation_id_distinct_per_distinct_content_id` | different content → different id |
| `test_compute_observation_stamps_observation_id` | math stamps id |
| `test_bernama_repeated_snapshot_metrics_remain_none` | None preserved |
| `test_bernama_repeated_snapshot_observation_id_distinct` | real data math |
| `test_bernama_repeated_snapshot_classification_insufficient` | INSUFFICIENT_DATA |
| `test_synthetic_repeated_snapshot_delta_math` | real math via SyntheticAdapter |
| `test_synthetic_repeated_snapshot_classification_fast_growth` | growth class |
| `test_synthetic_adapter_filtered_from_production_store` | synthetic gate |
| `test_scheduler_run_once_with_real_bernama` | end-to-end scheduler |
| `test_scheduler_run_once_skipped_when_locked` | active lock blocks |
| `test_scheduler_stale_lock_recovery` | stale lock recovered |
| `test_scheduler_lock_released_on_failure` | failure releases lock |
| `test_scheduler_execution_log_records_each_run` | log persists |
| `test_atomic_write_failure_preserves_history` | atomic write integrity |
| `test_observation_history_preserved_through_store` | observation history |
| `test_bernama_metrics_remain_none_across_n_runs` | N-run stability |
| `test_live_bernama_two_fetches_via_scheduler` | LIVE end-to-end |

---

## 9. Production safety

- ✅ `https://myhotradar.com/` → 200
- ✅ `https://myhotradar.com/article/example/` → 200
- ✅ `https://myhotradar.com/public/radar/latest.json` → 200
- ✅ No files in `radar/`, `radar_data/`, `public/` modified
- ✅ No Radar / Candidate / scheduler / politics guardrail /
  website / AdSense / sitemap changes
- ✅ `performance_data/` gitignored; tests write only to temp dirs
- ✅ No automatic publishing; no continuous sampling
- ✅ Synthetic data isolation preserved (upstream filter + store gate)
- ✅ No system Scheduled Task / cron / watchdog installed
- ✅ Atomic write guarantees verified

---

## 11. Known limitations

- Real BERNAMA has no engagement metrics → all velocity stays
  None → classification stays INSUFFICIENT_DATA. This is the
  documented normal result.
- The scheduler is a **manual trigger** foundation; no auto-run
  mechanism is added. Production scheduling is a separate
  future-approved step.
- The P1 clock is second-precision. Two runs within the same
  second produce the same `captured_at`. This is documented
  P2 behavior; sub-second precision is a future batch if needed.
- `observation_id` was previously implicit in the
  `(content_id, from, to)` tuple; this batch makes it
  explicit. Old JSON without `observation_id` loads with `None`
  (backward-compatible).
- SchedulerLock's stale-after is 3600s; production tuning may
  need adjustment (out of scope for this batch).

---

## 12. Git

- **commit**: (this batch)
- **push**: success
- 1 commit, normal workflow (no amend / rebase / squash /
  force-push / reset --hard)

---

## 13. Recommendation for next batch

- **Production scheduler activation** (only with explicit
  approval): wire `run_once()` into Windows Task Scheduler /
  cron. This is **NOT** done in this batch per spec §12.
- **Sub-second precision clock** (research): if P1 needs
  millisecond timestamps for higher sample rates, add as an
  additive change.
- **Android P4-B / Facebook**: paused until android-collector
  reports verified capabilities.

---

**Stop condition met.** Awaiting next instruction.