# Performance Intelligence — P3-B-6: Real BERNAMA StoryCluster Formation Integration

**Status:** P3-B-6 — PASS

**Goal:** Observe how the existing P2 StoryCluster formation /
matching / category propagation pipeline behaves when fed real
BERNAMA RSS data. This is an integration / observation batch —
NOT a matching-algorithm tuning batch.

---

## 1. What P3-B-6 does

* Defines a thin helper `form_story_clusters(members)` in the
  test file that uses the EXISTING P2 `match_stories()` to
  compute pairwise matches, then groups by connected component
  to form `StoryCluster`s.
* Records the actual behavior of the existing P2 matcher on real
  BERNAMA data (live + cached).
* Reports cluster size distribution, category propagation stats,
  identity preservation, and synthetic isolation end-to-end.
* Audits for `FALSE_MERGE_CANDIDATE` and `MISSED_MERGE_CANDIDATE`
  on the data.

## 2. What P3-B-6 does NOT do

* ❌ NO modification to `match_stories()`.
* ❌ NO modification to Jaccard thresholds, entity overlap,
  location overlap, date proximity, or category compatibility
  rules.
* ❌ NO matching threshold tuning.
* ❌ NO scheduler / cron / repeated sampling.
* ❌ NO engagement API / metrics guessing.
* ❌ NO Facebook / Android Collector / PlatformContentRef.
* ❌ NO LLM / AI classification.
* ❌ NO Radar / Candidate / Website change.
* ❌ NO political scoring / ranking / prediction.
* ❌ NO Experience promotion.

---

## 3. Pipeline under test

```
BERNAMA RSS
       |
       v
AdapterObservation (P3-B-3 source_category extracted)
       |
       v
StoryMember (source_category preserved per-row)
       |
       v
match_stories()  (existing P2 matching — UNCHANGED)
       |
       v
form_story_clusters()  (test-only connected-component grouping)
       |
       v
derive_story_cluster_category()  (P3-B-5 follow-up convention)
       |
       v
StoryCluster.category = "WORLD" / ... / ""  (P2 empty-string convention)
```

---

## 4. Real BERNAMA observations (live, 2026-09-29)

```
total articles:      10
unique content_ids:  10
unique urls:         10
total clusters:      10
singleton clusters:  10
multi-member:        0
largest cluster:     1
average size:        1.00
```

**Honest finding:** A single BERNAMA RSS snapshot contains no
duplicate-coverage pairs. P2's matcher correctly produced 10
singletons. There are no multi-member clusters to audit on
this snapshot.

**Interpretation:** This is expected for a single RSS pull.
BERNAMA's feed at any moment is a snapshot of distinct stories;
it does not republish its own articles with different headlines
in the same feed. Multi-member clusters require either (a)
multiple BERNAMA snapshots taken over time (which requires the
paused P3-B-4 scheduler), or (b) cross-publisher matching (which
requires Android Collector / P4-B integration).

---

## 5. Cached real BERNAMA fixture (deterministic test path)

The cached fixture contains 6 articles — including two pairs of
near-duplicate titles to exercise the matcher:

```
Article 1: General : Cabinet Statement On Subsidy Review
Article 2: General : Government Announces Subsidy Review Mechanism
Article 3: World  : Trump Announces Trade Tariff Hike
Article 4: World  : Trade Tariff Hike Announced By Trump
Article 5: Sports : Malaysia Wins Football Tournament
Article 6: Business: Subsidy Review Impact On Markets
```

### Cluster results

```
total articles:    6
total clusters:    6
  singletons:      6
  multi-member:    0
  largest:         1
```

### Category propagation

```
propagated clusters: 6   (Case A: single-member-with-category)
unresolved clusters: 0
conflict clusters:   0

Category distribution:
  BUSINESS: 1
  GENERAL:  2
  SPORTS:   1
  WORLD:    2
```

### P2 matcher behavior on near-duplicate pairs

| Pair | Score | Reasons | Matched? |
|---|---|---|---|
| Subsidy pair (Articles 1 & 2) | 0.250 | `date_proximity`, `normalized_title_similarity_weak` | **False** |
| Tariff pair (Articles 3 & 4) | 0.550 | `date_proximity`, `normalized_title_similarity` | **False** |

**Missed Merge Candidate (observation, not auto-fix):**

* **Subsidy pair** (Articles 1 & 2): Same event ("subsidy review
  mechanism"), same category (`GENERAL`), same day. P2 returned
  `matched=False` because:
  - title similarity is `weak` (jaccard below `JACCARD_HIGH=0.3`)
  - no entity overlap (BERNAMA titles don't expose structured entities)
  - no location overlap
  P2's spec requires either `NAMED_ENTITY_OVERLAP` or
  `LOCATION_OVERLAP + similarity`. Neither is present here.
  **This is correct P2 behavior** per the strict rules.

* **Tariff pair** (Articles 3 & 4): Same event ("Trump tariff
  hike"), same category (`WORLD`), same day. P2 returned
  `matched=False` with `normalized_title_similarity` (above
  `JACCARD_MEDIUM=0.15`) but no entity/location overlap. Same
  reason as above.

**Conclusion:** P2's matcher correctly refuses to merge these
because they lack the corroborating evidence (entity/location
overlap) required by the spec. Real-world same-event detection
on RSS-only data requires entity extraction; this is a research
question for a future batch, not a P2 algorithm change.

---

## 6. Identity check

- ✅ URL → content_id rule unchanged (`ci_` + SHA-256 prefix)
- ✅ All 10 live BERNAMA URLs produce unique content_ids
- ✅ All 6 cached fixture URLs produce unique content_ids
- ✅ Same URL across multiple fetches produces same content_id
  (verified in P3-B-1; not re-tested here)

## 7. Metrics check

- ✅ All `views`, `likes`, `comments`, `shares`, `reposts` stay `None`
  on real BERNAMA observations
- ✅ No path coerces None → 0
- ✅ StoryCluster.to_dict() does not introduce metric fields

## 8. Synthetic isolation

- ✅ Live BERNAMA observations: no `_synthetic=True`
- ✅ Cached real BERNAMA fixture: no `_synthetic=True`
- ✅ StoryCluster / StoryMember produced from real data: no
  `_synthetic` field

## 9. Test results

| Suite | Count |
|---|---|
| P1 (existing) | 49 / 49 PASS |
| P2 (existing) | 59 / 59 PASS |
| P3-A (existing) | 37 / 37 PASS |
| Android Bridge (existing) | 39 / 39 PASS |
| P3-B-1 (existing) | 21 / 21 PASS |
| P3-B-2A (existing) | 24 / 24 PASS |
| P3-B-3 (existing) | 32 / 32 PASS |
| P3-B-5 (existing) | 33 / 33 PASS |
| **P3-B-6 (new)** | **15 / 15 PASS** |
| **Total Performance** | **309 / 309 PASS** |
| Radar (no-touch) | 396 / 396 PASS |
| **Grand Total** | **705 / 705 PASS** |

P3-B-6 test breakdown (15 tests):

| Test | Purpose |
|---|---|
| `test_live_bernama_adapter_observations_to_members` | Live AdapterObservation → StoryMember round-trip |
| `test_live_bernama_form_clusters_and_record_stats` | Live cluster formation + stats |
| `test_cached_bernama_members_to_clusters` | Cached real RSS → clusters |
| `test_cached_bernama_cluster_size_distribution` | Size distribution report |
| `test_cached_bernama_category_propagation_stats` | Per-cluster category stats |
| `test_cached_bernama_cluster_with_same_category_propagates` | Case A propagation observed |
| `test_cached_bernama_unresolved_uses_empty_string_not_unresolved` | P3-B-5 follow-up convention |
| `test_cached_bernama_category_conflict_uses_empty_string` | Conflict detection works |
| `test_cached_bernama_metrics_remain_none_through_pipeline` | No None → 0 |
| `test_cached_bernama_synthetic_isolation` | No synthetic leak |
| `test_cached_bernama_content_id_unchanged` | Identity preserved |
| `test_cached_bernama_cluster_audit_full_dump` | Human-auditable dump |
| `test_audit_no_synthetic_fabricated_clusters` | Synthetic gate end-to-end |
| `test_audit_categories_conflict_detection_works` | Conflict path |
| `test_live_bernama_observation_report` | Live full audit |

---

## 10. Cluster audit (multi-member clusters)

**Live BERNAMA (2026-09-29):**
- Multi-member clusters: 0
- No false-merge candidates (no merges happened)

**Cached real BERNAMA fixture:**
- Multi-member clusters: 0
- No false-merge candidates (no merges happened)

---

## 11. False-merge candidates

**None observed.** P2's matcher did not produce any cross-article
matches on the live data or the cached fixture. No false-merge
candidates to report.

---

## 12. Missed-merge candidates

(See section 5 above.)

- **Subsidy pair** (Articles 1 & 2, cached fixture): Same event,
  same category, same day. `matched=False`, score=0.250, only
  weak title similarity.
- **Tariff pair** (Articles 3 & 4, cached fixture): Same event,
  same category, same day. `matched=False`, score=0.550, only
  normalized title similarity.

**Why P2 didn't match:** P2 requires entity or location overlap
to corroborate weak/moderate title similarity. BERNAMA titles
don't expose structured entities in this batch, so neither
corroboration is available.

**This is correct P2 behavior per the spec, not a bug.** No
algorithm change proposed.

---

## 13. Category conflict

**None observed.** On the cached fixture, all 6 clusters are
singletons with one category each; no conflict arises.

**Conflict path verified explicitly** by
`test_cached_bernama_category_conflict_uses_empty_string` and
`test_audit_categories_conflict_detection_works`: building a
multi-member cluster with `WORLD` + `BUSINESS` correctly returns
`category=None, conflict=True`, and the cluster-level
representation is `""` (P3-B-5 follow-up convention).

---

## 14. Production safety

- ✅ `https://myhotradar.com/` → 200
- ✅ `https://myhotradar.com/article/example/` → 200
- ✅ `https://myhotradar.com/public/radar/latest.json` → 200
- ✅ No files in `radar/`, `radar_data/`, `public/` modified
- ✅ No Radar / Candidate / scheduler / politics guardrail /
  website / AdSense / sitemap changes
- ✅ `performance_data/` gitignored; tests write only to temp
  dirs
- ✅ No automatic publishing; no continuous sampling
- ✅ Synthetic data isolation preserved end-to-end

---

## 15. Git

- **commit**: (this batch)
- **push**: success
- 1 commit, normal workflow (no amend / rebase / squash /
  force-push / reset --hard)

---

## 16. Recommendation for next batch

- **P3-B-4 Scheduler** (only with explicit approval). The
  Missed-Merge Candidates in section 12 are research questions
  for a future batch — they would benefit from time-series
  sampling.
- **P3-B-7 Entity extraction** (research): If BERNAMA titles
  can be enriched with structured entities (people, locations),
  P2's matcher would have the corroboration needed to merge the
  subsidy / tariff near-duplicates. This is a separate research
  question, not part of P3-B-6.

---

**Stop condition met.** Awaiting next instruction.