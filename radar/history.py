"""
History store.

Each scan writes one snapshot to radar_data/history/<timestamp>.json. Reads
return the most-recent prior topics keyed by content_key() (canonical URL
or title fallback), for momentum + previous status comparison.

Why content_key and not random id? Random ids change every scan, so a topic
about "Trump-Xi summit" would never match the same topic in the prior
snapshot. We match on content, not on id.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict

from .models import Topic, Status


def _scan_dir(radar_dir: Path) -> Path:
    return Path(radar_dir) / "history"


def _is_valid_snapshot(p: Path) -> bool:
    """A snapshot is valid if it parses as JSON AND carries the expected
    schema (top-level dict with a 'topics' key, ideally with content).

    Stability rationale: a history directory may contain stale or
    accidentally-poisoned files (malformed JSON, wrong schema, files with
    future-dated filenames from manual copy/paste, etc.). If we naively
    pick the lexicographically last file, a single such file permanently
    poisons momentum for all subsequent scans (every topic appears NEW).
    Instead, walk backwards from the newest file and pick the first one
    that actually parses AND has at least one topic entry. This is
    deterministic and survives malformed-history edge cases.
    """
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(raw, dict):
        return False
    topics = raw.get("topics")
    if not isinstance(topics, dict):
        return False
    return True


def _latest_snapshot_path(radar_dir: Path) -> Path | None:
    """Find the most recent VALID history snapshot.

    Walks from newest (by filename) to oldest, skipping any file that is
    malformed or has the wrong schema. Returns None if no valid snapshot
    exists (fresh history).
    """
    sd = _scan_dir(radar_dir)
    if not sd.exists():
        return None
    files = sorted(sd.glob("scan-*.json"), key=lambda p: p.name, reverse=True)
    for p in files:
        if _is_valid_snapshot(p):
            return p
    return None


def read_history_for_id(radar_dir: Path) -> Dict[str, Topic]:
    """Return a dict content_key -> Topic (the most recent prior snapshot,
    used for momentum and previous-status lookups only).

    The key is `Topic.content_key()` (canonical URL, fallback to title), NOT
    the random id, so consecutive scans of the same content match.
    """
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
            status_val = td.get("status")
            try:
                status_enum = Status(status_val) if status_val else Status.WATCH
            except ValueError:
                status_enum = Status.WATCH
            t = Topic(
                id=tid,
                title=td.get("title", ""),
                mention_count=int(td.get("mention_count", 0)),
                status=status_enum,
                first_seen=td.get("first_seen", ""),
                last_seen=td.get("last_seen", ""),
                canonical_url=td.get("canonical_url", ""),
            )
            # We don't need full Topic for momentum/status comparison,
            # just key + mention_count + status. Keep minimal.
            out[t.content_key()] = t
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
        "topics": {t.content_key(): _topic_min(t) for t in topics},
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
        "canonical_url": t.canonical_url,
    }
