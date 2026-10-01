#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MHR Newsroom Runtime — Continuous Agent Integration.

Phase 6.

A coordinator for the four MHR Agent runtimes (Collector / Radar /
Default / Performance). Does NOT contain any Agent business logic;
only orchestrates the lifecycle, captures results, and persists
runtime state.

CLI:
  python scripts/newsroom_runtime.py startup
  python scripts/newsroom_runtime.py run-once [--agent collector|radar|default|performance|all]
  python scripts/newsroom_runtime.py health
  python scripts/newsroom_runtime.py reconcile [--since TIMESTAMP]
  python scripts/newsroom_runtime.py shutdown
  python scripts/newsroom_runtime.py status

Lifecycle:
  startup   → Initialize runtime state, verify Forum is reachable
  run-once  → Run Agent(s) once, write Forum events, update state
  health    → Show Agent last-run / status / Forum sync
  reconcile → Detect Agent runs whose Forum Events are missing
  shutdown  → Finalize runtime state (idempotent)

Critical guarantees (per Phase 6 spec):
  * Agent core NEVER modified. Adapters only CALL real Agent paths.
  * Forum unavailable → AdapterResult.forum_sync_status = FAILED,
    Agent run still returns its own status.
  * Idempotent on (topic_id, agent, event_type, run_id, source_message_id).
  * Forum state writes are atomic (tmp + os.replace).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT_ROOT))

import forum_v2  # noqa: E402
import runtime_state  # noqa: E402
import runtime_adapters.collector as adapter_collector  # noqa: E402
import runtime_adapters.radar as adapter_radar  # noqa: E402
import runtime_adapters.performance as adapter_performance  # noqa: E402
import runtime_adapters.default as adapter_default  # noqa: E402
import runtime_adapters.human_tip as adapter_human_tip  # noqa: E402
import human_tips  # noqa: E402
import human_tips_runtime  # noqa: E402


DEFAULT_FORUM_ROOT = Path(r"C:\MY-Hot-Radar-Bridge\forum")
DEFAULT_RUNTIME_STATE = DEFAULT_FORUM_ROOT / "runtime" / "state.json"


# ---------------------------------------------------------------------------
# Lifecycle operations
# ---------------------------------------------------------------------------

def do_startup(*, runtime_state_path: Path = DEFAULT_RUNTIME_STATE,
               forum_paths: Optional[forum_v2.ForumV2Paths] = None) -> Dict[str, Any]:
    """Initialize runtime state, verify Forum reachability."""
    store = runtime_state.RuntimeStateStore(runtime_state_path)
    state = store.load()
    # Try to update forum stats
    try:
        topics = forum_v2.list_topics(paths=forum_paths)
        events_total = 0
        for t in topics:
            events_total += len(forum_v2.get_events(t.topic_id, paths=forum_paths))
        store.update_forum(
            topics=len(topics),
            events=events_total,
            status=runtime_state.OK,
        )
        return {
            "ok": True,
            "state_path": str(runtime_state_path),
            "forum": {
                "topics": len(topics),
                "events": events_total,
                "status": runtime_state.OK,
            },
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}:{e}",
            "forum_status": runtime_state.SYNC_FAILED,
        }


def do_run_once(*, agents: List[str],
                runtime_state_path: Path = DEFAULT_RUNTIME_STATE,
                forum_paths: Optional[forum_v2.ForumV2Paths] = None,
                default_decisions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Run one or more Agents once and write Forum updates.

    Order per Phase 6 spec:
      Collector → Default → Performance → Default
    (Radar can be inserted; we keep a stable order: Collector, Radar,
    Performance, Default.)
    """
    store = runtime_state.RuntimeStateStore(runtime_state_path)
    paths = forum_paths or forum_v2.ForumV2Paths()
    results: Dict[str, Any] = {}

    # Define run order
    ordered = []
    if "collector" in agents:
        ordered.append(("collector", lambda rid: adapter_collector.run_collector_runtime(
            forum_paths=paths, run_id=rid)))
    if "radar" in agents:
        # Radar also picks up Human Tips awaiting ACK
        def _radar_with_tips(rid):
            radar_result = adapter_radar.run_radar_runtime(
                forum_paths=paths, run_id=rid)
            tip_result = adapter_human_tip.process_open_tips(
                forum_paths=paths, run_id=f"{rid}_tips")
            # Aggregate tip events into radar result
            radar_result.forum_events_written += tip_result.forum_events_written
            radar_result.topics_processed += tip_result.topics_processed
            for n in tip_result.notes:
                radar_result.notes.append(f"tip:{n}")
            return radar_result
        ordered.append(("radar", _radar_with_tips))
    if "performance" in agents or "mhr_performance" in agents:
        ordered.append(("performance", lambda rid: adapter_performance.run_performance_runtime(
            forum_paths=paths, run_id=rid)))
    if "default" in agents:
        # Default reviews LINKED Human Tips
        def _default_with_tips(rid):
            default_result = adapter_default.run_default_runtime(
                forum_paths=paths, run_id=rid,
                decisions_input=default_decisions,
            )
            tip_result = adapter_human_tip.process_linked_tips_for_default(
                forum_paths=paths, run_id=f"{rid}_tips")
            default_result.forum_events_written += tip_result.forum_events_written
            default_result.topics_processed += tip_result.topics_processed
            for n in tip_result.notes:
                default_result.notes.append(f"tip:{n}")
            return default_result
        ordered.append(("default", _default_with_tips))

    for agent_name, fn in ordered:
        run_id = runtime_state.make_run_id(agent_name)
        try:
            r = fn(run_id)
        except Exception as e:
            r = runtime_state.AdapterResult(
                agent=agent_name,
                run_id=run_id,
                started_at=runtime_state._utc_now_iso(),
                finished_at=runtime_state._utc_now_iso(),
                status=runtime_state.FAILED,
                agent_error=f"adapter_crash:{type(e).__name__}:{e}",
            )
        # Update runtime state
        store.update_agent(
            agent_name,
            last_run=r.started_at,
            last_run_id=r.run_id,
            last_status=r.status,
            last_forum_sync=r.finished_at,
            forum_sync_status=r.forum_sync_status,
            last_error=r.agent_error or r.forum_error,
            last_run_topics=r.topics_processed,
            last_run_events=r.forum_events_written,
            total_runs=(store.load().agents[agent_name].total_runs + 1),
            failed_runs=(store.load().agents[agent_name].failed_runs + (1 if r.status == runtime_state.FAILED else 0)),
        )
        results[agent_name] = r.to_dict()

    # Update forum stats
    try:
        topics = forum_v2.list_topics(paths=paths)
        events_total = 0
        for t in topics:
            events_total += len(forum_v2.get_events(t.topic_id, paths=paths))
        any_failed = any(
            results[a]["forum_sync_status"] == runtime_state.SYNC_FAILED
            for a in results
        )
        store.update_forum(
            topics=len(topics),
            events=events_total,
            status=runtime_state.DEGRADED if any_failed else runtime_state.OK,
        )
    except Exception:
        pass

    return {
        "ok": True,
        "ran_agents": list(results.keys()),
        "results": results,
    }


def do_health(*, runtime_state_path: Path = DEFAULT_RUNTIME_STATE,
              forum_paths: Optional[forum_v2.ForumV2Paths] = None) -> Dict[str, Any]:
    """Print runtime health.

    Output schema:
      {
        "agents": {...},
        "forum": {...},
        "human_tips": {"by_status": {...}, "total": N}
      }
    """
    store = runtime_state.RuntimeStateStore(runtime_state_path)
    state = store.load()

    out = {
        "schema_version": runtime_state.SCHEMA_VERSION,
        "agents": {},
        "forum": {
            "last_check": state.forum_last_check,
            "topics": state.forum_topics,
            "events": state.forum_events,
            "status": state.forum_status,
        },
        "human_tips": {},
    }

    # Try to refresh live counts (best-effort)
    try:
        topics = forum_v2.list_topics(paths=forum_paths)
        events_total = 0
        for t in topics:
            events_total += len(forum_v2.get_events(t.topic_id, paths=forum_paths))
        out["forum"]["topics"] = len(topics)
        out["forum"]["events"] = events_total
    except Exception as e:
        out["forum"]["error"] = f"{type(e).__name__}:{e}"

    for agent, rec in state.agents.items():
        out["agents"][agent] = {
            "last_run": rec.last_run,
            "last_run_id": rec.last_run_id,
            "last_status": rec.last_status,
            "last_forum_sync": rec.last_forum_sync,
            "forum_sync_status": rec.forum_sync_status,
            "total_runs": rec.total_runs,
            "failed_runs": rec.failed_runs,
            "last_error": rec.last_error,
            "last_run_topics": rec.last_run_topics,
            "last_run_events": rec.forum_events_written if hasattr(rec, "forum_events_written") else rec.last_run_events,
        }

    # Human tip stats (Phase 7)
    try:
        tip_paths = human_tips.HumanTipsPaths(forum_paths.root if forum_paths else None)
        tip_stats = human_tips_runtime.stats_summary(tip_paths)
        out["human_tips"] = tip_stats
    except Exception as e:
        out["human_tips"] = {"error": f"{type(e).__name__}:{e}"}

    return out


def do_reconcile(*, runtime_state_path: Path = DEFAULT_RUNTIME_STATE,
                 forum_paths: Optional[forum_v2.ForumV2Paths] = None,
                 since: Optional[str] = None) -> Dict[str, Any]:
    """Reconcile: check that every recorded Agent run has a matching Forum Event.

    Strategy:
      For each Agent:
        - Read recent entries from execution_log.jsonl
        - For each entry, ensure at least one Forum Event has run_id == entry_id
        - If missing, log "missing" but do NOT auto-generate (cannot fabricate)
    """
    out: Dict[str, Any] = {"ok": False, "checked": [], "missing": [], "notes": []}
    paths = forum_paths or forum_v2.ForumV2Paths()

    # Look at Radar execution_log.jsonl
    radar_log = Path("C:/MY-Hot-Radar/radar_data/execution_log.jsonl")
    perf_log = Path("C:/MY-Hot-Radar/performance_data/execution_log.jsonl")

    # Collect all event run_ids from Forum
    forum_run_ids: set = set()
    topics = forum_v2.list_topics(paths=paths)
    for t in topics:
        for e in forum_v2.get_events(t.topic_id, paths=paths):
            payload = e.payload if hasattr(e, "payload") else {}
            if isinstance(payload, dict):
                rid = payload.get("run_id", "")
                if rid:
                    forum_run_ids.add(rid)

    # Check Radar runs
    if radar_log.exists():
        try:
            lines = radar_log.read_text(encoding="utf-8").strip().split("\n")[-5:]
            for line in lines:
                rec = json.loads(line)
                scan_id = rec.get("scan_id", "")
                expected_run_id = f"radar_{scan_id.replace('-', '_')}"
                out["checked"].append(f"radar:{scan_id}")
                if scan_id not in forum_run_ids and expected_run_id not in forum_run_ids:
                    # Look for any radar event with run_id containing scan_id
                    found = any(scan_id in rid for rid in forum_run_ids)
                    if not found:
                        out["missing"].append(f"radar:{scan_id}:no_forum_event")
                        out["notes"].append(
                            f"Radar run {scan_id} has no Forum event matching its scan_id. "
                            f"Cannot auto-recover: real Agent artifacts did not produce a Forum event."
                        )
        except Exception as e:
            out["notes"].append(f"radar_log_read_failed:{e}")

    # Check Performance runs
    if perf_log.exists():
        try:
            lines = perf_log.read_text(encoding="utf-8").strip().split("\n")[-5:]
            for line in lines:
                rec = json.loads(line)
                rid = rec.get("run_id", "")
                out["checked"].append(f"performance:{rid}")
                if rid and rid not in forum_run_ids:
                    found = any(rid in fr for fr in forum_run_ids)
                    if not found:
                        out["missing"].append(f"performance:{rid}:no_forum_event")
                        out["notes"].append(
                            f"Performance run {rid} has no matching Forum event. "
                            f"Cannot auto-recover."
                        )
        except Exception as e:
            out["notes"].append(f"perf_log_read_failed:{e}")

    out["ok"] = True
    out["missing_count"] = len(out["missing"])
    out["checked_count"] = len(out["checked"])
    return out


def do_shutdown(*, runtime_state_path: Path = DEFAULT_RUNTIME_STATE) -> Dict[str, Any]:
    """Finalize runtime state. Idempotent."""
    store = runtime_state.RuntimeStateStore(runtime_state_path)
    state = store.load()
    # Touch the file to update timestamp
    store.save(state)
    return {"ok": True, "state_path": str(runtime_state_path)}


def do_tip_subcommand(args, forum_paths: forum_v2.ForumV2Paths) -> Dict[str, Any]:
    """Handle the 'tip' subcommand for Human Tip management."""
    tip_paths = human_tips.HumanTipsPaths(forum_paths.root if forum_paths else None)
    store = human_tips.HumanTipsStore(tip_paths)

    tip_command = getattr(args, "tip_command", None)
    if tip_command == "create":
        tip, evt = store.create_tip(
            title=args.title,
            description=getattr(args, "description", "") or "",
            source_url=getattr(args, "source_url", "") or "",
            evidence_urls=list(getattr(args, "evidence_url", []) or []),
            priority=getattr(args, "priority", "MEDIUM"),
            tags=list(getattr(args, "tag", []) or []),
            target_agent=getattr(args, "target_agent", "radar"),
            author=getattr(args, "author", "hermes"),
            source_message_id=getattr(args, "source_message_id", None),
        )
        return {"ok": True, "tip_id": tip.tip_id, "status": tip.status,
                "created_at": tip.created_at, "event_id": evt.event_id}

    elif tip_command == "list":
        tips = store.list_tips(status=getattr(args, "status", None))
        return {"ok": True, "count": len(tips), "tips": [t.to_dict() for t in tips]}

    elif tip_command == "show":
        tip = store.get_tip(args.tip_id)
        if tip is None:
            return {"ok": False, "error": "not_found", "tip_id": args.tip_id}
        events = store.get_events(args.tip_id)
        return {
            "ok": True,
            "tip": tip.to_dict(),
            "events": [e.to_dict() for e in events],
        }

    elif tip_command == "stats":
        return {"ok": True, "stats": human_tips_runtime.stats_summary(tip_paths)}

    elif tip_command == "ack":
        agent = args.agent if args.agent and args.agent != "all" else "radar"
        tip, evt = store.ack_tip(args.tip_id, agent=agent, note=args.note)
        return {"ok": True, "tip": tip.to_dict(), "event_id": evt.event_id}

    elif tip_command == "investigate":
        agent = args.agent if args.agent and args.agent != "all" else "radar"
        tip, evt = store.investigate_tip(args.tip_id, agent=agent, note=args.note)
        return {"ok": True, "tip": tip.to_dict(), "event_id": evt.event_id}

    elif tip_command == "link":
        agent = args.agent if args.agent and args.agent != "all" else "radar"
        tip = store.get_tip(args.tip_id)
        if tip is None:
            return {"ok": False, "error": "tip_not_found"}
        try:
            updated_tip, topic, was_created = human_tips_runtime.link_tip_to_topic(
                tip=tip,
                forum_paths=forum_paths,
                create_if_missing=True,
                agent=agent,
                note=args.note,
            )
            return {
                "ok": True,
                "tip": updated_tip.to_dict(),
                "topic_id": topic.topic_id,
                "was_created": was_created,
            }
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}:{e}"}

    elif tip_command == "resolve":
        agent = args.agent if args.agent and args.agent != "all" else "default"
        topic_id = getattr(args, "topic_id", None)
        tip, evt = store.resolve_tip(
            args.tip_id,
            resolution=args.resolution,
            agent=agent,
            note=args.note,
            topic_id=topic_id,
        )
        return {"ok": True, "tip": tip.to_dict(), "event_id": evt.event_id}

    return {"ok": False, "error": f"unknown_tip_command:{tip_command}"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MHR Newsroom Runtime")
    parser.add_argument("command",
                        choices=["startup", "run-once", "health", "reconcile",
                                 "shutdown", "status", "tip"],
                        help="Runtime command")
    parser.add_argument("--agent", default="all",
                        help="comma-separated: collector,radar,performance,default,all")
    parser.add_argument("--state-path", default=str(DEFAULT_RUNTIME_STATE),
                        help="Path to runtime state.json")
    parser.add_argument("--forum-root", default=str(DEFAULT_FORUM_ROOT),
                        help="Forum v2 root path")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")

    # Tip subcommands
    tip_sub = parser.add_argument_group("tip", "Human Tip subcommands")
    tip_sub.add_argument("--tip-command", dest="tip_command", default=None,
                         choices=["create", "list", "show", "stats",
                                  "ack", "investigate", "link", "resolve"])
    tip_sub.add_argument("--title")
    tip_sub.add_argument("--description", default="")
    tip_sub.add_argument("--source-url", default="")
    tip_sub.add_argument("--priority", default="MEDIUM",
                         choices=human_tips.TIP_PRIORITIES)
    tip_sub.add_argument("--evidence-url", action="append", default=[])
    tip_sub.add_argument("--tag", action="append", default=[])
    tip_sub.add_argument("--target-agent", default="radar",
                         choices=["radar", "default"])
    tip_sub.add_argument("--author", default="hermes")
    tip_sub.add_argument("--source-message-id", default=None)
    tip_sub.add_argument("--tip-id")
    tip_sub.add_argument("--topic-id")
    tip_sub.add_argument("--note", default="")
    tip_sub.add_argument("--resolution", choices=human_tips.TIP_RESOLUTION_KINDS)
    tip_sub.add_argument("--status",
                         choices=human_tips.TIP_STATUSES + [None])

    args = parser.parse_args(argv)

    forum_paths = forum_v2.ForumV2Paths(Path(args.forum_root))
    runtime_state_path = Path(args.state_path)

    if args.command == "startup":
        result = do_startup(
            runtime_state_path=runtime_state_path,
            forum_paths=forum_paths,
        )
    elif args.command == "run-once":
        agents = (
            ["collector", "radar", "performance", "default"]
            if args.agent == "all"
            else [a.strip() for a in args.agent.split(",")]
        )
        result = do_run_once(
            agents=agents,
            runtime_state_path=runtime_state_path,
            forum_paths=forum_paths,
        )
    elif args.command in ("health", "status"):
        result = do_health(
            runtime_state_path=runtime_state_path,
            forum_paths=forum_paths,
        )
    elif args.command == "reconcile":
        result = do_reconcile(
            runtime_state_path=runtime_state_path,
            forum_paths=forum_paths,
        )
    elif args.command == "shutdown":
        result = do_shutdown(runtime_state_path=runtime_state_path)
    elif args.command == "tip":
        result = do_tip_subcommand(args, forum_paths)
    else:
        result = {"ok": False, "error": f"unknown_command:{args.command}"}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # Human-readable output
        if args.command == "health" or args.command == "status":
            print("MHR NEWSROOM HEALTH")
            print("=" * 60)
            f = result.get("forum", {})
            print(f"Forum:")
            print(f"  TOPICS: {f.get('topics', 0)}")
            print(f"  EVENTS: {f.get('events', 0)}")
            print(f"  STATUS: {f.get('status', 'UNKNOWN')}")
            print(f"  LAST_CHECK: {f.get('last_check', '—')}")
            print()
            for agent, rec in result.get("agents", {}).items():
                print(f"{agent}:")
                print(f"  LAST_RUN:        {rec.get('last_run', '—')}")
                print(f"  LAST_STATUS:     {rec.get('last_status', '—')}")
                print(f"  FORUM_SYNC:      {rec.get('forum_sync_status', '—')}")
                print(f"  TOTAL_RUNS:      {rec.get('total_runs', 0)}")
                print(f"  LAST_RUN_TOPICS: {rec.get('last_run_topics', 0)}")
                print(f"  LAST_RUN_EVENTS: {rec.get('last_run_events', 0)}")
                if rec.get("last_error"):
                    print(f"  LAST_ERROR:      {rec.get('last_error', '')[:100]}")
                print()
        elif args.command == "run-once":
            print(f"Ran agents: {', '.join(result.get('ran_agents', []))}")
            for agent, r in result.get("results", {}).items():
                print(f"\n{agent}:")
                print(f"  run_id:          {r.get('run_id', '—')}")
                print(f"  status:          {r.get('status', '—')}")
                print(f"  forum_written:   {r.get('forum_events_written', 0)}")
                print(f"  forum_sync:      {r.get('forum_sync_status', '—')}")
                print(f"  topics_processed:{r.get('topics_processed', 0)}")
                if r.get("agent_error"):
                    print(f"  agent_error:     {r.get('agent_error', '')[:100]}")
                if r.get("forum_error"):
                    print(f"  forum_error:     {r.get('forum_error', '')[:100]}")
                notes = r.get("notes", [])
                if notes:
                    print(f"  notes ({len(notes)}):")
                    for n in notes[:5]:
                        print(f"    - {n}")
                    if len(notes) > 5:
                        print(f"    ... and {len(notes) - 5} more")
        elif args.command == "reconcile":
            print(f"Reconcile: checked={result.get('checked_count', 0)}, "
                  f"missing={result.get('missing_count', 0)}")
            for m in result.get("missing", [])[:10]:
                print(f"  MISSING: {m}")
            for n in result.get("notes", [])[:10]:
                print(f"  NOTE: {n}")
        elif args.command == "startup":
            print(f"Startup: {result}")
        elif args.command == "shutdown":
            print(f"Shutdown: {result}")

    return 0


if __name__ == "__main__":
    sys.exit(main())