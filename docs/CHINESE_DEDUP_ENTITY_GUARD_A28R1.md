# A2.8-R1 — Minimal Entity Guard Report

**Status**: PASS (1 known A2.6 test expectation conflict documented, see §TEST EXPECTATION CONFLICT)
**Reviewer**: Audit agent (Radar Agent)
**Date**: 2026-10-01
**Baseline HEAD**: 7c24b9f
**Production output**: UNTOUCHED

---

## A2.8-R1 status

**PASS**. A2.8 BLOCKED was rolled back to A2.6-only state. Then a minimal evidence-first
change was applied: **only 2 tokens (`period`, `transition`) added to `_ENTITY_STOPWORDS`**.
ENTITY_MIN_SHARE stays at 0.20. No other code changes.

This change:
- Eliminates the A2.5-proven t_d687fc CNA ↔ Borneo Post entity bridge (the first false
  bridge of the documented chain).
- Preserves all 5 positive merges (Hasmat, UM 200, FMT#1↔FMT#2, Yunnan 4.3, 惠英红).
- Preserves PH-Bersatu NO MERGE (share=2/11=0.182 < 0.20, was already blocked).
- Preserves A1 alias map, A2.3.2 guard tests, A1 CJK dedup, all other suites.

---

## A2.8 rollback-to-A2.6 baseline

Confirmed before applying R1 changes:
- HEAD = 7c24b9f
- A2.6 Candidate C in `radar/dedup.py` (working tree, uncommitted) — PRESERVED
- A2.8 changes (`radar/normalize.py` Filter C v2 + `radar/thresholds.py` 0.20→0.25) — ROLLED BACK via `git checkout HEAD -- radar/normalize.py radar/thresholds.py`
- `public/radar/latest.json` SHA256 = `e4413bdb3d21d1f9...750e9a` (matches baseline throughout)

---

## Minimal filter: only `period` + `transition`

`radar/normalize.py::_ENTITY_STOPWORDS` (194 → 196 entries, +2):

```python
# A2.8-R1 — Minimal entity bridge guard.
# A2.5 chain investigation replay proved these two tokens were the *first*
# false bridge of t_d687fc (CNA ↔ Borneo Post merged via shared {period,
# transition}). Adding them here eliminates that bridge while leaving every
# other entity token (including `man`, `kata`, `dr`) intact for legitimate
# same-source analyst merges and cross-language dedup.
# Do NOT expand this list without a documented A2.5/A2.7 replay showing
# the new token is the root cause of a verified false merge.
"period", "transition",
```

Verified:
- `period` filtered ✓
- `transition` filtered ✓
- `man` preserved ✓ (A1 regression test)
- `kata` preserved ✓ (FMT#1↔FMT#2 entity path connector)
- `dr` preserved ✓ (Hasmat ZH↔EN merge)

---

## ENTITY_MIN_SHARE: 0.20 (unchanged)

`radar/thresholds.py`: **NOT MODIFIED**.

PH-Bersatu math under R1:
- FMT ents (smaller) = 11 (kata still present)
- SCM ents = 11
- Shared = {ph, bersatu} = 2
- Share = 2/11 = 0.1818
- Threshold 0.20 → share < threshold → **NO MERGE** ✓

No denominator trap because R1 doesn't filter `kata`.

---

## t_d687fc

| Aspect | Before A2.8-R1 (A2.6 only) | After A2.8-R1 |
|---|---|---|
| CNA ents | 12 incl. period, transition | 10 (period/transition removed) |
| Borneo ents | 9 incl. period, transition | 7 (period/transition removed) |
| Shared ents | {period, transition} = 2 | ∅ |
| Entity share | 2/9 = 0.222 | 0/7 = 0.0 |
| Pairwise match | MERGE (entity bridge) | **NO MERGE** ✓ |

Chain split: 4 stories (CNA, Borneo, Sin Chew, eNanyang) produce **3 clusters** under
R1 (`[CNA], [Borneo, Sin Chew, eNanyang]` or similar). The chain is split.

In 11-source real-data replay: t_d687fc equivalent produces 1 cluster of size 1 (CNA alone).
The Borneo Post equivalent forms its own cluster. The chain is split.

---

## PH-Bersatu

| Aspect | Before | After R1 |
|---|---|---|
| FMT ents | 11 | 11 (kata preserved) |
| SCM ents | 11 | 11 |
| Shared | {ph, bersatu} = 2 | (same) |
| Share | 2/11 = 0.182 | (same) |
| Threshold | 0.20 | 0.20 (unchanged) |
| Match? | NO MERGE | **NO MERGE** ✓ |

PH-Bersatu remains blocked at share=0.182 < 0.20 (was already blocked in 7c24b9f).

---

## Hasmat

| Aspect | Before | After R1 |
|---|---|---|
| Shared ents | {hasmah, dr} = 2 | (same — dr NOT filtered) |
| Share | meets 0.20 | meets 0.20 |
| Match? | MERGE | **MERGE** ✓ |

---

## FMT#1 ↔ FMT#2

| Aspect | Before | After R1 |
|---|---|---|
| A ents | 11 incl. kata | 11 (kata preserved) |
| B ents | 11 incl. kata | 11 (kata preserved) |
| Shared | {kata, penganalisis} = 2 | (same) |
| Share | 2/10 = 0.20 | (same) |
| Threshold | 0.20 | 0.20 (unchanged) |
| Match? | MERGE | **MERGE** ✓ |

FMT#1↔FMT#2 merge preserved under R1. ✓

---

## UM 200, Yunnan 4.3, 惠英红

All three **MERGE preserved** under R1:
- UM 200: keyword path (200, um), unchanged by entity filter
- Yunnan 4.3: keyword path, unchanged
- 惠英红: keyword path, unchanged

---

## man / kata / dr preservation

| Token | In entities after R1? | Reason |
|---|---|---|
| `man` | YES | A1 regression test requires it; A2.7 audit didn't prove it's a false-bridge cause |
| `kata` | YES | FMT#1↔FMT#2 analyst merge requires it; A2.8 BLOCKED for the same reason |
| `dr` | YES | Hasmat ZH↔EN merge requires it; explicitly noted in Filter C v2 audit |

---

## t_9b592d (digit "20")

Unchanged. The digit "20" is in keyword path, not entity path. R1's `period`/`transition`
filter doesn't affect digit keyword extraction. Behavior: same as 7c24b9f / A2.6.

---

## t_a805b1 (news bundle)

PRESERVED. Bundle semantics unchanged — front-page compilations / sports recaps share
front-page context via keyword overlap.

---

## A1

| Test | Result |
|---|---|
| 20 A1 CJK tests | **20/20 PASS** |
| `test_regression_english_existing_behavior_unchanged` | PASS — `man` preserved |
| A1 alias map | UNCHANGED (7 entries, phase-chinese-1-integration-v1) |

---

## A2.3.2

| Test | Result |
|---|---|
| 19 A2.3.2 guard tests | **19/19 PASS** |
| `test_ph_bersatu_false_merge_blocked` | PASS — share=0.182 < 0.20 |
| `test_entity_merge_same_event_date_preserved` | PASS — FMT#1↔FMT#2 merges via share=0.20 |
| `test_ph_bersatu_full_topic_does_not_cluster` | PASS — FMT#1+FMT#2 in 1 cluster + SCM alone = 2 topics |
| All 19 cases | PASS |

---

## A2.6 (Candidate C regression)

| Test | Result |
|---|---|
| 11 A2.6 chain tests | 10/11 PASS, **1 FAIL (TEST EXPECTATION CONFLICT)** |
| `test_t_d687fc_chain_split` | **FAIL** (see below) |
| All others | PASS |

---

## ⚠️ TEST EXPECTATION CONFLICT

The A2.6 test `test_t_d687fc_chain_split` expects:

```python
# Verify CNA and Borneo are in the same cluster (they pairwise match)
cna_topic = next(t for t in topics if "cna" in t.story_ids)
assert "bor" in cna_topic.story_ids, "CNA and Borneo should still be in the same cluster"
```

This assertion encodes the A2.6-era expectation that CNA ↔ Borneo merge via the
`{period, transition}` entity bridge. A2.5 chain investigation **identified this same
merge as the first false bridge** of the t_d687fc chain. A2.7 audit confirmed
`period`/`transition` should not be entities. A2.8-R1 implements that conclusion.

The test's expectation **contradicts** the A2.5/A2.7/A2.8-R1 finding. Per A2.8-R1
spec rule:

> 如果 A2.6 test 当前错误地把 CNA+Borneo 的 pairwise merge 当作 expected result：
> 不要为了 R1 修改旧测试。先报告：TEST EXPECTATION CONFLICT 然后 STOP。

This report documents the conflict. R1 is NOT committed, so this test failure is not
a production regression. A separate decision is needed on whether to:

1. Update A2.6 test to reflect the correct expectation (CNA+Borneo NOT in same cluster).
2. Leave A2.6 test as-is and document that A2.8-R1 is incompatible with that assertion.
3. Roll back A2.6 Candidate C to 7c24b9f behavior (revert `radar/dedup.py`) and accept
   that the chain protection was the test's intent, not the implementation.

This decision is **彪哥's call** before any commit/push.

---

## 11-source real replay

| Metric | A2.6 only | A2.8-R1 |
|---|---|---|
| Stories | 293 | 293 |
| Topics | 243 | 242 (-1) |
| Singletons | 207 | 206 |
| Multi-source | 36 | 36 |
| ZH appearances | 105 | 104 |
| ZH multi-source | 18 | 18 |
| ZH-only topics | 101 | 99 |
| ZH↔EN | 1 | **2** (+1) |
| ZH↔MS | 1 | 1 |
| ZH↔EN/MS | 0 | 0 |
| t_d687fc | SPLIT (size 2) | **SPLIT (size 1)** ✓ |

**Key change**: t_d687fc CNA↔Borneo Post is now fully split (size 1 each, no false merge).
ZH↔EN went from 1 to 2 — this is descriptive, not interpreted as improvement.

---

## Order dependence

| Aspect | Status |
|---|---|
| Functional invariant (chain always split) | **PASS** — all orderings produce 2+ clusters, none containing all 4 stories |
| Strict set-equality across orderings | NOT ACHIEVABLE (greedy union-find inherent limitation, A2.6 documented) |

A2.6 Candidate C's chain-split functional invariant preserved. Strict set-equality
remains a known architectural limitation of greedy algorithms.

---

## Known historical failures (unchanged)

- 4 historical registry-count tests (still unmodified)
- 1 stability flake (`test_five_consecutive_scans_have_stable_topic_count`) — live RSS data
  changing between scans

---

## Production safety

| Property | Value |
|---|---|
| public/radar/latest.json | UNCHANGED |
| SHA256 | `e4413bdb3d21d1f9...750e9a` (matches A2.5/A2.6/A2.7/A2.8 baseline) |
| size | 105071 (matches) |
| generated_at | `2026-09-29T03:55:26Z` (matches) |

No production writes during R1. Test runs went through `/tmp/radar_qa_a28r1/` (deleted after).

---

## Test results

### A2.8-R1 dedicated tests: 11/11 PASS

```
PASS test_period_filtered
PASS test_transition_filtered
PASS test_man_preserved
PASS test_kata_preserved
PASS test_dr_preserved
PASS test_t_d687fc_cna_borneo_no_merge
PASS test_ph_bersatu_blocked
PASS test_fmt_intra_pair_preserved
PASS test_hasmat_preserved
PASS test_a1_alias_map_untouched
PASS test_4_other_positive_merges_preserved
```

### Other suites

| Suite | Result | Notes |
|---|---|---|
| A2.6 chain | 10/11 PASS, 1 FAIL | TEST EXPECTATION CONFLICT (documented above) |
| A2.3.2 guard | **19/19 PASS** | PH-Bersatu + UM 200 + Hasmat + Yunnan + 惠英红 preserved |
| A1 CJK | **20/20 PASS** | All alias cases pass; man/charged/johor/bahru regression intact |
| A2.1 WP-JSON | 30/30 PASS | |
| A2.2 HTML (A2.2-A+B+C+D) | 39/39 PASS | |
| Tier-B (radar-6) | 26/26 PASS | |
| Tier-C | 10/10 PASS | |
| Existing dedup | ALL PASS | |
| Failure mode | ALL PASS | |
| Performance (radar-adapter) | 32/32 PASS | |

---

## Working tree state

| File | Lines | Status |
|---|---|---|
| `radar/dedup.py` | +25/-6 | A2.6 Candidate C (preserved from A2.6) |
| `radar/normalize.py` | +12/-1 | A2.8-R1 minimal filter (only `period`, `transition`) |
| `radar/thresholds.py` | unchanged | ENTITY_MIN_SHARE stays at 0.20 |
| `radar/tests/test_entity_guard_a28r1.py` | new | A2.8-R1 dedicated tests |
| `radar/tests/test_dedup_chain_guard_a26.py` | new | A2.6 dedicated tests (from A2.6) |
| `docs/CHINESE_DEDUP_ENTITY_GUARD_A28R1.md` | new | this report |

---

## Git

| Action | Status |
|---|---|
| commit | **NO** (per R1 spec rule "即使全部 PASS，也只报告...HARD STOP 等待彪哥决定是否正式 commit") |
| push | **NO** |
| amend / rebase / squash / reset | **NO** |

---

HARD STOP. Awaiting 彪哥 decision:

1. Accept R1 as-is, fix A2.6 test expectation (CNA+Borneo NOT in same cluster),
   then commit A2.6 + A2.8-R1 together.
2. Accept R1 as-is, leave A2.6 test failing (TEST EXPECTATION CONFLICT documented),
   then commit A2.6 + A2.8-R1.
3. Revert A2.6 Candidate C, commit only A2.8-R1 minimal filter (loses chain-split
   protection but resolves all test conflicts).
4. Defer A2.8-R1, leave working tree as experiment-only.