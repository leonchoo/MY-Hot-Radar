#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MHR Human Tip CLI — 彪哥提交人工线索。

Usage:
  python scripts/human_tip_cli.py create
      --title "新闻标题"
      --description "新闻描述"
      --source-url "https://..."
      [--priority LOW|MEDIUM|HIGH|URGENT]
      [--evidence-url URL]            (可多次)
      [--tag TAG]                     (可多次)
      [--target-agent radar|default]
      [--author hermes]

  python scripts/human_tip_cli.py list
      [--status OPEN|ACKNOWLEDGED|INVESTIGATING|LINKED|RESOLVED]

  python scripts/human_tip_cli.py show --tip-id HT_xxx

  python scripts/human_tip_cli.py stats

  python scripts/human_tip_cli.py ack --tip-id HT_xxx --agent radar --note "..."
  python scripts/human_tip_cli.py investigate --tip-id HT_xxx --agent radar --note "..."
  python scripts/human_tip_cli.py link --tip-id HT_xxx --agent radar --topic-id T_xxx --note "..."
  python scripts/human_tip_cli.py resolve --tip-id HT_xxx --agent default
      --resolution NO_NEWS_VALUE|ALREADY_COVERED|PUBLISHED|TOPIC_CLOSED|MERGED|REACTIVATED|PENDING
      --note "..."
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import human_tips
import human_tips_runtime  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MHR Human Tip — 彪哥人工线索")
    parser.add_argument("--forum-root", default=r"C:\MY-Hot-Radar-Bridge\forum")
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="创建 Human Tip")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--description", default="")
    p_create.add_argument("--source-url", default="")
    p_create.add_argument("--priority", default="MEDIUM",
                          choices=human_tips.TIP_PRIORITIES)
    p_create.add_argument("--evidence-url", action="append", default=[])
    p_create.add_argument("--tag", action="append", default=[])
    p_create.add_argument("--target-agent", default="radar",
                          choices=["radar", "default"])
    p_create.add_argument("--author", default="hermes")
    p_create.add_argument("--source-message-id", default=None)

    # list
    p_list = sub.add_parser("list")
    p_list.add_argument("--status", default=None,
                        choices=human_tips.TIP_STATUSES + [None])

    # show
    p_show = sub.add_parser("show")
    p_show.add_argument("--tip-id", required=True)

    # stats
    sub.add_parser("stats")

    # ack
    p_ack = sub.add_parser("ack")
    p_ack.add_argument("--tip-id", required=True)
    p_ack.add_argument("--agent", default="radar")
    p_ack.add_argument("--note", default="")

    # investigate
    p_inv = sub.add_parser("investigate")
    p_inv.add_argument("--tip-id", required=True)
    p_inv.add_argument("--agent", default="radar")
    p_inv.add_argument("--note", default="")

    # link
    p_link = sub.add_parser("link")
    p_link.add_argument("--tip-id", required=True)
    p_link.add_argument("--agent", default="radar")
    p_link.add_argument("--topic-id", required=True)
    p_link.add_argument("--note", default="")

    # resolve
    p_res = sub.add_parser("resolve")
    p_res.add_argument("--tip-id", required=True)
    p_res.add_argument("--agent", default="default")
    p_res.add_argument("--resolution", required=True,
                       choices=human_tips.TIP_RESOLUTION_KINDS)
    p_res.add_argument("--note", default="")
    p_res.add_argument("--topic-id", default=None)

    args = parser.parse_args(argv)

    paths = human_tips.HumanTipsPaths(Path(args.forum_root))
    store = human_tips.HumanTipsStore(paths)

    if args.command == "create":
        tip, evt = store.create_tip(
            title=args.title,
            description=args.description,
            source_url=args.source_url,
            evidence_urls=args.evidence_url,
            priority=args.priority,
            tags=args.tag,
            target_agent=args.target_agent,
            author=args.author,
            source_message_id=args.source_message_id,
        )
        print(f"Created Human Tip:")
        print(json.dumps({
            "tip_id": tip.tip_id,
            "title": tip.title,
            "status": tip.status,
            "priority": tip.priority,
            "author": tip.author,
            "created_at": tip.created_at,
        }, ensure_ascii=False, indent=2))

    elif args.command == "list":
        tips = store.list_tips(status=args.status)
        if not tips:
            print("No tips" + (f" with status={args.status}" if args.status else ""))
            return 0
        print(f"{'tip_id':<22} {'status':<14} {'priority':<8} {'topic':<22} title")
        print("-" * 100)
        for t in tips:
            print(f"{t.tip_id:<22} {t.status:<14} {t.priority:<8} "
                  f"{(t.topic_id or '—'):<22} {t.title[:40]}")

    elif args.command == "show":
        tip = store.get_tip(args.tip_id)
        if tip is None:
            print(f"NOT FOUND: {args.tip_id}")
            return 1
        print("=== Tip ===")
        print(json.dumps(tip.to_dict(), ensure_ascii=False, indent=2))
        print("\n=== Events ===")
        events = store.get_events(args.tip_id)
        for e in events:
            payload = e.payload or {}
            note = payload.get("note", "") or payload.get("description", "")
            if isinstance(note, dict):
                note = note.get("zh", "") or note.get("en", "")
            print(f"  {e.timestamp}  [{e.event_type}]  agent={e.agent}  note={note[:80]}")

    elif args.command == "stats":
        s = human_tips_runtime.stats_summary(paths)
        print("MHR Human Tip Stats:")
        print(json.dumps(s, ensure_ascii=False, indent=2))

    elif args.command == "ack":
        tip, evt = store.ack_tip(args.tip_id, agent=args.agent, note=args.note)
        print(f"ACKED: {tip.tip_id} → status={tip.status}, acknowledged_at={tip.acknowledged_at}")

    elif args.command == "investigate":
        tip, evt = store.investigate_tip(args.tip_id, agent=args.agent, note=args.note)
        print(f"INVESTIGATING: {tip.tip_id} → status={tip.status}")

    elif args.command == "link":
        tip, evt = store.link_tip(args.tip_id, topic_id=args.topic_id,
                                  agent=args.agent, note=args.note)
        print(f"LINKED: {tip.tip_id} → topic_id={tip.topic_id}, status={tip.status}")

    elif args.command == "resolve":
        tip, evt = store.resolve_tip(args.tip_id, resolution=args.resolution,
                                    agent=args.agent, note=args.note,
                                    topic_id=args.topic_id)
        print(f"RESOLVED: {tip.tip_id} → status={tip.status}, resolution={tip.resolution}")

    return 0


if __name__ == "__main__":
    sys.exit(main())