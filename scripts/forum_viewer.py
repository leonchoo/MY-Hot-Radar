#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MY Hot Radar — Forum v2 Newsroom Thread Viewer.

Phase 5 — 中文 Newsroom 只读 Viewer。

这是一个 Python stdlib-only HTTP server,提供:
  * 首页: Topic 列表 (中文优先)
  * Topic Thread 页面: 完整事件时间线
  * JSON API:
      GET /api/topics                  → 所有 topics 摘要
      GET /api/topics/<topic_id>       → 单个 topic + events
      GET /api/dashboard               → dashboard 聚合统计

设计原则:
  * 完全只读 — 永远不会修改 forum/topics/ 或 forum/dashboard/
  * Python stdlib only (http.server, json, urllib, pathlib)
  * 中文优先,英文 fallback,不编造
  * Machine schema / enum / agent IDs 保持英文

使用:
    python scripts/forum_viewer.py [--port 8080] [--forum-root /c/MY-Hot-Radar-Bridge/forum]
    浏览器访问 http://localhost:8080/
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
VIEWER_DIR = HERE.parent / "forum" / "viewer"

sys.path.insert(0, str(HERE))
import forum_v2  # noqa: E402
import forum_i18n  # noqa: E402


# ---------------------------------------------------------------------------
# UI 标签 (中文 label, machine value 不变)
# ---------------------------------------------------------------------------

AGENT_LABELS: Dict[str, str] = {
    "collector": "Collector",
    "radar": "Radar",
    "default": "MHR Default",
    "mhr_performance": "MHR Performance",
}

AGENT_COLORS: Dict[str, str] = {
    "collector": "#16a34a",     # green
    "radar": "#2563eb",         # blue
    "default": "#9333ea",       # purple
    "mhr_performance": "#ea580c",  # orange
}

CLASSIFICATION_LABELS: Dict[str, str] = {
    "BREAKING": "突发",
    "RISING": "上升",
    "HOT": "热门",
    "COOLING": "降温",
    "WATCH": "关注",
}

STATUS_LABELS: Dict[str, str] = {
    "NEW": "新发现",
    "RADAR_TRACKING": "Radar 跟踪中",
    "EDITORIAL_REVIEW": "编辑审核",
    "PUBLISHED": "已发布",
    "MONITORING": "持续监测",
    "FOLLOW_UP": "后续跟进",
    "REACTIVATED": "重新升温",
    "CLOSED": "已关闭",
}

EVENT_TYPE_LABELS: Dict[str, str] = {
    "CREATE_TOPIC": "创建 Topic",
    "OBSERVATION": "观察记录",
    "SOCIAL_HEAT_SIGNAL": "社交热度信号",
    "REACTIVATION_SIGNAL": "重新升温信号",
    "EVIDENCE": "证据",
    "SOURCE_UPDATE": "来源更新",
    "TOPIC_UPDATE": "Topic 更新",
    "CROSS_SOURCE_CONFIRMATION": "多来源确认",
    "MOMENTUM_UPDATE": "热度变化",
    "CLASSIFICATION_UPDATE": "分类变更",
    "PUBLISH": "发布决定",
    "UPDATE_ARTICLE": "更新文章",
    "EDITORIAL_REVIEW": "编辑审核",
    "FOLLOW_UP": "后续跟进",
    "MONITOR": "持续监测",
    "CLOSE": "关闭 Topic",
    "PERFORMANCE_REPORT": "传播表现报告",
    "VELOCITY_UPDATE": "速度更新",
    "ENGAGEMENT_UPDATE": "互动更新",
    "SUSTAINED_SIGNAL": "持续热度信号",
    "COOLING_SIGNAL": "降温信号",
}


# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------

def render_topic_title(topic: Dict[str, Any]) -> Dict[str, str]:
    """Render Topic title with Chinese priority.

    Returns a dict:
        {
          "primary": "zh title (or fallback to en)",
          "secondary": "en title if zh was used (else null)"
        }
    """
    title_i18n = topic.get("title_i18n") or {}
    if isinstance(title_i18n, dict):
        zh = title_i18n.get("zh") or ""
        en = title_i18n.get("en") or ""
    else:
        zh = ""
        en = ""
    if not zh:
        zh = topic.get("title", "") or ""
        en = ""
    elif topic.get("title", "") and topic.get("title") != zh:
        en = topic.get("title", "")
    return {"primary": zh, "secondary": en or None}


def render_event_note(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract human-readable content from an Event payload.

    Priority: zh > en > nothing (NEVER fabricate).

    Looks for these field names in order:
      * note (collector / radar / default / performance)
      * summary
      * reason
      * decision
      * change_summary

    For each: prefer the .zh value of a bilingual; fall back to .en.
    """
    fields = ["note", "summary", "reason", "decision", "change_summary"]
    out: Dict[str, Any] = {"primary": "", "primary_lang": None, "secondary": None}
    for field in fields:
        value = payload.get(field) if isinstance(payload, dict) else None
        if value is None:
            continue
        if isinstance(value, dict):
            zh = value.get("zh") or ""
            en = value.get("en") or ""
        elif isinstance(value, str):
            zh = ""
            en = value
        else:
            continue
        if zh:
            if not out["primary"]:
                out["primary"] = zh
                out["primary_lang"] = "zh"
            elif out["primary_lang"] == "en":
                out["secondary"] = zh
        elif en:
            if not out["primary"]:
                out["primary"] = en
                out["primary_lang"] = "en"
    return out


def render_evidence_summary(evidence: Any) -> Optional[str]:
    """Return a human-readable evidence summary if evidence is non-empty."""
    if not isinstance(evidence, dict) or not evidence:
        return None
    parts = []
    if evidence.get("source"):
        parts.append(f"来源：{evidence['source']}")
    if evidence.get("source_name"):
        parts.append(f"来源：{evidence['source_name']}")
    if evidence.get("source_url"):
        parts.append(f"URL：{evidence['source_url']}")
    if evidence.get("post_url"):
        parts.append(f"Post URL：{evidence['post_url']}")
    if evidence.get("heat_score") is not None:
        parts.append(f"热度评分：{evidence['heat_score']}")
    if evidence.get("source_message_id"):
        parts.append(f"Message ID：{evidence['source_message_id']}")
    return " · ".join(parts) if parts else None


def extract_urls_from_payload(payload: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """Find URL fields in payload and evidence."""
    urls = []
    candidates = [
        ("url", "source_url"),
        ("source_url", "source_url"),
        ("canonical_url", "article"),
        ("post_url", "post_url"),
    ]
    for payload_key, label in candidates:
        v = payload.get(payload_key) if isinstance(payload, dict) else None
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            urls.append({"label": label, "url": v})
    if isinstance(evidence, dict):
        for key in ("source_url", "post_url", "url"):
            v = evidence.get(key)
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                if not any(u["url"] == v for u in urls):
                    urls.append({"label": key, "url": v})
    return urls


def build_lifecycle_stages(events: List[Dict[str, Any]], current_status: str) -> List[Dict[str, Any]]:
    """Build lifecycle strip from real events.

    Each stage has machine value, label, and reached status.
    """
    lifecycle_order = [
        "NEW", "RADAR_TRACKING", "EDITORIAL_REVIEW",
        "PUBLISHED", "MONITORING", "REACTIVATED",
        "FOLLOW_UP", "CLOSED",
    ]
    # Track which stages have been entered (look at next_status on append_event
    # calls; if not present, derive from event_type).
    seen_stages = {"NEW": False, "RADAR_TRACKING": False, "EDITORIAL_REVIEW": False,
                   "PUBLISHED": False, "MONITORING": False, "REACTIVATED": False,
                   "FOLLOW_UP": False, "CLOSED": False}
    seen_stages["NEW"] = True  # Every Topic starts at NEW
    for e in events:
        evt_type = e.get("event_type")
        # Heuristics for which lifecycle stages each event_type implies
        type_to_stage = {
            "CREATE_TOPIC": None,  # stays NEW
            "SOURCE_UPDATE": "RADAR_TRACKING",
            "TOPIC_UPDATE": "RADAR_TRACKING",
            "CLASSIFICATION_UPDATE": "RADAR_TRACKING",
            "CROSS_SOURCE_CONFIRMATION": "RADAR_TRACKING",
            "MOMENTUM_UPDATE": "RADAR_TRACKING",
            "EDITORIAL_REVIEW": "EDITORIAL_REVIEW",
            "PUBLISH": "PUBLISHED",
            "MONITOR": "MONITORING",
            "UPDATE_ARTICLE": None,
            "FOLLOW_UP": "FOLLOW_UP",
            "CLOSE": "CLOSED",
            "REACTIVATION_SIGNAL": "REACTIVATED",
            "SOCIAL_HEAT_SIGNAL": "REACTIVATED",
            "PERFORMANCE_REPORT": None,
            "OBSERVATION": None,
            "EVIDENCE": None,
        }
        stage = type_to_stage.get(evt_type)
        if stage:
            seen_stages[stage] = True

    out = []
    for stage in lifecycle_order:
        out.append({
            "machine": stage,
            "label": STATUS_LABELS.get(stage, stage),
            "reached": seen_stages.get(stage, False),
            "current": stage == current_status,
        })
    return out


def topic_to_api_dict(topic_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Topic to its API representation."""
    title_rendered = render_topic_title(topic_dict)
    return {
        "topic_id": topic_dict.get("topic_id"),
        "title": topic_dict.get("title"),
        "title_rendered": title_rendered,
        "title_i18n": topic_dict.get("title_i18n"),
        "status": topic_dict.get("status"),
        "status_label": STATUS_LABELS.get(topic_dict.get("status", ""), topic_dict.get("status", "")),
        "classification": topic_dict.get("classification"),
        "classification_label": CLASSIFICATION_LABELS.get(topic_dict.get("classification", ""), topic_dict.get("classification", "")),
        "first_seen": topic_dict.get("first_seen"),
        "last_seen": topic_dict.get("last_seen") or topic_dict.get("updated_at"),
        "source_count": topic_dict.get("source_count", 0),
        "languages": topic_dict.get("languages", []),
        "participants": topic_dict.get("participants", []),
        "events_count": topic_dict.get("events_count", 0),
        "tags": topic_dict.get("tags", []),
        "linkage_key": topic_dict.get("linkage_key"),
    }


def event_to_api_dict(event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an Event to its API representation."""
    payload = event_dict.get("payload", {})
    evidence = event_dict.get("evidence", {})
    return {
        "event_id": event_dict.get("event_id"),
        "topic_id": event_dict.get("topic_id"),
        "agent": event_dict.get("agent"),
        "agent_label": AGENT_LABELS.get(event_dict.get("agent", ""), event_dict.get("agent", "")),
        "agent_color": AGENT_COLORS.get(event_dict.get("agent", ""), "#6b7280"),
        "event_type": event_dict.get("event_type"),
        "event_type_label": EVENT_TYPE_LABELS.get(
            event_dict.get("event_type", ""),
            event_dict.get("event_type", "")
        ),
        "timestamp": event_dict.get("timestamp"),
        "confidence": event_dict.get("confidence"),
        "payload": payload,
            "note_rendered": render_event_note(payload),
        "urls": extract_urls_from_payload(payload, evidence),
        "evidence_summary": render_evidence_summary(evidence),
        "evidence": evidence,
        "is_reactivation": event_dict.get("event_type") in ("REACTIVATION_SIGNAL", "SOCIAL_HEAT_SIGNAL"),
    }


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

def get_topics_api(paths: forum_v2.ForumV2Paths) -> Dict[str, Any]:
    """GET /api/topics — list all topics with summary."""
    topics = forum_v2.list_topics(paths=paths)
    api_topics = []
    for t in topics:
        td = t.to_dict()
        api_topics.append(topic_to_api_dict(td))
    # Sort by last_seen desc
    api_topics.sort(key=lambda x: (x.get("last_seen") or ""), reverse=True)
    return {
        "schema_version": "forum/viewer-v1",
        "topics": api_topics,
        "total": len(api_topics),
    }


def get_topic_detail_api(topic_id: str, paths: forum_v2.ForumV2Paths) -> Optional[Dict[str, Any]]:
    """GET /api/topics/<id> — topic + chronological events."""
    topic = forum_v2.get_topic(topic_id, paths=paths)
    if topic is None:
        return None
    topic_dict = topic.to_dict()
    events = forum_v2.get_events(topic_id, paths=paths)
    api_events = [event_to_api_dict(e.to_dict()) for e in events]
    # Sort ASC by timestamp
    api_events.sort(key=lambda e: (e.get("timestamp") or ""))
    return {
        "schema_version": "forum/viewer-v1",
        "topic": topic_to_api_dict(topic_dict),
        "events": api_events,
        "lifecycle": build_lifecycle_stages([e.to_dict() for e in events], topic_dict.get("status", "NEW")),
        "total_events": len(api_events),
    }


def get_dashboard_api(paths: forum_v2.ForumV2Paths) -> Dict[str, Any]:
    """GET /api/dashboard — aggregate stats from live topics."""
    topics = forum_v2.list_topics(paths=paths)
    by_status: Dict[str, int] = {}
    by_classification: Dict[str, int] = {}
    by_agent: Dict[str, int] = {}
    total = 0
    for t in topics:
        total += 1
        s = t.status or "UNKNOWN"
        by_status[s] = by_status.get(s, 0) + 1
        c = t.classification or "UNKNOWN"
        by_classification[c] = by_classification.get(c, 0) + 1
        for a in (t.participants or []):
            by_agent[a] = by_agent.get(a, 0) + 1
    return {
        "schema_version": "forum/viewer-v1",
        "total_topics": total,
        "by_status": by_status,
        "by_classification": by_classification,
        "by_agent_participation": by_agent,
        "classification_labels": CLASSIFICATION_LABELS,
        "status_labels": STATUS_LABELS,
    }


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class ViewerHTTPHandler(BaseHTTPRequestHandler):
    forum_paths: forum_v2.ForumV2Paths = None  # set per server instance
    viewer_dir: Path = None  # set per server instance

    def log_message(self, format, *args):
        # quieter log
        sys.stderr.write(f"[viewer] {self.address_string()} - {format % args}\n")

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self._send_json(404, {"error": "not_found", "path": str(path)})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _route(self, parsed) -> None:
        path = parsed.path

        # API
        if path == "/api/topics":
            self._send_json(200, get_topics_api(self.forum_paths))
            return
        if path.startswith("/api/topics/"):
            tid = path[len("/api/topics/"):]
            tid = tid.split("/")[0]
            data = get_topic_detail_api(tid, self.forum_paths)
            if data is None:
                self._send_json(404, {"error": "topic_not_found", "topic_id": tid})
            else:
                self._send_json(200, data)
            return
        if path == "/api/dashboard":
            self._send_json(200, get_dashboard_api(self.forum_paths))
            return

        # Static files (HTML)
        if path == "/" or path == "/index.html":
            self._send_file(self.viewer_dir / "index.html", "text/html; charset=utf-8")
            return
        if path == "/topic.html":
            self._send_file(self.viewer_dir / "topic.html", "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            rel_file = path[len("/static/"):]
            # disallow path traversal
            if ".." in rel_file or "/" in rel_file:
                self._send_json(403, {"error": "forbidden"})
                return
            self._send_file(self.viewer_dir / rel_file, "text/css; charset=utf-8")
            return
        if path == "/labels.json":
            self._send_json(200, {
                "agents": AGENT_LABELS,
                "classifications": CLASSIFICATION_LABELS,
                "statuses": STATUS_LABELS,
                "event_types": EVENT_TYPE_LABELS,
                "agent_colors": AGENT_COLORS,
            })
            return

        self._send_json(404, {"error": "not_found", "path": path})

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            self._route(parsed)
        except Exception as e:
            self._send_json(500, {"error": "internal_error", "message": str(e)})


def make_handler(forum_paths: forum_v2.ForumV2Paths, viewer_dir: Path):
    class _Handler(ViewerHTTPHandler):
        pass
    _Handler.forum_paths = forum_paths
    _Handler.viewer_dir = viewer_dir
    return _Handler


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Forum v2 Newsroom Viewer")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--forum-root",
        default=r"C:\MY-Hot-Radar-Bridge\forum",
        help="Forum v2 root path (READ-ONLY)",
    )
    parser.add_argument(
        "--viewer-dir",
        default=str(VIEWER_DIR),
        help="Static viewer assets directory",
    )
    args = parser.parse_args(argv)

    forum_paths = forum_v2.ForumV2Paths(Path(args.forum_root))
    viewer_dir = Path(args.viewer_dir)
    if not viewer_dir.exists():
        print(f"viewer dir not found: {viewer_dir}", file=sys.stderr)
        return 1
    handler = make_handler(forum_paths, viewer_dir)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Forum Newsroom Viewer: http://{args.host}:{args.port}/")
    print(f"  Forum root (READ-ONLY): {args.forum_root}")
    print(f"  Viewer assets: {args.viewer_dir}")
    print(f"  Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())