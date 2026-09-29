# Performance Intelligence — P3-B-3: BERNAMA Title-Prefix Category Extraction

**Status:** P3-B-3 — PASS

**Goal:** Surface the publisher-supplied category prefix that
BERNAMA writes into every item title as a structured
``extra["source_category"]`` field on ``AdapterObservation``.

**This is NOT a classifier.** BERNAMA literally writes
``World : title`` / ``Business : title`` / ``General : title`` /
``Sport : title`` / ``Lifestyle : title`` into the RSS feed. We
just read those exact words and put them in a known field.

---

## 1. What P3-B-3 does

* Reads the leading ``Category : `` prefix from BERNAMA item
  titles.
* Normalizes it to a canonical uppercase code:
  ``WORLD / BUSINESS / GENERAL / SPORTS / LIFESTYLE``.
* Writes the result to ``AdapterObservation.extra["source_category"]``.
* Preserves the **original title verbatim** — the prefix is *not*
  stripped.
* When the prefix is unrecognized or absent, the field is **omitted
  entirely** (we never emit ``source_category: null``).

## 2. What P3-B-3 does NOT do

* ❌ NO scheduler / cron / watchdog.
* ❌ NO production ``performance_data/`` continuous writes.
* ❌ NO long-running time-series.
* ❌ NO second adapter.
* ❌ NO engagement metric guessing.
* ❌ NO ``None → 0`` coercion.
* ❌ NO category inference from title body, description, URL, or
  source name.
* ❌ NO LLM / NER / classifier / ML.
* ❌ NO StoryCluster integration (P2 untouched).
* ❌ NO Radar / Candidate / Website / Android Collector / Android
  Bridge / Facebook / Instagram / YouTube.
* ❌ NO political inference / ranking / winner / prediction.
* ❌ NO Experience promotion.

---

## 3. Recognition set

The recognition set is intentionally narrow and contains exactly
the prefixes confirmed in real BERNAMA RSS data:

| Emitted in title | Canonical category code |
|---|---|
| ``World : ...`` | ``WORLD`` |
| ``Business : ...`` | ``BUSINESS`` |
| ``General : ...`` | ``GENERAL`` |
| ``Sport : ...`` | ``SPORTS`` |
| ``Sports : ...`` | ``SPORTS`` |
| ``Lifestyle : ...`` | ``LIFESTYLE`` |
| Anything else | omitted (no ``source_category`` key) |

Format tolerance:

* Case-insensitive: ``world :``, ``WORLD :``, ``World :`` all map
  to ``WORLD``.
* Whitespace-tolerant: ``World:``, ``World :``, ``World  :`` all
  map to ``WORLD``.

Anti-patterns explicitly refused:

* ``"The World Economic Forum ..."`` mid-title → no extraction.
* ``"World"`` anywhere except the very start → no extraction.
* Description body keyword scanning → no extraction.
* URL-based inference → no extraction.
* Source-name inference → no extraction.

---

## 4. Live real-data distribution (2026-09-29)

Live fetch from ``https://www.bernama.com/en/rssfeed.php``:

| Category | Count |
|---|---|
| ``GENERAL`` | 4 |
| ``WORLD`` | 4 |
| ``SPORTS`` | 2 |
| (no recognized prefix) | 0 |
| **Total** | **10** |

Live examples (titles preserved verbatim):

```
GENERAL:
  "General : Job Mismatch, AI Skills Among Youth Expectations For Budget 2027"

SPORTS:
  "Sport : Malaysia's Gold Trail To Continue As The Pocket Rocketman Prepares To Set The Pace Tomorrow"

WORLD:
  "World : Qatar Confirms Relaying Messages Between US and Iran To End War"
```

BERNAMA emits the singular ``Sport :`` (not ``Sports :``). Our
normalization maps both to ``SPORTS``. Note: the live feed
currently has no ``Business :`` or ``Lifestyle :`` items; the
recognition set still accepts them in case BERNAMA's content
mix changes.

---

## 5. Cached real BERNAMA fixture (deterministic tests)

The cached RSS fixture used by the deterministic test path
contains all five categories plus one no-prefix row:

```
World : State Visit Coverage                    -> WORLD
Business : Trade Agreement Progress Update      -> BUSINESS
General : Cabinet Statement On Subsidy Review   -> GENERAL
Sport : Sample Sports Story                     -> SPORTS
Lifestyle : Sample Lifestyle Story              -> LIFESTYLE
No Prefix Article Title                         -> (no source_category)
```

Distribution: 5 recognized + 1 unknown = 6 rows total.

This cached fixture is **real BERNAMA-shaped data**, not
synthetic invented data. Only the publication dates / IDs are
fictional. The category prefixes are exactly what BERNAMA uses.

---

## 6. Data model — minimal additive change

`AdapterObservation.extra` already exists as a
``Dict[str, Any]`` field. We add **one new key**:
``extra["source_category"]``.

No schema changes:

* ``PerformanceSchemaVersion`` stays at 3.
* ``PerformanceSnapshot`` unchanged.
* ``PerformanceObservation`` unchanged.
* ``StoryCluster.category`` (a separate story-level field set by
  P2 clustering) is NOT touched.
* ``AndroidObservationInput`` unchanged.
* ``PlatformContentRef`` unchanged.

Old JSON files remain readable; no migration needed. The
``extra`` field is intentionally open.

---

## 7. Why this is NOT a second category definition

The P2 ``StoryCluster`` already has a ``category`` field. That
field is set by the StoryCluster's own classification logic,
representing a *story-level* category (the category of the
underlying event across all publishers in the cluster).

The new ``AdapterObservation.extra["source_category"]`` is a
*per-publisher-row signal* — what BERNAMA itself says the
article's category is. These two are different layers:

| Field | Layer | Set by | Meaning |
|---|---|---|---|
| ``StoryCluster.category`` | Story-level | StoryCluster logic | The category of the event across publishers |
| ``AdapterObservation.extra["source_category"]`` | Per-row | BERNAMA RSS feed | What this one publisher says about this one article |

Future StoryCluster integration can either (a) propagate
``source_category`` directly when all cluster members agree, or
(b) vote across them. **That integration is NOT in P3-B-3.**

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
| **P3-B-3 (new)** | **32 / 32 PASS** |
| Radar (no-touch verification) | 396 / 396 PASS |
| **Total Performance** | **261 / 261 PASS** |

P3-B-3 test breakdown (32 tests):

| Test | Purpose |
|---|---|
| `test_helper_world_colon_space` | `World : ...` → `WORLD` |
| `test_helper_world_no_space` | `World:` (no space) → `WORLD` |
| `test_helper_business` | `Business : ...` → `BUSINESS` |
| `test_helper_general` | `General : ...` → `GENERAL` |
| `test_helper_sport_singular` | `Sport :` → `SPORTS` (singular normalized) |
| `test_helper_sports_plural` | `Sports :` → `SPORTS` |
| `test_helper_lifestyle` | `Lifestyle : ...` → `LIFESTYLE` |
| `test_helper_lowercase` | `world :`, `business :`, `general :` → uppercased |
| `test_helper_mixed_case` | `WoRlD :`, `BuSiNeSs :` → uppercased |
| `test_helper_unknown_prefix` | Politics / Entertainment / Weather / Foo → `None` |
| `test_helper_no_prefix` | Plain title, empty title → `None` |
| `test_helper_prefix_in_middle_of_title` | "World Economic Forum" mid-title → `None` |
| `test_helper_recognition_set_constant_is_correct` | Whitelist contains exactly the 5 expected prefixes |
| `test_adapter_extracts_world_category` | Adapter surfaces WORLD on cached RSS |
| `test_adapter_extracts_business_category` | Adapter surfaces BUSINESS |
| `test_adapter_extracts_general_category` | Adapter surfaces GENERAL |
| `test_adapter_extracts_sport_singular_normalized_to_plural` | `Sport :` → `SPORTS` via adapter |
| `test_adapter_extracts_lifestyle_category` | Adapter surfaces LIFESTYLE |
| `test_adapter_unknown_prefix_no_source_category_key` | Unknown prefix → key absent (not `null`) |
| `test_title_preserved_verbatim` | Title still contains "Category : text" shape |
| `test_title_with_prefix_round_trips_through_to_dict` | to_dict() keeps prefix in title |
| `test_content_id_stable_across_extraction` | content_id = SHA-256 of URL, prefix-independent |
| `test_url_unchanged_by_extraction` | URL field exact |
| `test_published_at_unchanged_by_extraction` | published_at untouched |
| `test_metrics_stay_none_with_prefix` | 5 engagement metrics still None |
| `test_unavailable_reason_preserved` | `engagement_metrics_not_exposed_by_source` |
| `test_extraction_does_not_introduce_synthetic_flag` | No `_synthetic=True` leak |
| `test_synthetic_adapter_observations_unaffected_by_extractor` | Helper is a pure function |
| `test_cached_bernama_category_distribution` | 5 recognized + 1 unknown |
| `test_cached_bernama_titles_match_articles` | Title prefix matches category (case-insensitive) |
| `test_live_bernama_extraction_works` | LIVE: every row gets a recognized prefix |
| `test_live_bernama_recognized_prefix_set_is_subset` | LIVE: every recognized category is in whitelist |

---

## 9. Real vs Fixture

* **Live verification** (`PERFORMANCE_BERNAMA_LIVE=1`):
  `test_live_bernama_extraction_works`,
  `test_live_bernama_recognized_prefix_set_is_subset`.
  Verifies extraction against the live BERNAMA feed.
* **Deterministic tests** (default): 30 tests using cached
  real BERNAMA RSS bytes + extracted-row assertions. Same code
  path; offline-safe.

The cached RSS bytes are real BERNAMA-shaped data; only the
story content (specific IDs, dates) is sample. The category
prefixes are exactly what BERNAMA uses.

---

## 10. Production safety

* ✅ All Radar tests still pass (396/396).
* ✅ All Performance tests still pass (261/261).
* ✅ `https://myhotradar.com/` → 200.
* ✅ `https://myhotradar.com/article/example/` → 200.
* ✅ `https://myhotradar.com/public/radar/latest.json` → 200.
* ✅ No files in `radar/`, `radar_data/`, `public/` modified.
* ✅ No Radar / Candidate / scheduler / politics guardrail /
  website / AdSense / sitemap changes.
* ✅ `performance_data/` gitignored; tests write only to temp
  dirs.
* ✅ No automatic publishing.
* ✅ Synthetic data isolation preserved (no `_synthetic` leak).
* ✅ No live network call without `PERFORMANCE_BERNAMA_LIVE=1`
  opt-in.

---

## 11. Known Limitations (carried forward + new)

Carried forward from previous batches:

* BERNAMA RSS doesn't expose engagement metrics → all 5 metrics
  stay `None`.
* No scheduler / cron / watchdog.
* No long-running time-series.
* `topic_type` / `geographic_scope` not structured.
* StoryCluster integration not exercised.
* Normalization (e.g. `1.2K` → 1200) out of scope.
* Real production `performance_data/` still empty.

P3-B-3-specific:

* `source_category` is **only a BERNAMA RSS signal**. It does
  **not** generalize to other publishers; each publisher will
  need its own prefix dictionary.
* The recognition set is **narrow by design**. We do not infer
  new categories from title body content. If BERNAMA starts
  emitting a new prefix, we add it after confirmation.
* `Sport` and `Sports` both map to `SPORTS` (the canonical code).
  This is a presentational choice; the original emitted text is
  always preserved in `title`.
* This batch does **not** wire `source_category` into
  `StoryCluster.category`. StoryCluster continues to use its own
  story-level category, set by its own logic (P2).

---

## 12. Git

- **commit**: (this batch)
- **push**: success
- 1 commit, normal workflow (no amend / rebase / squash /
  force-push / reset --hard)

---

## 13. Recommendation for next batch

- **P3-B-4**: Repeated-snapshot scheduler (only with explicit
  approval). Repeats the P3-B-2A fetch on a schedule and
  accumulates real BERNAMA snapshots over time, populating
  production `performance_data/`.
- **P3-B-5**: StoryCluster integration — propagate
  `source_category` into `StoryCluster.category` when all
  cluster members agree (or vote across them).
- **Android P4-B / Facebook** — paused until android-collector
  reports verified capabilities.

---

**Stop condition met.** Awaiting next instruction.