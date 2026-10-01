#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Human Tips — 彪哥/Hermes 人工发现线索管理。

Phase 7 — Forum 扩展。

Forum Human Tip 是一种独立的 Forum 对象(类似但独立于 Topic):
  * 由 hermes agent 创建
  * 记录彪哥人工发现的一条新闻线索
  * 被 Radar 接手 / 验证
  * 建立或匹配到 Topic
  * 最终由 Default 编辑决定

Tip 自身有生命周期:
  OPEN → ACKNOWLEDGED → INVESTIGATING → LINKED → RESOLVED

Tip 文件布局:
  forum/human_tips/<tip_id>/
      tip.json          # tip state + metadata
      events.jsonl      # 状态变更历史

权限边界:
  * hermes:             CREATE_TIP (创建)
  * radar:              ACK_TIP / INVESTIGATE_TIP / LINK_TIP (验证 + 建立匹配 Topic)
  * default:            RESOLVE_TIP (关闭 / 编辑决策)
  * mhr_performance:    REPORT_TIP (传播表现报告)
  * collector:          只能 SCAN_TIP (读取观察)

事件类型 (Forum Human Tip event_type):
  CREATE_TIP          — 创建 tip
  ACK_TIP             — Radar 接手确认
  INVESTIGATE_TIP     — Radar 调查中
  LINK_TIP            — Radar 已建立/匹配到 Topic
  RESOLVE_TIP         — Default 关闭 / 编辑决策
  TIP_REPORT          — Performance / 表现报告
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TIP_SCHEMA_VERSION = "forum/v1-human_tip"

# Tip status enum
TIP_OPEN = "OPEN"
TIP_ACKNOWLEDGED = "ACKNOWLEDGED"
TIP_INVESTIGATING = "INVESTIGATING"
TIP_LINKED = "LINKED"
TIP_RESOLVED = "RESOLVED"

TIP_STATUSES = [TIP_OPEN, TIP_ACKNOWLEDGED, TIP_INVESTIGATING, TIP_LINKED, TIP_RESOLVED]

# Allowed status transitions
TIP_TRANSITIONS: Dict[str, List[str]] = {
    TIP_OPEN:         [TIP_ACKNOWLEDGED, TIP_RESOLVED],
    TIP_ACKNOWLEDGED: [TIP_INVESTIGATING, TIP_LINKED, TIP_RESOLVED],
    TIP_INVESTIGATING:[TIP_LINKED, TIP_RESOLVED],
    TIP_LINKED:       [TIP_RESOLVED, TIP_INVESTIGATING],
    TIP_RESOLVED:     [],  # terminal
}

# Tip event types
EVT_CREATE_TIP = "CREATE_TIP"
EVT_ACK_TIP = "ACK_TIP"
EVT_INVESTIGATE_TIP = "INVESTIGATE_TIP"
EVT_LINK_TIP = "LINK_TIP"
EVT_RESOLVE_TIP = "RESOLVE_TIP"
EVT_TIP_REPORT = "TIP_REPORT"

TIP_EVENT_TYPES = [EVT_CREATE_TIP, EVT_ACK_TIP, EVT_INVESTIGATE_TIP,
                  EVT_LINK_TIP, EVT_RESOLVE_TIP, EVT_TIP_REPORT]

# Permission matrix
TIP_PERMISSIONS: Dict[str, List[str]] = {
    "hermes": [EVT_CREATE_TIP],
    "radar": [EVT_CREATE_TIP, EVT_ACK_TIP, EVT_INVESTIGATE_TIP, EVT_LINK_TIP],
    "default": [EVT_CREATE_TIP, EVT_LINK_TIP, EVT_RESOLVE_TIP],
    "mhr_performance": [EVT_TIP_REPORT, EVT_CREATE_TIP],
    "collector": [],
}

# Priority enum
TIP_PRIORITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"]

# Resolution outcomes
TIP_RESOLUTION_KINDS = [
    "NO_NEWS_VALUE",      # Radar: 没有新闻价值
    "ALREADY_COVERED",   # 已存在 Topic 已覆盖
    "PUBLISHED",          # Default 已发布
    "TOPIC_CLOSED",       # Topic 已关闭
    "MERGED",             # 合并到其他 Topic
    "REACTIVATED",        # 触发 CLOSED Topic 重新升温
    "PENDING",            # 暂未决定
]


# ---------------------------------------------------------------------------
# Errors
class TipError(Exception):
    pass


class TipPermissionError(TipError):
    pass


class TipStatusError(TipError):
    pass


class TipNotFoundError(TipError):
    pass


# ---------------------------------------------------------------------------
# Dataclasses
@dataclass
class HumanTip:
    tip_id: str
    schema_version: str = TIP_SCHEMA_VERSION
    title: str = ""
    description: str = ""
    source_url: str = ""
    evidence_urls: List[str] = field(default_factory=list)
    priority: str = "MEDIUM"
    status: str = TIP_OPEN
    author: str = "hermes"               # who created it
    target_agent: str = "radar"           # who should pick it up
    topic_id: Optional[str] = None       # populated after Radar links
    resolution: str = ""                 # resolution kind
    resolution_note: str = ""            # human-readable resolution note
    tags: List[str] = field(default_factory=list)
    created_at: str = ""                 # ISO 8601 UTC
    updated_at: str = ""                 # ISO 8601 UTC
    acknowledged_at: str = ""
    linked_at: str = ""
    resolved_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "HumanTip":
        # Filter to known dataclass fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**kwargs)


@dataclass
class HumanTipEvent:
    event_id: str
    tip_id: str
    agent: str
    event_type: str
    timestamp: str
    payload: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Utilities
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_to_myt_display(utc_iso: str) -> str:
    """Convert UTC ISO to MYT display string."""
    if not utc_iso:
        return ""
    try:
        dt = datetime.strptime(utc_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        myt = dt.astimezone(timezone(timedelta(hours=8)))
        return myt.strftime("%Y-%m-%d %H:%M:%S MYT")
    except Exception:
        return utc_iso


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Atomically write a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".tip_", suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    """Atomically append to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def _check_transition(current: str, new: str) -> None:
    """Verify a status transition is allowed."""
    if new not in TIP_STATUSES:
        raise TipStatusError(f"invalid_status:{new}")
    if current == new:
        return
    allowed = TIP_TRANSITIONS.get(current, [])
    if new not in allowed:
        raise TipStatusError(
            f"illegal_transition:{current}->{new} (allowed: {allowed})"
        )


def _check_permission(agent: str, event_type: str) -> None:
    """Verify an agent can emit a tip event_type."""
    allowed = TIP_PERMISSIONS.get(agent, [])
    if event_type not in allowed:
        raise TipPermissionError(
            f"agent '{agent}' not permitted to emit '{event_type}'. "
            f"Allowed for {agent}: {allowed}"
        )


def _make_tip_id() -> str:
    """Generate a unique tip_id."""
    return "HT_" + uuid.uuid4().hex[:16]


def _make_event_id() -> str:
    """Generate a unique event_id."""
    return "tip_evt_" + uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Storage (forum/human_tips/)
class HumanTipsPaths:
    """Filesystem layout for human tips."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else Path("C:/MY-Hot-Radar-Bridge/forum")
        self.tips_dir = self.root / "human_tips"

    def tip_dir(self, tip_id: str) -> Path:
        return self.tips_dir / tip_id

    def tip_json(self, tip_id: str) -> Path:
        return self.tip_dir(tip_id) / "tip.json"

    def events_jsonl(self, tip_id: str) -> Path:
        return self.tip_dir(tip_id) / "events.jsonl"

    def ensure_layout(self) -> None:
        self.tips_dir.mkdir(parents=True, exist_ok=True)

    def list_tip_ids(self) -> List[str]:
        if not self.tips_dir.exists():
            return []
        return sorted(
            p.name for p in self.tips_dir.iterdir()
            if p.is_dir() and p.name.startswith("HT_")
        )


class HumanTipsStore:
    """File-backed Human Tips store."""
    _lock = threading.Lock()

    def __init__(self, paths: Optional[HumanTipsPaths] = None):
        self.paths = paths or HumanTipsPaths()
        self.paths.ensure_layout()

    # ---- Tip CRUD ----
    def create_tip(self, *, title: str, description: str = "",
                    source_url: str = "",
                    evidence_urls: Optional[List[str]] = None,
                    priority: str = "MEDIUM",
                    author: str = "hermes",
                    target_agent: str = "radar",
                    tags: Optional[List[str]] = None,
                    payload: Optional[Dict[str, Any]] = None,
                    evidence: Optional[Dict[str, Any]] = None,
                    source_message_id: Optional[str] = None,
                    confidence: float = 1.0,
                    ) -> Tuple[HumanTip, HumanTipEvent]:
        """Create a new Human Tip. Returns (tip, create_event)."""
        if priority not in TIP_PRIORITIES:
            raise TipError(f"invalid_priority:{priority}")
        if target_agent not in ("radar", "default"):
            raise TipError(f"invalid_target_agent:{target_agent}")
        _check_permission(agent=author, event_type=EVT_CREATE_TIP)

        now = _utc_now_iso()
        tip_id = _make_tip_id()
        tip = HumanTip(
            tip_id=tip_id,
            title=title,
            description=description,
            source_url=source_url,
            evidence_urls=list(evidence_urls or []),
            priority=priority,
            status=TIP_OPEN,
            author=author,
            target_agent=target_agent,
            tags=list(tags or []),
            created_at=now,
            updated_at=now,
        )
        # Write tip.json atomically
        _atomic_write_json(self.paths.tip_json(tip_id), tip.to_dict())

        # Write CREATE_TIP event
        evt_payload = dict(payload or {})
        evt_payload.setdefault("title", title)
        evt_payload.setdefault("description", description)
        evt_payload.setdefault("priority", priority)
        if source_url:
            evt_payload.setdefault("source_url", source_url)
        if evidence_urls:
            evt_payload.setdefault("evidence_urls", list(evidence_urls))
        if source_message_id:
            evt_payload["source_message_id"] = source_message_id
        if author == author:
            evt_payload["author"] = author
        evt_payload["target_agent"] = target_agent

        event = HumanTipEvent(
            event_id=_make_event_id(),
            tip_id=tip_id,
            agent=author,
            event_type=EVT_CREATE_TIP,
            timestamp=now,
            payload=evt_payload,
            evidence=dict(evidence or {}),
            confidence=confidence,
        )
        _atomic_append_jsonl(self.paths.events_jsonl(tip_id), event.to_dict())
        return tip, event

    def get_tip(self, tip_id: str) -> Optional[HumanTip]:
        path = self.paths.tip_json(tip_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return HumanTip.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None

    def list_tips(self, status: Optional[str] = None) -> List[HumanTip]:
        ids = self.paths.list_tip_ids()
        out = []
        for tid in ids:
            t = self.get_tip(tid)
            if t is None:
                continue
            if status and t.status != status:
                continue
            out.append(t)
        # Sort by created_at desc
        out.sort(key=lambda t: t.created_at or "", reverse=True)
        return out

    def get_events(self, tip_id: str) -> List[HumanTipEvent]:
        path = self.paths.events_jsonl(tip_id)
        if not path.exists():
            return []
        out = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        out.append(HumanTipEvent(**{
                            k: v for k, v in d.items()
                            if k in HumanTipEvent.__dataclass_fields__
                        }))
                    except (json.JSONDecodeError, TypeError):
                        continue
        except OSError:
            pass
        return out

    def _write_tip(self, tip: HumanTip) -> None:
        tip.updated_at = _utc_now_iso()
        _atomic_write_json(self.paths.tip_json(tip.tip_id), tip.to_dict())

    # ---- Status transitions ----
    def ack_tip(self, tip_id: str, *, agent: str = "radar",
                note: str = "",
                confidence: float = 1.0) -> Tuple[HumanTip, HumanTipEvent]:
        _check_permission(agent=agent, event_type=EVT_ACK_TIP)
        tip = self.get_tip(tip_id)
        if tip is None:
            raise TipNotFoundError(f"tip_not_found:{tip_id}")
        _check_transition(tip.status, TIP_ACKNOWLEDGED)
        tip.status = TIP_ACKNOWLEDGED
        tip.acknowledged_at = _utc_now_iso()
        self._write_tip(tip)
        evt = self._emit_event(tip, agent, EVT_ACK_TIP, note=note, confidence=confidence)
        return tip, evt

    def investigate_tip(self, tip_id: str, *, agent: str = "radar",
                         note: str = "",
                         confidence: float = 1.0) -> Tuple[HumanTip, HumanTipEvent]:
        _check_permission(agent=agent, event_type=EVT_INVESTIGATE_TIP)
        tip = self.get_tip(tip_id)
        if tip is None:
            raise TipNotFoundError(f"tip_not_found:{tip_id}")
        _check_transition(tip.status, TIP_INVESTIGATING)
        tip.status = TIP_INVESTIGATING
        self._write_tip(tip)
        evt = self._emit_event(tip, agent, EVT_INVESTIGATE_TIP, note=note, confidence=confidence)
        return tip, evt

    def link_tip(self, tip_id: str, *, topic_id: str, agent: str = "radar",
                 note: str = "",
                 confidence: float = 1.0) -> Tuple[HumanTip, HumanTipEvent]:
        """Link a tip to a Topic. Can be done by Radar or Default."""
        _check_permission(agent=agent, event_type=EVT_LINK_TIP)
        tip = self.get_tip(tip_id)
        if tip is None:
            raise TipNotFoundError(f"tip_not_found:{tip_id}")
        # LINK_TIP can come from ACKNOWLEDGED, INVESTIGATING, or already LINKED
        if tip.status not in (TIP_ACKNOWLEDGED, TIP_INVESTIGATING, TIP_LINKED):
            _check_transition(tip.status, TIP_LINKED)
        tip.status = TIP_LINKED
        tip.topic_id = topic_id
        tip.linked_at = _utc_now_iso()
        self._write_tip(tip)
        payload: Dict[str, Any] = {"topic_id": topic_id}
        if note:
            payload["note"] = note
        evt = self._emit_event(tip, agent, EVT_LINK_TIP, payload=payload,
                               note=note, confidence=confidence)
        return tip, evt

    def resolve_tip(self, tip_id: str, *, resolution: str,
                    agent: str = "default",
                    note: str = "",
                    topic_id: Optional[str] = None,
                    confidence: float = 1.0) -> Tuple[HumanTip, HumanTipEvent]:
        """Resolve a tip. terminal state."""
        _check_permission(agent=agent, event_type=EVT_RESOLVE_TIP)
        if resolution not in TIP_RESOLUTION_KINDS:
            raise TipError(f"invalid_resolution:{resolution}")
        tip = self.get_tip(tip_id)
        if tip is None:
            raise TipNotFoundError(f"tip_not_found:{tip_id}")
        _check_transition(tip.status, TIP_RESOLVED)
        tip.status = TIP_RESOLVED
        tip.resolution = resolution
        tip.resolution_note = note
        if topic_id:
            tip.topic_id = topic_id
        tip.resolved_at = _utc_now_iso()
        self._write_tip(tip)
        payload: Dict[str, Any] = {"resolution": resolution}
        if note:
            payload["note"] = note
        if topic_id:
            payload["topic_id"] = topic_id
        evt = self._emit_event(tip, agent, EVT_RESOLVE_TIP, payload=payload,
                               note=note, confidence=confidence)
        return tip, evt

    def add_report(self, tip_id: str, *, agent: str = "mhr_performance",
                   velocity: str = "", engagement: str = "",
                   window: str = "24h",
                   note: str = "",
                   confidence: float = 1.0) -> Tuple[HumanTip, HumanTipEvent]:
        """Add a Performance TIP_REPORT to a tip."""
        _check_permission(agent=agent, event_type=EVT_TIP_REPORT)
        tip = self.get_tip(tip_id)
        if tip is None:
            raise TipNotFoundError(f"tip_not_found:{tip_id}")
        payload = {"velocity": velocity, "engagement": engagement, "window": window}
        if note:
            payload["note"] = note
        evt = self._emit_event(tip, agent, EVT_TIP_REPORT, payload=payload,
                               note=note, confidence=confidence)
        return tip, evt

    def _emit_event(self, tip: HumanTip, agent: str, event_type: str,
                    *, payload: Optional[Dict[str, Any]] = None,
                    note: str = "",
                    confidence: float = 1.0) -> HumanTipEvent:
        full_payload = dict(payload or {})
        if note and "note" not in full_payload:
            full_payload["note"] = note
        event = HumanTipEvent(
            event_id=_make_event_id(),
            tip_id=tip.tip_id,
            agent=agent,
            event_type=event_type,
            timestamp=_utc_now_iso(),
            payload=full_payload,
            confidence=confidence,
        )
        _atomic_append_jsonl(self.paths.events_jsonl(tip.tip_id), event.to_dict())
        return event


# ---------------------------------------------------------------------------
# Idempotency helper for Human Tip
def compute_tip_key(*, title: str, source_url: str = "",
                    author: str = "hermes") -> str:
    """Deterministic key for Human Tip idempotency."""
    import hashlib
    raw = f"{author}|{title}|{source_url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


# ---------------------------------------------------------------------------
# CLI for testing
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--forum-root", default=r"C:\MY-Hot-Radar-Bridge\forum")
    parser.add_argument("command", choices=["create", "list", "show"])
    parser.add_argument("--tip-id", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--description", default="")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--priority", default="MEDIUM")
    args = parser.parse_args()

    paths = HumanTipsPaths(Path(args.forum_root))
    store = HumanTipsStore(paths)

    if args.command == "create":
        if not args.title:
            print("ERROR: --title required")
            sys.exit(1)
        tip, evt = store.create_tip(
            title=args.title,
            description=args.description,
            source_url=args.source_url,
            priority=args.priority,
        )
        print(f"Created: tip_id={tip.tip_id}, event_id={evt.event_id}")
    elif args.command == "list":
        tips = store.list_tips()
        for t in tips:
            print(f"  {t.tip_id}  [{t.status}]  {t.priority}  {t.title}")
    elif args.command == "show":
        if not args.tip_id:
            print("ERROR: --tip-id required")
            sys.exit(1)
        tip = store.get_tip(args.tip_id)
        if tip is None:
            print(f"NOT FOUND: {args.tip_id}")
        else:
            print(json.dumps(tip.to_dict(), ensure_ascii=False, indent=2))