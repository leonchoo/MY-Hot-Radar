"""
History store.

Each scan writes one snapshot to radar_data/history/<timestamp>.json. Reads
return the most-recent prior topics keyed by id (for momentum + previous
status), so the current scan can compare against the prior snapshot.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict

from .models import Topic


def _scan_dir(radar_dir: Path) -> Path:
    return Path(radar_dir) / "history"


def _latest_snapshot_path(radar_dir: Path) -> Path | None:
    sd = _scan_dir(radar_dir)
    if not sd.exists():
        return None
    files = sorted(sd.glob("scan-*.json"), key=lambda p: p.name)
    return files[-1] if files else None


def read_history_for_id(radar_dir: Path) -> Dict[str, Topic]:
    """Return a dict topic_id -> Topic (the most recent prior snapshot, used
    for momentum and previous-status lookups only)."""
    p = _latest_snapshot_path(Path(radar_dir))
    if p is None:
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: Dict[str, Topic] = {}
    for tid, td in raw.get("topics", {}).items():
        try:
            t = Topic(
                id=tid,
                title=td.get("title", ""),
                mention_count=int(td.get("mention_count", 0)),
                status=Status(td["status"]) if td.get("status") else Status.WATCH,
                first_seen=td.get("first_seen", ""),
                last_seen=td.get("last_seen", ""),
            )
            # We don't need full Topic for momentum/status comparison,
            # just id/mention_count/status. Keep minimal.
            out[tid] = t
        except Exception:
            continue
    return out


def save_scan(radar_dir: Path, topics, scan_meta: dict) -> Path:
    """Persist this scan's snapshot.

    Idempotent-ish: writes one file per call, never overwrites. The most
    recent file is the live "previous scan" for the next run.
    """
    sd = _scan_dir(Path(radar_dir))
    sd.mkdir(parents=True, exist_ok=True)
    ts = scan_meta.get("started_at", "unknown").replace(":", "")
    safe = ts.replace("/", "-")
    target = sd / f"scan-{safe}.json"
    payload = {
        "meta": scan_meta,
        "topics": {t.id: _topic_min(t) for t in topics},
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _topic_min(t: Topic) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "mention_count": t.mention_count,
        "status": t.status.value if hasattr(t.status, "value") else str(t.status),
        "first_seen": t.first_seen,
        "last_seen": t.last_seen,
        "category": t.category.value if hasattr(t.category, "value") else str(t.category),
    }
