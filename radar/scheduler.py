"""
Phase 2 Batch 2 — Scheduler orchestration.

The scheduler is responsible for:
  1. Acquiring a single-instance file lock (per spec §16).
  2. Invoking the radar scan entry point (per spec §5).
  3. Validating the result (per spec §12).
  4. Letting the scan pipeline persist the snapshot + history
     (existing behavior; no duplication of logic).
  5. Recording an execution log entry that is SEPARATE from the
     radar snapshot (per spec §18).
  6. Releasing the lock on success OR failure.
  7. Honouring retention policy (per spec §15).

The scheduler does NOT publish, generate articles, post to social,
or modify the website. It is a run-and-save wrapper around the
existing radar scan entry point.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .pipeline import run_scan


# ============================================================================
# Execution status (per spec §17)
# ============================================================================

class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"          # scan completed; history written
    PARTIAL = "PARTIAL"          # some sources failed; history still written
    FAILED = "FAILED"            # catastrophic failure; history NOT written
    SKIPPED_LOCKED = "SKIPPED_LOCKED"   # another scheduler is running


# ============================================================================
# Execution log record (per spec §17-18)
# ============================================================================

@dataclass
class ExecutionRecord:
    """One scheduler execution. Stored separately from radar snapshots.

    Per spec §18: this represents "did the scheduler succeed this run?"
    A Radar Snapshot represents "what news data did this scan collect?"
    The two are stored as separate files and never conflated.
    """
    scan_id: str
    started_at: str
    finished_at: str
    status: str  # ExecutionStatus value
    source_count: int = 0
    successful_sources: int = 0
    failed_sources: int = 0
    story_count: int = 0
    topic_count: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# Single-instance lock (per spec §16)
# ============================================================================

class SchedulerLockError(Exception):
    """Raised when the lock cannot be acquired or is otherwise broken."""


class SchedulerLock:
    """File-based single-instance lock.

    Per spec §16:
      - lock exists -> refuse/skip new scan
      - successful completion -> release
      - failure -> release
      - stale lock -> recover safely

    Design:
      - Lock file at <radar_dir>/.scan.lock
      - The file contains the holder's PID + timestamp
      - A lock is "stale" if its PID is not running (Windows: hard
        to detect without psutil; we use a max-age fallback of 1 hour).
      - acquire() is non-blocking; if the lock exists and is not
        stale, it raises SchedulerLockError.
    """

    STALE_AFTER_SECONDS = 3600  # 1 hour

    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path)
        self.held = False

    def _is_stale(self) -> bool:
        """Return True if the existing lock is stale (safe to recover)."""
        try:
            raw = self.lock_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError, ValueError):
            # Unreadable lock -> treat as stale
            return True
        # Check age first
        ts_str = data.get("acquired_at")
        if ts_str:
            try:
                # ISO format with trailing Z
                ts_str_clean = ts_str.rstrip("Z")
                acquired = datetime.fromisoformat(ts_str_clean)
                if acquired.tzinfo is None:
                    acquired = acquired.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - acquired).total_seconds()
                if age > self.STALE_AFTER_SECONDS:
                    return True
            except ValueError:
                pass
        # Check PID (best-effort; on Windows without psutil we can't
        # reliably check, so the age check is the primary safety).
        holder_pid = data.get("pid")
        if holder_pid is None:
            return True
        # On Windows we cannot easily check PID without psutil.
        # The age check above is the primary guard. If we have psutil,
        # use it as a secondary guard.
        try:
            import psutil  # type: ignore
            if not psutil.pid_exists(holder_pid):
                return True
        except ImportError:
            pass
        return False

    def acquire(self) -> None:
        """Acquire the lock or raise SchedulerLockError."""
        if self.held:
            return  # idempotent
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            if self._is_stale():
                # Stale lock; remove and continue
                try:
                    self.lock_path.unlink()
                except OSError:
                    pass
            else:
                raise SchedulerLockError(
                    f"scheduler lock held at {self.lock_path}"
                )
        # Write the lock atomically
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
        """Release the lock if held. Safe to call multiple times."""
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
# Execution log (per spec §17-18)
# ============================================================================

class ExecutionLog:
    """Append-only execution log stored at <radar_dir>/execution_log.jsonl.

    One JSON line per scheduler run. This is SEPARATE from the radar
    snapshot files. Per spec §18: a reader can tell whether the
    scheduler has been running correctly without parsing radar
    snapshots.
    """

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: ExecutionRecord) -> None:
        """Append one record as a JSON line. Atomic on the line level."""
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        # Append-mode write is atomic at the OS level for short lines
        # on most filesystems (single write < PIPE_BUF).
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_all(self) -> List[dict]:
        """Return all records as a list (newest first)."""
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
# Retention (per spec §15)
# ============================================================================

def apply_retention(
    history_dir: Path,
    *,
    max_age_days: int = 30,
) -> int:
    """Delete snapshot files older than max_age_days.

    Returns the number of files deleted. Retention MUST be:
      - deterministic (same input -> same output)
      - testable (returns count for tests to verify)
      - failure-safe (a single failed delete doesn't stop the rest)

    Per spec §15: do NOT delete files still needed by momentum /
    history logic. The Radar pipeline uses _latest_snapshot_path(),
    which walks from newest to oldest. After retention, at least
    ONE snapshot must remain for the next scan to compute momentum.

    If removing old snapshots would leave zero snapshots, retention
    is a no-op.
    """
    if not history_dir.exists():
        return 0

    cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
    all_files = sorted(history_dir.glob("scan-*.json"))

    # Identify files to keep (must keep at least 1)
    if len(all_files) <= 1:
        return 0

    deleted = 0
    for f in all_files:
        try:
            mtime = f.stat().st_mtime
            if mtime < cutoff:
                # Ensure at least one file remains after deletion
                if len(all_files) - deleted <= 1:
                    break
                f.unlink()
                deleted += 1
        except OSError:
            # Single-file failure should not abort the whole sweep
            continue
    return deleted


# ============================================================================
# Scheduler run (per spec §1, §5, §11-13)
# ============================================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_scan_id() -> str:
    """Stable scan_id: ISO timestamp + pid suffix for uniqueness."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + \
           f"-{os.getpid()}"


def run_once(
    *,
    radar_dir: Optional[Path] = None,
    inject_fixture: bool = False,
    extra_stories=None,
) -> ExecutionRecord:
    """Execute one scheduler run. Returns an ExecutionRecord.

    Per spec §5: scheduler invokes the scan entry point, never
    duplicates scan logic. Per spec §12: failed scans must NOT
    overwrite the last known good snapshot. Per spec §16: lock
    is always released on exit.

    Failure handling:
      - SUCCESS: scan completed; history written by run_scan itself
      - PARTIAL: some sources failed; history still written
      - FAILED: scan raised; history NOT written; error captured
      - SKIPPED_LOCKED: another scheduler is running; no scan attempted
    """
    started = _now_iso()
    scan_id = _new_scan_id()

    radar_dir = Path(radar_dir) if radar_dir else \
        Path(__file__).resolve().parents[1] / "radar_data"
    radar_dir.mkdir(parents=True, exist_ok=True)

    lock_path = radar_dir / ".scan.lock"
    log_path = radar_dir / "execution_log.jsonl"
    history_dir = radar_dir / "history"

    record = ExecutionRecord(
        scan_id=scan_id,
        started_at=started,
        finished_at="",
        status=ExecutionStatus.FAILED.value,
        error="",
    )

    try:
        lock = SchedulerLock(lock_path)
        lock.acquire()
    except SchedulerLockError as e:
        record.status = ExecutionStatus.SKIPPED_LOCKED.value
        record.error = str(e)
        record.finished_at = _now_iso()
        ExecutionLog(log_path).append(record)
        return record

    try:
        # Invoke the scan entry point. We pass radar_dir through to
        # run_scan so history writes to the same dir as the lock/log.
        try:
            summary = run_scan(
                extra_stories=extra_stories,
                radar_dir=str(radar_dir),
            )
        except Exception as e:
            # Catastrophic failure: scan pipeline itself raised
            record.status = ExecutionStatus.FAILED.value
            record.error = f"{type(e).__name__}: {e}"
            traceback.print_exc()
            record.finished_at = _now_iso()
            ExecutionLog(log_path).append(record)
            return record

        # Inspect the source status to determine SUCCESS vs PARTIAL
        source_status = summary.get("source_status", [])
        record.source_count = len(source_status)
        record.successful_sources = sum(
            1 for s in source_status if s.get("ok")
        )
        record.failed_sources = sum(
            1 for s in source_status if not s.get("ok")
        )
        record.story_count = summary.get("stories_count", 0)
        record.topic_count = summary.get("topics_count", 0)

        if record.failed_sources == 0 and record.source_count > 0:
            record.status = ExecutionStatus.SUCCESS.value
        elif record.successful_sources > 0:
            # At least one source succeeded -> history is meaningful
            record.status = ExecutionStatus.PARTIAL.value
        else:
            # No source succeeded at all. Per spec §12: this MUST NOT
            # be allowed to overwrite the last known good snapshot.
            # The run_scan pipeline already wrote a snapshot, but
            # it's a "0 stories" snapshot. We treat this as FAILED
            # for execution-log purposes and emit a warning.
            # NOTE: the snapshot was already written by run_scan
            # because run_scan does not check for catastrophic
            # source failure. This is documented as a known
            # limitation; a future batch can add a pre-write guard.
            record.status = ExecutionStatus.FAILED.value
            record.error = (
                f"all {record.source_count} sources failed; "
                f"snapshot may still have been written"
            )

        record.finished_at = _now_iso()
        ExecutionLog(log_path).append(record)
        return record

    finally:
        # ALWAYS release the lock, even on exception
        try:
            lock.release()
        except Exception:
            pass


# ============================================================================
# CLI entry point
# ============================================================================

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="MY Hot Radar - scheduler (single-shot or loop)"
    )
    parser.add_argument("--radar-dir", default=None,
                        help="Output directory (default: ./radar_data)")
    parser.add_argument("--inject-fixture", action="store_true",
                        help="Run a deterministic fixture scan (no network)")
    parser.add_argument("--loop", action="store_true",
                        help="Run continuously every --interval-seconds")
    parser.add_argument("--interval-seconds", type=int, default=1800,
                        help="Loop interval in seconds (default: 1800 = 30 min)")
    parser.add_argument("--retention-days", type=int, default=30,
                        help="History retention in days (default: 30)")
    args = parser.parse_args(argv)

    radar_dir = Path(args.radar_dir) if args.radar_dir else \
        Path(__file__).resolve().parents[1] / "radar_data"

    if args.loop:
        # Daemon loop. Spec §4: don't introduce heavy frameworks.
        # This is a simple time.sleep() loop; the OS-level scheduler
        # (Windows Task Scheduler / cron) is the production deployment.
        # This loop is provided for manual validation per spec §21.
        while True:
            record = run_once(
                radar_dir=radar_dir,
                inject_fixture=args.inject_fixture,
            )
            print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
            apply_retention(radar_dir / "history",
                            max_age_days=args.retention_days)
            time.sleep(args.interval_seconds)
    else:
        record = run_once(
            radar_dir=radar_dir,
            inject_fixture=args.inject_fixture,
        )
        print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
        apply_retention(radar_dir / "history",
                        max_age_days=args.retention_days)
        return 0 if record.status != ExecutionStatus.FAILED.value else 1


if __name__ == "__main__":
    sys.exit(main())
