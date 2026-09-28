"""
Report writer: emits two artefacts per scan:
  radar_data/latest.json  - machine-readable
  radar_data/latest.md    - human-readable

The markdown must never claim data we don't actually have. Topics that come
only from synthetic fixtures are explicitly labeled.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from .models import (
    Topic, Story, Status, VerificationStatus,
)
from .thresholds import RADAR_REPORT_TOP_N


STATUS_ORDER = [
    Status.BREAKING, Status.RISING, Status.HOT, Status.WATCH, Status.COOLING,
]


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def write_report(
    *,
    radar_dir: Path,
    topics: List[Topic],
    source_status: List[dict],
    all_stories: List[Story],
    history_by_id: Dict,
) -> Dict[str, str]:
    radar_dir = Path(radar_dir)
    radar_dir.mkdir(parents=True, exist_ok=True)

    # Order topics: BREAKING -> RISING -> HOT -> WATCH -> COOLING, then
    # within a bucket, by mention_count desc.
    def bucket(t: Topic) -> int:
        return STATUS_ORDER.index(t.status) if t.status in STATUS_ORDER else len(STATUS_ORDER)
    sorted_topics = sorted(topics, key=lambda t: (bucket(t), -t.mention_count))

    summary = {
        "generated_at": _now_stamp(),
        "stories_seen": len(all_stories),
        "topics_produced": len(topics),
        "source_status": source_status,
        "topics": [t.to_dict() for t in sorted_topics[:RADAR_REPORT_TOP_N]],
    }

    json_path = radar_dir / "latest.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = radar_dir / "latest.md"
    md_path.write_text(render_markdown(summary), encoding="utf-8")

    return {"json": str(json_path), "md": str(md_path)}


def render_markdown(summary: dict) -> str:
    lines = []
    push(lines, "# MY HOT RADAR")
    push(lines, f"Scan: {summary['generated_at']}")
    push(lines, f"Stories seen: {summary['stories_seen']}    "
                f"Topics produced: {summary['topics_produced']}")
    push(lines, "")

    src_ok = sum(1 for s in summary["source_status"] if s.get("ok"))
    src_fail = sum(1 for s in summary["source_status"] if not s.get("ok"))
    push(lines, f"Sources: {src_ok} ok, {src_fail} failed")
    for s in summary["source_status"]:
        status = "OK" if s.get("ok") else "FAIL"
        reason = ""
        if not s.get("ok"):
            reason = f" — {s.get('error', 'unknown')}"
        push(lines, f"  - {s['name']} ({s['type']}) → {status}"
                     f"  fetched={s.get('fetched', 0)}{reason}")
    push(lines, "")

    if not summary["topics"]:
        push(lines, "_No topics produced in this scan._")
        return "\n".join(lines) + "\n"

    by_status: Dict[Status, List[dict]] = {s: [] for s in STATUS_ORDER}
    for t in summary["topics"]:
        st = Status(t["status"]) if isinstance(t["status"], str) else t["status"]
        by_status.setdefault(st, []).append(t)

    for status in STATUS_ORDER:
        bucket_topics = by_status.get(status, [])
        if not bucket_topics:
            continue
        push(lines, f"## {status.value}")
        push(lines, "")
        for i, t in enumerate(bucket_topics, 1):
            ver = t["verification"]
            mom = t["momentum"]
            growth = _fmt_growth(mom)
            ev_count = ver.get("independent_sources", 0)
            push(lines, f"### {i}. {t['title']}")
            push(lines, f"   {growth} · {t['mention_count']} mentions · "
                         f"{ev_count} independent sources ({ver.get('raw_source_count', ev_count)} total) · {ver['status']}")
            push(lines, f"   category: {t['category']}")
            if t.get("classification_reasons"):
                push(lines, f"   rationale: {' / '.join(t['classification_reasons'])}")
            if ver.get("reasons"):
                push(lines, f"   verification: {' / '.join(ver['reasons'])}")
            if t.get("related_urls"):
                sample = t["related_urls"][:3]
                push(lines, f"   sources: " + ", ".join(sample))
            push(lines, "")

    return "\n".join(lines) + "\n"


def _fmt_growth(mom: dict) -> str:
    if mom.get("is_new"):
        return "NEW"
    rate = mom.get("growth_rate")
    if rate is None:
        # previous 0 and current 0 -> no change
        return "±0%"
    sign = "+" if rate >= 0 else ""
    return f"{sign}{rate:.1f}%"


def push(lines: list, s: str) -> None:
    lines.append(s)
