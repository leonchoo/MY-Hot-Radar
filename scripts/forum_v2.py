#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MY Hot Radar — Forum v2 (Topic Lifecycle + Four-Agent Integration).

Adds a Topic / Thread / Event layer on top of the existing Forum v1
transport (outbox/, inbox/<agent>/, state/). Forum v1 files are NEVER
modified, deleted, or relocated. v2 only ADDS:

    forum/
      topics/
        <TOPIC-ID>/
          topic.json         (current Topic state)
          events.jsonl       (append-only Event timeline)
      dashboard/
        index.json           (read-only aggregate for Dashboard UI)

Topic lifecycle:
    NEW -> RADAR_TRACKING -> EDITORIAL_REVIEW -> PUBLISHED -> MONITORING
    -> FOLLOW_UP -> CLOSED
    Any state -> REACTIVATED (Collector finds the same news resurfacing)
    REACTIVATED -> RADAR_TRACKING (re-enters the pipeline)

Four agents:
    collector         MHR Collector (Android Collector)
    radar             MHR Radar (source/normalize/dedup/topic)
    default           MHR Default (Hermes / editorial owner)
    mhr_performance   MHR Performance (velocity / engagement / cooling)

This module exposes:
    ForumV2Paths           filesystem layout helpers (additive, never destructive)
    Topic                  dataclass for the persisted Topic record
    Event                  dataclass for the append-only Event line
    TopicLifecycle         Enum of allowed lifecycle states
    AgentRole              Enum of the four allowed agents
    ALLOWED_EVENT_TYPES    mapping agent -> set of allowed event types
    create_topic()         create or reactivate a Topic (idempotent on linkage_key)
    append_event()         append a single Event to a Topic
    list_topics()          enumerate all Topics (newest first)
    get_topic()            load a Topic by id
    get_events()            read all events of a Topic
    build_dashboard_index() rebuild forum/dashboard/index.json from disk

Strict rules:
    * Forum v1 files (outbox/, inbox/, state/) are never touched.
    * Topics are immutable in their event history (events.jsonl only appends).
    * The 'topic.json' file is updated atomically on every lifecycle change.
    * Topic reactivation MUST happen via linkage_key match BEFORE creating a
      new Topic. The caller passes a linkage_key; if a Topic exists with the
      same linkage_key, the existing Topic is reused.
    * topic_id is deterministic: T_<sha256(linkage_key)[:16]>. Same linkage_key
      always produces the same topic_id.
    * All file writes are atomic (tmp + os.replace).
    * Permission denied / partial-write failures abort the operation with an
      exception. No silent half-writes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "forum/v2-topic"
EVENT_SCHEMA_VERSION = "forum/v2-event"

DEFAULT_FORUM_ROOT = Path(
    os.environ.get(
        "MY_HOT_RADAR_FORUM_ROOT",
        r"C:\MY-Hot-Radar-Bridge\forum",
    )
)


class AgentRole(str, Enum):
    COLLECTOR = "collector"
    RADAR = "radar"
    DEFAULT = "default"
    MHR_PERFORMANCE = "mhr_performance"


class TopicLifecycle(str, Enum):
    NEW = "NEW"
    RADAR_TRACKING = "RADAR_TRACKING"
    EDITORIAL_REVIEW = "EDITORIAL_REVIEW"
    PUBLISHED = "PUBLISHED"
    MONITORING = "MONITORING"
    FOLLOW_UP = "FOLLOW_UP"
    REACTIVATED = "REACTIVATED"
    CLOSED = "CLOSED"


# Lifecycle transition table (forward-compatible). Any transition not
# explicitly listed here is rejected.
#
# Design intent:
#   * NEW can fast-path to REACTIVATED (collector found old news).
#   * Almost any non-terminal state can fast-path to FOLLOW_UP.
#   * CLOSED is reopenable to REACTIVATED only.
ALLOWED_TRANSITIONS: Dict[str, set] = {
    TopicLifecycle.NEW.value: {
        TopicLifecycle.RADAR_TRACKING.value,
        TopicLifecycle.EDITORIAL_REVIEW.value,
        TopicLifecycle.CLOSED.value,
        TopicLifecycle.REACTIVATED.value,
    },
    TopicLifecycle.RADAR_TRACKING.value: {
        TopicLifecycle.EDITORIAL_REVIEW.value,
        TopicLifecycle.MONITORING.value,
        TopicLifecycle.FOLLOW_UP.value,
        TopicLifecycle.CLOSED.value,
        TopicLifecycle.REACTIVATED.value,
    },
    TopicLifecycle.EDITORIAL_REVIEW.value: {
        TopicLifecycle.PUBLISHED.value,
        TopicLifecycle.RADAR_TRACKING.value,
        TopicLifecycle.FOLLOW_UP.value,
        TopicLifecycle.CLOSED.value,
        TopicLifecycle.REACTIVATED.value,
    },
    TopicLifecycle.PUBLISHED.value: {
        TopicLifecycle.MONITORING.value,
        TopicLifecycle.FOLLOW_UP.value,
        TopicLifecycle.CLOSED.value,
        TopicLifecycle.REACTIVATED.value,
    },
    TopicLifecycle.MONITORING.value: {
        TopicLifecycle.FOLLOW_UP.value,
        TopicLifecycle.CLOSED.value,
        TopicLifecycle.REACTIVATED.value,
    },
    TopicLifecycle.FOLLOW_UP.value: {
        TopicLifecycle.MONITORING.value,
        TopicLifecycle.CLOSED.value,
        TopicLifecycle.REACTIVATED.value,
    },
    TopicLifecycle.REACTIVATED.value: {
        TopicLifecycle.RADAR_TRACKING.value,
        TopicLifecycle.EDITORIAL_REVIEW.value,
        TopicLifecycle.MONITORING.value,
        TopicLifecycle.FOLLOW_UP.value,
        TopicLifecycle.CLOSED.value,
    },
    TopicLifecycle.CLOSED.value: {
        TopicLifecycle.REACTIVATED.value,
    },
}


# Event types each agent is allowed to emit. Forward-compatible: unknown
# event types from existing v1 messages are recorded as-is but flagged.
ALLOWED_EVENT_TYPES: Dict[str, set] = {
    AgentRole.COLLECTOR.value: {
        "OBSERVATION",
        "SOCIAL_HEAT_SIGNAL",
        "REACTIVATION_SIGNAL",
        "EVIDENCE",
        "CREATE_TOPIC",
    },
    AgentRole.RADAR.value: {
        "SOURCE_UPDATE",
        "TOPIC_UPDATE",
        "CROSS_SOURCE_CONFIRMATION",
        "MOMENTUM_UPDATE",
        "CLASSIFICATION_UPDATE",
    },
    AgentRole.DEFAULT.value: {
        "EDITORIAL_REVIEW",
        "PUBLISH",
        "UPDATE_ARTICLE",
        "FOLLOW_UP",
        "MONITOR",
        "CLOSE",
    },
    AgentRole.MHR_PERFORMANCE.value: {
        "PERFORMANCE_REPORT",
        "VELOCITY_UPDATE",
        "ENGAGEMENT_UPDATE",
        "SUSTAINED_SIGNAL",
        "COOLING_SIGNAL",
        "REACTIVATION_SIGNAL",
    },
}


# Topic Classification values
CLASSIFICATIONS = {
    "BREAKING", "RISING", "HOT", "COOLING", "WATCH",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ForumV2Error(Exception):
    pass


class LifecycleError(ForumV2Error):
    pass


class AgentPermissionError(ForumV2Error):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def topic_id_from_linkage(linkage_key: str) -> str:
    """Deterministic topic_id from a linkage_key.

    The same linkage_key always produces the same topic_id. This is the
    core of reactivation: a Collector returning to an old topic with the
    same linkage_key will resolve to the existing topic_id.
    """
    if not isinstance(linkage_key, str) or not linkage_key.strip():
        raise ForumV2Error("linkage_key must be a non-empty string")
    digest = hashlib.sha256(linkage_key.encode("utf-8")).hexdigest()[:16]
    return f"T_{digest}"


def make_event_id() -> str:
    """Globally-unique event_id (similar to forum v1 message_id)."""
    return f"evt_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def normalize_linkage_key(title: str) -> str:
    """Normalize a title into a linkage_key.

    The normalization removes dates, lowercase, strip punctuation, and
    collapse whitespace. Two titles that mean the same story produce the
    same key.
    """
    if not isinstance(title, str) or not title.strip():
        raise ForumV2Error("title must be a non-empty string for linkage_key")
    s = title.lower()
    # Drop common date formats
    s = re.sub(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", " ", s)
    s = re.sub(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", " ", s)
    # Drop common time formats
    s = re.sub(r"\b\d{1,2}:\d{2}(:\d{2})?\s*(am|pm|utc)?\b", " ", s, flags=re.IGNORECASE)
    # Drop punctuation (keep ASCII letters, digits, CJK ideographs, spaces)
    # \u4e00-\u9fff covers CJK Unified Ideographs
    s = re.sub(r"[^\w\u4e00-\u9fff\s]+", " ", s, flags=re.UNICODE)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        # Title is all symbols/numbers — fall back to its raw lowercase form
        s = title.lower().strip()
    return s


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

class ForumV2Paths:
    """Filesystem layout for v2 Topic/Thread layer.

    All paths are derived from a single forum_root. v1 directories are
    referenced but NEVER modified or removed.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_FORUM_ROOT

    @property
    def topics_dir(self) -> Path:
        return self.root / "topics"

    @property
    def dashboard_dir(self) -> Path:
        return self.root / "dashboard"

    def topic_dir(self, topic_id: str) -> Path:
        return self.topics_dir / topic_id

    def topic_json(self, topic_id: str) -> Path:
        return self.topic_dir(topic_id) / "topic.json"

    def events_jsonl(self, topic_id: str) -> Path:
        return self.topic_dir(topic_id) / "events.jsonl"

    def ensure_layout(self) -> None:
        """Create topics/ and dashboard/ directories. Never touches v1 dirs."""
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        self.dashboard_dir.mkdir(parents=True, exist_ok=True)

    def list_topic_ids(self) -> List[str]:
        if not self.topics_dir.exists():
            return []
        return sorted(
            p.name for p in self.topics_dir.iterdir() if p.is_dir()
        )


# ---------------------------------------------------------------------------
# Topic dataclass
# ---------------------------------------------------------------------------

@dataclass
class Topic:
    topic_id: str
    schema_version: str
    title: str
    created_at: str
    updated_at: str
    status: str
    classification: str
    first_seen: str
    last_seen: str
    source_count: int
    languages: List[str]
    participants: List[str]
    linkage_key: str
    events_count: int
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Topic":
        return cls(
            topic_id=str(d.get("topic_id") or ""),
            schema_version=str(d.get("schema_version") or SCHEMA_VERSION),
            title=str(d.get("title") or ""),
            created_at=str(d.get("created_at") or ""),
            updated_at=str(d.get("updated_at") or ""),
            status=str(d.get("status") or TopicLifecycle.NEW.value),
            classification=str(d.get("classification") or "WATCH"),
            first_seen=str(d.get("first_seen") or ""),
            last_seen=str(d.get("last_seen") or ""),
            source_count=int(d.get("source_count") or 0),
            languages=list(d.get("languages") or []),
            participants=list(d.get("participants") or []),
            linkage_key=str(d.get("linkage_key") or ""),
            events_count=int(d.get("events_count") or 0),
            tags=list(d.get("tags") or []),
        )


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class Event:
    event_id: str
    topic_id: str
    agent: str
    event_type: str
    timestamp: str
    payload: Dict
    evidence: Dict
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Event":
        return cls.from_dict(json.loads(text))

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            event_id=str(d.get("event_id") or ""),
            topic_id=str(d.get("topic_id") or ""),
            agent=str(d.get("agent") or ""),
            event_type=str(d.get("event_type") or ""),
            timestamp=str(d.get("timestamp") or ""),
            payload=dict(d.get("payload") or {}),
            evidence=dict(d.get("evidence") or {}),
            confidence=float(d.get("confidence") if d.get("confidence") is not None else 1.0),
        )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

_write_lock = threading.Lock()  # global lock for atomic topic.json + events.jsonl


def _atomic_write_json(target: Path, payload: dict) -> None:
    """Atomic JSON write: write to .tmp + os.replace."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + f".tmp.{os.getpid()}.{int(time.time() * 1e6) % 1000000}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)


def _append_event_line(events_path: Path, event: Event) -> None:
    """Append a single Event as one JSON line to events.jsonl.

    Uses 'a' mode — atomic per-line on POSIX; on Windows we open, write,
    and close so the line is flushed. Concurrent writers are serialised
    by the module-level _write_lock.
    """
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(event.to_json() + "\n")


def _check_event_permission(agent: str, event_type: str) -> None:
    """Raise AgentPermissionError if the agent is not allowed to emit
    this event_type."""
    if agent not in ALLOWED_EVENT_TYPES:
        raise AgentPermissionError(
            f"unknown agent: {agent!r} (must be one of {sorted(ALLOWED_EVENT_TYPES)})"
        )
    allowed = ALLOWED_EVENT_TYPES[agent]
    if event_type not in allowed:
        raise AgentPermissionError(
            f"agent {agent!r} is not allowed to emit event_type {event_type!r}; "
            f"allowed: {sorted(allowed)}"
        )


def _check_lifecycle_transition(from_status: str, to_status: str) -> None:
    if from_status not in ALLOWED_TRANSITIONS:
        raise LifecycleError(f"unknown source lifecycle: {from_status!r}")
    if to_status not in ALLOWED_TRANSITIONS:
        raise LifecycleError(f"unknown target lifecycle: {to_status!r}")
    allowed = ALLOWED_TRANSITIONS[from_status]
    if to_status not in allowed:
        raise LifecycleError(
            f"illegal lifecycle transition: {from_status!r} -> {to_status!r} "
            f"(allowed from {from_status!r}: {sorted(allowed)})"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_topic_by_linkage(linkage_key: str, paths: ForumV2Paths) -> Optional[Topic]:
    """Find an existing Topic by linkage_key (case-insensitive equality
    after normalization)."""
    target = normalize_linkage_key(linkage_key)
    target_tid = topic_id_from_linkage(target)
    p = paths.topic_json(target_tid)
    if not p.exists():
        # Also search all topics for any with the same linkage_key (catches
        # topics created under a different pre-normalized key).
        for tid in paths.list_topic_ids():
            cand = paths.topic_json(tid)
            if not cand.exists():
                continue
            try:
                t = Topic.from_dict(json.loads(cand.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
            if t.linkage_key == target:
                return t
        return None
    try:
        return Topic.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def create_topic(
    *,
    title: str,
    agent: str,
    paths: Optional[ForumV2Paths] = None,
    classification: str = "WATCH",
    languages: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    event_payload: Optional[Dict] = None,
    event_evidence: Optional[Dict] = None,
    confidence: float = 1.0,
) -> Tuple[Topic, Event, bool]:
    """Create a new Topic, or REACTIVATE an existing one with the same
    linkage_key. Returns (topic, event, was_reactivated).

    If an existing Topic is found, this:
      1. Transitions it to REACTIVATED
      2. Appends a REACTIVATION_SIGNAL event (by the same agent)
      3. Returns the existing Topic + the new event + was_reactivated=True

    Otherwise:
      1. Creates a fresh Topic with status=NEW
      2. Appends a CREATE_TOPIC event
      3. Returns the new Topic + event + was_reactivated=False

    Idempotent on linkage_key: calling twice with the same title
    produces ONE Topic, with two events (the second call reactivates).
    """
    paths = paths or ForumV2Paths()
    paths.ensure_layout()
    linkage = normalize_linkage_key(title)
    now = _utc_now_iso()

    existing = find_topic_by_linkage(linkage, paths)
    with _write_lock:
        if existing is not None:
            # Reactivate.
            _check_lifecycle_transition(existing.status, TopicLifecycle.REACTIVATED.value)
            existing.status = TopicLifecycle.REACTIVATED.value
            existing.updated_at = now
            existing.last_seen = now
            existing.events_count = existing.events_count + 1
            if agent not in existing.participants:
                existing.participants.append(agent)
            if existing.events_count > 0:
                pass  # last_seen tracks the latest event
            _atomic_write_json(paths.topic_json(existing.topic_id), existing.to_dict())
            evt_type = "REACTIVATION_SIGNAL"
            evt = Event(
                event_id=make_event_id(),
                topic_id=existing.topic_id,
                agent=agent,
                event_type=evt_type,
                timestamp=now,
                payload=event_payload or {"title": title, "linkage_key": linkage},
                evidence=event_evidence or {},
                confidence=confidence,
            )
            _check_event_permission(agent, evt_type)
            _append_event_line(paths.events_jsonl(existing.topic_id), evt)
            return existing, evt, True

        # New topic.
        tid = topic_id_from_linkage(linkage)
        topic = Topic(
            topic_id=tid,
            schema_version=SCHEMA_VERSION,
            title=title,
            created_at=now,
            updated_at=now,
            status=TopicLifecycle.NEW.value,
            classification=classification if classification in CLASSIFICATIONS else "WATCH",
            first_seen=now,
            last_seen=now,
            source_count=1,
            languages=list(languages or []),
            participants=[agent],
            linkage_key=linkage,
            events_count=1,
            tags=list(tags or []),
        )
        _atomic_write_json(paths.topic_json(tid), topic.to_dict())
        evt = Event(
            event_id=make_event_id(),
            topic_id=tid,
            agent=agent,
            event_type="CREATE_TOPIC",
            timestamp=now,
            payload=event_payload or {"title": title, "linkage_key": linkage},
            evidence=event_evidence or {},
            confidence=confidence,
        )
        _check_event_permission(agent, "CREATE_TOPIC")
        _append_event_line(paths.events_jsonl(tid), evt)
        return topic, evt, False


def append_event(
    *,
    topic_id: str,
    agent: str,
    event_type: str,
    payload: Optional[Dict] = None,
    evidence: Optional[Dict] = None,
    confidence: float = 1.0,
    paths: Optional[ForumV2Paths] = None,
    next_status: Optional[str] = None,
) -> Tuple[Topic, Event]:
    """Append an event to an existing Topic. Optionally transition the
    Topic's lifecycle to ``next_status`` (atomic).

    Returns (updated_topic, new_event).

    Raises:
        ForumV2Error if topic_id does not exist.
        AgentPermissionError if agent is not allowed to emit event_type.
        LifecycleError if next_status is provided and the transition is illegal.
    """
    paths = paths or ForumV2Paths()
    topic_path = paths.topic_json(topic_id)
    if not topic_path.exists():
        raise ForumV2Error(f"topic does not exist: {topic_id}")

    _check_event_permission(agent, event_type)

    with _write_lock:
        topic = Topic.from_dict(json.loads(topic_path.read_text(encoding="utf-8")))
        now = _utc_now_iso()

        if next_status is not None:
            _check_lifecycle_transition(topic.status, next_status)
            topic.status = next_status
            topic.updated_at = now

        topic.last_seen = now
        topic.events_count = topic.events_count + 1
        if agent not in topic.participants:
            topic.participants.append(agent)

        _atomic_write_json(topic_path, topic.to_dict())

        evt = Event(
            event_id=make_event_id(),
            topic_id=topic_id,
            agent=agent,
            event_type=event_type,
            timestamp=now,
            payload=payload or {},
            evidence=evidence or {},
            confidence=confidence,
        )
        _append_event_line(paths.events_jsonl(topic_id), evt)
        return topic, evt


def get_topic(topic_id: str, paths: Optional[ForumV2Paths] = None) -> Optional[Topic]:
    paths = paths or ForumV2Paths()
    p = paths.topic_json(topic_id)
    if not p.exists():
        return None
    return Topic.from_dict(json.loads(p.read_text(encoding="utf-8")))


def get_events(topic_id: str, paths: Optional[ForumV2Paths] = None) -> List[Event]:
    paths = paths or ForumV2Paths()
    p = paths.events_jsonl(topic_id)
    if not p.exists():
        return []
    out: List[Event] = []
    with p.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Event.from_json(line))
            except json.JSONDecodeError:
                # Skip corrupt lines; surface the index in evidence.
                continue
    return out


def list_topics(paths: Optional[ForumV2Paths] = None) -> List[Topic]:
    paths = paths or ForumV2Paths()
    out: List[Topic] = []
    for tid in paths.list_topic_ids():
        t = get_topic(tid, paths)
        if t is not None:
            out.append(t)
    # Newest first
    out.sort(key=lambda t: t.last_seen, reverse=True)
    return out


# ---------------------------------------------------------------------------
# Dashboard index
# ---------------------------------------------------------------------------

def build_dashboard_index(paths: Optional[ForumV2Paths] = None) -> dict:
    """Build a read-only aggregate index for the Dashboard UI.

    Returns a dict; also writes it to forum/dashboard/index.json atomically.
    """
    paths = paths or ForumV2Paths()
    paths.ensure_layout()

    topics = list_topics(paths)
    by_status: Dict[str, int] = {}
    by_classification: Dict[str, int] = {}
    by_agent_participation: Dict[str, int] = {}
    for t in topics:
        by_status[t.status] = by_status.get(t.status, 0) + 1
        by_classification[t.classification] = by_classification.get(t.classification, 0) + 1
        for a in t.participants:
            by_agent_participation[a] = by_agent_participation.get(a, 0) + 1

    index = {
        "schema_version": "forum/v2-dashboard",
        "generated_at": _utc_now_iso(),
        "total_topics": len(topics),
        "by_status": by_status,
        "by_classification": by_classification,
        "by_agent_participation": by_agent_participation,
        "topics": [
            {
                "topic_id": t.topic_id,
                "title": t.title,
                "status": t.status,
                "classification": t.classification,
                "events_count": t.events_count,
                "participants": t.participants,
                "first_seen": t.first_seen,
                "last_seen": t.last_seen,
                "languages": t.languages,
                "tags": t.tags,
            }
            for t in topics
        ],
    }
    _atomic_write_json(paths.dashboard_dir / "index.json", index)
    return index


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        description="MHR Forum v2 — Topic Lifecycle CLI",
    )
    sub = p.add_subparsers(dest="cmd")

    # create
    p_create = sub.add_parser("create", help="Create a new Topic (or reactivate existing)")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--agent", required=True)
    p_create.add_argument("--classification", default="WATCH")
    p_create.add_argument("--language", action="append", default=[])
    p_create.add_argument("--tag", action="append", default=[])
    p_create.add_argument("--payload-json", default=None)
    p_create.add_argument("--evidence-json", default=None)
    p_create.add_argument("--confidence", type=float, default=1.0)

    # event
    p_evt = sub.add_parser("event", help="Append an event to a Topic")
    p_evt.add_argument("--topic-id", required=True)
    p_evt.add_argument("--agent", required=True)
    p_evt.add_argument("--event-type", required=True)
    p_evt.add_argument("--next-status", default=None)
    p_evt.add_argument("--payload-json", default=None)
    p_evt.add_argument("--evidence-json", default=None)
    p_evt.add_argument("--confidence", type=float, default=1.0)

    # show
    p_show = sub.add_parser("show", help="Show a Topic and its events")
    p_show.add_argument("--topic-id", required=True)

    # list
    sub.add_parser("list", help="List all Topics")

    # dashboard
    sub.add_parser("dashboard", help="Rebuild dashboard/index.json")

    args = p.parse_args(argv)
    paths = ForumV2Paths()

    if args.cmd == "create":
        payload = json.loads(args.payload_json) if args.payload_json else None
        evidence = json.loads(args.evidence_json) if args.evidence_json else None
        topic, evt, was_reactivated = create_topic(
            title=args.title,
            agent=args.agent,
            paths=paths,
            classification=args.classification,
            languages=args.language or None,
            tags=args.tag or None,
            event_payload=payload,
            event_evidence=evidence,
            confidence=args.confidence,
        )
        print(json.dumps({
            "topic_id": topic.topic_id,
            "title": topic.title,
            "status": topic.status,
            "was_reactivated": was_reactivated,
            "event": evt.to_dict(),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "event":
        payload = json.loads(args.payload_json) if args.payload_json else None
        evidence = json.loads(args.evidence_json) if args.evidence_json else None
        topic, evt = append_event(
            topic_id=args.topic_id,
            agent=args.agent,
            event_type=args.event_type,
            payload=payload,
            evidence=evidence,
            confidence=args.confidence,
            paths=paths,
            next_status=args.next_status,
        )
        print(json.dumps({
            "topic_id": topic.topic_id,
            "status": topic.status,
            "event": evt.to_dict(),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "show":
        topic = get_topic(args.topic_id, paths)
        if topic is None:
            print(f"[FAIL] topic {args.topic_id} not found", file=sys.stderr)
            return 2
        events = get_events(args.topic_id, paths)
        print(json.dumps({
            "topic": topic.to_dict(),
            "events": [e.to_dict() for e in events],
        }, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "list":
        topics = list_topics(paths)
        print(json.dumps({
            "count": len(topics),
            "topics": [
                {
                    "topic_id": t.topic_id,
                    "title": t.title,
                    "status": t.status,
                    "classification": t.classification,
                    "events_count": t.events_count,
                }
                for t in topics
            ],
        }, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "dashboard":
        idx = build_dashboard_index(paths)
        print(json.dumps(idx, ensure_ascii=False, indent=2))
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
