#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance Runtime Adapter.

Phase 6 MHR Newsroom Runtime.

Wraps the REAL Performance production scheduler:
    performance.scheduler.run_once(adapter, ...)

The scheduler produces snapshots/observations internally; we extract
those and write Forum v2 PERFORMANCE_REPORT / VELOCITY_UPDATE /
ENGAGEMENT_UPDATE / SUSTAINED_SIGNAL / COOLING_SIGNAL events.

Important constraints (per Phase 6 spec):
  * DO NOT modify performance/analysis.py, scheduler.py
  * We ONLY CALL run_once() and READ its return value
  * We DO NOT generate synthetic signals — we mirror only real ones
  * Forum write failures DO NOT raise into the performance run
  * Performance emits NO publish/close/editorial decisions — permission
    boundary enforced by forum_v2 ALLOWED_EVENT_TYPES (validated server-side)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import forum_v2  # noqa: E402
import forum_integration  # noqa: E402
import runtime_state  # noqa: E402
from runtime_adapters import AdapterResult, utc_now_iso  # noqa: E402


def _try_load_adapter():
    """Try to instantiate a BernamaRssAdapter for the performance scheduler.

    Returns (adapter, error_message). error_message is non-empty if loading
    or instantiation failed.
    """
    try:
        sys.path.insert(0, str(HERE.parent))
        from performance.adapters import BernamaRssAdapter
        return BernamaRssAdapter(), ""
    except Exception as e:
        return None, f"{type(e).__name__}:{e}"


def run_performance_runtime(
    *,
    data_dir: Optional[Path] = None,
    forum_paths: Optional[forum_v2.ForumV2Paths] = None,
    run_id: Optional[str] = None,
    skip_if_no_network: bool = True,
) -> AdapterResult:
    """Run the Performance adapter.

    1. Loads BernamaRssAdapter (REAL production adapter).
    2. Calls performance.scheduler.run_once(adapter, ...).
    3. Reads snapshots from performance_data/snapshots/.
    4. Writes Forum v2 PERFORMANCE_REPORT for each snapshot, plus
       SUSTAINED_SIGNAL / COOLING_SIGNAL based on real signal strength.

    Forum failures never raise. Adapter instantiation/network failures
    report SKIPPED, never FAILED the Agent (per spec point 二).
    """
    started = utc_now_iso()
    run_id = run_id or runtime_state.make_run_id(runtime_state.AGENT_PERFORMANCE)
    paths = forum_paths or forum_v2.ForumV2Paths()

    result = AdapterResult(
        agent=runtime_state.AGENT_PERFORMANCE,
        run_id=run_id,
        started_at=started,
        finished_at=started,
        status=runtime_state.OK,
    )

    # Load Performance runtime
    try:
        import performance.scheduler as ps
    except ImportError as e:
        result.status = runtime_state.SKIPPED
        result.agent_error = f"performance_unavailable:{e}"
        result.notes.append("performance_import_failed")
        result.finished_at = utc_now_iso()
        return result

    # Instantiate adapter (BernamaRssAdapter requires network)
    adapter, adapter_err = _try_load_adapter()
    if adapter is None:
        if skip_if_no_network:
            result.status = runtime_state.SKIPPED
            result.agent_error = adapter_err
            result.notes.append("adapter_unavailable_skipping")
            result.finished_at = utc_now_iso()
            return result
        result.agent_error = adapter_err

    # Run scheduler
    try:
        kwargs = {"adapter": adapter}
        if data_dir is not None:
            kwargs["data_dir"] = data_dir
        exec_record = ps.run_once(**kwargs)
    except Exception as e:
        result.status = runtime_state.FAILED
        result.agent_error = f"{type(e).__name__}:{e}"
        result.finished_at = utc_now_iso()
        return result

    # Result of scheduler
    exec_status = getattr(exec_record, "status", None)
    status_str = exec_status.value if hasattr(exec_status, "value") else exec_status
    status_str = status_str or "UNKNOWN"
    result.notes.append(f"performance_status:{status_str}")
    result.notes.append(f"performance_run_id:{exec_record.run_id}")
    result.notes.append(f"performance_source:{exec_record.source_name}")
    result.notes.append(f"performance_observations:{exec_record.observation_count}")

    if status_str == "SKIPPED_LOCKED":
        result.status = runtime_state.SKIPPED
        result.finished_at = utc_now_iso()
        return result
    if status_str == "FAILED" and exec_record.observation_count == 0:
        # Catastrophic and nothing captured
        result.status = runtime_state.FAILED
        result.agent_error = exec_record.error or "performance_failed"
        result.finished_at = utc_now_iso()
        return result

    # Read the snapshots that the scheduler just persisted
    if data_dir is None:
        data_dir = Path("C:/MY-Hot-Radar/performance_data")
    snapshots_dir = data_dir / "snapshots"
    snapshots = []
    if snapshots_dir.exists():
        # Most recent snapshot files
        all_files = sorted(snapshots_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        # Take the ones from this run (within last 60 seconds of started_at)
        from datetime import datetime, timezone
        started_dt = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        for f in all_files[:50]:
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                if (started_dt - mtime).total_seconds() <= 60:
                    snapshots.append(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError, ValueError):
                continue

    if not snapshots:
        result.notes.append("no_snapshots")
        result.finished_at = utc_now_iso()
        return result

    # For each snapshot, find or create a Forum Topic and write PERFORMANCE_REPORT
    written_topics = 0
    for snap in snapshots:
        # Snapshot schema includes: source_name, observation_count, snapshot_count,
        # captured_at, velocity, engagement, window, velocity_delta etc.
        # We look up Forum Topic by linkage_key from the snapshot's primary_topic_id
        radar_topic_id = snap.get("radar_topic_id") or ""
        title = snap.get("title") or ""
        if not radar_topic_id and not title:
            continue

        # Try to find Forum Topic by radar_topic_id linkage
        forum_topic = None
        if title:
            linkage = forum_v2.normalize_linkage_key(title)
            forum_topic = forum_v2.find_topic_by_linkage(linkage, paths=paths)

        if forum_topic is None:
            # No Topic to attach to — skip this snapshot.
            # Performance NEVER creates Topics (Collector/Radar are discoverers).
            result.notes.append(f"orphan_snapshot:{radar_topic_id}:{title[:30]}")
            continue

        # Write PERFORMANCE_REPORT
        velocity = snap.get("velocity", "") or "unknown"
        engagement = snap.get("engagement", "") or "unknown"
        window = snap.get("window", "") or "24h"
        try:
            forum_integration.performance_emit_report(
                topic_id=forum_topic.topic_id,
                velocity=str(velocity),
                engagement=str(engagement),
                window=str(window),
                source_message_id=f"perf:{exec_record.run_id}:{radar_topic_id}",
                confidence=1.0,
                paths=paths,
            )
            written_topics += 1
            result.forum_events_written += 1
        except Exception as e:
            result.forum_error = f"{type(e).__name__}:{e}"
            result.forum_sync_status = runtime_state.SYNC_FAILED
            result.notes.append(f"perf_report_failed:{forum_topic.topic_id}:{str(e)[:80]}")

        # Write SUSTAINED_SIGNAL when velocity is "rising" and observation_count >= 2
        if velocity == "rising" and snap.get("observation_count", 0) >= 2:
            try:
                forum_integration.performance_emit_sustained(
                    topic_id=forum_topic.topic_id,
                    duration_hours=float(snap.get("duration_hours", 24) or 24),
                    sources_increasing=bool(snap.get("sources_increasing", False)),
                    paths=paths,
                )
                result.forum_events_written += 1
            except Exception as e:
                result.forum_error = f"{type(e).__name__}:{e}"
                result.forum_sync_status = runtime_state.SYNC_FAILED
                result.notes.append(f"sustained_failed:{forum_topic.topic_id}:{str(e)[:80]}")

        # Write COOLING_SIGNAL when velocity is "cooling"
        if velocity in ("cooling", "falling", "declining"):
            try:
                forum_integration.performance_emit_cooling(
                    topic_id=forum_topic.topic_id,
                    window=str(window),
                    paths=paths,
                )
                result.forum_events_written += 1
            except Exception as e:
                result.forum_error = f"{type(e).__name__}:{e}"
                result.forum_sync_status = runtime_state.SYNC_FAILED
                result.notes.append(f"cooling_failed:{forum_topic.topic_id}:{str(e)[:80]}")

    result.topics_processed = written_topics
    result.notes.append(f"snapshots_processed:{len(snapshots)}")
    result.finished_at = utc_now_iso()
    if result.forum_error and result.forum_events_written == 0:
        result.status = runtime_state.FAILED
    return result


if __name__ == "__main__":
    paths = forum_v2.ForumV2Paths()
    r = run_performance_runtime(forum_paths=paths)
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))