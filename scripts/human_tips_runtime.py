#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Human Tip → Topic Lifecycle integration.

Phase 7 — bridges the Human Tip system with:
  * Forum v2 Topic system (find-or-create Topic for the tip's title)
  * Runtime adapters (Radar / Default / Performance)

Critical guarantees (per 彪哥's spec):
  * Hermes can only CREATE_TIP — no editorial decisions
  * Radar only ACKs / Investigates / Links — no Editorial Decisions
  * Default only RESOLVES — the final editorial decision
  * Performance only REPORTS — observation only
  * Tip cannot directly PUBLISH articles — must go through Default

Lifecycle:
  1. hermes creates tip
  2. Radar runtime detects OPEN tips → ACK → INVESTIGATE
  3. Radar finds/creates a Forum v2 Topic by linkage_key → LINK
  4. Default reviews the Topic Thread → may RESOLVE the tip
  5. Performance observes velocity → adds TIP_REPORT events
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import forum_v2  # noqa: E402
import human_tips  # noqa: E402


def link_tip_to_topic(
    *,
    tip: human_tips.HumanTip,
    forum_paths: Optional[forum_v2.ForumV2Paths] = None,
    create_if_missing: bool = True,
    agent: str = "radar",
    note: str = "",
) -> Tuple[human_tips.HumanTip, Optional[forum_v2.Topic], bool]:
    """Find or create a Forum v2 Topic for a Human Tip and link them.

    Returns:
      (updated_tip, topic, was_created)
        - updated_tip: tip with topic_id set and status=LINKED
        - topic: Forum v2 Topic object
        - was_created: True if Topic was newly created
    """
    paths = forum_paths or forum_v2.ForumV2Paths()

    # 1. Find existing Topic by linkage_key
    linkage = forum_v2.normalize_linkage_key(tip.title)
    existing = forum_v2.find_topic_by_linkage(linkage, paths=paths)

    created = False
    topic = None
    if existing is None and create_if_missing:
        # Create a new Topic via Collector OBSERVATION (Tip is essentially
        # an observation that needs verification). The Topic gets
        # status=NEW and a CREATE_TOPIC event.
        topic, evt, was_reactivated = forum_v2.create_topic(
            title=tip.title,
            agent="collector",  # Tip origin → Collector as discoverer
            paths=paths,
            classification="WATCH",
            languages=None,
            tags=list(tip.tags or []) + ["human_tip"],
            event_payload={
                "source": "human_tip",
                "tip_id": tip.tip_id,
                "priority": tip.priority,
                "author": tip.author,
            },
            event_evidence={
                "tip_id": tip.tip_id,
                "source_url": tip.source_url,
                "evidence_urls": list(tip.evidence_urls or []),
            },
            confidence=1.0,
        )
        created = True
    elif existing:
        # Existing Topic: check if it's CLOSED — if so, reactivate
        if existing.status == "CLOSED":
            # Trigger reactivation by creating a REACTIVATION_SIGNAL observation
            # via collector semantics
            try:
                # Need to find a way to reactivate — use find_topic_by_linkage
                # and update status. We use the OBSERVATION approach.
                from runtime_adapters import AdapterResult, append_event_safe  # type: ignore
                forum_v2.append_event(
                    topic_id=existing.topic_id,
                    agent="collector",
                    event_type="REACTIVATION_SIGNAL",
                    payload={
                        "source": "human_tip",
                        "tip_id": tip.tip_id,
                        "reactivation_reason": "Human Tip suggests topic is newsworthy again",
                    },
                    paths=paths,
                )
            except Exception:
                # REACTIVATION_SIGNAL may not be allowed by all paths;
                # fall back to OBSERVATION
                forum_v2.append_event(
                    topic_id=existing.topic_id,
                    agent="collector",
                    event_type="OBSERVATION",
                    payload={
                        "source": "human_tip",
                        "tip_id": tip.tip_id,
                        "note": "Human Tip suggests CLOSED topic may be newsworthy again",
                    },
                    paths=paths,
                )
        topic = existing

    if topic is None:
        # Try one more time to find (race condition)
        topic = forum_v2.find_topic_by_linkage(linkage, paths=paths)
        if topic is None:
            raise RuntimeError(f"failed to find or create topic for tip {tip.tip_id}")

    # 2. Update tip → LINKED
    # If the tip is still OPEN (called from link subcommand without prior ACK),
    # transition through ACK + INVESTIGATE first to satisfy the lifecycle matrix.
    if tip.status == human_tips.TIP_OPEN:
        try:
            store_internal = human_tips.HumanTipsStore(
                human_tips.HumanTipsPaths(forum_paths.root if forum_paths else None)
            )
            store_internal.ack_tip(tip.tip_id, agent=agent,
                                   note="Auto-ACK during link")
            store_internal.investigate_tip(tip.tip_id, agent=agent,
                                            note="Auto-investigate during link")
        except Exception:
            pass
        tip = human_tips.HumanTipsStore(
            human_tips.HumanTipsPaths(forum_paths.root if forum_paths else None)
        ).get_tip(tip.tip_id)
    note_msg = note or f"Linked to topic {topic.topic_id}" + (" (newly created)" if created else " (matched existing)")
    updated_tip, _evt = human_tips.HumanTipsStore(
        human_tips.HumanTipsPaths(forum_paths.root if forum_paths else None)
    ).link_tip(
        tip.tip_id,
        topic_id=topic.topic_id,
        agent=agent,
        note=note_msg,
    )

    # 3. Append a SOURCE_UPDATE event to the Topic pointing back to the tip
    # (only when newly created — for existing, the LINK_TIP event already
    # records the connection)
    if created and tip.source_url:
        try:
            forum_v2.append_event(
                topic_id=topic.topic_id,
                agent=agent,
                event_type="SOURCE_UPDATE",
                payload={
                    "url": tip.source_url,
                    "source_name": "Human Tip (hermes)",
                    "language": "zh",
                    "note": {
                        "en": f"Human Tip {tip.tip_id} submitted by {tip.author}",
                        "zh": f"彪哥通过 Human Tip {tip.tip_id} 提交的线索",
                    },
                    "tip_id": tip.tip_id,
                },
                evidence={
                    "tip_id": tip.tip_id,
                    "source_url": tip.source_url,
                    "priority": tip.priority,
                },
                paths=paths,
            )
        except Exception:
            pass

    return updated_tip, topic, created


def get_unacked_tips(paths: Optional[human_tips.HumanTipsPaths] = None) -> List[human_tips.HumanTip]:
    """Get all OPEN tips awaiting Radar acknowledgment."""
    store = human_tips.HumanTipsStore(paths)
    return store.list_tips(status=human_tips.TIP_OPEN)


def get_investigating_tips(paths: Optional[human_tips.HumanTipsPaths] = None) -> List[human_tips.HumanTip]:
    """Get ACKNOWLEDGED + INVESTIGATING tips awaiting Radar link."""
    store = human_tips.HumanTipsStore(paths)
    return [
        t for t in store.list_tips()
        if t.status in (human_tips.TIP_ACKNOWLEDGED, human_tips.TIP_INVESTIGATING)
    ]


def get_linked_tips(paths: Optional[human_tips.HumanTipsPaths] = None) -> List[human_tips.HumanTip]:
    """Get LINKED tips awaiting Default editorial decision."""
    store = human_tips.HumanTipsStore(paths)
    return store.list_tips(status=human_tips.TIP_LINKED)


def get_resolved_tips(paths: Optional[human_tips.HumanTipsPaths] = None) -> List[human_tips.HumanTip]:
    """Get RESOLVED tips (terminal state)."""
    store = human_tips.HumanTipsStore(paths)
    return store.list_tips(status=human_tips.TIP_RESOLVED)


def stats_summary(paths: Optional[human_tips.HumanTipsPaths] = None) -> Dict[str, int]:
    """Return count by status for the Human Tip system."""
    store = human_tips.HumanTipsStore(paths)
    all_tips = store.list_tips()
    counts = {s: 0 for s in human_tips.TIP_STATUSES}
    for t in all_tips:
        if t.status in counts:
            counts[t.status] += 1
    counts["TOTAL"] = len(all_tips)
    return counts


if __name__ == "__main__":
    paths = human_tips.HumanTipsPaths()
    store = human_tips.HumanTipsStore(paths)
    s = stats_summary(paths)
    print(json.dumps(s, ensure_ascii=False, indent=2))