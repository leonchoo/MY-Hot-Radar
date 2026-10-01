#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collector Runtime Adapter.

Phase 6 MHR Newsroom Runtime.

The Collector's REAL observation path is the bridge writer:
    MY-Hot-Radar-Collector/src/bridge_writer.py

This adapter:
  1. Reads v1 bridge messages from forum/inbox/<source>/ (or wherever
     the Collector pipeline deposits them).
  2. For each new message, calls forum_integration.bridge_v1_message_to_v2_event.
  3. Records run metadata to forum/runtime/state.json.
  4. Returns AdapterResult for the runtime orchestrator.

Failure isolation:
  * Bridge inbox missing / corrupt → adapter logs SKIPPED, never raises.
  * Forum write failures → captured in AdapterResult.forum_error, never raised.

If no Collector bridge is available in the local repo (e.g. this adapter
runs on a different machine than the Collector pipeline), it reports
SKIPPED with notes explaining why.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import forum_v2  # noqa: E402
import forum_integration  # noqa: E402
import runtime_state  # noqa: E402
import event_identity  # noqa: E402
from runtime_adapters import AdapterResult, utc_now_iso, append_event_safe  # noqa: E402


DEFAULT_BRIDGE_ROOT = Path(r"C:\MY-Hot-Radar-Bridge")


def discover_v1_messages(bridge_root: Path) -> List[Path]:
    """Discover v1 bridge message files in the bridge inbox.

    Returns paths to JSON files in forum/inbox/ (Collector deposits here)
    and the standalone inbox/ folder at bridge root.
    """
    candidates = []
    inbox_roots = [
        bridge_root / "forum" / "inbox",
        bridge_root / "inbox",
    ]
    for root in inbox_roots:
        if root.exists():
            for p in root.glob("**/*.json"):
                candidates.append(p)
    return candidates


def run_collector_runtime(
    *,
    bridge_root: Optional[Path] = None,
    forum_paths: Optional[forum_v2.ForumV2Paths] = None,
    run_id: Optional[str] = None,
) -> AdapterResult:
    """Run the Collector adapter.

    1. Discovers v1 bridge messages.
    2. For each, calls forum_integration.bridge_v1_message_to_v2_event.
    3. Records metadata.

    No-op if no bridge messages found — returns SKIPPED status.
    """
    started = utc_now_iso()
    run_id = run_id or runtime_state.make_run_id(runtime_state.AGENT_COLLECTOR)
    bridge_root = bridge_root or DEFAULT_BRIDGE_ROOT
    paths = forum_paths or forum_v2.ForumV2Paths()

    result = AdapterResult(
        agent=runtime_state.AGENT_COLLECTOR,
        run_id=run_id,
        started_at=started,
        finished_at=started,
        status=runtime_state.OK,
    )

    if not bridge_root.exists():
        result.status = runtime_state.SKIPPED
        result.notes.append(f"bridge_root_missing:{bridge_root}")
        result.finished_at = utc_now_iso()
        return result

    try:
        messages = discover_v1_messages(bridge_root)
    except Exception as e:
        result.status = runtime_state.FAILED
        result.agent_error = f"discover_failed:{type(e).__name__}:{e}"
        result.finished_at = utc_now_iso()
        return result

    if not messages:
        result.status = runtime_state.SKIPPED
        result.notes.append("no_bridge_messages")
        result.finished_at = utc_now_iso()
        return result

    # Process each message
    for msg_path in messages:
        try:
            msg_data = json.loads(msg_path.read_text(encoding="utf-8"))
            source_message_id = msg_data.get("message_id") or msg_path.stem
            ok, rv, err = (False, None, "no_bridge_fn")
            try:
                topic, event, was_reactivated, was_created = forum_integration.bridge_v1_message_to_v2_event(
                    message=msg_data,
                    paths=paths,
                )
                ok = True
                rv = (topic, event)
                if ok and was_created:
                    result.topics_processed += 1
                if ok:
                    result.forum_events_written += 1
                tag = "reactivated" if was_reactivated else ("created" if was_created else "appended")
                result.notes.append(f"bridged:{source_message_id}:{tag}")
            except Exception as e:
                err = f"{type(e).__name__}:{e}"
                result.forum_error = err
                result.forum_sync_status = runtime_state.SYNC_FAILED
                result.notes.append(f"bridge_failed:{source_message_id}:{err[:100]}")
        except Exception as e:
            result.notes.append(f"read_failed:{msg_path.name}:{type(e).__name__}:{e}")

    result.finished_at = utc_now_iso()
    if result.forum_error and result.forum_events_written == 0:
        result.status = runtime_state.FAILED
    return result


if __name__ == "__main__":
    paths = forum_v2.ForumV2Paths()
    r = run_collector_runtime(forum_paths=paths)
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))