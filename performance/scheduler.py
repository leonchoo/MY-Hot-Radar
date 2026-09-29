"""
P3-B-4 Performance Scheduler foundation.

Goal: provide a minimal, reliable repeated-snapshot / time-series
foundation for the Performance Intelligence layer.

This module is INTENTIONALLY light. It does not:
  * Modify Radar / Candidate / Website / Android Collector.
  * Auto-run via cron / Task Scheduler / watchdog.
  * Connect to Facebook / Instagram / YouTube.
  * Perform ranking / prediction / publishing.

Architecture (modeled after radar/scheduler.py — independent copy,
NOT a shared module, to keep Radar untouched):

  SchedulerLock
      file-based single-instance lock
      stale-lock recovery via max-age fallback
      atomic acquire (tmp + os.replace)
      released on success AND failure

  ExecutionStatus (enum)
      SUCCESS     — fetch + persist completed
      PARTIAL     — fetch had issues but at least one snapshot saved
      FAILED      — catastrophic failure; no history written
      SKIPPED_LOCKED — another run is in progress

  ExecutionRecord (dataclass)
      one row in execution_log.jsonl per scheduler run
      separate from snapshot files (per spec §18)

  ExecutionLog
      append-only JSONL at <performance_data>/execution_log.jsonl
      recoverable: read_all() returns all rows

  PerformanceScheduler
      the runnable construction combining the above
      run_once(adapter, store, *, captured_at=None, clock=None) -> ExecutionRecord
      acquire lock, fetch adapter, project to PerformanceSnapshot,
      persist snapshots, log execution, release lock on success/failure

  History guarantees:
      * Snapshots keyed by (captured_at, content_id) -> never overwrite
      * Two runs at distinct captured_at -> distinct snapshot files
      * Observations keyed by (content_id, from, to, observation_id)
      * All performance_data/ writes go through PerformanceStore
        (atomic write, synthetic gate preserved)

Repeated-snapshot semantics:

  Same URL across runs:
      content_id stable (URL-anchored deterministic hash).
  Distinct captured_at:
      different snapshot files (history preserved).
  observation_id:
      deterministic over (content_id, from_captured_at, to_captured_at).
      Same triple -> same id (idempotent re-write).
      Different triple -> different id (history preserved).

BERNAMA repeated snapshots will produce:
  * same content_id
  * distinct snapshot files (one per captured_at)
  * observations with views_delta=None, likes_delta=None, etc.
  * classification = INSUFFICIENT_DATA (None metrics)
  * velocity fields all None

This is the documented normal result for BERNAMA; not an error.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from .models import PerformanceSnapshot
from .store import (
    DEFAULT_PERFORMANCE_DATA_DIR,
    PerformanceStore,
    SyntheticFixtureError,
)


# ============================================================================
# Execution status
# ============================================================================

class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED_LOCKED = "SKIPPED_LOCKED"


# ============================================================================
# Execution record
# ============================================================================

@dataclass
class ExecutionRecord:
    """One scheduler execution.

    Stored SEPARATELY from snapshots. A reader can tell whether the
    scheduler has been running correctly without parsing snapshots.
    """
    run_id: str
    started_at: str
    finished_at: str
    status: str  # ExecutionStatus value
    source_name: str = ""
    observation_count: int = 0
    snapshot_count: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# Single-instance lock
# ============================================================================

class SchedulerLockError(Exception):
    """Raised when the lock cannot be acquired or is otherwise broken."""


class SchedulerLock:
    """File-based single-instance lock.

    Design:
      - Lock file at <data_dir>/.scan.lock
      - The file contains the holder's PID + acquired_at timestamp
      - A lock is "stale" if its acquired_at is older than
        STALE_AFTER_SECONDS.
      - acquire() is non-blocking; if the lock exists and is not
        stale, it raises SchedulerLockError.
      - atomic acquire: tmp + os.replace.

    Failure modes:
      - Acquire raises SchedulerLockError -> caller should skip
        and log SKIPPED_LOCKED.
      - Acquire succeeds but downstream raises -> release() must
        still be called. Use as context manager (with statement).
    """
    STALE_AFTER_SECONDS = 3600  # 1 hour

    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path)
        self.held = False

    def _is_stale(self) -> bool:
        try:
            raw = self.lock_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError, ValueError):
            return True  # unreadable -> stale
        ts_str = data.get("acquired_at")
        if ts_str:
            try:
                ts_str_clean = ts_str.rstrip("Z")
                acquired = datetime.fromisoformat(ts_str_clean)
                if acquired.tzinfo is None:
                    acquired = acquired.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - acquired).total_seconds()
                if age > self.STALE_AFTER_SECONDS:
                    return True
            except ValueError:
                pass
        holder_pid = data.get("pid")
        if holder_pid is None:
            return True
        try:
            import psutil  # type: ignore
            if not psutil.pid_exists(holder_pid):
                return True
        except ImportError:
            pass
        return False

    def acquire(self) -> None:
        if self.held:
            return
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            if self._is_stale():
                try:
                    self.lock_path.unlink()
                except OSError:
                    pass
            else:
                raise SchedulerLockError(
                    f"performance scheduler lock held at {self.lock_path}"
                )
        lock_payload = {
            "pid": os.getpid(),
            "acquired_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }
        tmp = self.lock_path.with_suffix(".lock.tmp")
        tmp.write_text(json.dumps(lock_payload), encoding="utf-8")
        os.replace(tmp, self.lock_path)
        self.held = True

    def release(self) -> None:
        if not self.held:
            return
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except OSError:
            pass
        self.held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


# ============================================================================
# Execution log (append-only JSONL)
# ============================================================================

class ExecutionLog:
    """Append-only execution log stored at <data_dir>/execution_log.jsonl.

    One JSON line per scheduler run. SEPARATE from snapshots. A
    reader can tell whether the scheduler has been running
    correctly without parsing snapshot files.
    """

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: ExecutionRecord) -> None:
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_all(self) -> List[dict]:
        if not self.log_path.exists():
            return []
        out = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        out.reverse()  # newest first
        return out


# ============================================================================
# Time helpers
# ============================================================================

def _now_iso(clock: Optional[Callable[[], datetime]] = None) -> str:
    """Return current UTC ISO-8601 timestamp at second precision."""
    if clock is None:
        clock = lambda: datetime.now(timezone.utc)
    return clock().strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_run_id(
    clock: Optional[Callable[[], datetime]] = None,
    captured_at: Optional[str] = None,
) -> str:
    """Stable run id: ISO timestamp + pid suffix.

    When ``captured_at`` is provided (deterministic test path),
    the run id is derived from it to make tests reproducible.
    Otherwise the wall-clock second-precision timestamp is used.
    """
    if captured_at is not None:
        ts_part = captured_at.replace(":", "").replace("-", "")
    else:
        ts_part = _now_iso(clock).replace(":", "").replace("-", "")
    return ts_part + f"-{os.getpid()}"


# ============================================================================
# Scheduler run
# ============================================================================

def run_once(
    *,
    adapter,  # PublicPerformanceAdapter — duck-typed
    store: Optional[PerformanceStore] = None,
    captured_at: Optional[str] = None,
    clock: Optional[Callable[[], datetime]] = None,
    data_dir: Optional[Path] = None,
) -> ExecutionRecord:
    """Execute one scheduler run.

    The scheduler does NOT publish, generate articles, post to
    social, or modify the website. It is a run-and-save wrapper
    around the adapter framework.

    Args:
      adapter: any PublicPerformanceAdapter (typically BernamaRssAdapter).
      store:   PerformanceStore instance. If None, a new one is built
               using data_dir (or the default performance_data dir).
      captured_at: ISO-8601 timestamp to stamp onto every snapshot.
                    If None, the wall-clock second-precision timestamp
                    at run time is used.
      clock:   Optional clock callable for deterministic tests.
      data_dir: Storage directory; defaults to DEFAULT_PERFORMANCE_DATA_DIR.

    Returns:
      ExecutionRecord describing what happened.

    Failure handling:
      - SUCCESS:    snapshots persisted for every observation
      - PARTIAL:    some observations persisted; some failed
      - FAILED:     catastrophic; no snapshots persisted
      - SKIPPED_LOCKED: another run is in progress

    Synthetic safety:
      - SyntheticAdapter rows would carry extra['_synthetic']=True;
        those rows are FILTERED OUT before persistence. The store's
        defence-in-depth _validate_payload() gate also fires on
        _synthetic=True payloads, but the upstream filter keeps the
        execution clean.
    """
    started = _now_iso(clock)
    run_id = _new_run_id(clock, captured_at=captured_at)

    if store is None:
        if data_dir is None:
            data_dir = DEFAULT_PERFORMANCE_DATA_DIR
        store = PerformanceStore(data_dir=data_dir)
    data_dir = Path(store.data_dir)

    lock_path = data_dir / ".scan.lock"
    log_path = data_dir / "execution_log.jsonl"

    record = ExecutionRecord(
        run_id=run_id,
        started_at=started,
        finished_at="",
        status=ExecutionStatus.FAILED.value,
        source_name="",
        error="",
    )

    lock = SchedulerLock(lock_path)
    try:
        lock.acquire()
    except SchedulerLockError as e:
        record.status = ExecutionStatus.SKIPPED_LOCKED.value
        record.error = str(e)
        record.finished_at = _now_iso(clock)
        ExecutionLog(log_path).append(record)
        return record

    try:
        # Fetch
        try:
            result = adapter.fetch()
        except Exception as e:
            record.status = ExecutionStatus.FAILED.value
            record.error = f"fetch failed: {type(e).__name__}: {e}"
            traceback.print_exc()
            record.finished_at = _now_iso(clock)
            ExecutionLog(log_path).append(record)
            return record

        record.source_name = getattr(result, "source_name", "unknown")

        # Determine captured_at once for the whole run, so all
        # observations in this run share a single timestamp.
        run_captured_at = captured_at or _now_iso(clock)

        # Filter out synthetic rows (defence in depth; store gate
        # also enforces, but we never feed synthetic into
        # production data in the first place).
        observations = []
        synthetic_filtered = 0
        for o in result.observations:
            if o.extra.get("_synthetic"):
                synthetic_filtered += 1
                continue
            observations.append(o)

        # Project AdapterObservation -> PerformanceSnapshot
        snap_count = 0
        obs_count = 0
        errors: List[str] = []
        for o in observations:
            try:
                snap = PerformanceSnapshot(
                    content_id=o.content_id,
                    captured_at=run_captured_at,
                    views=o.views,
                    likes=o.likes,
                    comments=o.comments,
                    shares=o.shares,
                    reposts=o.reposts,
                )
                # store gate (synthetic check + atomic write)
                store.put_snapshot(snap)
                snap_count += 1
                obs_count += 1
            except SyntheticFixtureError as e:
                # store gate fired; this row would be unsafe
                errors.append(f"synthetic:{o.content_id}: {e}")
            except Exception as e:
                errors.append(f"snapshot:{o.content_id}: "
                              f"{type(e).__name__}: {e}")

        record.observation_count = obs_count
        record.snapshot_count = snap_count

        if errors and snap_count > 0:
            record.status = ExecutionStatus.PARTIAL.value
            record.error = "; ".join(errors[:3])
        elif errors:
            record.status = ExecutionStatus.FAILED.value
            record.error = "; ".join(errors[:3])
        else:
            record.status = ExecutionStatus.SUCCESS.value

        record.finished_at = _now_iso(clock)
        ExecutionLog(log_path).append(record)
        return record
    finally:
        # Lock always released, success or failure. The lock
        # instance was created above and is reused here so its
        # ``held`` flag is set correctly.
        try:
            lock.release()
        except Exception:
            pass


# ============================================================================
# Public exports
# ============================================================================

__all__ = [
    "ExecutionStatus",
    "ExecutionRecord",
    "ExecutionLog",
    "SchedulerLock",
    "SchedulerLockError",
    "run_once",
    "_now_iso",
    "_new_run_id",
]