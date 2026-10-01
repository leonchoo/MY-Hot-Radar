#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event Identity — Deterministic event_id and idempotency.

Phase 6 MHR Newsroom Runtime.

Goals:
  * One (topic, agent, event_type, run_id) → exactly one Forum Event
  * Event identity MUST be reproducible across restart
  * Crash A (Topic created but Event not finished) → recovery resumes safely
  * Crash B (Event written but state not saved) → no duplicate Event

event_key formula:
    sha256(topic_id + "|" + agent + "|" + event_type + "|" + run_id + "|" + source_message_id)

This is intentionally simple — combines the 4 canonical identifiers.
If two Forum writers try to append the same logical Event (same key),
the second write is silently skipped.

Topic-level idempotency:
    topic_linkage_key (in Topic schema) is already a normalized string
    used for find-or-create. See forum_v2.normalize_linkage_key.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Matches forum/v2 event_id format
EVENT_ID_RE = re.compile(r"^E_[0-9a-f]{16}$")


def compute_event_key(
    *,
    topic_id: str,
    agent: str,
    event_type: str,
    run_id: str,
    source_message_id: Optional[str] = None,
) -> str:
    """Compute a deterministic event_key from canonical identifiers.

    The key is a hex SHA-256 prefix. NOT used directly as event_id
    (Forum v2 uses its own event_id format E_<16-hex>), but used
    for idempotency checks.
    """
    parts = [
        topic_id or "",
        agent or "",
        event_type or "",
        run_id or "",
        source_message_id or "",
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def derive_event_id(
    *,
    topic_id: str,
    agent: str,
    event_type: str,
    run_id: str,
    source_message_id: Optional[str] = None,
) -> str:
    """Derive a Forum v2 event_id (E_<16-hex>) from canonical identifiers.

    This is the deterministic event_id when run_id is provided.
    Forum v2 also has its own make_event_id() — this is the
    runtime-side counterpart for idempotency.
    """
    full = compute_event_key(
        topic_id=topic_id,
        agent=agent,
        event_type=event_type,
        run_id=run_id,
        source_message_id=source_message_id,
    )
    return f"E_{full[:16]}"


def event_already_recorded(
    events_path: Path,
    event_id: Optional[str] = None,
    *,
    topic_id: Optional[str] = None,
    agent: Optional[str] = None,
    event_type: Optional[str] = None,
    run_id: Optional[str] = None,
    source_message_id: Optional[str] = None,
) -> bool:
    """Check whether an event has been recorded.

    Two complementary checks:
      1. By event_id (if provided) — fast string match.
      2. By canonical identity (topic_id+agent+event_type+run_id+source_message_id)
         — payload-level match. This is needed because Forum v2 generates
         its own event_id and we cannot rely on our own derived one.

    Returns True if found in either form.
    """
    if not events_path.exists():
        return False
    target_event_id = f'"event_id": "{event_id}"' if event_id else None
    # Identity-based predicates
    id_checks = []
    if topic_id:
        id_checks.append((f'"topic_id": "{topic_id}"', False))   # (substring, exact)
    if agent:
        id_checks.append((f'"agent": "{agent}"', False))
    if event_type:
        id_checks.append((f'"event_type": "{event_type}"', False))
    if run_id:
        id_checks.append((f'"run_id": "{run_id}"', False))
    if source_message_id:
        id_checks.append((f'"source_message_id": "{source_message_id}"', False))

    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                if target_event_id and target_event_id in line:
                    return True
                if id_checks:
                    # All predicates must match in the same line
                    if all(substring in line for substring, _ in id_checks):
                        return True
    except OSError:
        return False
    return False


def list_event_ids(events_path: Path) -> List[str]:
    """List all event_ids in events.jsonl."""
    if not events_path.exists():
        return []
    out = []
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "event_id" in obj:
                        out.append(obj["event_id"])
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def topic_event_count(events_path: Path, topic_id: str) -> int:
    """Count events for a specific topic_id in events.jsonl."""
    if not events_path.exists():
        return 0
    target = f'"topic_id": "{topic_id}"'
    count = 0
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                if target in line:
                    count += 1
    except OSError:
        pass
    return count


if __name__ == "__main__":
    # Smoke tests
    k1 = compute_event_key(
        topic_id="T_abc",
        agent="radar",
        event_type="SOURCE_UPDATE",
        run_id="radar_20261001T120000Z_abcd",
        source_message_id=None,
    )
    k2 = compute_event_key(
        topic_id="T_abc",
        agent="radar",
        event_type="SOURCE_UPDATE",
        run_id="radar_20261001T120000Z_abcd",
        source_message_id=None,
    )
    assert k1 == k2, "Same canonical inputs → same key"

    # Different source_message_id → different key
    k3 = compute_event_key(
        topic_id="T_abc",
        agent="radar",
        event_type="SOURCE_UPDATE",
        run_id="radar_20261001T120000Z_abcd",
        source_message_id="msg_001",
    )
    assert k3 != k1, "Different source_message_id → different key"

    # Derive event_id
    eid = derive_event_id(
        topic_id="T_abc",
        agent="radar",
        event_type="SOURCE_UPDATE",
        run_id="radar_20261001T120000Z_abcd",
    )
    assert EVENT_ID_RE.match(eid), f"Bad event_id format: {eid}"

    print("EventIdentity smoke-tests OK")