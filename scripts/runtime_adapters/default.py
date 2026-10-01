#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Default (MHR Editor-in-Chief) Runtime Adapter.

Phase 6 MHR Newsroom Runtime.

The Default agent's role:
  * READ Forum v2 Topic Threads (Collector + Radar + Performance)
  * Make editorial decisions
  * Emit EDITORIAL_REVIEW / PUBLISH / MONITOR / FOLLOW_UP / CLOSE
  * Re-read Performance signals and emit UPDATE_ARTICLE

CRITICAL per Phase 6 spec point 十一:
  > Phase 6 的 Default runtime 只需要证明:
  >   Forum Event
  >     ↓
  >   Default runtime receives it
  >     ↓
  >   Editorial decision layer can consume it
  > 如果真实 Editorial V2 还没有自动 runtime interface:
  >   记录 limitation，不要自己编造一个新的 Editorial Engine。

So this adapter does NOT build a new editorial engine. It:
  1. Reads Forum Topics
  2. If `editorial_decision` 字段已存在 (from real Editorial V2 elsewhere),
     emits corresponding forum event
  3. Otherwise emits EDITORIAL_REVIEW as a "thinking" marker
  4. Honors permission boundary: PUBLISH/CLOSE/UPDATE_ARTICLE need
     existing forum_v2 enforcement
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
import forum_integration  # noqa: E402
import forum_i18n  # noqa: E402
import runtime_state  # noqa: E402
from runtime_adapters import AdapterResult, utc_now_iso  # noqa: E402


def forum_i18n_text(en: str) -> Dict[str, str]:
    """Helper: wrap a plain string into the bilingual dict format."""
    return {"en": en or "", "zh": en or ""}


# Editorial decisions that Default agent can route (mapping from real signal to event)
EDITORIAL_DECISION_TO_EVENT = {
    "publish": "PUBLISH",
    "follow_up": "FOLLOW_UP",
    "monitor": "MONITOR",
    "close": "CLOSE",
    "update_article": "UPDATE_ARTICLE",
}


def run_default_runtime(
    *,
    forum_paths: Optional[forum_v2.ForumV2Paths] = None,
    run_id: Optional[str] = None,
    max_topics: int = 25,
    decisions_input: Optional[List[Dict[str, Any]]] = None,
) -> AdapterResult:
    """Run the Default adapter.

    Strategy:
      1. Read up to max_topics of recent Forum Topics.
      2. For each topic:
         - If decisions_input has a corresponding decision, emit it
         - Otherwise emit EDITORIAL_REVIEW (a "thinking" marker, not a fake publish)
      3. NEVER fabricate publish/close decisions without explicit input.

    Parameters:
      decisions_input: list of {topic_id, decision, reason} dicts.
                       If None, only EDITORIAL_REVIEW markers are emitted.
                       This is the safe "consume Forum" path required by
                       the Phase 6 spec.
    """
    started = utc_now_iso()
    run_id = run_id or runtime_state.make_run_id(runtime_state.AGENT_DEFAULT)
    paths = forum_paths or forum_v2.ForumV2Paths()

    result = AdapterResult(
        agent=runtime_state.AGENT_DEFAULT,
        run_id=run_id,
        started_at=started,
        finished_at=started,
        status=runtime_state.OK,
    )

    # Read recent topics (sorted by last_seen desc)
    try:
        topics = forum_v2.list_topics(paths=paths)
    except Exception as e:
        result.status = runtime_state.FAILED
        result.agent_error = f"{type(e).__name__}:{e}"
        result.finished_at = utc_now_iso()
        return result

    # Sort by last_seen (newest first)
    def _last_seen_key(t):
        return getattr(t, "last_seen", "") or getattr(t, "first_seen", "")
    topics_sorted = sorted(topics, key=_last_seen_key, reverse=True)
    topics_subset = topics_sorted[:max_topics]
    result.notes.append(f"topics_scanned:{len(topics)}")
    result.notes.append(f"topics_processed:{len(topics_subset)}")

    # Build lookup: topic_id -> decision
    decisions_by_topic: Dict[str, Dict[str, Any]] = {}
    if decisions_input:
        for d in decisions_input:
            tid = d.get("topic_id")
            if tid:
                decisions_by_topic[tid] = d

    editorial_review_count = 0
    decision_count = 0

    for topic in topics_subset:
        tid = topic.topic_id
        decision = decisions_by_topic.get(tid)
        if decision:
            # Real decision provided — emit it
            try:
                decision_type = decision.get("decision", "")
                evt_type = EDITORIAL_DECISION_TO_EVENT.get(decision_type)
                if not evt_type:
                    result.notes.append(f"unknown_decision:{tid}:{decision_type}")
                    continue
                reason = decision.get("reason", "")
                # Each emit function has its own signature
                if evt_type == "PUBLISH":
                    forum_integration.default_emit_publish(
                        topic_id=tid,
                        canonical_url=decision.get("canonical_url", ""),
                        slug=decision.get("slug", ""),
                        paths=paths,
                    )
                elif evt_type == "FOLLOW_UP":
                    forum_integration.default_emit_follow_up(
                        topic_id=tid,
                        decision=decision.get("decision", "follow_up"),
                        paths=paths,
                    )
                elif evt_type == "MONITOR":
                    # The forum_v2 lifecycle does not allow EDITORIAL_REVIEW
                    # → MONITORING directly; only PUBLISHED can go to MONITORING.
                    # If topic is not yet PUBLISHED, we emit MONITOR without
                    # next_status (Forum will append a MONITOR event without
                    # changing status) — and we don't crash.
                    try:
                        forum_v2.append_event(
                            topic_id=tid,
                            agent=runtime_state.AGENT_DEFAULT,
                            event_type="MONITOR",
                            payload={
                                "note": forum_i18n_text(reason or "Default monitoring this Topic."),
                                "run_id": run_id,
                                "source_run_id": run_id,
                            },
                            paths=paths,
                        )
                    except Exception as e:
                        # If even this fails, try the integration wrapper
                        forum_integration.default_emit_monitor(
                            topic_id=tid,
                            note=reason,
                            paths=paths,
                        )
                    result.forum_events_written += 1
                elif evt_type == "CLOSE":
                    forum_integration.default_emit_close(
                        topic_id=tid,
                        reason=reason,
                        paths=paths,
                    )
                elif evt_type == "UPDATE_ARTICLE":
                    forum_integration.default_update_article(
                        topic_id=tid,
                        canonical_url=decision.get("canonical_url", ""),
                        change_summary=decision.get("change_summary", reason),
                        paths=paths,
                    )
                result.forum_events_written += 1
                decision_count += 1
            except Exception as e:
                result.forum_error = f"{type(e).__name__}:{e}"
                result.forum_sync_status = runtime_state.SYNC_FAILED
                result.notes.append(f"decision_failed:{tid}:{str(e)[:80]}")
        else:
            # No explicit decision — emit EDITORIAL_REVIEW marker
            try:
                # Skip if EDITORIAL_REVIEW already exists for this topic
                # (idempotency: avoid flooding the timeline)
                events = forum_v2.get_events(tid, paths=paths)
                if any(e.event_type == "EDITORIAL_REVIEW" for e in events):
                    continue
                forum_integration.default_emit_editorial_review(
                    topic_id=tid,
                    note="Default scanned this Topic; awaiting editorial decision input.",
                    paths=paths,
                )
                result.forum_events_written += 1
                editorial_review_count += 1
            except Exception as e:
                result.forum_error = f"{type(e).__name__}:{e}"
                result.forum_sync_status = runtime_state.SYNC_FAILED
                result.notes.append(f"review_failed:{tid}:{str(e)[:80]}")

    result.notes.append(f"editorial_review_emitted:{editorial_review_count}")
    result.notes.append(f"decision_emitted:{decision_count}")
    result.topics_processed = len(topics_subset)
    result.finished_at = utc_now_iso()
    if result.forum_error and result.forum_events_written == 0:
        result.status = runtime_state.FAILED
    return result


if __name__ == "__main__":
    paths = forum_v2.ForumV2Paths()
    r = run_default_runtime(forum_paths=paths, max_topics=5)
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))