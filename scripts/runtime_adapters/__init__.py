#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runtime Adapter Base — shared utilities for Agent runtime adapters.

Phase 6 MHR Newsroom Runtime.

Each adapter wraps an Agent's REAL runtime execution path
(e.g. radar.scheduler.run_once, performance.scheduler.run_once,
Collector bridge writer) and bridges the resulting signals into
Forum v2 via forum_integration.

Critical design rules:
  1. Agent core code is NEVER imported and altered. Adapters only
     CALL Agent functions and observe results.
  2. Forum integration is best-effort. ANY failure in Forum writes
     is logged but MUST NOT propagate into the Agent's success path.
  3. Each adapter is idempotent: running twice with same run_id
     produces zero new Forum Events.
  4. Adapters record their own errors and return a Result object;
     callers can inspect to decide whether to retry.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import forum_v2  # noqa: E402
import forum_integration  # noqa: E402
import runtime_state  # noqa: E402
import event_identity  # noqa: E402


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AdapterResult:
    """Result of a single adapter run."""
    agent: str
    run_id: str
    started_at: str
    finished_at: str
    status: str                    # OK / FAILED / SKIPPED
    forum_events_written: int = 0
    forum_events_skipped_duplicate: int = 0
    forum_sync_status: str = runtime_state.SYNCED
    topics_processed: int = 0
    agent_error: str = ""
    forum_error: str = ""
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def append_event_safe(
    *,
    paths: forum_v2.ForumV2Paths,
    topic_id: str,
    agent: str,
    event_type: str,
    run_id: str,
    source_message_id: Optional[str] = None,
    payload_extra: Optional[Dict[str, Any]] = None,
    confidence: float = 1.0,
    source_run_id: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """Append a single Event to a Topic with idempotency.

    Returns: (appended: bool, event_id: str, error_message: str)
      - appended=True  → Event was newly written
      - appended=False → Event was skipped (duplicate, or Topic missing)

    Strategy:
      1. Compute deterministic event_id from (topic_id, agent, event_type,
         run_id, source_message_id).
      2. Check events.jsonl for existing event_id. If found → skip.
      3. Verify Topic exists in forum_v2.
      4. Construct payload with run_id + source_message_id + extras.
      5. Call forum_v2.append_event and catch all exceptions.
    """
    event_id = event_identity.derive_event_id(
        topic_id=topic_id,
        agent=agent,
        event_type=event_type,
        run_id=run_id,
        source_message_id=source_message_id,
    )

    events_path = paths.events_jsonl(topic_id)
    if event_identity.event_already_recorded(
        events_path,
        topic_id=topic_id,
        agent=agent,
        event_type=event_type,
        run_id=run_id,
        source_message_id=source_message_id,
    ):
        return False, event_id, ""

    # Verify Topic exists
    topic = forum_v2.get_topic(topic_id, paths=paths)
    if topic is None:
        return False, event_id, f"topic_not_found:{topic_id}"

    # Build payload
    payload: Dict[str, Any] = {
        "run_id": run_id,
        "source_run_id": source_run_id or run_id,
    }
    if source_message_id:
        payload["source_message_id"] = source_message_id
    if payload_extra:
        payload.update(payload_extra)

    try:
        # append_event signature: topic_id, agent, event_type, payload,
        #                       evidence=None, confidence=1.0, paths=None
        #                       next_status=None
        # source_message_id goes INTO payload
        payload_with_smid = dict(payload)
        if source_message_id and "source_message_id" not in payload_with_smid:
            payload_with_smid["source_message_id"] = source_message_id
        forum_v2.append_event(
            topic_id=topic_id,
            agent=agent,
            event_type=event_type,
            payload=payload_with_smid,
            evidence=None,
            confidence=confidence,
            paths=paths,
        )
        return True, event_id, ""
    except Exception as e:
        return False, event_id, f"{type(e).__name__}: {e}"


def topic_id_for_linkage(
    *,
    title: str,
    source_url: str,
    paths: forum_v2.ForumV2Paths,
    topic_id: Optional[str] = None,
) -> str:
    """Resolve a Topic for an observation.

    If topic_id is given and exists → use it.
    Otherwise find-or-create via linkage_key.
    """
    if topic_id:
        existing = forum_v2.get_topic(topic_id, paths=paths)
        if existing:
            return existing.topic_id
    # Find by linkage_key (title-based)
    if title:
        linkage = forum_v2.normalize_linkage_key(title)
        found = forum_v2.find_topic_by_linkage(linkage, paths=paths)
        if found:
            return found.topic_id
        # Create new (note: create_topic handles reactivation automatically)
        topic, _evt, _was_reactivated = forum_v2.create_topic(
            title=title,
            agent=runtime_state.AGENT_COLLECTOR,
            paths=paths,
        )
        return topic.topic_id
    raise ValueError("either topic_id or title must be provided")


def safe_wrap_forum_call(
    forum_fn,
    *args,
    **kwargs,
) -> Tuple[bool, Any, str]:
    """Execute a forum_* callable and catch all exceptions.

    Returns: (success: bool, return_value: Any, error_message: str)
    """
    try:
        rv = forum_fn(*args, **kwargs)
        return True, rv, ""
    except Exception as e:
        tb = traceback.format_exc()
        return False, None, f"{type(e).__name__}: {e}\n{tb}"


if __name__ == "__main__":
    print("Runtime adapter base loaded (no smoke test).")