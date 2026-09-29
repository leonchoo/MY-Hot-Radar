# Performance Intelligence — P3-B-2A: Real Dual-Snapshot Verification

**Status:** P3-B-2A (real Web dual-snapshot math verification) — PASS

**Goal:** Verify that the existing Performance math chain
(`compute_observation`) produces semantically correct
`PerformanceObservation` records when fed two real BERNAMA RSS
snapshots taken at distinct timestamps. This is a single-shot
end-to-end verification, NOT a scheduler.

This batch does NOT add a scheduler, cron, watchdog, or any
auto-sampling. It exercises the **same code path** that a future
scheduler would call, but only twice in a row.

---

## 1. What P3-B-2A does

* Two real BERNAMA RSS fetches, separated by a configurable
  interval (default ~3 seconds).
* Project each fetch to `PerformanceSnapshot`s.
* Run `compute_observation(snap1, snap2)` to produce a
  `PerformanceObservation`.
* Verify every mathematical and semantic invariant on real data.
* Document the contract under both live and offline conditions.

## 2. What P3-B-2A does NOT do

* ❌ No scheduler / cron / watchdog.
* ❌ No production `performance_data/` continuous writes.
* ❌ No long-running time-series.
* ❌ No second adapter.
* ❌ No engagement metric guessing.
* ❌ No `None → 0` coercion.
* ❌ No `category` / `topic_type` / `geographic_scope` inference.
* ❌ No StoryCluster integration.
* ❌ No Radar / Candidate / Website / Android changes.
* ❌ No Facebook / Instagram / YouTube / Android Collector.
* ❌ No political inference / ranking / prediction.
* ❌ No LLM. No Experience promotion.

---

## 3. Live dual-snapshot verification

Run with:

```
PERFORMANCE_BERNAMA_LIVE=1 python -m performance.tests.test_dual_snapshot
```

The live path makes two real HTTPS GETs against
`https://www.bernama.com/en/rssfeed.php` separated by ~3
seconds.

Verified live run (this batch):

```
Fetch #1: status=AVAILABLE, rows=10
  article[0]: content_id=ci_d21c35156d5600eff2295a6a
              url=http://www.bernama.com/en/news.php?id=2613520
              observed_at=2026-09-29T15:56:03Z
              published_at=2026-09-29T00:00:00Z
              metrics=None/None/None/None/None
              unavailable_reason=engagement_metrics_not_exposed_by_source
Waiting 3s...
Fetch #2: status=AVAILABLE, rows=10
  article[0] (2nd fetch): observed_at=2026-09-29T15:56:07Z
                        metrics=None/None/None/None/None

compute_observation result:
  content_id: ci_d21c35156d5600eff2295a6a
  from_captured_at: 2026-09-29T15:56:03Z
  to_captured_at:   2026-09-29T15:56:07Z
  elapsed_seconds: 4
  views_delta: None
  likes_delta: None
  comments_delta: None
  shares_delta: None
  views_per_hour: None
  likes_per_hour: None
  comments_per_hour: None
  shares_per_hour: None
  performance_class: INSUFFICIENT_DATA
```

All invariants verified:

| Invariant | Verified |
|---|---|
| `content_id` stable across two fetches | ✅ same `ci_d21c35156d5600eff2295a6a` |
| `url` stable | ✅ same article URL |
| `observed_at` distinct | ✅ `15:56:03Z` vs `15:56:07Z` |
| `elapsed_seconds > 0` | ✅ 4 (3s wait + 1s second-resolution rounding) |
| `compute_observation` succeeds | ✅ returns PerformanceObservation |
| `views_delta / likes_delta / comments_delta / shares_delta` = None | ✅ all None |
| `views_per_hour / likes_per_hour / comments_per_hour / shares_per_hour` = None | ✅ all None |
| `performance_class` for empty metrics = `INSUFFICIENT_DATA` | ✅ |
| `_synthetic` flag absent on real data | ✅ |
| `content_id` doesn't change on second observation | ✅ same |

---

## 4. Deterministic test path (default, offline)

The deterministic path uses **cached real BERNAMA RSS bytes**
(frozen from a 2026-09-29 fetch) and explicit fixed
second-precision timestamps. It exercises the same
`compute_observation` code path as the live run.

Why this matters:

* The CI environment may not have outbound HTTPS access to
  BERNAMA.
* The cache contains real BERNAMA-shaped data (not synthetic
  invented data); the only thing the deterministic path
  simulates is the network, not the data shape.
* The test suite must be deterministic. We use fixed
  second-precision timestamps rather than `time.sleep(0.05)`
  + `datetime.now()` (sub-second) because the P1 clock is
  second-resolution — that would produce non-deterministic
  same-second collisions.

A small real-data quality finding was surfaced by P3-B-2A:

> The P1 clock uses **second-resolution** ISO 8601 strings
> (`%Y-%m-%dT%H:%M:%SZ`). Two `BernamaRssAdapter.fetch()`
> calls within the same second produce identical
> `observed_at`. `compute_observation` returns
> `elapsed_seconds=0`, and `classify_performance` returns
> `INSUFFICIENT_DATA` because the window is too small.

This is documented behavior, not a bug. A future batch may
add sub-second precision at the adapter layer if needed;
P3-B-2A does not change the clock.

---

## 5. Math correctness on real BERNAMA data

The core invariant verified by both deterministic and live tests:

**When BERNAMA's metric fields are all `None`, every derived
quantity in the math chain stays `None`.**

```
AdapterObservation
  views=None, likes=None, comments=None, shares=None, reposts=None
        ↓
PerformanceSnapshot (projection)
  views=None, likes=None, comments=None, shares=None, reposts=None
        ↓
compute_observation(snap1, snap2)
        ↓
PerformanceObservation
  views_delta       = None     (because _safe_delta returns None on None)
  likes_delta       = None
  comments_delta    = None
  shares_delta      = None
  views_per_hour    = None     (because _per_hour returns None when delta is None)
  likes_per_hour    = None
  comments_per_hour = None
  shares_per_hour   = None
        ↓
classify_performance(obs)
  → INSUFFICIENT_DATA    (because views_per_hour is None)
```

This is the **correct** result. The system refuses to invent
metrics it doesn't have.

---

## 6. Test results

| Suite | Count |
|---|---|
| P1 (existing) | 49 / 49 PASS |
| P2 (existing) | 59 / 59 PASS |
| P3-A (existing) | 37 / 37 PASS |
| Android Bridge (existing) | 39 / 39 PASS |
| P3-B-1 (existing) | 21 / 21 PASS |
| **P3-B-2A (new)** | **24 / 24 PASS** |
| Radar (existing, no touch) | 396 / 396 (verified at commit time) |
| **Total Performance** | **229 / 229 PASS** |

P3-B-2A test breakdown:

| Test | Purpose |
|---|---|
| `test_deterministic_first_fetch_produces_bernama_rows` | First fetch sanity check (snapshot_1 baseline) |
| `test_deterministic_two_fetches_same_content_ids` | content_id stable across two fetches |
| `test_deterministic_two_fetches_distinct_observed_at_via_clock` | observed_at diverges when wall-clock seconds differ |
| `test_deterministic_observation_has_elapsed_seconds_positive` | elapsed_seconds > 0 when timestamps differ by ≥1s |
| `test_deterministic_same_second_snapshots_yield_zero_elapsed` | Documents the second-resolution contract: same-second → elapsed=0 |
| `test_deterministic_observation_preserves_none_for_all_metrics` | All 8 metric fields stay None |
| `test_deterministic_velocity_not_fabricated_when_delta_none` | *_per_hour stays None even when elapsed > 0 |
| `test_deterministic_engagement_total_is_none_when_all_unknown` | engagement_total() = None when no components known |
| `test_deterministic_engagement_rate_is_none_when_views_unknown` | engagement_rate() = None when views=None |
| `test_deterministic_classify_returns_insufficient_data` | classify_performance() = INSUFFICIENT_DATA |
| `test_deterministic_same_article_two_snapshots_compose` | Same article → observation succeeds |
| `test_deterministic_different_content_ids_rejected` | Different articles → observation = None |
| `test_deterministic_non_monotonic_timestamps_rejected` | t_new < t_old → observation = None |
| `test_deterministic_content_id_unchanged_after_second_observation` | content_id stable across recompute |
| `test_deterministic_second_snapshot_not_treated_as_new_content` | No new content_id |
| `test_deterministic_elapsed_seconds_matches_timestamps` | elapsed_seconds = exact second delta |
| `test_deterministic_store_round_trip_preserves_observation` | Write+read of PerformanceObservation preserves all fields |
| `test_deterministic_synthetic_observation_refused_at_store` | Caller-side gate prevents synthetic leak |
| `test_deterministic_synthetic_payload_dict_rejected_by_store` | Store's defence-in-depth gate fires |
| `test_deterministic_bernama_observations_carry_no_synthetic_flag` | Real BERNAMA data is never marked synthetic |
| `test_deterministic_persisted_observation_carry_no_synthetic_flag` | Persisted real observations never synthetic |
| `test_live_bernama_first_fetch` | LIVE: first HTTPS GET succeeds |
| `test_live_bernama_two_fetches_same_content_ids` | LIVE: real content_ids match across two fetches |
| `test_live_bernama_dual_snapshot_math` | LIVE: end-to-end dual-snapshot math |

---

## 7. Real vs Fixture

**Real live verification** (gated by `PERFORMANCE_BERNAMA_LIVE=1`):

* `test_live_bernama_first_fetch` — single real HTTPS GET against BERNAMA RSS
* `test_live_bernama_two_fetches_same_content_ids` — two real HTTPS GETs, content_id stability verified against the real RSS feed
* `test_live_bernama_dual_snapshot_math` — full real dual-snapshot pipeline: fetch → wait 3s → fetch → compute_observation → verify

**Deterministic tests** (default, run always):

* 21 tests using cached real BERNAMA RSS bytes + fixed second-precision timestamps
* Exercise the **same code path** as the live run
* The cached RSS bytes are from a real BERNAMA fetch (captured during P3-B-1 development); no invented / synthetic RSS data
* Deterministic means: same result on every run, regardless of network availability

**The deterministic path is NOT synthetic data** — it is real
BERNAMA-shaped RSS bytes with simulated capture timestamps. The
math exercised is identical to the live path.

---

## 8. Production safety

* ✅ `https://myhotradar.com/` → 200 (verified before this batch)
* ✅ `https://myhotradar.com/article/example/` → 200
* ✅ `https://myhotradar.com/public/radar/latest.json` → 200
* ✅ No files in `radar/`, `radar_data/`, `public/` modified
* ✅ No Radar / Candidate / scheduler / politics guardrail / website changes
* ✅ `performance_data/` gitignored; P3-B-2A writes only to temp dirs
* ✅ No automatic publishing of any kind
* ✅ Synthetic data isolation preserved
* ✅ No live network call without env var opt-in
* ✅ Two-fetches-only verification, no continuous sampling

---

## 9. Known Limitations (carried forward + new)

| Limitation | Status |
|---|---|
| BERNAMA RSS doesn't expose engagement metrics | unchanged — all 5 metrics stay `None` |
| No scheduler / cron / watchdog | unchanged — P3-B-2A is single-shot |
| No long-running time-series | unchanged |
| `category` / `topic_type` / `geographic_scope` not structured | unchanged |
| StoryCluster integration not exercised | unchanged |
| Normalization (e.g. `1.2K` → 1200) | unchanged — out of scope |
| Clock is second-resolution (`iso_utc`) | **documented;** same-second fetches → `elapsed_seconds=0` |
| Two live fetches in same second produce identical `observed_at` | **documented;** future batch may add sub-second precision |

The clock-resolution finding is the only **new** discovery from
this batch. It is not a defect — it is a contract clarification:
the second-resolution clock is intentional, and callers needing
sub-second precision must layer their own clock on top.

---

## 10. Real vs Fixture → table

| Concern | Real live path | Deterministic path |
|---|---|---|
| Network | Real HTTPS GET to BERNAMA | Patched `urllib.request.urlopen` |
| RSS bytes | Live from BERNAMA server | Cached bytes from a real BERNAMA fetch |
| `observed_at` | Wall-clock (second-resolution) | Hard-coded second-precision strings |
| Wall-clock wait | `time.sleep(3)` between two fetches | Not applicable |
| Adapter `fetch()` | Same code | Same code |
| `to_snapshots()` projection | Same code | Same code |
| `compute_observation` math | Same code | Same code |
| `classify_performance` | Same code | Same code |
| `PerformanceStore` write/read | Same code | Same code |
| `_synthetic` gate | Same code | Same code |
| Tests count | 3 | 21 |
| Default run | SKIP unless `PERFORMANCE_BERNAMA_LIVE=1` | ALWAYS RUN |

---

## 11. Git

- **commit**: (this batch)
- **push**: success
- 1 commit, normal workflow (no amend / rebase / squash / force-push / reset --hard)

---

## 12. Recommendation for next batch

- **P3-B-3: Title-prefix category extraction** — parse `World :`,
  `Business :`, `General :`, `Sports :` from BERNAMA titles into a
  structured `category` field. Independent of Radar.
- **P3-B-4: Repeated-snapshot scheduler** — only with explicit
  approval. Repeats the P3-B-2A fetch on a schedule and accumulates
  real BERNAMA snapshots over time, populating production
  `performance_data/`.
- **Android P4-B / Facebook** — paused until android-collector
  reports verified capabilities.

---

**Stop condition met.** Awaiting next instruction.
