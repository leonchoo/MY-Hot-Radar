# Performance Intelligence — P3-B-5: StoryCluster category propagation

**Status:** P3-B-5 — PASS

**Goal:** Conserve and propagate the publisher-provided category
(surfaced in P3-B-3 as `AdapterObservation.extra["source_category"]`)
into the cluster-level `StoryCluster.category`, strictly per
documented rules, without any classification / voting / ranking.

---

## 1. What P3-B-5 does

* Adds an optional `source_category: Optional[str] = None` field to
  `StoryMember`, preserving the per-row category inside a cluster.
* Adds a new pure function `derive_story_cluster_category(members)`
  that returns a `StoryCategoryPropagation` result.
* Adds `StoryCategoryPropagation` as a small audit dataclass
  (`category`, `conflict`, `has_any`, `member_count`,
  `known_count`).
* Updates `StoryCluster.from_dict` to read the new optional field
  (backward-compatible with old JSON).
* Updates `validate_story_cluster` to validate `source_category`
  as a short string when present (max 64 chars).

## 2. What P3-B-5 does NOT do

* ❌ NO classification / inference / voting / ranking.
* ❌ NO keyword / URL / publisher / country / location inference.
* ❌ NO LLM / NER / classifier / ML.
* ❌ NO StoryCluster matching algorithm change.
* ❌ NO StoryMatch score change.
* ❌ NO scheduler / cron / watchdog.
* ❌ NO production `performance_data/` continuous writes.
* ❌ NO Radar / Candidate / Website / Android Collector / Android
  Bridge / Facebook / Instagram / YouTube changes.
* ❌ NO political inference / ranking / winner / prediction.
* ❌ NO Experience promotion.

---

## 3. Propagation rules (per spec)

| Case | Members | Result |
|---|---|---|
| A | All members carry the same category | propagate that category |
| B | Partial coverage (some None, others agree) | `None`, `conflict=False`, `has_any=True` |
| C | Two or more members carry different categories | `None`, `conflict=True`, `has_any=True` |
| D | No member carries a category | `None`, `conflict=False`, `has_any=False` |
| E | Single member, has category | propagate (Case A on N=1) |
| E | Single member, no category | `None` |

The function never guesses. It does not vote. It does not pick
"majority". It does not invent a category from titles, URLs, or
publisher names. It is a pure read over `member.source_category`.

---

## 4. Layer separation

Three layers, three distinct fields:

| Layer | Field | Type | Set by |
|---|---|---|---|
| Source-provided (per row) | `AdapterObservation.extra["source_category"]` | `str` or absent | BernamaRssAdapter (P3-B-3) |
| Per-member cluster member | `StoryMember.source_category` | `Optional[str]` | caller (default None) |
| Cluster-level (story) | `StoryCluster.category` | `str` | caller (after `derive_story_cluster_category`) |
| Audit trail | `StoryCategoryPropagation` | dataclass | `derive_story_cluster_category` |

**These are NOT the same field.** They are documented separately
and never collapsed.

### Cluster-level `category` sentinel

`StoryCluster.category` is a required `str` (validated by
`validate_str` which rejects empty strings). When
`derive_story_cluster_category` returns `None` (Case B/C/D), the
caller writes the sentinel string `"UNRESOLVED"` into the cluster
field. The per-member `source_category` is the authoritative
audit trail; the sentinel only satisfies validation.

---

## 5. Real BERNAMA verification (live, 2026-09-29)

```
total member rows:    10
with category:        10  (100%)
without category:     0
source_category distribution:
  WORLD:     4
  GENERAL:   4
  SPORTS:    2

Per-category sub-cluster propagation:
  WORLD  (4 rows):   category='WORLD',  conflict=False  [Case A]
  GENERAL (4 rows):  category='GENERAL', conflict=False  [Case A]
  SPORTS  (2 rows):  category='SPORTS', conflict=False  [Case A]
  Mixed (all 10):    category=None,      conflict=True   [Case C]
```

**Interpretation:**

* When **real clusters** contain articles that all carry the same
  source_category (which is exactly what same-story matching
  would produce in practice: publishers covering the same event
  also tend to agree on the category), propagation is successful.
* When BERNAMA's feed is treated as one huge "cluster"
  (artificial), different categories conflict and propagation
  yields `None` with `conflict=True`. This is correct: the
  function does not know what "should be a cluster" — that's the
  job of StoryCluster matching logic (P2), which is unchanged.

**Limitation acknowledged:**

StoryCluster formation (deciding which articles belong to the
same cluster) is a P2 problem that this batch does NOT solve.
This batch only plumbs the category signal into members and
provides the propagation function. Whether real BERNAMA articles
actually form same-story clusters is a separate research question.

---

## 6. Test results

| Suite | Count |
|---|---|
| P1 (existing) | 49 / 49 PASS |
| P2 (existing, unchanged) | 59 / 59 PASS |
| P3-A (existing) | 37 / 37 PASS |
| Android Bridge (existing) | 39 / 39 PASS |
| P3-B-1 (existing) | 21 / 21 PASS |
| P3-B-2A (existing) | 24 / 24 PASS |
| P3-B-3 (existing) | 32 / 32 PASS |
| **P3-B-5 (new)** | **27 / 27 PASS** |
| Radar (no-touch verification) | 396 / 396 PASS |
| **Total Performance** | **288 / 288 PASS** |
| **Grand Total** | **684 / 684 PASS** |

P3-B-5 test breakdown (27 tests):

| Test | Purpose |
|---|---|
| `test_case_a_all_members_same_category_propagates` | Case A (3 members) |
| `test_case_a_two_members_agree` | Case A (2 members) |
| `test_case_b_partial_coverage_no_category` | Case B |
| `test_case_b_most_members_have_one_doesnt` | Case B (9/10) — no voting |
| `test_case_c_two_distinct_categories_conflict` | Case C (WORLD vs SPORTS) |
| `test_case_c_three_distinct_categories_conflict` | Case C (3 distinct) |
| `test_case_c_conflict_with_partial_coverage_still_flags_conflict` | Case C + partial |
| `test_case_d_no_member_has_category` | Case D |
| `test_case_d_empty_member_list` | Empty members |
| `test_case_e_single_member_with_category_propagates` | Case E propagate |
| `test_case_e_single_member_without_category` | Case E None |
| `test_propagation_result_object_is_dataclass` | Audit dataclass shape |
| `test_propagation_does_not_mutate_members` | Pure read |
| `test_propagation_does_not_alter_content_id` | Identity preserved |
| `test_propagation_does_not_alter_publisher_or_platform` | Identity preserved |
| `test_propagation_does_not_alter_url_or_published_at` | Identity preserved |
| `test_propagation_does_not_alter_source_category_field` | Member field not written |
| `test_story_cluster_accepts_derived_category` | Cluster integration |
| `test_story_cluster_with_conflict_keeps_member_level_signal` | Conflict + audit trail |
| `test_story_cluster_serialization_round_trip_preserves_source_category` | to_dict/from_dict |
| `test_story_cluster_from_dict_handles_old_json_without_source_category` | Backward compat |
| `test_propagation_does_not_alter_story_match` | StoryMatch independence |
| `test_real_bernama_members_to_story_cluster` | Real RSS → Cluster |
| `test_real_bernama_cross_category_conflict` | Real RSS → conflict |
| `test_real_bernama_distribution_of_source_categories` | Real RSS → stats |
| `test_live_bernama_source_categories_can_form_propagated_cluster` | LIVE end-to-end |
| `test_report_real_bernama_propagation_stats` | Real-data report |

---

## 7. Compatibility

* ✅ `StoryCluster` is **additive only**. The new field on
  `StoryMember` defaults to `None`. Old code that doesn't pass
  `source_category` keeps working.
* ✅ `StoryCluster.from_dict` reads `m.get("source_category")`,
  so old JSON without the field loads with `None`.
* ✅ `validate_story_cluster` accepts the new field; old clusters
  still validate.
* ✅ `to_dict()` serializes the new field; round-trip preserved.
* ✅ `match_stories` is untouched. It still takes
  `left_category`/`right_category` as inputs (cluster-level, not
  source-level). Propagation does not influence match scores.
* ✅ `ContentIdentity`, `PerformanceSnapshot`,
  `PerformanceObservation`, `PerformanceStore` unchanged.
* ✅ P3-B-1 (real adapter persistence) unchanged.
* ✅ P3-B-2A (real dual-snapshot) unchanged.
* ✅ P3-B-3 (category extraction) unchanged.
* ✅ Android Bridge unchanged.

---

## 8. Production safety

* ✅ Radar tests: 396/396 PASS (no touch).
* ✅ Performance tests: 288/288 PASS.
* ✅ `https://myhotradar.com/` → 200.
* ✅ `https://myhotradar.com/article/example/` → 200.
* ✅ `https://myhotradar.com/public/radar/latest.json` → 200.
* ✅ No files in `radar/`, `radar_data/`, `public/` modified.
* ✅ No Radar / Candidate / scheduler / politics guardrail /
  website / AdSense / sitemap changes.
* ✅ `performance_data/` gitignored; tests write only to temp
  dirs.
* ✅ No automatic publishing; no continuous sampling.
* ✅ Synthetic data isolation preserved (no `_synthetic` leak).

---

## 9. Known Limitations (carried forward + new)

Carried forward:

* BERNAMA RSS doesn't expose engagement metrics → all 5 metrics
  stay `None`.
* No scheduler / cron / watchdog.
* No long-running time-series.
* `topic_type` / `geographic_scope` not structured.
* StoryCluster **formation** (deciding which articles are the
  same story) is P2 logic and **not changed** by this batch.
* Normalization (e.g. `1.2K` → 1200) out of scope.
* Real production `performance_data/` still empty.

P3-B-5-specific:

* **This batch only plumbs the signal.** Whether real BERNAMA
  articles actually form same-story clusters is a P2 question
  (story matching) that this batch does NOT solve.
* **`UNRESOLVED` is a sentinel.** When propagation returns
  `None`, the cluster's `category` field holds `"UNRESOLVED"`.
  This satisfies the existing `validate_str` constraint that
  rejects empty strings. Per-member `source_category` is the
  authoritative audit trail.
* **`source_category` is BERNAMA-specific today.** Other
  publishers will need their own prefix detection; this batch
  does not generalize to other publishers.
* **No conflict resolution.** Case C returns `None` + the
  conflict flag; we never pick a winner.

---

## 10. Git

- **commit**: (this batch)
- **push**: success
- 1 commit, normal workflow (no amend / rebase / squash /
  force-push / reset --hard)

---

## 11. Recommendation for next batch

- **P3-B-4 Scheduler**: blocked until explicit approval.
- **P3-B-6**: StoryCluster formation integration — given a set of
  real BERNAMA articles, build StoryCluster members with
  source_category propagated and verify cross-publisher
  same-story cases produce consistent categories.
- **Android P4-B / Facebook**: paused until android-collector
  reports verified capabilities.

---

**Stop condition met.** Awaiting next instruction.