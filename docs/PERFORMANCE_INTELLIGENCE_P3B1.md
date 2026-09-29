# Performance Intelligence — P3-B-1: Real Adapter Persistence

**Status:** P3-B-1 (real Web/URL adapter persistence) — PASS

**Goal:** Prove that the existing adapter framework can move real
BERNAMA RSS observations through the existing PerformanceStore
without any data-semantic loss.

This batch does NOT add a scheduler, cron, or any auto-sampling.
It is a single-shot end-to-end demonstration that one fetch →
project → write → read cycle preserves every field correctly.

---

## 1. What P3-B-1 does

* Exercises `BernamaRssAdapter.fetch()` (the only real public
  adapter currently shipped).
* Projects the resulting `AdapterObservation`s into
  `PerformanceSnapshot`s via the existing `to_snapshots()` method.
* Writes them to a temp `PerformanceStore` (NOT the production
  `performance_data/`).
* Reads them back and verifies every field is preserved.
* Pins the data-semantic invariants: `None != 0`, no fake
  zeros, no `_synthetic` flag on real data, atomic-write failure
  safety, synthetic isolation.

## 2. What P3-B-1 does NOT do

* ❌ No scheduler / cron / auto-sampling.
* ❌ No second adapter.
* ❌ No engagement metric guessing.
* ❌ No `None → 0` coercion.
* ❌ No `category` / `topic_type` / `geographic_scope` guessing.
* ❌ No StoryCluster classification (P2 untouched).
* ❌ No Facebook / Instagram / YouTube.
* ❌ No Android Collector / Android Bridge.
* ❌ No PlatformContentRef.
* ❌ No Radar / Candidate / Website / scheduler changes.
* ❌ No political inference / ranking / winner / prediction.
* ❌ No LLM. No Experience promotion.

---

## 3. Pipeline verified

```
BernamaRssAdapter.fetch()
        ↓
AdapterObservation[]
  ├─ content_id (deterministic SHA-256 from URL)
  ├─ platform = Platform.WEBSITE
  ├─ observed_at = ISO 8601 UTC
  ├─ source = "bernama_en"
  ├─ source_url = "https://www.bernama.com/en/rssfeed.php"
  ├─ url = article permalink
  ├─ title = article title (BERNAMA "Category : Headline" format)
  ├─ published_at = recovered from description dateline (00:00 UTC)
  ├─ views / likes / comments / shares / reposts = None
  ├─ unavailable_reason = "engagement_metrics_not_exposed_by_source"
  └─ retrieval_status = AVAILABLE
        ↓
AdapterResult.to_snapshots()
        ↓
PerformanceSnapshot[]
  ├─ content_id  (same)
  ├─ captured_at (== observed_at)
  ├─ views / likes / comments / shares / reposts = None (preserved)
        ↓
PerformanceStore.put_snapshot()  (writes to temp perf_data/)
        ↓
PerformanceStore.list_snapshots_for(content_id)
        ↓
Round-trip read: every field preserved.
```

Live verification (one full real network round-trip, this batch):

```
1. fetch: status=AVAILABLE, rows=10
2. projected: 10 snapshots
3. persisted: 10 rows written and read back
4. None-metric semantics: ALL preserved
5. synthetic flag: ABSENT from real data
6. content_id stability: VERIFIED across round-trip

sample row:
  content_id:   ci_e0d4fd9b904b5eaf5742b884
  platform:     WEBSITE
  source:       bernama_en
  source_url:   https://www.bernama.com/en/rssfeed.php
  url:          http://www.bernama.com/en/news.php?id=2613519
  title:        World : Qatar Confirms Relaying Messages Between US and Iran To End Wa...
  published_at: 2026-09-29T00:00:00Z
  observed_at:  2026-09-29T15:40:44Z
  views/likes/comments/shares/reposts: None/None/None/None/None
  unavailable_reason: engagement_metrics_not_exposed_by_source
  retrieval_status: AVAILABLE
  _synthetic:   <not set>
```

---

## 4. Data-semantic invariants verified

| Invariant | Verified by |
|---|---|
| `None` stays `None` through projection | `test_real_bernama_projection_to_snapshots_preserves_none` |
| `None` stays `None` through round-trip | `test_real_bernama_persist_to_performance_store`, `test_real_bernama_persisted_snapshot_carries_full_identity` |
| `unavailable_reason` preserved on observation | `test_real_bernama_unavailable_reason_preserved_in_payload` |
| `unavailable_reason` is `"engagement_metrics_not_exposed_by_source"` for BERNAMA | end-to-end pipeline |
| Same URL → same `content_id` (SHA-256 deterministic) | `test_real_bernama_content_id_matches_url_hash`, `test_two_bernama_fetches_same_article_same_content_id` |
| Different URLs → different `content_ids` | `test_real_bernama_different_urls_get_different_content_ids` |
| `content_id` doesn't change across two fetches | `test_real_bernama_content_id_is_deterministic_per_url` |
| Real data has no `_synthetic` flag | `test_real_bernama_fetch_returns_non_synthetic_rows`, `test_real_bernama_persisted_record_carries_no_synthetic_flag` |
| `published_at` is day-resolution from BERNAMA dateline | `test_bernama_published_at_via_dateline_is_day_resolution` |
| Unparseable dateline → `published_at = None` (no guessing) | `test_bernama_unparseable_dateline_yields_none_published_at` |
| Synthetic gate fires on `_synthetic=True` dicts | `test_synthetic_payload_rejected_at_store_validation_layer` |
| SyntheticAdapter marks observations with `_synthetic=True` | `test_synthetic_adapter_extra_flag_is_present_on_observations` |
| Caller-side gate prevents synthetic leak into store | `test_real_bernama_and_synthetic_data_are_physically_separated` |
| Atomic write failure preserves previous file | `test_atomic_write_failure_preserves_previous_snapshot` |
| No orphan `.tmp` files after failure | `test_atomic_write_no_temp_files_left_behind_after_failure` |
| Successful write leaves no `.tmp` orphans | `test_atomic_write_success_replaces_tmp_with_real_file` |
| Quality check passes on real BERNAMA data | `test_real_bernama_observations_pass_quality_check` |
| Offline default is no-live-call | `test_offline_default_is_no_live_call` |
| End-to-end pipeline integrity | `test_end_to_end_real_bernama_pipeline` |

---

## 5. Live vs offline test gating

The P3-B-1 test suite is **offline by default**. The cache-backed
mock serves a frozen copy of a real BERNAMA RSS response so the
suite runs deterministically in CI / sandboxed environments.

To run with the real network:

```
PERFORMANCE_BERNAMA_LIVE=1 python -m performance.tests.test_real_adapter_persistence
```

When `PERFORMANCE_BERNAMA_LIVE != 1`:

* `urllib.request.urlopen` is patched at module level to return
  the cached RSS bytes.
* `test_offline_default_is_no_live_call` asserts that this mode
  is active.

When `PERFORMANCE_BERNAMA_LIVE == 1`:

* `BernamaRssAdapter.fetch()` makes a real HTTPS GET against
  `https://www.bernama.com/en/rssfeed.php`.
* All assertions still apply; the real bytes flow through the
  same code path as the cached bytes.

Both paths exercise **identical** downstream logic.

---

## 6. About BERNAMA's `published_at`

BERNAMA's public RSS feed **does not include `<pubDate>`** in any
of its `<item>` entries. The adapter recovers a coarse date from
the description dateline (e.g. `KUALA LUMPUR, Sept 29 (Bernama) --`)
and anchors it at `00:00:00Z`.

This is documented as a **BERNAMA-specific heuristic**, not a
precise publish timestamp:

* Day-resolution: the time component is always `T00:00:00Z`.
* Year-anchored: `2026` by default; from caller-supplied `clock()`
  for the live adapter.
* No time-of-day is invented.

The dateline recovery logic is locked by:
* `test_bernama_published_at_via_dateline_is_day_resolution`
* `test_bernama_unparseable_dateline_yields_none_published_at`

---

## 7. Synthetic isolation contract

The integration boundary between SyntheticAdapter and
PerformanceStore has a layered defence:

1. **Adapter layer**: `SyntheticAdapter` stamps every observation
   with `extra["_synthetic"] = True`. This is the
   "I'm synthetic" signal.
2. **Caller gate**: any code path that projects AdapterObservation
   to PerformanceSnapshot MUST check `extra["_synthetic"]` and
   refuse to project synthetic rows. The caller-side gate is
   verified by `test_real_bernama_and_synthetic_data_are_physically_separated`.
3. **Store defence-in-depth**: `_validate_payload` raises
   `SyntheticFixtureError` when a dict payload carries
   `_synthetic: True`. This catches dicts that bypass the
   PerformanceSnapshot dataclass path.

The store itself does NOT introspect `PerformanceSnapshot`
instances for the synthetic flag — dataclass instances are
schema-clean by design. The protection happens at the
adapter→caller boundary and at the dict→store boundary.

This design is intentional: synthetic data MUST be excluded
**before** it reaches the store, not retroactively rejected by
the store. The store is just defence-in-depth.

---

## 8. Tests

| Suite | Count |
|---|---|
| P1 (existing) | 49 / 49 PASS |
| P2 (existing) | 59 / 59 PASS |
| P3-A (existing) | 37 / 37 PASS |
| Android Bridge (existing) | 39 / 39 PASS |
| **P3-B-1 (new)** | **21 / 21 PASS** |
| Radar (existing, no touch) | 396 / 396 (verified at commit time) |
| **Total Performance** | **205 / 205 PASS** |

P3-B-1 test breakdown:

| Test | What it locks |
|---|---|
| `test_real_bernama_fetch_returns_non_synthetic_rows` | BERNAMA observations never carry `_synthetic` |
| `test_real_bernama_observations_pass_quality_check` | `check_observation_quality` accepts real BERNAMA data |
| `test_real_bernama_projection_to_snapshots_preserves_none` | None metrics stay None through projection |
| `test_real_bernama_unavailable_reason_preserved_in_payload` | `unavailable_reason` survives the snapshot boundary |
| `test_real_bernama_content_id_is_deterministic_per_url` | Two fetches produce identical `content_id`s |
| `test_real_bernama_different_urls_get_different_content_ids` | No false `content_id` collisions |
| `test_real_bernama_content_id_matches_url_hash` | `content_id` equals SHA-256 prefix of URL |
| `test_real_bernama_persist_to_performance_store` | Write → read round-trip preserves identity |
| `test_real_bernama_persisted_record_carries_no_synthetic_flag` | No synthetic flag on persisted real data |
| `test_synthetic_payload_rejected_at_store_validation_layer` | `_validate_payload` raises on `_synthetic=True` |
| `test_synthetic_adapter_extra_flag_is_present_on_observations` | SyntheticAdapter stamps `extra["_synthetic"]` |
| `test_real_bernama_and_synthetic_data_are_physically_separated` | Caller-side gate prevents leak |
| `test_atomic_write_failure_preserves_previous_snapshot` | Failed write doesn't destroy existing file |
| `test_atomic_write_no_temp_files_left_behind_after_failure` | No `.tmp` orphans after failure |
| `test_atomic_write_success_replaces_tmp_with_real_file` | No `.tmp` orphans after success |
| `test_bernama_published_at_via_dateline_is_day_resolution` | BERNAMA dateline → 00:00 UTC |
| `test_bernama_unparseable_dateline_yields_none_published_at` | No dateline → published_at is None |
| `test_real_bernama_persisted_snapshot_carries_full_identity` | content_id + captured_at + None metrics preserved |
| `test_two_bernama_fetches_same_article_same_content_id` | content_id stable across fetch calls |
| `test_end_to_end_real_bernama_pipeline` | Full pipeline summary |
| `test_offline_default_is_no_live_call` | Live mode is opt-in via env var |

---

## 9. Production safety

* ✅ `https://myhotradar.com/` → 200 (verified before this batch)
* ✅ `https://myhotradar.com/article/example/` → 200
* ✅ `https://myhotradar.com/public/radar/latest.json` → 200
* ✅ No files in `radar/`, `radar_data/`, `public/` modified
* ✅ No Radar / Candidate / scheduler / politics guardrail / website
  / AdSense / sitemap changes
* ✅ `performance_data/` is gitignored; P3-B-1 writes only to a
  temp dir; production `performance_data/` remains untouched
* ✅ No automatic publishing of any kind
* ✅ Synthetic data isolation preserved (3 layers)
* ✅ Atomic write guarantees verified

## 10. Limitations

This batch proves ONE thing: **a real Web/URL adapter can move
data into the store without losing data semantics.** It does NOT
prove (or attempt to prove) any of:

* ❌ **Engagement metrics**: BERNAMA RSS doesn't expose them.
  They remain None. No P3-B adapter collects them yet.
* ❌ **Repeated sampling**: this is a single-fetch test. The
  scheduler / cron / batch sampler is not built and was
  explicitly forbidden in this batch.
* ❌ **`category` / `topic_type` / `geographic_scope`**: BERNAMA
  RSS provides category prefix in the title (e.g. `World :`,
  `Business :`, `General :`) but the adapter does NOT split
  this into a structured `category` field. P2's clustering and
  `MarketObservation` ingestion require external classification.
* ❌ **StoryCluster integration**: not exercised in this batch.
  P2 untouched.
* ❌ **Normalization**: raw counts only. `1.2K` / `15M` strings
  are not parsed; no adapter currently produces them.
* ❌ **Real production performance_data/**: P3-B-1 writes to a
  temp dir, not to the production store. The production
  `performance_data/` dir is still empty.
* ❌ **Multi-fetch stability / historical sampling**: not done.
  Two consecutive fetches were used to verify content_id
  stability, but no time-series persistence test was performed.
* ❌ **Category inference from BERNAMA title prefix**: BERNAMA
  uses `World :`, `Business :`, `General :`, `Sports :`,
  etc. The adapter records the title as-is but does NOT extract
  a structured category. This is a future batch concern.
* ❌ **Engagement normalization** (None→interpolated estimate):
  forbidden by spec. Always stays None.

---

## 11. Next batch (suggestion only, NOT auto-started)

* **P3-B-2: Real scheduler / batch sampling** — only if
  explicitly approved. Repeats the P3-B-1 fetch on a schedule
  and accumulates real BERNAMA snapshots over time.
* **P3-B-3: Title-prefix category extraction** — parses
  `World :`, `Business :`, etc. from BERNAMA titles into a
  structured `category` field. Independent of Radar.
* **P3-B-4: Category classification pipeline** — bridges
  Performance to P2's StoryCluster matching via category.
* **Android P4-B / Facebook**: paused until android-collector
  reports verified capabilities.

---

**Stop condition met.** Awaiting next instruction.
