#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Human Tip → Radar Runtime Adapter.

Phase 7.

This extends the Radar runtime adapter to ALSO process Human Tips:
  1. Detects OPEN tips → ACKs them
  2. Investigates them
  3. Finds/creates Forum v2 Topic → Links tip

Critical constraint: Radar still cannot emit the order/radar to publish articles
default only on Forum. Linking is just an Observation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import forum_v2  # noqa: E402
import human_tips  # noqa: E402
import human_tips_runtime  # noqa: E402
import runtime_state  # noqa: E402
from runtime_adapters import AdapterResult, utc_now_iso  # noqa: E402


def process_open_tips(
    *,
    forum_paths: Optional[forum_v2.ForumV2Paths] = None,
    run_id: Optional[str] = None,
    max_tips: int = 50,
) -> AdapterResult:
    """Radar processes OPEN tips:
      * ACK each OPEN tip
      * Auto-investigate
      * Try to find/create a Topic and LINK
    Returns AdapterResult for the Radar runtime integration.
    """
    started = utc_now_iso()
    run_id = run_id or runtime_state.make_run_id(runtime_state.AGENT_RADAR)
    paths = forum_paths or forum_v2.ForumV2Paths()
    tip_paths = human_tips.HumanTipsPaths(paths.root)
    store = human_tips.HumanTipsStore(tip_paths)

    result = AdapterResult(
        agent=runtime_state.AGENT_RADAR,
        run_id=run_id,
        started_at=started,
        finished_at=started,
        status=runtime_state.OK,
    )

    open_tips = store.list_tips(status=human_tips.TIP_OPEN)[:max_tips]
    if not open_tips:
        result.notes.append("no_open_tips")
        result.finished_at = utc_now_iso()
        return result

    for tip in open_tips:
        try:
            # 1. ACK
            ack_note = f"Radar 接手验证（runtime {run_id}）"
            store.ack_tip(tip.tip_id, agent="radar", note=ack_note)
            result.forum_events_written += 1
            # 2. INVESTIGATE
            store.investigate_tip(tip.tip_id, agent="radar",
                                  note="正在匹配或创建 Forum v2 Topic")
            result.forum_events_written += 1
            # 3. LINK (find-or-create Topic)
            updated, topic, was_created = human_tips_runtime.link_tip_to_topic(
                tip=tip,
                forum_paths=paths,
                create_if_missing=True,
                agent="radar",
                note=f"Auto-linked via run_id={run_id}",
            )
            result.topics_processed += 1
            result.notes.append(
                f"tip_linked:{tip.tip_id}->{topic.topic_id}:"
                f"{'new' if was_created else 'matched'}"
            )
        except Exception as e:
            result.forum_error = f"{type(e).__name__}:{e}"
            result.forum_sync_status = runtime_state.SYNC_FAILED
            result.notes.append(f"tip_failed:{tip.tip_id}:{str(e)[:80]}")

    result.finished_at = utc_now_iso()
    if result.forum_error and result.forum_events_written == 0:
        result.status = runtime_state.FAILED
    return result


def process_linked_tips_for_default(
    *,
    forum_paths: Optional[forum_v2.ForumV2Paths] = None,
    run_id: Optional[str] = None,
    default_decision_fn: Optional[Any] = None,
    max_tips: int = 50,
) -> AdapterResult:
    """Default processes LINKED tips.

    Without an explicit decision function, this only emits an EDITORIAL_REVIEW
    marker to the linked Topic. The actual editorial decision is the user's
    responsibility (per Phase 6 spec point 十一).
    """
    started = utc_now_iso()
    run_id = run_id or runtime_state.make_run_id(runtime_state.AGENT_DEFAULT)
    paths = forum_paths or forum_v2.ForumV2Paths()
    tip_paths = human_tips.HumanTipsPaths(paths.root)
    store = human_tips.HumanTipsStore(tip_paths)

    result = AdapterResult(
        agent=runtime_state.AGENT_DEFAULT,
        run_id=run_id,
        started_at=started,
        finished_at=started,
        status=runtime_state.OK,
    )

    linked_tips = store.list_tips(status=human_tips.TIP_LINKED)[:max_tips]
    if not linked_tips:
        result.notes.append("no_linked_tips")
        result.finished_at = utc_now_iso()
        return result

    for tip in linked_tips:
        if not tip.topic_id:
            result.notes.append(f"tip_no_topic:{tip.tip_id}")
            continue
        try:
            # Emit an EDITORIAL_REVIEW on the linked Topic
            forum_v2.append_event(
                topic_id=tip.topic_id,
                agent=runtime_state.AGENT_DEFAULT,
                event_type="EDITORIAL_REVIEW",
                payload={
                    "note": {
                        "en": f"Default reviewing Topic linked from Human Tip {tip.tip_id}",
                        "zh": f"Default 审核 Human Tip {tip.tip_id} 关联的 Topic",
                    },
                    "tip_id": tip.tip_id,
                    "run_id": run_id,
                },
                paths=paths,
            )
            result.forum_events_written += 1
            result.topics_processed += 1
            result.notes.append(f"tip_reviewed:{tip.tip_id}:{tip.topic_id}")
        except Exception as e:
            result.forum_error = f"{type(e).__name__}:{e}"
            result.forum_sync_status = runtime_state.SYNC_FAILED
            result.notes.append(f"tip_review_failed:{tip.tip_id}:{str(e)[:80]}")

    result.finished_at = utc_now_iso()
    if result.forum_error and result.forum_events_written == 0:
        result.status = runtime_state.FAILED
    return result


if __name__ == "__main__":
    paths = forum_v2.ForumV2Paths()
    r = process_open_tips(forum_paths=paths)
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))