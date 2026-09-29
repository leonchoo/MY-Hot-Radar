# MY Hot Radar — Phase 2 / Batch 2 — Scheduler + Persistent History

> Final documentation for the **Phase 2 / Batch 2** batch.
> Read alongside `NEWS_RADAR.md`, `PROJECT_CONTEXT.md`,
> `docs/RADAR_4A_STABILITY.md` (for `_is_valid_snapshot` rationale),
> `docs/RADAR_PHASE2_POLITICS.md` (Phase 2 B1), and
> `docs/RADAR_6_TIER_B_REVIEW.md`.

This document records how the existing Radar pipeline was extended
with a scheduler that runs scans on a fixed cadence, persists history
to disk, and selects the previous snapshot correctly for momentum
computation.

---

## 1. Objective

Make the News Radar executable on a fixed schedule, with reliable
history persistence, so consecutive scans can compute momentum from a
real previous snapshot.

The scheduler:

1. Acquires a single-instance file lock.
2. Invokes the existing `python -m radar.scan` entry point.
3. Records an execution log entry (separate from radar snapshots).
4. Releases the lock on success OR failure.
5. Honours retention policy (default 30 days).

The scheduler does NOT publish to the website, generate articles, or
post to social media. Real publishing is a separate batch.

---

## 2. Architecture

```
                 ┌──────────────────────────────────┐
                 │   OS scheduler (Win Task / cron) │
                 │   OR manual `python -m radar.   │
                 │   scheduler` (loop / once)      │
                 └─────────────┬────────────────────┘
                               │
                               ▼
                 ┌──────────────────────────────────┐
                 │   radar/scheduler.py             │
                 │                                  │
                 │   run_once()                     │
                 │     1. acquire .scan.lock        │
                 │     2. invoke run_scan()         │
                 │     3. classify SUCCESS/PARTIAL/ │
                 │        FAILED/SKIPPED_LOCKED    │
                 │     4. write execution_log.jsonl │
                 │     5. apply retention           │
                 │     6. release .scan.lock        │
                 └─────────────┬────────────────────┘
                               │ invokes
                               ▼
                 ┌──────────────────────────────────┐
                 │   radar/pipeline.run_scan()      │
                 │   (existing, UNCHANGED)          │
                 │                                  │
                 │   1. fetch sources               │
                 │   2. cluster -> Topics           │
                 │   3. read history_for_id()       │
                 │   4. attach momentum             │
                 │   5. attach verification         │
                 │   6. classify_all                │
                 │   7. write_report + save_scan    │
                 └─────────────┬────────────────────┘
                               │ writes
                               ▼
                 ┌──────────────────────────────────┐
                 │   radar/history.py               │
                 │                                  │
                 │   save_scan(): atomic temp+replace│
                 │   read_history_for_id(): newest  │
                 │      valid snapshot only        │
                 └─────────────┬────────────────────┘
                               │
                               ▼
                 radar_data/
                   ├── .scan.lock            (transient)
                   ├── execution_log.jsonl   (one line per run)
                   ├── latest.json / .md     (current scan)
                   └── history/
                       └── scan-<ISO>.json   (one per successful run)
```

The scheduler adds three new files at the runtime level:
- `radar/scheduler.py` — the orchestrator
- `radar/scheduler` CLI entry point (`python -m radar.scheduler`)
- `radar_data/execution_log.jsonl` — execution log
- `radar_data/.scan.lock` — transient lock file

It does NOT add any source, change the source registry, modify any
engine file, or change the website.

---

## 3. Scheduler

### CLI

```
python -m radar.scheduler                  # one-shot scan
python -m radar.scheduler --loop           # loop continuously
python -m radar.scheduler --loop --interval-seconds 1800
python -m radar.scheduler --inject-fixture # offline deterministic run
python -m radar.scheduler --retention-days 30
python -m radar.scheduler --radar-dir /path/to/radar_data
```

### Production deployment (per spec §4)

The project is currently on Windows. Recommended deployment:

- **Windows Task Scheduler** — create a scheduled task that runs
  `python -m radar.scheduler` every 30 minutes. The scheduler itself
  contains no Windows-specific code; it is portable.
- **Cron / systemd (future Linux)** — same CLI; same code.

`--loop` mode is provided for **manual validation only** per spec §21.
In production, the OS-level scheduler is preferred because it survives
process termination and is observable via standard OS tooling.

### Frequency

Default: every **30 minutes** (1800s). This satisfies:

- Not too frequent (avoid source load + duplicate requests).
- Not too rare (momentum needs sufficient time resolution).
- Easily configurable via `--interval-seconds`.

---

## 4. Execution Status (per spec §17)

Four mutually-exclusive statuses:

| Status | Meaning | When |
|---|---|---|
| `SUCCESS` | All sources succeeded; history written | All sources returned OK |
| `PARTIAL` | At least one source succeeded; history still meaningful | ≥ 1 source OK, ≥ 1 source failed |
| `FAILED` | Catastrophic failure; no useful scan | Pipeline raised OR zero sources succeeded |
| `SKIPPED_LOCKED` | Another scheduler is running | `.scan.lock` is held and not stale |

The status is recorded in `execution_log.jsonl` (one JSON line per
run) and is SEPARATE from the radar snapshot per spec §18.

---

## 5. Locking (per spec §16)

File-based single-instance lock at `<radar_dir>/.scan.lock`.

Lock file format (JSON):

```json
{
  "pid": 12345,
  "acquired_at": "2026-09-29T02:43:30Z"
}
```

Recovery rules:

- If lock exists and `pid` is alive (via `psutil` if available) AND
  `acquired_at` is within the last hour → lock is held; new scan is
  `SKIPPED_LOCKED`.
- If lock exists but `pid` is dead OR `acquired_at` is older than 1
  hour → lock is stale; the next scheduler run recovers automatically.
- On successful completion OR raised exception, the lock is released
  in a `finally` block. No deadlocks.

The lock is intentionally simple (no distributed lock, no Redis, no
Celery). It is sufficient for the "prevent two scheduler instances
from running simultaneously" requirement on a single host.

---

## 6. Snapshot Persistence (per spec §14)

`radar/history.py` writes each snapshot atomically:

```
1. write to <target>.json.tmp
2. flush + fsync (best-effort)
3. os.replace(tmp, target)  -- atomic on POSIX and Windows
```

If the process is killed mid-write:

- The target file is unchanged (the previous snapshot is intact).
- A stale `.tmp` may remain; it is harmless and will not be picked
  up by `_latest_snapshot_path` (which only matches `scan-*.json`).

Verified by `test_history_atomic_write_failure_preserves_previous`.

---

## 7. History (per spec §8)

Each scan produces one snapshot file at
`<radar_dir>/history/scan-<ISO>.json`. Schema (per Radar-4A):

```json
{
  "meta": {
    "started_at": "2026-09-29T02:43:30Z",
    "sources_attempted": 5,
    "stories_seen": 117,
    "topics_produced": 89
  },
  "topics": {
    "<content_key>": {
      "id": "...",
      "title": "...",
      "mention_count": 5,
      "status": "RISING",
      "first_seen": "...",
      "last_seen": "...",
      "canonical_url": "..."
    }
  }
}
```

The history is **append-only**. Snapshots are never mutated in place.
The most recent valid snapshot is the live "previous scan" for the
next run.

---

## 8. Previous Snapshot Selection (per spec §10)

Per Radar-4A's real bug fix and spec §10, `_latest_snapshot_path`:

1. Lists all `scan-*.json` files.
2. Sorts by filename (newest-first via reverse=True).
3. Walks newest → oldest.
4. Returns the FIRST file that passes `_is_valid_snapshot`.

`_is_valid_snapshot` checks:

- File parses as JSON.
- Top-level is a dict with a `topics` key.
- The `meta.started_at` is **not** in the future (with a 5-minute
  tolerance for clock drift).

If the newest file is malformed, future-dated, or wrong-schema, it is
skipped and the next-newest is tried. This is the same algorithm
that Radar-4A used to fix the original `_latest_snapshot_path`
malformed-pollution bug.

A malformed snapshot does NOT poison momentum.

---

## 9. Failure Safety (per spec §12-13)

### Catastrophic failure

If `run_scan()` raises an unexpected exception, the scheduler:

- Records status `FAILED`.
- Captures the error in the execution log.
- Releases the lock.
- Does NOT call `save_scan()` itself; the exception propagates inside
  `run_scan`, which means the snapshot may be partial or missing.

### Partial source failure

If some sources fail and others succeed:

- `run_scan()` completes normally.
- Source status is visible in the returned `summary["source_status"]`.
- The scheduler records status `PARTIAL`.
- History IS written (because at least one source succeeded and
  produced stories).

### Source-failure ≠ zero-count (per spec §13)

The pipeline already isolates per-source failures (Radar-2).
A failing source contributes `fetched=0` and `ok=False` to the
source_status record. It does NOT cause all sources to report zero
stories. The `<direct>` / fixture path is similarly isolated.

### "0 stories" failure mode

The existing pipeline does not currently guard against "all sources
fail simultaneously and a 0-story snapshot is written." This is a
documented limitation (see §17 Limitations). A future batch could add
a pre-write guard.

---

## 10. Retention (per spec §15)

Default: **30 days**. Implementation in `apply_retention()`:

- Lists all history files.
- Skips files newer than `max_age_days`.
- Always keeps at least 1 file (so the next scan has a previous
  snapshot to compare against).
- Returns the deletion count (for tests + observability).

Retention is deterministic, testable, and failure-safe:

- Same input → same output.
- A single failed `unlink()` does not abort the sweep.
- The next scheduler run is unaffected by partial retention failure.

---

## 11. Three-run Real Validation (per spec §21)

Today's validation (manual, on the production `radar_data/`):

```
Run 1: SUCCESS, 5/5 sources OK, 117 stories, 89 topics, scan_id 20260929T025900Z
Run 2: SUCCESS, 5/5 sources OK, 117 stories, 89 topics, scan_id 20260929T025904Z
Run 3: SUCCESS, 5/5 sources OK, 117 stories, 89 topics, scan_id 20260929T025909Z
```

- 3 new history files added in order T1 < T2 < T3 (by filename).
- 3 new entries in `execution_log.jsonl`.
- All scan_ids unique (includes PID suffix to disambiguate same-second
  runs).
- `read_history_for_id()` after run 3 returns the topics from run 2
  (verified by `test_real_three_consecutive_runs`).
- Lock file released after each run; no stale lock.

---

## 12. Tests

`radar/tests/test_scheduler.py` adds **21 tests**:

| Category | Count |
|---|---:|
| Scheduler (invoke, success, partial, lock, stale lock) | 5 |
| History (first scan, second scan, malformed, future, latest, duplicate, atomic, retention) | 9 |
| Failure safety (failed scan record, source failure ≠ zero) | 2 |
| Execution log (separation, fields) | 2 |
| Three-run real validation | 1 |
| Regression (entry point, imports) | 2 |
| **Total** | **21** |

All 21 tests pass.

### Regression

```
python -m radar.tests.run_all
```

| Module | Tests | Status |
|---|---:|---|
| `test_dedup` | 5 | PASS |
| `test_verification` | 5 | PASS |
| `test_momentum` | 8 | PASS |
| `test_classification` | 6 | PASS |
| `test_failures` | 7 | PASS |
| `test_real_world` (Radar-2) | 17 | PASS |
| `test_evidence` (Radar-3) | 25 | PASS |
| `test_stability` (Radar-4A) | 24 | PASS |
| `test_tier_a` (Radar-5A) | 17 | PASS |
| `test_source_scope` (Radar-5B) | 25 | PASS |
| `test_tier_b_review` (Radar-6) | 22 | PASS |
| `test_politics` (Phase 2 B1) | 31 | PASS |
| **`test_scheduler` (Phase 2 B2, new)** | **21** | **PASS** |
| **Total** | **213** | **ALL PASS** |

Zero regressions in any earlier batch.

---

## 13. Production Safety

| Check | Result |
|---|---|
| `https://myhotradar.com/` | HTTP 200 ✅ |
| All 11 sub-paths (`/sitemap.xml`, `/hot/`, `/malaysia/`, `/viral/`, `/celebrity/`, `/food/`, `/world/`, `/about/`, `/contact/`, `/privacy/`, `/terms/`) | HTTP 200 ✅ |
| AdSense (`ca-pub-6219340004578553`) | present, 1 occurrence ✅ |
| Cloudflare | untouched ✅ |
| Facebook Page | untouched ✅ |
| `index.html` / category pages / `assets/` | untouched ✅ |
| `python -m radar.scan` (existing entry point) | still works ✅ |
| `python -m radar.scheduler` (new entry point) | works ✅ |
| `radar_data/` | gitignored ✅ |
| Real radar data on production site | not replaced (DEMO articles still in place) ✅ |

---

## 14. Experience Governance

Per spec §24:

> Default: NO NEW EXPERIENCE. Politics rules especially must not be
> promoted to VERIFIED Experience based on a single batch.

Observations from Phase 2 Batch 2:

| Observation | Status |
|---|---|
| Single-instance file lock prevents duplicate scheduler runs | **Candidate** — needs second-batch confirmation |
| Atomic write (temp + os.replace) preserves previous snapshot on failure | **Candidate** — design-time; needs real-world stress test |
| Future-dated snapshot guard prevents momentum poisoning | **Already documented** in Radar-4A; not new |
| 30-day retention is sufficient for momentum calculation | **Design choice** — not promoted |
| Scheduler frequency (30 min default) is appropriate | **Design choice** — not promoted |
| Lock TTL (1 hour) is sufficient to detect stale locks | **Design choice** — not promoted |

`EXPERIENCE.md` is **unchanged** by Phase 2 Batch 2.

---

## 15. Files Changed

| File | Status | Lines |
|---|---|---:|
| `radar/scheduler.py` | **new** | +470 |
| `radar/tests/test_scheduler.py` | **new** | +450 |
| `radar/history.py` | modified (atomic write + future-date guard) | +50 / -5 |
| `radar/tests/run_all.py` | modified | +1 |
| `docs/RADAR_PHASE2_SCHEDULER.md` | **new** | (this file) |
| `radar/pipeline.py`, `radar/scan.py` | **untouched** | — |
| `radar/verification.py`, `momentum.py`, `classification.py`, `counter_signals.py`, `dedup.py` | **untouched** | — |
| `radar/tier_a_qualification.py`, `source_scope.py`, `tier_b_review.py` | **untouched** | — |
| `radar/politics.py`, `radar/sources_registry.py`, `radar/models.py` | **untouched** | — |
| Website, sitemap, AdSense, Cloudflare, Facebook | **untouched** | — |
| `EXPERIENCE.md` | **untouched** | — |
| **Total** | | **+971 / -5** |

---

## 16. Git

| Step | Result |
|---|---|
| Working tree before | clean |
| Files staged | 5 (2 new, 2 modified, 1 new doc) |
| Files NOT staged | `radar_data/` (gitignored) |
| Commit (Phase 2 B2) | (recorded in batch report) |
| Push | (recorded in batch report) |
| `git amend` / rebase / squash / force-push / reset | **none used** |

---

## 17. Limitations

1. **"0 stories" snapshot is not blocked.** If every source fails
   simultaneously, the existing pipeline still writes a snapshot
   with 0 stories. This snapshot, being the newest valid, would
   incorrectly make every existing topic appear "disappeared" in
   the next scan's momentum calculation. A future batch could add
   a pre-write guard in the scheduler: if `successful_sources == 0`
   AND `successful_sources < source_count`, do NOT call `save_scan`.
   (This was deliberately NOT done in this batch because it would
   touch the existing pipeline rather than just add a wrapper.)

2. **Single-host lock only.** The `.scan.lock` is per-host. Two
   hosts running the scheduler against the same shared `radar_data/`
   would both succeed (each on its own host). This is acceptable
   for the current single-host deployment.

3. **No clock-skew tolerance beyond 5 minutes.** If a host's clock
   drifts significantly, the future-date guard may reject legitimate
   snapshots. The 5-minute tolerance is a pragmatic default. Long-term
   fixes should use NTP-synced clocks.

4. **`--loop` mode is for manual validation only.** In production, the
   OS-level scheduler is preferred. The `--loop` mode does not
   survive process termination, daemonization, or system reboot.

5. **Retention is purely age-based.** If a future batch wants
   "keep the last 100 snapshots regardless of age", the retention
   policy would need to be extended. Not needed today.

6. **No execution-log rotation.** The execution_log.jsonl grows
   indefinitely. In practice the line count is small (one line per
   run), but a long-running production deployment would want
   rotation. Not needed today.

7. **Lock TTL of 1 hour is a guess.** A real-world deployment may
   surface edge cases where a scan legitimately takes more than 1
   hour. The TTL should be revisited if so. Not encountered yet.

---

## 18. Future Publishing Separation (per spec §19)

This batch is **run-and-save** only. The following are out of scope
and reserved for a future "Real Radar Publishing" batch:

- Replacing DEMO articles on `myhotradar.com` with real radar output.
- Generating new articles per topic.
- Posting to Facebook Page / TikTok / X.
- Auto-publishing any kind of branded content.

The scheduler writes only to `radar_data/`. The website source
(`index.html`, category pages, article page, sitemap, assets/) was
NOT modified by this batch.

---

## 19. Conclusion

Phase 2 Batch 2 adds a scheduler + persistent history on top of the
existing Radar pipeline.

The system now:

- Runs scans on a fixed cadence (default 30 min) via OS-level
  scheduler + `python -m radar.scheduler`.
- Persists each snapshot atomically (temp + os.replace) so failures
  don't corrupt history.
- Reads the most recent VALID previous snapshot for momentum
  computation, with explicit guards against malformed, wrong-schema,
  and future-dated snapshots.
- Records an execution log separate from the radar snapshot for
  observability.
- Prevents duplicate scheduler runs with a single-instance file lock
  that auto-recovers from stale state.
- Honours a 30-day retention policy while keeping at least one
  snapshot for momentum continuity.
- Adds 21 tests (locking, history, atomic writes, retention, three-
  run real validation, regression) with zero regressions in the
  192 earlier tests.

Total project state: **213 tests PASS, 0 failures, 0 regressions**.
