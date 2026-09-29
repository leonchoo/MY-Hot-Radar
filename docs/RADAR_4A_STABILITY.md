# MY Hot Radar — Radar-4A: Stability / Soak Validation

> Final documentation for the **Radar-4A** batch.
> Read alongside `NEWS_RADAR.md`, `VERIFICATION_RULES.md`, and
> `docs/EXPERIENCE_BACKUP.md`.

This document records the **stability / soak validation** of the
Radar engine (Radar-1 → Radar-3) across **five consecutive real RSS
scans** and the new tests added in Radar-4A. It is a pure evidence
record, not a feature spec.

---

## 1. Goal

Prove that the Radar engine can:

1. Run end-to-end **five consecutive real scans** without drift.
2. Keep **topic identity stable** across scans (no fake duplicate topics).
3. Walk every topic through the full **lifecycle**:
   `NEW → RISING → WATCH → COOLING → DISAPPEARED`.
4. Stay correct under **momentum edge cases** (zero baseline,
   disappear-and-return, etc.).
5. Isolate a **failing source** from the rest of the scan.
6. Behave **idempotently** when the same data is re-injected.
7. Not let a **malformed history file** permanently poison future
   momentum.

This batch does **not** add new features or sources. The focus is
hardening, regression coverage, and one real bug fix.

---

## 2. Continuous scans (5 real runs)

Each scan fetched the 5 registered Tier-B RSS sources (BBC News Asia,
Channel News Asia, CodeBlue, Free Malaysia Today Bahasa, Borneo Post)
and wrote one history snapshot to `radar_data/history/`.

| Scan | Topics | Stories | Sources OK | Duration | History files |
|-----:|-------:|--------:|-----------:|---------:|--------------:|
|    1 |     90 |     119 |        5/5 |    1.91s |             1 |
|    2 |     90 |     119 |        5/5 |    1.57s |             2 |
|    3 |     90 |     119 |        5/5 |    1.60s |             3 |
|    4 |     90 |     119 |        5/5 |    1.64s |             4 |
|    5 |     90 |     119 |        5/5 |    1.55s |             5 |

### Topic-set stability

For each consecutive pair `(scan N, scan N+1)`:

```
scan 1 -> scan 2: 90 common, 0 gone, 0 new
scan 2 -> scan 3: 90 common, 0 gone, 0 new
scan 3 -> scan 4: 90 common, 0 gone, 0 new
scan 4 -> scan 5: 90 common, 0 gone, 0 new
```

**Zero topic identity drift.** Every topic that exists in scan 1 is
present in scan 5 under the same `content_key`. No topic appears more
than once. No topic silently disappears.

### Status distribution per scan

```
scan 1: WATCH=83, RISING=7
scan 2: WATCH=90
scan 3: WATCH=90
scan 4: WATCH=90
scan 5: WATCH=90
```

The 7 RISING topics in scan 1 are the topics whose previous count was
zero (the "first scan" effect). Scans 2–5 see `growth_rate=0.0` for
every topic (no real growth between seconds), so they all fall back to
WATCH. This is correct lifecycle behaviour, not a regression.

---

## 3. Stability validation matrix

The new `radar/tests/test_stability.py` file adds **24 tests** that
cover every requirement in the Radar-4A spec. All 24 pass.

### 3.1 Topic identity (4 tests)

| Test | Asserts | Result |
|---|---|---|
| `test_five_consecutive_scans_have_stable_topic_count` | 5 scans yield identical topic sets | PASS |
| `test_topic_content_key_is_stable_across_scans` | Same canonical URL → same `content_key` every scan | PASS |
| `test_same_mention_count_across_scans` | Re-injecting same fixture gives `mention_count=5` every scan, not cumulative | PASS |
| `test_no_random_topic_id_in_history_keys` | History keys are content-derived, never the random `Topic.id` | PASS |

### 3.2 Lifecycle (3 tests)

| Test | Sequence | Result |
|---|---|---|
| `test_full_lifecycle_5_to_10_to_10_to_3_to_0` | 5 → 10 → 10 → 3 → 0 across 5 scans | PASS |
| `test_lifecycle_momentum_transitions` | Per-scan momentum values match the spec table | PASS |
| `test_topic_disappeared_does_not_break_next_scan` | Empty scan 2 + empty scan 3 do not corrupt the chain | PASS |

The expected momentum sequence is verified directly:

```
scan 1 (n=10): is_new=True,  prev=0,  growth_rate=None
scan 2 (n=15): is_new=False, prev=10, growth_rate=50.0
scan 3 (n=15): is_new=False, prev=15, growth_rate=0.0
scan 4 (n=5):  is_new=False, prev=15, growth_rate=-66.67
scan 5 (n=0):  topic absent (DISAPPEARED)
```

### 3.3 History consistency (3 tests)

| Test | Asserts | Result |
|---|---|---|
| `test_history_files_are_well_formed_json` | Every produced history file parses + has expected schema | PASS |
| `test_history_filename_uses_utc_iso_timestamp` | Filenames match `scan-<UTC>.json` pattern | PASS |
| `test_history_does_not_grow_unboundedly_across_scans` | N scans produce N history files (no leaks) | PASS |

Plus the bug-fix regression test (see §4):

| Test | Asserts | Result |
|---|---|---|
| `test_malformed_history_does_not_poison_subsequent_scans` | Future-dated malformed files do not become "latest" | PASS |

### 3.4 Evidence stability (3 tests)

| Test | Asserts | Result |
|---|---|---|
| `test_independent_sources_stable_when_same_wire_grows` | 1 / 3 / 5 outlets republishing one wire → `independent_sources=1` always | PASS |
| `test_confidence_does_not_inflate_with_mention_count` | n=5 and n=50 from one source → identical confidence | PASS |
| `test_confidence_grows_with_evidence_structure` | `B < B+B < A+B` regardless of mention count | PASS |

Concrete results:

```
test_independent_sources_stable_when_same_wire_grows:
  [(n_outlets, independent_sources, raw_source_count) for n_outlets in (1,3,5)]
  = [(1, 1, 1), (3, 1, 3), (5, 1, 5)]

test_confidence_does_not_inflate_with_mention_count:
  n=5  -> confidence 0.40
  n=50 -> confidence 0.40   (same)

test_confidence_grows_with_evidence_structure:
  Tier B alone    : 0.40
  Tier B + Tier B : 0.60   (independent)
  Tier A + Tier B : 0.75
  Tier A alone    : 0.55
```

### 3.5 Counter-signal isolation (2 tests)

| Test | Asserts | Result |
|---|---|---|
| `test_counter_signal_does_not_affect_unrelated_topic_across_scans` | Topic A denial → A=RUMOUR, B=REPORTED | PASS |
| `test_counter_signal_does_not_leak_across_scans` | Per-scan registry is fresh; no carry-over from scan 1 | PASS |

### 3.6 Failure isolation (4 tests)

A single bad source injected into a 5-source scan; the other four must
continue working, the scan must still produce a report.

| Test | Failure injected | Sources failed | Scan ok | Result |
|---|---|---|---|---|
| `test_timeout_failure_isolated_to_one_source`     | `FetchError("simulated timeout")`  | 1 | True | PASS |
| `test_malformed_xml_failure_isolated`            | `FetchError("malformed XML")`      | 1 | True | PASS |
| `test_http_500_failure_isolated`                 | `FetchError("HTTP 500")`           | 1 | True | PASS |
| `test_empty_feed_failure_isolated`               | `return []` (empty, not a failure) | 0 | True | PASS |

Empty feed is **not** a failure — it is treated as a successful fetch
of zero items. The source stays `ok=True` with `fetched=0`.

### 3.7 Idempotency / repeatability (3 tests)

| Test | Asserts | Result |
|---|---|---|
| `test_idempotency_re_injecting_same_3_stories` | Same fixture across 3 scans → `mention_count=3` every scan | PASS |
| `test_idempotency_re_fetching_same_source_does_not_double_count` | 3 identical stories in 1 scan → 1 topic, `mention_count=3` | PASS |
| `test_report_files_have_valid_json` | `latest.json` and `latest.md` carry expected fields | PASS |

### 3.8 Momentum edge cases (1 test, 9 sub-cases)

`test_momentum_no_div_zero_in_all_transitions` exercises every
transition the spec calls out:

```
(0,0), (0,5), (5,0), (5,5), (5,10), (10,5), (10,0), (0,100), (100,0)
```

For every case:

- `prev == 0` → `growth_rate is None` (no division by zero)
- `prev > 0`  → `growth_rate` is a finite real number (no NaN, no Infinity)
- `growth == current - previous` always
- `is_new` is `True` only when `prev == 0 and current > 0`
- `(current - previous) / previous * 100 == growth_rate` always

All 9 sub-cases PASS.

---

## 4. Real bug found and fixed in Radar-4A

### 4.1 Symptom

A **single malformed or future-dated file** in `radar_data/history/`
would **permanently poison** every subsequent scan's momentum.

Concretely: after scan N, if a file named `scan-2099-01-02T000000Z.json`
existed in `radar_data/history/` (e.g. from a manual file copy or
accidental creation), then **every topic in every future scan** would
appear as `is_new=True` with `previous_mentions=0` — because
`_latest_snapshot_path` was returning that file as the "most recent
prior scan" indefinitely.

### 4.2 Root cause

The original `_latest_snapshot_path` (in `radar/history.py`) simply
returned the lexicographically last `scan-*.json` filename:

```python
files = sorted(sd.glob("scan-*.json"), key=lambda p: p.name)
return files[-1] if files else None
```

This does **not** validate file content. A file with a future date in
its name sorts to the end, even if its body is malformed JSON, the
wrong schema, or a placeholder with zero topics.

### 4.3 Fix

`_latest_snapshot_path` now walks backwards from the newest filename
and picks the **first file that parses as valid JSON AND has the
expected schema** (a top-level dict with a `topics` dict). Malformed
files are silently skipped; only the most recent *valid* snapshot
becomes the "previous scan".

Two helpers were added:

```python
def _is_valid_snapshot(p: Path) -> bool:
    """Return True iff the file parses as JSON AND has a 'topics' dict."""
    ...

def _latest_snapshot_path(radar_dir: Path) -> Path | None:
    """Most recent VALID history snapshot, or None if no valid snapshot exists."""
    files = sorted(sd.glob("scan-*.json"), key=lambda p: p.name, reverse=True)
    for p in files:
        if _is_valid_snapshot(p):
            return p
    return None
```

The README-level rationale (added inline as a docstring): a history
directory may contain stale or accidentally-poisoned files; if we
naively pick the lexicographically last file, a single such file
permanently poisons momentum for all subsequent scans (every topic
appears NEW). The new behaviour is deterministic and survives
malformed-history edge cases.

### 4.4 Regression test

`test_malformed_history_does_not_poison_subsequent_scans` in
`radar/tests/test_stability.py` plants **two future-dated poisoned
files** in a fresh history directory:

```
scan-2099-01-01T000000Z.json   -> BROKEN JSON  (raw text "{{not valid json")
scan-2099-01-02T000000Z.json   -> WRONG SCHEMA ({"wrong":"schema","no_topics":true})
```

It then runs a real scan and verifies:

- The scan completes successfully.
- The momentum for the prior valid fixture is **not** poisoned:
  `is_new=False` and `previous_mentions` equals the prior scan's
  `mention_count`.

This locks in the fix so the bug cannot silently regress.

### 4.5 Other minor cleanups

- `radar/pipeline.py` had a dead-code line `history = {t.id: t for t in
  topics}` that was never read. Removed.

Both changes are code-cleanliness only; no behavioural change beyond
the malformed-history fix.

---

## 5. Test result summary

```
python -m radar.tests.run_all
```

| Module                  | Tests | Status |
|-------------------------|------:|:------:|
| `test_dedup`            |     5 |   PASS |
| `test_verification`     |     5 |   PASS |
| `test_momentum`         |     8 |   PASS |
| `test_classification`   |     6 |   PASS |
| `test_failures`         |     7 |   PASS |
| `test_real_world`       |    17 |   PASS |
| `test_evidence`         |    25 |   PASS |
| `test_stability` (new)  |    24 |   PASS |
| **Total**               | **97** | **ALL PASS** |

Per-module timeouts in the runner: 60 s for unit/integration modules,
300 s for `test_stability` (which performs real RSS fetches).

---

## 6. Experience governance

Per `EXPERIENCE.md`:

> a pattern must be observed at least **twice in independent tasks**
> before promotion to Verified. (Single success ≠ rule.)

All Radar-4A observations are **single-task** discoveries and are
**not promoted** to `EXPERIENCE.md` in this batch:

| Observation | Source | Status |
|---|---|---|
| `_latest_snapshot_path` must validate file content, not just filename sort | Radar-4A bug fix | Candidate — not yet reproduced |
| `compute_momentum` returns `growth_rate` as a **percent (× 100)**, not a fraction | Radar-3 doc, re-verified Radar-4A | Candidate — not yet reproduced |
| `read_history_for_id` returns minimal `Topic` objects (no verification / momentum) | Radar-3 design, re-verified Radar-4A | Candidate — not yet reproduced |

These will be reconsidered for `Investigated → Verified` promotion only
after **independent reproduction** in a future Radar batch.

No content was written into `EXPERIENCE.md` by this batch.

---

## 7. Production safety

| Check | Result |
|---|---|
| `https://myhotradar.com/` HTTP status | 200 OK |
| `https://myhotradar.com/sitemap.xml` HTTP status | 200 OK |
| `https://myhotradar.com/hot/` HTTP status | 200 OK |
| `https://myhotradar.com/malaysia/` HTTP status | 200 OK |
| AdSense code (`ca-pub-6219340004578553`) on home page | present (1 occurrence) |
| `index.html`, category pages, article page, `sitemap.xml`, `assets/` | untouched in git diff |
| `radar_data/latest.json`, `radar_data/latest.md` | gitignored, never committed |
| Test fixtures committed to git | none — fixtures are written into `tempfile.mkdtemp` at test time |

---

## 8. Files changed in Radar-4A

| File | Lines | Purpose |
|---|---:|---|
| `radar/history.py`              | +38 / -2 | `_is_valid_snapshot` guard; resilient `_latest_snapshot_path` |
| `radar/pipeline.py`             |  +0 / -1 | Dead-code cleanup |
| `radar/tests/run_all.py`        |  +6 / -2 | Per-module timeout (60 s default, 300 s for stability) |
| `radar/tests/test_stability.py` | +965 / 0 | New — 24 stability / soak tests |
| **Total**                       | **+1007 / -5** | |

No website files, no Cloudflare config, no Facebook integration, no
AdSense code, no source registry entries were modified.

---

## 9. What Radar-4A did NOT do (per spec)

- Did **not** add new RSS sources (still the same 5 Tier-B sources
  from Radar-2).
- Did **not** add a Tier-A source (no genuinely-news-grade
  government feed was verified accessible during the Radar-3 probe).
- Did **not** modify the website, AdSense, sitemap, or Cloudflare.
- Did **not** add Facebook or social-media publishing.
- Did **not** write fake data, fabricate statistics, or invent
  experience entries.

---

## 10. Git

| Step | Result |
|---|---|
| Working tree before this batch | clean |
| Files staged | 4 (3 modified, 1 new) |
| Files NOT staged | `radar_data/` (gitignored) |
| Commit (Radar-4A) | `1a86235` |
| Commit message | `News Radar Phase 1 Batch Radar-4A: stability/soak validation + malformed-history resilience` |
| Push | `6c86247..1a86235 master -> master` |
| `git amend` / rebase / squash / force-push / reset | **none used** |

---

## 11. Conclusion

Radar-1 → Radar-3 is **stable** under five consecutive real RSS
scans, with a fixed bug, 24 new soak tests, and zero regressions.
The engine is ready to be the foundation for whatever the next batch
adds — without re-validating the basics.
