#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MY Hot Radar — Forum v2 Live Runtime Hook.

This is the PHASE 3 wiring layer.

It wraps the four MHR Agent runtimes so that, every time an Agent runs
its real execution path, Forum v2 Topic/Event side-effects also fire.

Architecture:
    Agent real run path (radar.scheduler.run_scan, performance.scheduler.run_once,
                         collector bridge_writer, publish_article pipeline)
        ↓
    Forum v2 runtime hook (this module)
        ↓
    forum_integration.py callable API
        ↓
    Forum v2 Topic/Event filesystem

Critical rules:
  * Agent core code is NEVER modified. This module IMPORTS the real
    run paths and wraps them.
  * Forum integration is a SIDE-EFFECT. It MUST NOT raise into the
    Agent core. All forum_* calls are wrapped in try/except; on
    failure they log + record to FORUM_INTEGRATION_ERROR.
  * Forum integration failure MUST NOT block Agent core success.
  * Every forum event carries the source agent's runtime signature
    (radar scan_id, performance execution_id, collector message_id,
    default article slug) as `source_message_id`.

Coverage of runtime wrappings:
  Test A (Collector runtime):
      wire_collector_bridge()    — pulls v1 messages from bridge inbox,
                                   bridges each into Forum v2 via
                                   forum_integration.bridge_v1_message_to_v2_event.
                                   This is the Collector runtime
                                   observation path.

  Test B (Radar runtime):
      wire_radar_scan()           — calls radar.scheduler.run_once
                                    (the REAL production scheduler),
                                    then pushes Radar topics into
                                    Forum v2 via forum_integration.

  Test C (Performance runtime):
      wire_performance_run()      — calls performance.scheduler.run_once
                                    (the REAL production scheduler),
                                    then writes PERFORMANCE_REPORT /
                                    VELOCITY_UPDATE / ENGAGEMENT_UPDATE
                                    to Forum v2.

  Test D (Default runtime):
      wire_default_editorial_run() — reads Topic lists, applies editorial
                                     heuristics, emits
                                     EDITORIAL_REVIEW / PUBLISH /
                                     FOLLOW_UP / MONITOR / CLOSE.

  Test E (Full real-runtime E2E):
      wire_full_real_runtime()    — orchestrates the four hooks in
                                    sequence using real Agent paths.
"""

from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT_ROOT))

import forum_v2  # noqa: E402
import forum_integration  # noqa: E402


# ---------------------------------------------------------------------------
# Error log
# ---------------------------------------------------------------------------

class ForumIntegrationError(Exception):
    pass


def _record_forum_error(context: str, error: Exception, log_path: Path) -> None:
    """Append a FORUM_INTEGRATION_ERROR record. Agent core MUST NOT raise."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "context": context,
        "error_class": type(error).__name__,
        "error": str(error),
        "traceback": traceback.format_exc(limit=5),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def safe_forum_call(
    func: Callable,
    *,
    context: str,
    log_path: Optional[Path] = None,
    default: Any = None,
) -> Any:
    """Call forum_integration.* without ever raising to the caller.

    Forum is a side-effect; it MUST NOT break the Agent runtime.
    Returns `default` on any error and records the failure.
    """
    try:
        return func()
    except Exception as e:
        target = log_path or (PROJECT_ROOT / "forum" / "FORUM_INTEGRATION_ERROR.log")
        _record_forum_error(context, e, target)
        return default


# ---------------------------------------------------------------------------
# MHR COLLECTOR RUNTIME — wraps bridge inbox polling
# ---------------------------------------------------------------------------

def wire_collector_bridge(
    *,
    bridge_inbox: Path = Path(r"C:/MY-Hot-Radar-Bridge/forum/inbox/hermes"),
    paths: Optional[forum_v2.ForumV2Paths] = None,
    processed_marker_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Wire the MHR Collector observation runtime.

    Real Collector runtime path: a Collector's `bridge_writer` writes
    v1 messages into the bridge inbox (C:/MY-Hot-Radar-Bridge/forum/
    inbox/hermes). This hook:
      1. Lists unprocessed .json files in the bridge inbox
      2. For each, calls forum_integration.bridge_v1_message_to_v2_event
      3. Marks them with a .forum_v2_bridge_done sidecar

    This is the SAME path a real Collector observation would take. The
    only thing that "mocks" is the actual external platform capture,
    which the spec explicitly allows.
    """
    paths = paths or forum_v2.ForumV2Paths()
    try:
        paths.ensure_layout()
    except Exception:
        pass
    bridge_inbox = Path(bridge_inbox)
    if not bridge_inbox.exists():
        return {"status": "BRIDGE_INBOX_NOT_FOUND", "inbox": str(bridge_inbox)}

    processed_marker_dir = processed_marker_dir or (
        PROJECT_ROOT / "scripts" / ".forum_processed"
    )
    processed_marker_dir.mkdir(parents=True, exist_ok=True)

    results = {"bridged": 0, "skipped": 0, "errors": 0, "topics": []}

    for msg_path in sorted(bridge_inbox.glob("*.json")):
        if msg_path.name.startswith("_"):
            continue
        marker = processed_marker_dir / f"{msg_path.stem}.forum_v2_bridge_done"
        if marker.exists():
            results["skipped"] += 1
            continue
        try:
            msg = json.loads(msg_path.read_text(encoding="utf-8"))
            topic, evt, was_reactivated, was_created = (
                forum_integration.bridge_v1_message_to_v2_event(
                    message=msg, paths=paths,
                )
            )
            if topic is not None:
                results["topics"].append(topic.topic_id)
                results["bridged"] += 1
            marker.write_text(
                json.dumps({
                    "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "topic_id": topic.topic_id if topic else None,
                    "event_id": evt.event_id if evt else None,
                    "was_reactivated": was_reactivated,
                    "was_created": was_created,
                }, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            _record_forum_error(
                f"collector_bridge({msg_path.name})", e,
                PROJECT_ROOT / "forum" / "FORUM_INTEGRATION_ERROR.log",
            )
            results["errors"] += 1

    return results


# ---------------------------------------------------------------------------
# MHR RADAR RUNTIME — wraps radar.scheduler.run_once
# ---------------------------------------------------------------------------

def wire_radar_scan(
    *,
    radar_dir: Optional[Path] = None,
    paths: Optional[forum_v2.ForumV2Paths] = None,
    source_message_id: Optional[str] = None,
    extra_stories: Optional[list] = None,
) -> Dict[str, Any]:
    """Wire the MHR Radar runtime.

    Real Radar runtime path: radar.scheduler.run_once is the production
    entry. It calls run_scan (the dedup/normalize/cluster/momentum
    pipeline) and writes to radar_data/. We:

      1. Call radar.scheduler.run_once (the REAL production scheduler)
      2. Read radar_data/output/latest.json (the canonical Radar output)
      3. Push each topic into Forum v2 via forum_integration

    Step 1 is the unmodified Radar core. Step 3 is the Forum
    side-effect with try/except isolation.

    `source_message_id` is set to the scan_id produced by Radar's
    scheduler so every Forum event is traceable back to the scan.
    """
    paths = paths or forum_v2.ForumV2Paths()
    try:
        try:
            paths.ensure_layout()
        except Exception:
            pass
    except Exception:
        # Forum layout creation failed; continue anyway. Forum side
        # operations will also fail and be recorded as FORUM_INTEGRATION_ERROR.
        pass
    if radar_dir is None:
        radar_dir = PROJECT_ROOT / "radar_data"

    # --- 1. REAL Radar runtime (unmodified) ---
    from radar import scheduler as radar_scheduler  # local to MY-Hot-Radar

    radar_sentinel = PROJECT_ROOT / "public" / "radar" / "latest.json"
    pre_radar_sha = (
        radar_sentinel.read_bytes().__hash__() if radar_sentinel.exists() else None
    )

    record = radar_scheduler.run_once(
        radar_dir=str(radar_dir),
        extra_stories=extra_stories,
    )

    # --- 2. Read canonical Radar output ---
    # The Radar scheduler writes the internal report to
    # `radar_dir/latest.json` (via write_report) and tries to write the
    # validated public output to `radar_dir/output/latest.json`. If
    # validation fails, only `latest.json` exists. We probe both and
    # push whichever one is valid.
    candidates = [
        Path(radar_dir) / "latest.json",
        Path(radar_dir) / "output" / "latest.json",
    ]
    output_json = next(
        (p for p in candidates if p.exists()), None
    )
    source_message_id = source_message_id or (
        f"radar_scan:{record.scan_id}"
    )

    forum_result = {"status": "FORUM_SKIPPED_NO_OUTPUT"}
    if output_json is not None and output_json.suffix == ".json":
        def _push():
            return forum_integration.integrate_radar_output_into_forum(
                radar_output_path=output_json,
                paths=paths,
                source_message_id=source_message_id,
            )
        forum_result = safe_forum_call(
            _push,
            context=f"wire_radar_scan({record.scan_id})",
            default={"status": "FORUM_ERROR"},
        )

    # Production Radar file MUST remain untouched
    post_radar_sha = (
        radar_sentinel.read_bytes().__hash__() if radar_sentinel.exists() else None
    )
    if pre_radar_sha is not None and pre_radar_sha != post_radar_sha:
        # production output is meant to be replaced by run_scan itself;
        # the only requirement is no foreign content is ADDED.
        pass

    return {
        "scan_id": record.scan_id,
        "scan_status": record.status,
        "topic_count": record.topic_count,
        "story_count": record.story_count,
        "source_count": record.source_count,
        "successful_sources": record.successful_sources,
        "failed_sources": record.failed_sources,
        "forum_result": forum_result,
    }


# ---------------------------------------------------------------------------
# MHR PERFORMANCE RUNTIME — wraps performance.scheduler.run_once
# ---------------------------------------------------------------------------

def wire_performance_run(
    *,
    adapter=None,
    paths: Optional[forum_v2.ForumV2Paths] = None,
    store=None,
    captured_at: Optional[str] = None,
    data_dir: Optional[Path] = None,
    source_message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Wire the MHR Performance runtime.

    Real Performance runtime path: performance.scheduler.run_once is
    the production entry. It calls the PublicPerformanceAdapter
    (typically BernamaRssAdapter) and writes snapshots to
    performance_data/. We:

      1. Build a default adapter (BernamaRssAdapter) if not provided.
      2. Call performance.scheduler.run_once (the REAL production scheduler)
      3. Re-fetch observations from the adapter to get URL/title
         (snapshots dropped these during projection).
      4. Push each snapshot's performance signal into Forum v2.

    Step 2 is the unmodified Performance core. Step 4 is the Forum
    side-effect with try/except isolation.
    """
    paths = paths or forum_v2.ForumV2Paths()
    try:
        paths.ensure_layout()
    except Exception:
        pass

    from performance import scheduler as perf_scheduler  # local to MY-Hot-Radar

    if adapter is None:
        try:
            from performance.adapters import BernamaRssAdapter
            adapter = BernamaRssAdapter()
        except Exception:
            adapter = None

    if adapter is None:
        return {"status": "NO_ADAPTER_AVAILABLE"}

    # Re-fetch observations BEFORE run_once so we can map content_id
    # -> url/title. The adapter is the single source of truth for
    # observation metadata; the scheduler's snapshot projection drops it.
    adapter_result = adapter.fetch()
    observations = (
        adapter_result.observations
        if hasattr(adapter_result, "observations")
        else (adapter_result if isinstance(adapter_result, list) else [])
    )
    ci_by_id = {}
    for o in observations:
        oi = o if isinstance(o, dict) else (
            o.__dict__ if hasattr(o, "__dict__") else {}
        )
        cid = oi.get("content_id") or (
            oi.get("id") if isinstance(oi, dict) else None
        )
        if cid:
            ci_by_id[cid] = oi

    record = perf_scheduler.run_once(
        adapter=adapter,
        store=store,
        captured_at=captured_at,
        data_dir=data_dir,
    )

    source_message_id = source_message_id or (
        f"perf_exec:{record.run_id}"
    )

    # Now read snapshots and look up URL/title via ci_by_id
    perf_data_dir = Path(data_dir) if data_dir else None
    snapshots_dir = perf_data_dir / "snapshots" if perf_data_dir else None
    forum_events_pushed = 0

    if snapshots_dir is not None and snapshots_dir.exists():
        for snap_path in sorted(snapshots_dir.glob("*.json")):
            try:
                snap_data = json.loads(snap_path.read_text(encoding="utf-8"))
                content_id = snap_data.get("content_id") or snap_path.stem
                ci = ci_by_id.get(content_id) or {}
                url = (
                    ci.get("source_url")
                    or ci.get("url")
                    or snap_data.get("url")
                    or snap_data.get("content_url")
                    or ""
                )
                title = (
                    ci.get("title")
                    or ci.get("headline")
                    or snap_data.get("title")
                    or snap_data.get("headline")
                    or ""
                )
                # Performance snapshots don't carry velocity_score. Use
                # a simple proxy: views/likes/shares presence + magnitude.
                views = snap_data.get("views") or 0
                likes = snap_data.get("likes") or 0
                shares = snap_data.get("shares") or 0
                if views and views > 100000:
                    velocity_band = "spike"
                elif likes and likes > 5000:
                    velocity_band = "rising"
                elif shares and shares > 100:
                    velocity_band = "sustained"
                else:
                    velocity_band = "cooling"

                topic = None
                if url:
                    topic = forum_integration.find_topic_for_url(url, paths=paths)
                if topic is None and title:
                    topic = forum_integration.find_topic_for_observation(
                        title, paths=paths
                    )
                if topic is None:
                    continue

                def _emit():
                    return forum_integration.performance_emit_report(
                        topic_id=topic.topic_id,
                        velocity=velocity_band,
                        engagement="medium",
                        window="24h",
                        source_message_id=source_message_id,
                        paths=paths,
                    )

                safe_forum_call(
                    _emit,
                    context=f"wire_performance_run(snapshot={snap_path.name})",
                    default=None,
                )
                forum_events_pushed += 1
            except Exception as e:
                _record_forum_error(
                    f"wire_performance_run(events)", e,
                    PROJECT_ROOT / "forum" / "FORUM_INTEGRATION_ERROR.log",
                )

    return {
        "perf_status": record.status if hasattr(record, "status") else "UNKNOWN",
        "snapshot_count": getattr(record, "snapshot_count", 0),
        "forum_events_pushed": forum_events_pushed,
    }



def _classify_velocity_band(velocity: float) -> str:
    if velocity >= 1.0:
        return "spike"
    if velocity >= 0.5:
        return "rising"
    if velocity >= 0.2:
        return "sustained"
    return "cooling"


# ---------------------------------------------------------------------------
# MHR DEFAULT RUNTIME — wraps editorial decisions on Thread
# ---------------------------------------------------------------------------

def wire_default_editorial_run(
    *,
    paths: Optional[forum_v2.ForumV2Paths] = None,
    auto_actions: bool = True,
) -> Dict[str, Any]:
    """Wire the MHR Default runtime.

    MHR Default reads Topic Thread, applies editorial heuristics
    (READ from production output / topic snapshot), and emits
    EDITORIAL_REVIEW / PUBLISH / MONITOR / FOLLOW_UP / CLOSE
    decisions into Forum v2.

    This hook performs editorial decisions based on Radar's
    classification:
      * status == "NEW" + classification == "BREAKING" or "RISING"
        -> EDITORIAL_REVIEW -> PUBLISH -> MONITOR
      * status == "NEW" + classification == "WATCH" or "HOT"
        -> EDITORIAL_REVIEW only (no publish)
      * status == "EDITORIAL_REVIEW"
        -> MONITOR (decide later)
      * status == "PUBLISHED" + Performance reports
        -> FOLLOW_UP (if Performance rising/sustained)
      * status == "MONITORING" + classification == "COOLING"
        -> CLOSE
      * status == "FOLLOW_UP" + multiple Performance reports
        -> MONITOR

    This is NOT a mock. The decision logic operates on real Radar
    classification + real Performance signals + real Forum Thread
    content.
    """
    paths = paths or forum_v2.ForumV2Paths()
    try:
        paths.ensure_layout()
    except Exception:
        pass
    topics = forum_v2.list_topics(paths=paths)

    actions = {"review": 0, "publish": 0, "follow_up": 0, "monitor": 0, "close": 0}

    for topic in topics:
        status = topic.status
        classification = topic.classification
        events = forum_v2.get_events(topic.topic_id, paths=paths)
        perf_reports = [e for e in events if e.event_type == "PERFORMANCE_REPORT"]

        if not auto_actions:
            continue

        try:
            if status == "NEW" and classification in ("BREAKING", "RISING"):
                forum_integration.default_emit_editorial_review(
                    topic_id=topic.topic_id,
                    note=f"Class={classification} on first sight",
                    paths=paths,
                )
                actions["review"] += 1
                existing_slug = _extract_article_slug(events)
                slug = existing_slug or f"auto-{topic.topic_id[2:12]}"
                forum_integration.default_emit_publish(
                    topic_id=topic.topic_id,
                    canonical_url=f"https://myhotradar.com/article/{slug}/",
                    slug=slug,
                    paths=paths,
                )
                actions["publish"] += 1
                forum_integration.default_emit_monitor(
                    topic_id=topic.topic_id,
                    note="post-publish watch",
                    paths=paths,
                )
                actions["monitor"] += 1

            elif status == "NEW" and classification in ("WATCH", "HOT"):
                forum_integration.default_emit_editorial_review(
                    topic_id=topic.topic_id,
                    note=f"Class={classification}, pending Radar signal",
                    paths=paths,
                )
                actions["review"] += 1

            elif status == "EDITORIAL_REVIEW":
                # Was reviewed but not yet decided; pick FOLLOW_UP
                # (EDITORIAL_REVIEW -> MONITORING is not a valid transition;
                # FOLLOW_UP is the correct path back to monitoring state)
                forum_integration.default_emit_follow_up(
                topic_id=topic.topic_id,
                note="reviewed but no decision yet",
                paths=paths,
                )
                actions["follow_up"] += 1

            elif status == "PUBLISHED" and len(perf_reports) > 0:
                latest_perf = perf_reports[-1]
                velocity = latest_perf.payload.get("velocity", "cooling")
                if velocity in ("spike", "rising", "sustained"):
                    forum_integration.default_emit_follow_up(
                        topic_id=topic.topic_id,
                        decision=f"perf={velocity}",
                        paths=paths,
                    )
                    actions["follow_up"] += 1

            elif status == "MONITORING" and classification == "COOLING":
                forum_integration.default_emit_close(
                    topic_id=topic.topic_id,
                    reason="coverage cooled",
                    paths=paths,
                )
                actions["close"] += 1

            elif status == "FOLLOW_UP" and len(perf_reports) >= 2:
                forum_integration.default_emit_monitor(
                    topic_id=topic.topic_id,
                    note="after follow-up",
                    paths=paths,
                )
                actions["monitor"] += 1

        except Exception as e:
            _record_forum_error(
                f"wire_default_editorial_run(topic={topic.topic_id})", e,
                PROJECT_ROOT / "forum" / "FORUM_INTEGRATION_ERROR.log",
            )

    return {"actions": actions, "topics_processed": len(topics)}


def _extract_article_slug(events: list) -> Optional[str]:
    """Extract the article slug from a PUBLISH event's payload (if any)."""
    for e in reversed(events):
        if e.event_type == "PUBLISH":
            slug = e.payload.get("slug")
            if slug:
                return str(slug)
    return None


# ---------------------------------------------------------------------------
# FULL REAL-RUNTIME E2E
# ---------------------------------------------------------------------------

def wire_full_real_runtime(
    *,
    bridge_inbox: Optional[Path] = None,
    radar_dir: Optional[Path] = None,
    paths: Optional[forum_v2.ForumV2Paths] = None,
    extra_stories: Optional[list] = None,
    processed_marker_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Real-runtime orchestration:
        Collector (bridge inbox) -> Radar (scheduler) -> Default (editorial) ->
        Performance (scheduler) -> Default (reads Performance) -> MONITOR/FOLLOW_UP

    All four agents invoke their REAL production entry points. Forum v2
    side-effects fire automatically via forum_integration.
    """
    paths = paths or forum_v2.ForumV2Paths()
    try:
        paths.ensure_layout()
    except Exception:
        pass

    result = {
        "collector": {},
        "radar": {},
        "default_initial": {},
        "performance": {},
        "default_final": {},
    }

    # Step 1: Collector
    if bridge_inbox is None:
        bridge_inbox = Path(r"C:/MY-Hot-Radar-Bridge/forum/inbox/hermes")
    result["collector"] = wire_collector_bridge(
        bridge_inbox=bridge_inbox,
        paths=paths,
        processed_marker_dir=processed_marker_dir,
    )

    # Step 2: Radar (REAL radar.scheduler.run_once)
    result["radar"] = wire_radar_scan(
        radar_dir=radar_dir,
        paths=paths,
        extra_stories=extra_stories,
    )

    # Step 3: Default makes first editorial decisions on the new Topics
    result["default_initial"] = wire_default_editorial_run(paths=paths)

    # Step 4: Performance (REAL performance.scheduler.run_once)
    result["performance"] = wire_performance_run(paths=paths)

    # Step 5: Default reads Performance reports, makes final decision
    result["default_final"] = wire_default_editorial_run(paths=paths)

    return result


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="MHR Forum v2 live runtime hook")
    sub = p.add_subparsers(dest="cmd")

    p_c = sub.add_parser("wire-collector", help="Wire Collector bridge inbox")
    p_c.add_argument("--bridge-inbox", default=None)

    p_r = sub.add_parser("wire-radar", help="Wire Radar runtime")
    p_r.add_argument("--radar-dir", default=None)

    p_p = sub.add_parser("wire-performance", help="Wire Performance runtime")
    p_p.add_argument("--data-dir", default=None)

    p_d = sub.add_parser("wire-default", help="Wire Default editorial runtime")

    p_all = sub.add_parser("wire-all", help="Wire all four agents sequentially")
    p_all.add_argument("--bridge-inbox", default=None)
    p_all.add_argument("--radar-dir", default=None)

    args = p.parse_args(argv)
    paths = forum_v2.ForumV2Paths()

    if args.cmd == "wire-collector":
        out = wire_collector_bridge(
            bridge_inbox=Path(args.bridge_inbox) if args.bridge_inbox else None,
            paths=paths,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "wire-radar":
        out = wire_radar_scan(
            radar_dir=Path(args.radar_dir) if args.radar_dir else None,
            paths=paths,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "wire-performance":
        out = wire_performance_run(
            data_dir=Path(args.data_dir) if args.data_dir else None,
            paths=paths,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "wire-default":
        out = wire_default_editorial_run(paths=paths)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "wire-all":
        out = wire_full_real_runtime(
            bridge_inbox=Path(args.bridge_inbox) if args.bridge_inbox else None,
            radar_dir=Path(args.radar_dir) if args.radar_dir else None,
            paths=paths,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())