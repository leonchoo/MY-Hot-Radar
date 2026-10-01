#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Runtime Adapter.

Phase 6 MHR Newsroom Runtime.

Wraps the REAL Radar production scheduler:
    radar.scheduler.run_once(radar_dir=...)

The scheduler produces topics/stories internally; we extract those
and write Forum v2 SOURCE_UPDATE / CROSS_SOURCE_CONFIRMATION /
CLASSIFICATION_UPDATE / MOMENTUM_UPDATE events.

Important constraints (per Phase 6 spec):
  * DO NOT modify radar/dedup.py, normalize.py, thresholds.py
  * DO NOT modify radar/scheduler.py
  * We ONLY CALL run_once() and READ its return value
  * We DO NOT generate synthetic cross-source / momentum events —
    we mirror only what the REAL scheduler actually produced
  * Forum write failures DO NOT raise into the radar run
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import forum_v2  # noqa: E402
import forum_integration  # noqa: E402
import runtime_state  # noqa: E402
from runtime_adapters import AdapterResult, utc_now_iso, append_event_safe  # noqa: E402


@dataclass
class RadarOutput:
    """Snapshot of Radar run results we care about."""
    scan_id: str
    topic_count: int
    story_count: int
    successful_sources: int
    failed_sources: int
    topics: List[Dict[str, Any]] = None
    stories: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.topics is None:
            self.topics = []
        if self.stories is None:
            self.stories = []


def extract_radar_output(exec_record, run_scan_internals: Optional[Dict] = None) -> RadarOutput:
    """Pull a RadarOutput from an ExecutionRecord and optional internals."""
    out = RadarOutput(
        scan_id=getattr(exec_record, "scan_id", ""),
        topic_count=int(getattr(exec_record, "topic_count", 0)),
        story_count=int(getattr(exec_record, "story_count", 0)),
        successful_sources=int(getattr(exec_record, "successful_sources", 0)),
        failed_sources=int(getattr(exec_record, "failed_sources", 0)),
    )
    if run_scan_internals:
        # run_scan(... return_internals=True) returns dict with 'stories' list
        out.stories = run_scan_internals.get("stories", []) or []
        out.topics = run_scan_internals.get("topics", []) or []
    return out


def build_payload_from_radar_topic(radar_topic: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Radar topic to a Forum v2 SOURCE_UPDATE payload (real fields only)."""
    payload = {
        "title": radar_topic.get("title", ""),
        "classification": radar_topic.get("classification", ""),
        "language": radar_topic.get("language", ""),
    }
    # Real fields only
    if radar_topic.get("url"):
        payload["url"] = radar_topic["url"]
    if radar_topic.get("canonical_url"):
        payload["canonical_url"] = radar_topic["canonical_url"]
    if radar_topic.get("source_name"):
        payload["source_name"] = radar_topic["source_name"]
    if radar_topic.get("source_url"):
        payload["source_url"] = radar_topic["source_url"]
    if radar_topic.get("topics_index") is not None:
        payload["radar_topic_index"] = radar_topic["topics_index"]
    return payload


def run_radar_runtime(
    *,
    radar_dir: Optional[Path] = None,
    forum_paths: Optional[forum_v2.ForumV2Paths] = None,
    run_id: Optional[str] = None,
    inject_fixture: bool = False,
) -> AdapterResult:
    """Run the Radar adapter.

    1. Calls radar.scheduler.run_once() — REAL production path.
    2. Reads the execution_log.jsonl and finds stories for the run.
    3. Writes Forum v2 events for each story/topic.

    Forum failures never raise.
    """
    started = utc_now_iso()
    run_id = run_id or runtime_state.make_run_id(runtime_state.AGENT_RADAR)
    paths = forum_paths or forum_v2.ForumV2Paths()

    result = AdapterResult(
        agent=runtime_state.AGENT_RADAR,
        run_id=run_id,
        started_at=started,
        finished_at=started,
        status=runtime_state.OK,
    )

    # Import Radar runtime (do not modify)
    try:
        import radar.scheduler as rs
    except ImportError as e:
        result.status = runtime_state.SKIPPED
        result.agent_error = f"radar_unavailable:{e}"
        result.notes.append("radar_import_failed")
        result.finished_at = utc_now_iso()
        return result

    # Run Radar (real)
    try:
        kwargs = {"inject_fixture": inject_fixture}
        if radar_dir is not None:
            kwargs["radar_dir"] = radar_dir
        exec_record = rs.run_once(**kwargs)
        result.topics_processed = int(getattr(exec_record, "topic_count", 0))
    except Exception as e:
        result.status = runtime_state.FAILED
        result.agent_error = f"{type(e).__name__}:{e}"
        result.finished_at = utc_now_iso()
        return result

    # Determine if Radar actually succeeded
    exec_status = getattr(exec_record, "status", None)
    # exec_status may be a string ("SUCCESS") or an Enum
    status_str = exec_status.value if hasattr(exec_status, "value") else exec_status
    if status_str and status_str != "SUCCESS":
        result.agent_error = f"radar_status:{status_str}"
        # Continue to Forum side: don't fail the runtime

    # Extract topics for Forum bridging from the radar production output
    # We read radar_data/output/latest.json (this is the radar's public
    # snapshot, not its core)
    if radar_dir is None:
        radar_dir = Path("C:/MY-Hot-Radar/radar_data")
    output_path = radar_dir / "output" / "latest.json"

    radar_topics = []
    if output_path.exists():
        try:
            data = json.loads(output_path.read_text(encoding="utf-8"))
            radar_topics = data.get("topics", []) or []
        except (json.JSONDecodeError, OSError) as e:
            result.notes.append(f"output_read_failed:{type(e).__name__}")

    # Track which forum Topic IDs were created/seen
    forum_topic_ids = set()
    cross_source_count = 0

    for radar_topic in radar_topics:
        title = radar_topic.get("title") or ""
        if not title:
            continue
        source_url = (
            radar_topic.get("canonical_url")
            or radar_topic.get("url")
            or radar_topic.get("source_url")
            or ""
        )
        source_name = radar_topic.get("source_name") or ""
        language = radar_topic.get("language") or "en"
        try:
            topic, _evt, was_reactivated = forum_integration.radar_emit_source_update(
                radar_topic_id=radar_topic.get("topic_id", ""),
                title=title,
                source_url=source_url,
                source_name=source_name,
                language=language,
                source_message_id=f"radar:{exec_record.scan_id}:{radar_topic.get('topic_id', '')}",
                paths=paths,
            )
            forum_topic_ids.add(topic.topic_id)
            if was_reactivated:
                result.notes.append(f"reactivated:{topic.topic_id}")
            result.forum_events_written += 1
        except Exception as e:
            result.forum_error = f"{type(e).__name__}:{e}"
            result.forum_sync_status = runtime_state.SYNC_FAILED
            result.notes.append(f"source_update_failed:{title[:30]}:{str(e)[:80]}")

    # Emit CROSS_SOURCE_CONFIRMATION only when the SAME topic title appears
    # in multiple radar sources (real cross-source signal).
    title_to_topics: Dict[str, List[Dict]] = {}
    for rt in radar_topics:
        t = rt.get("title") or ""
        if t:
            title_to_topics.setdefault(t, []).append(rt)
    for title, sources in title_to_topics.items():
        if len(sources) >= 2:
            # Find a Forum Topic by linkage_key (title-based)
            linkage = forum_v2.normalize_linkage_key(title)
            forum_topic = forum_v2.find_topic_by_linkage(linkage, paths=paths)
            if forum_topic is None:
                continue
            # Emit one CROSS_SOURCE_CONFIRMATION per additional source
            for extra in sources[1:]:
                try:
                    forum_integration.radar_emit_cross_source_confirmation(
                        topic_id=forum_topic.topic_id,
                        source_url=extra.get("canonical_url", "") or extra.get("url", ""),
                        source_name=extra.get("source_name", ""),
                        paths=paths,
                    )
                    cross_source_count += 1
                    result.forum_events_written += 1
                except Exception as e:
                    result.forum_error = f"{type(e).__name__}:{e}"
                    result.forum_sync_status = runtime_state.SYNC_FAILED
                    result.notes.append(f"cross_source_failed:{title[:30]}:{str(e)[:80]}")

    result.notes.append(f"radar_scan_id:{exec_record.scan_id}")
    result.notes.append(f"radar_topics:{exec_record.topic_count}")
    result.notes.append(f"radar_stories:{exec_record.story_count}")
    result.notes.append(f"cross_source_pairs:{cross_source_count}")
    result.finished_at = utc_now_iso()

    if result.forum_error and result.forum_events_written == 0:
        result.status = runtime_state.FAILED
    return result


if __name__ == "__main__":
    paths = forum_v2.ForumV2Paths()
    r = run_radar_runtime(forum_paths=paths)
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))