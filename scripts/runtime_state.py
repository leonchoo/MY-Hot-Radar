#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runtime State — 轻量 runtime coordination state.

Phase 6 MHR Newsroom Runtime.

This is NOT:
  - Radar production state (public/radar/latest.json)
  - Forum Topic/Event state (forum/topics/)
  - Performance calculation results

This IS:
  - Per-agent last-run metadata
  - Forum sync status (which Agent runs successfully mirrored to Forum)
  - Health markers
  - Recovery checkpoint per Agent

Schema (forum/runtime/state.json):
{
  "schema_version": "forum/runtime-v1",
  "agents": {
    "collector": {
      "last_run": "2026-10-01T12:00:00Z",
      "last_run_id": "collector_20261001T120000Z_abcd",
      "last_status": "OK",                  # OK / FAILED / SKIPPED
      "last_forum_sync": "2026-10-01T12:00:01Z",
      "forum_sync_status": "SYNCED",        # SYNCED / DEGRADED / FAILED
      "total_runs": 12,
      "failed_runs": 0
    },
    "radar": {...},
    "default": {...},
    "mhr_performance": {...}
  },
  "forum": {
    "last_check": "2026-10-01T12:05:00Z",
    "topics": 33,
    "events": 0,
    "status": "OK"
  }
}

Isolation guarantees:
  - All writes are atomic (tmp file + os.replace)
  - State directory is independent from production output
  - State file is NOT in forum/topics/ (which is read-only to the Viewer)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


SCHEMA_VERSION = "forum/runtime-v1"

# Agent identifiers (must match Forum v2 agent enum)
AGENT_COLLECTOR = "collector"
AGENT_RADAR = "radar"
AGENT_DEFAULT = "default"
AGENT_PERFORMANCE = "mhr_performance"

ALL_AGENTS = [AGENT_COLLECTOR, AGENT_RADAR, AGENT_DEFAULT, AGENT_PERFORMANCE]

# Status enums
OK = "OK"
FAILED = "FAILED"
SKIPPED = "SKIPPED"
DEGRADED = "DEGRADED"

ALL_STATUS = [OK, FAILED, SKIPPED]

# Forum sync status
SYNCED = "SYNCED"
SYNC_FAILED = "SYNC_FAILED"
NEVER_SYNCED = "NEVER_SYNCED"

ALL_SYNC_STATUS = [SYNCED, SYNC_FAILED, NEVER_SYNCED]


@dataclass
class AgentRunRecord:
    """One Agent's most recent run record."""
    last_run: Optional[str] = None              # ISO 8601 timestamp
    last_run_id: Optional[str] = None            # run_id
    last_status: str = NEVER_SYNCED             # OK / FAILED / SKIPPED / NEVER_SYNCED
    last_forum_sync: Optional[str] = None        # ISO 8601 timestamp
    forum_sync_status: str = NEVER_SYNCED
    total_runs: int = 0
    failed_runs: int = 0
    last_error: str = ""                         # human-readable error
    last_run_topics: int = 0                     # topics processed in last run
    last_run_events: int = 0                     # events emitted in last run


@dataclass
class RuntimeState:
    """Top-level runtime state."""
    schema_version: str = SCHEMA_VERSION
    agents: Dict[str, AgentRunRecord] = field(default_factory=dict)
    forum_last_check: Optional[str] = None
    forum_topics: int = 0
    forum_events: int = 0
    forum_status: str = NEVER_SYNCED

    def __post_init__(self):
        for agent in ALL_AGENTS:
            if agent not in self.agents:
                self.agents[agent] = AgentRunRecord()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "agents": {a: asdict(r) for a, r in self.agents.items()},
            "forum": {
                "last_check": self.forum_last_check,
                "topics": self.forum_topics,
                "events": self.forum_events,
                "status": self.forum_status,
            },
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RuntimeState":
        state = cls(schema_version=d.get("schema_version", SCHEMA_VERSION))
        agents_dict = d.get("agents", {}) or {}
        for agent, a in state.agents.items():
            rec = agents_dict.get(agent, {}) or {}
            for k, v in rec.items():
                if hasattr(a, k):
                    setattr(a, k, v)
        forum = d.get("forum", {}) or {}
        state.forum_last_check = forum.get("last_check")
        state.forum_topics = int(forum.get("topics", 0))
        state.forum_events = int(forum.get("events", 0))
        state.forum_status = forum.get("status", NEVER_SYNCED)
        return state


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RuntimeStateStore:
    """File-backed atomic RuntimeState store.

    All writes go through a tmp file + os.replace to ensure crash safety.
    """
    _lock = threading.Lock()

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return RuntimeState.from_dict(data)
        except (json.JSONDecodeError, OSError, ValueError):
            return RuntimeState()

    def save(self, state: RuntimeState) -> None:
        payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
        # Atomic write: tmp file in same directory, then os.replace
        fd, tmp_path = tempfile.mkstemp(
            prefix=".runtime_state_", suffix=".json.tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            # Clean up tmp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def update_agent(self, agent: str, **kwargs) -> RuntimeState:
        """Update an Agent's record fields and persist.

        With file lock for thread-safety.
        """
        with self._lock:
            state = self.load()
            if agent not in state.agents:
                state.agents[agent] = AgentRunRecord()
            for k, v in kwargs.items():
                if hasattr(state.agents[agent], k):
                    setattr(state.agents[agent], k, v)
            self.save(state)
            return state

    def update_forum(self, *, topics: int, events: int,
                     status: str = OK,
                     last_check: Optional[str] = None) -> RuntimeState:
        with self._lock:
            state = self.load()
            state.forum_topics = topics
            state.forum_events = events
            state.forum_status = status
            state.forum_last_check = last_check or _utc_now_iso()
            self.save(state)
            return state


def make_run_id(agent: str) -> str:
    """Generate a deterministic-ish run_id for an Agent.

    Format: <agent>_<YYYYMMDDTHHMMSSZ>_<6-hex>
    Example: radar_20261001T120000Z_a1b2c3
    """
    timestamp = _utc_now_iso().replace("-", "").replace(":", "")
    suffix = os.urandom(3).hex()
    return f"{agent}_{timestamp}_{suffix}"


if __name__ == "__main__":
    # Smoke-test the store
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        store = RuntimeStateStore(Path(td) / "state.json")
        s = store.load()
        s.agents[AGENT_RADAR].last_run = _utc_now_iso()
        s.agents[AGENT_RADAR].last_status = OK
        store.save(s)
        loaded = store.load()
        assert loaded.agents[AGENT_RADAR].last_status == OK
        print("RuntimeStateStore smoke-test OK")
        sys.exit(0)