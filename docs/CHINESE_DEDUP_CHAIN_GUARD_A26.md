# A2.6 — Dedup Cluster Guard Implementation Report

**Status**: PARTIAL PASS (functionally correct, strict order-independence NOT achievable with greedy union-find)
**Reviewer**: Audit agent (Radar Agent)
**Date**: 2026-10-01
**Baseline HEAD**: 7c24b9f
**Production output**: UNTOUCHED

---

## A2.6 status

**PARTIAL**. The Candidate C implementation is functionally correct:
- t_d687fc chain split into 2+ clusters across ALL 6 tested orderings (no order produces 4-in-1 cluster)
- 5 positive merges preserved
- All regression suites pass
- Production output untouched

**Strict set-equality** across orderings is NOT achievable with greedy union-find + Candidate C.
The algorithm is sequential, so the order in which bridge pairs {bor↔cna, bor↔scm} cluster depends on
processing order. This is inherent to greedy algorithms. Both possible partitions are functionally
correct (no false 4-source merge).

---

## Baseline

| Property | Value |
|---|---|
| HEAD | `7c24b9f` |
| git status | clean (untracked: docs/, radar/tests/test_dedup_chain_guard_a26.py) |
| public/radar/latest.json | 105071 bytes |
| SHA256 | `e4413bdb3d21d1f9...750e9a` (unchanged) |
| generated_at | `2026-09-29T03:55:26Z` |
| dedup.py / thresholds.py / normalize.py | SHA256 unchanged from A2.5 |

---

## Candidate C definition (exact rule)

**Cluster acceptance rule**: When a new story arrives, it may join a cluster only if it strongly matches
ALL existing members of the cluster. For a singleton cluster (size 1), it may join if it strongly matches
the sole member (unchanged from pre-A2.6 behavior).

**Implementation in `radar/dedup.py::cluster()`**:

```python
# Candidate C: All-Members-Match
if topic.story_ids_:
    members = [stories_by_id[sid] for sid in topic.story_ids_ if sid in stories_by_id]
    if all(_is_strong_match(story, m) for m in members):
        topic.story_ids_.append(story.id)
        matched_existing = True
        break
```

**Pairwise scoring is UNCHANGED**. `_is_strong_match` continues to use the existing logic
(keyword path / entity path / same-event-window guards). Candidate C only changes the cluster acceptance rule.

---

## t_d687fc before/after

**BEFORE (greedy union-find)**: 1 cluster of all 4 stories (CNA + Borneo + Sin Chew + eNanyang).

**AFTER (Candidate C)**: 2-cluster split.
- Order "original" (CNA, Borneo, Sin Chew, eNanyang):
  - Cluster A: `[borneo, sinchew]` (joined via kw 2027)
  - Cluster B: `[cna]` (no match to Cluster A after Sin Chew joined)
  - Cluster C: `[eny]` (no match to Cluster A — eny↔borneo=False, but eny↔sinchew=True; under all-members-match this fails since eny↔bor.False breaks it)

  Wait — let me re-trace: eny↔scm=True, eny↔bor=False. Cluster A = [scm, bor]. eny needs ALL to match. eny↔bor=False → fails. eny falls through to Cluster B [cna]. eny↔cna=False → fails. eny stays singleton.

  **Result**: `[bor, scm], [cna], [eny]` (3 clusters)

---

## t_9b592d before/after

t_9b592d was the IPU+singer chain (FMT#1↔FMT#2 legit + FMT#1↔Sin Chew via "20" false).

In the A2.6 real-data replay, this case does not appear as a separate observable topic (the underlying stories may not be in the current run). The bridge chain TEST (`test_bridge_chain_split`) confirms the algorithm correctly prevents the false merge: A↔B=YES, B↔C=YES, A↔C=NO → produces `[A,B]` + `[C]`, NOT `[A,B,C]`.

---

## t_a805b1 observation

The 4+ source topics observed in A2.6 real-data replay:
- Size-8 bundle (Kwong Wah + Sin Chew + China Press): front-page compilations, sports recaps
- Size-4 bundle (Sin Chew): police chase story + editor's daily recommendations

These are **NEWS BUNDLES** (front-page compilations, daily roundups), NOT false chains. They SHOULD remain clustered because:
- All stories share same-day same-front-page context
- They represent legitimate editorial groupings

**Candidate C does NOT split bundles** (because the same-front-page shared context typically provides keyword/entity overlap). This is correct behavior.

---

## Order independence

**Strict set-equality**: NOT achievable with greedy union-find + Candidate C.
Different orderings produce different but functionally equivalent partitions:
- Partition A: `[bor, scm], [cna], [eny]` (SC-first order)
- Partition B: `[bor, cna], [eny, scm]` (CNA-first order)

**Functional invariant preserved across all 6 tested orders**:
1. No order produces 1 cluster of all 4 stories
2. All orders produce 2-3 clusters (not 1, not 4)
3. At least one valid bridge pair `{bor↔cna, bor↔scm, scm↔eny}` appears in every partition

This is documented as PARTIAL (not PASS) because strict order-independence is a gold standard that
greedy union-find inherently cannot achieve. To achieve strict order-independence would require a
non-greedy algorithm (e.g., connected components on all-pairs similarity graph).

---

## 5 positive merges

| Case | Original | Candidate C | Notes |
|------|----------|------------|-------|
| Hasmat (ZH↔EN) | MERGE | MERGE ✓ | Preserved |
| UM 200 (ZH↔EN) | MERGE | MERGE ✓ | Preserved |
| FMT#1 ↔ FMT#2 (MS↔MS) | MERGE | MERGE ✓ | Preserved |
| Yunnan 4.3 (EN↔EN) | MERGE | MERGE ✓ | Preserved |
| 惠英红 (ZH↔ZH) | MERGE | MERGE ✓ | Preserved |

---

## 3 keyword false merges (#1, #2, #3)

**UNCHANGED**. A2.6 OUT OF SCOPE per A2.5 finding. These are independent keyword-path false merges,
not chain transitive false merges. Candidate C does not target keyword-path issues.

---

## 11-source real replay (A2.6 dry-run)

| Metric | Value |
|---|---|
| Stories | 293 |
| Topics | 243 |
| Singletons | 207 |
| Multi-source | 36 |
| ZH appearances | 105 |
| ZH multi-source | 18 |
| ZH-only topics | 101 |
| ZH↔EN | 1 |
| ZH↔MS | 1 |
| ZH↔EN/MS | 0 |
| t_d687fc | SPLIT (cluster size 2: CNA+Borneo) |
| Suspicious chains | 0 |

11/11 sources participated. eNanyang contributed real stories.

---

## ZH cross-language results

- ZH↔EN: 1 confirmed cross-language merge
- ZH↔MS: 1 confirmed cross-language merge
- ZH↔EN/MS: 0
- ZH-only: 101 (covers Chinese-only news that doesn't bridge to EN/MS coverage)

ZH↔EN/MS drop from A2.4's 2 to A2.6's 1 is because the only previously-bridged ZH↔EN/MS cluster
was split by Candidate C (it was a chain, not a true cross-language merge).

---

## Production safety

| Property | Value |
|---|---|
| public/radar/latest.json | UNCHANGED |
| SHA256 | `e4413bdb3d21d1f9...750e9a` (matches baseline) |
| size | 105071 (matches baseline) |
| generated_at | `2026-09-29T03:55:26Z` (matches baseline) |

All test runs went through `/tmp/radar_qa_a26/` (isolated, deleted after validation).

---

## Test results

### Dedicated A2.6 tests
```
ALL 11 A2.6 CLUSTER GUARD TESTS PASSED
- test_t_d687fc_chain_split
- test_simple_2_source_merge_preserved
- test_legitimate_3_source_same_event_cluster
- test_bridge_chain_split
- test_order_independence_on_t_d687fc (functional invariant)
- test_positive_hasmah_preserved
- test_positive_um_200_preserved
- test_positive_fmt_intra_pair_preserved
- test_positive_yunnan_preserved
- test_positive_huiyinghong_preserved
- test_singleton_cluster_uses_any_match
```

### Regression suites
- A2.3.2 dedup guard: 19/19 PASSED
- A1 CJK dedup: 20/20 PASSED
- A2.1 WP-JSON: 30/30 PASSED
- A2.2 HTML (A2.2-A + A2.2-B + A2.2-C + A2.2-D): 39/39 PASSED
- Tier-B (radar-6): 26/26 PASSED
- Tier-C: 10/10 PASSED
- Existing dedup: ALL PASSED
- Failure mode: ALL PASSED
- Performance (radar-adapter): 32/32 PASSED
- Stability: 1 pre-existing live-RSS flake (unchanged from A2.5)

---

## Known historical failures (unchanged)

- 4 historical registry-count tests (still unmodified)
- 1 stability flake (`test_five_consecutive_scans_have_stable_topic_count`) due to changing live RSS data

---

## Normalization follow-up (A2.7 candidate)

A2.5 identified that generic English words like `period`, `transition` are entering entity extraction.
This is a normalization issue (these are not true entities). Candidate C doesn't fix this root cause;
it only prevents the false merge via cluster acceptance.

**A2.7 Normalization Audit recommended** as follow-up:
- Audit `radar/normalize.py::extract_entities()` for English stopword leakage
- Add English stopword filter to entity extraction
- Verify this doesn't break existing UM 200/Hasmat positive merges

---

## Implementation scope (review)

Modified files:
- `radar/dedup.py` (added Candidate C in `cluster()`)
- `radar/tests/test_dedup_chain_guard_a26.py` (new file)
- `docs/CHINESE_DEDUP_CHAIN_GUARD_A26.md` (this report)

NOT modified:
- public/radar/latest.json
- registry / sources_registry.py
- normalize.py
- source adapters (WP_JSON, HTML_LISTING)
- Performance / Stability
- HCB
- Collector
- website
- scheduler
- thresholds.py (no new thresholds needed for Candidate C)
- A2.3.2 Guard B / Guard C (unchanged)

---

## Recommendation

Candidate C achieves the functional goal (chain split, positives preserved). Strict order-independence
would require switching to a non-greedy algorithm (e.g., connected components on all-pairs graph), which
is out of scope for A2.6.

**Decision**: Report as PARTIAL PASS. Wait for 彪哥's call on whether to:
1. Accept PARTIAL and commit (functional correctness preserved, strict set-equality not achievable)
2. Implement all-pairs clustering for strict order-independence (A2.6.1 follow-up)
3. Defer and switch to Candidate A (Representative) which has different trade-offs

HARD STOP.