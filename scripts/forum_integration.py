#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MY Hot Radar — Forum v2 Agent Integration Bridge.

Adapts the four MHR Agents to the Forum v2 Topic/Thread/Event layer.

Architecture (per 彪哥's spec):
    MHR Collector   ->  find_topic_for_observation() / collector_emit_observation()
    MHR Radar       ->  radar_emit_source_update / radar_emit_classification_update
    MHR Default     ->  default_emit_editorial_decision (PUBLISH / MONITOR / CLOSE / ...)
    MHR Performance ->  performance_emit_report (PERFORMANCE_REPORT / SUSTAINED / COOLING)

All entry points follow the rules:
  * Forum v2 is the HUB (not a linear pipeline).
  * Any agent can call find_topic_for_*() to detect existing Topics.
  * Reactivation is automatic: same linkage_key -> same topic_id.
  * Cross-agent permission boundaries enforced (delegates to forum_v2).
  * Performance never publishes/closes/monitors (no editorial decision).
  * Radar never publishes/closes (no editorial decision).
  * Default is the editorial decision owner.

Hard rules:
  * This module NEVER modifies radar/, performance/, dashboard/, public/,
    Collector core code. It only imports them for reading.
  * Atomic writes delegated to forum_v2.
  * Idempotent: re-running the same call with the same args produces
    no duplicate Events (events.jsonl gets a single append).
  * source_message_id is preserved if a v1 message_id is provided.

This module is the only place that bridges v1 message transport with v2
Topic layer. Forum v1 files are NEVER modified.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import forum_v2  # noqa: E402
import forum_i18n  # noqa: E402


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DEFAULT_FORUM_ROOT = forum_v2.DEFAULT_FORUM_ROOT
DEFAULT_RADAR_OUTPUT = (
    HERE.parent / "radar_data" / "output" / "latest.json"
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class IntegrationError(Exception):
    pass


# ---------------------------------------------------------------------------
# 中文 i18n helpers (Phase 4 — 中文新闻室)
# ---------------------------------------------------------------------------

def _wrap_payload_forum(payload: Optional[Dict]) -> Optional[Dict]:
    """Wrap a payload for Forum v2 by translating note/summary/reason/etc.

    The schema keys remain English (machine contract). Human-readable
    strings become bilingual {"en": ..., "zh": ...}. Existing English
    content is kept under "en"; Chinese content is generated under "zh"
    by the i18n module.

    If payload is None or not a dict, returns it unchanged.
    """
    if payload is None:
        return None
    if not isinstance(payload, dict):
        return payload
    return forum_i18n.i18n_payload(payload)


def _wrap_evidence(evidence: Optional[Dict]) -> Optional[Dict]:
    """Wrap evidence for Forum v2.

    If evidence contains a `source_description` field, translate it
    to Chinese. Otherwise pass through.
    """
    if not isinstance(evidence, dict):
        return evidence
    if "source_description" in evidence:
        ev = dict(evidence)
        ev["source_description"] = forum_i18n.i18n_payload(
            {"note": ev["source_description"]}
        ).get("note", ev["source_description"])
        return ev
    return evidence


# ---------------------------------------------------------------------------
# Linkage-key helpers (Agent-specific)
# ---------------------------------------------------------------------------

def linkage_key_from_radar_topic(radar_topic_id: str, title: str) -> str:
    """Build a Forum v2 linkage_key for a Radar topic.

    Uses the canonical title normalized; the topic_id is supplementary
    and folded into the linkage if present (for stability across title
    edits).
    """
    base = forum_v2.normalize_linkage_key(title)
    if radar_topic_id:
        # Append a stable identifier segment so two radars with very
        # similar titles can still merge if their topic_ids are stable.
        return f"{base}|rid={radar_topic_id}"
    return base


def linkage_key_from_observation(title: str) -> str:
    """Build a linkage_key for a Collector observation (by title)."""
    return forum_v2.normalize_linkage_key(title)


def linkage_key_from_url(url: str) -> str:
    """Build a linkage_key for a Performance observation (by URL)."""
    if not isinstance(url, str) or not url.strip():
        return ""
    s = url.lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = re.sub(r"\?.*$", "", s)
    s = re.sub(r"#.*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Topic lookup (find existing Topic for an Agent observation)
# ---------------------------------------------------------------------------

def find_topic_for_observation(
    title: str,
    *,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Optional[forum_v2.Topic]:
    """Find an existing Forum v2 Topic matching a Collector observation."""
    paths = paths or forum_v2.ForumV2Paths()
    key = linkage_key_from_observation(title)
    return forum_v2.find_topic_by_linkage(key, paths)


def find_topic_for_radar_topic(
    radar_topic_id: str,
    title: str,
    *,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Optional[forum_v2.Topic]:
    paths = paths or forum_v2.ForumV2Paths()
    key = linkage_key_from_radar_topic(radar_topic_id, title)
    return forum_v2.find_topic_by_linkage(key, paths)


def find_topic_for_url(
    url: str,
    *,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Optional[forum_v2.Topic]:
    """Find a Topic matching a URL (used by MHR Performance for reports)."""
    paths = paths or forum_v2.ForumV2Paths()
    key = linkage_key_from_url(url)
    if not key:
        return None
    return forum_v2.find_topic_by_linkage(key, paths)


# ---------------------------------------------------------------------------
# Source-message bridge (v1 message_id <-> v2 source_message_id)
# ---------------------------------------------------------------------------

def build_event_with_source_message(
    *,
    payload: Dict,
    source_message_id: Optional[str] = None,
) -> Dict:
    """Inject `source_message_id` into an Event payload if provided.

    This preserves the v1 message_id binding inside the v2 Event payload,
    so an audit can trace from a v2 Event back to the v1 message that
    triggered it (when applicable). If no source_message_id is given,
    the payload is returned unchanged.
    """
    if not source_message_id:
        return payload
    p = dict(payload)
    p["source_message_id"] = source_message_id
    return p


# ---------------------------------------------------------------------------
# MHR Collector integration
# ---------------------------------------------------------------------------

def collector_emit_observation(
    *,
    title: str,
    evidence: Dict,
    source_message_id: Optional[str] = None,
    classification: str = "WATCH",
    languages: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    confidence: float = 1.0,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event, bool, bool]:
    """MHR Collector emits a Topic-level observation.

    Behavior:
      1. Compute linkage_key from the title.
      2. If a Topic exists with the same linkage_key:
         - If status is CLOSED or MONITORING/FOLLOW_UP with new heat
           evidence -> emit REACTIVATION_SIGNAL + transition to REACTIVATED
         - Otherwise -> emit OBSERVATION (no status change)
      3. Otherwise create a new Topic with status=NEW.

    Returns (topic, event, was_reactivated, was_created).

    中文新闻室 (Phase 4):
      * Title is stored as plain string (backward compat).
      * topic.json also gets `title_i18n` field with bilingual titles.
      * Event payload gets `note` (bilingual) describing the observation.
    """
    paths = paths or forum_v2.ForumV2Paths()
    paths.ensure_layout()
    existing = find_topic_for_observation(title, paths=paths)

    title_zh = forum_i18n.translate_title(title)
    note_bilingual = forum_i18n.collector_observation_note(evidence)
    payload = build_event_with_source_message(
        payload={
            "observation": evidence,
            "title": title,
            "note": note_bilingual,
        },
        source_message_id=source_message_id,
    )

    if existing is None:
            # Brand-new Topic.
            topic, evt, was_reactivated = forum_v2.create_topic(
                title=title,
                agent="collector",
                paths=paths,
                classification=classification,
                languages=languages,
                tags=tags,
                event_payload=_wrap_payload_forum({
                    **payload,
                    "title_i18n": forum_i18n.title_payload(title),
                }),
                event_evidence=_wrap_evidence(evidence),
                confidence=confidence,
            )
            return topic, evt, False, True

    # Existing Topic.
    # Reactivate if CLOSED; otherwise append an OBSERVATION event.
    if existing.status in (forum_v2.TopicLifecycle.CLOSED.value,):
        note_reactive = forum_i18n.collector_social_heat_note(evidence)
        payload_reactive = build_event_with_source_message(
            payload={
                "observation": evidence,
                "title": title,
                "note": note_reactive,
            },
            source_message_id=source_message_id,
        )
        topic, evt, _ = forum_v2.create_topic(
            title=title,
            agent="collector",
            paths=paths,
            event_payload=_wrap_payload_forum(payload_reactive),
            event_evidence=_wrap_evidence(evidence),
            confidence=confidence,
        )
        return topic, evt, True, False

    # Append an OBSERVATION (no status change).
    topic, evt = forum_v2.append_event(
        topic_id=existing.topic_id,
        agent="collector",
        event_type="OBSERVATION",
        payload=_wrap_payload_forum(payload),
        evidence=_wrap_evidence(evidence),
        confidence=confidence,
        paths=paths,
    )
    return topic, evt, False, False


def collector_emit_social_heat_signal(
    *,
    title: str,
    evidence: Dict,
    source_message_id: Optional[str] = None,
    confidence: float = 1.0,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    """MHR Collector detects new heat on an EXISTING Topic.

    Looks up by title linkage. If found, emits SOCIAL_HEAT_SIGNAL and
    transitions the Topic to REACTIVATED. If not found, this is an
    error (the heat signal must reference a known Topic).

    中文新闻室 (Phase 4):
      * Payload gets `note` (bilingual) describing the social heat.
    """
    paths = paths or forum_v2.ForumV2Paths()
    existing = find_topic_for_observation(title, paths=paths)
    if existing is None:
        raise IntegrationError(
            f"SOCIAL_HEAT_SIGNAL referenced unknown title: {title!r} — "
            f"cannot find existing Topic"
        )
    payload = build_event_with_source_message(
        payload={
            "title": title,
            "note": forum_i18n.collector_social_heat_note(evidence),
        },
        source_message_id=source_message_id,
    )
    topic, evt = forum_v2.append_event(
        topic_id=existing.topic_id,
        agent="collector",
        event_type="SOCIAL_HEAT_SIGNAL",
        payload=_wrap_payload_forum(payload),
        evidence=_wrap_evidence(evidence),
        confidence=confidence,
        paths=paths,
        next_status=forum_v2.TopicLifecycle.REACTIVATED.value,
    )
    return topic, evt


# ---------------------------------------------------------------------------
# MHR Radar integration
# ---------------------------------------------------------------------------

def radar_emit_source_update(
    *,
    radar_topic_id: str,
    title: str,
    source_url: str,
    source_name: str,
    language: str = "en",
    source_message_id: Optional[str] = None,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event, bool]:
    """MHR Radar records a new source attached to a Topic.

    If the Radar topic_id is unknown to Forum v2:
      - First, route through Collector (Collector is the discoverer).
      - Collector emits an OBSERVATION (which finds-or-creates the Topic).
      - Then Radar appends SOURCE_UPDATE to the resulting Topic.

    This preserves the agent permission boundary: Radar never emits
    CREATE_TOPIC; only Collector does. The integration module
    orchestrates the multi-step emit.
    """
    paths = paths or forum_v2.ForumV2Paths()
    payload = build_event_with_source_message(
            payload={
                "radar_topic_id": radar_topic_id,
                "url": source_url,
                "source_name": source_name,
                "language": language,
                "note": forum_i18n.radar_source_note(source_name, language),
            },
            source_message_id=source_message_id,
        )
    # Look up by either radar_topic_id linkage OR title linkage.
    existing = find_topic_for_radar_topic(radar_topic_id, title, paths=paths)
    if existing is None:
        existing = find_topic_for_observation(title, paths=paths)
    bootstrap_happened = False
    if existing is None:
        # Bootstrap via Collector (which has CREATE_TOPIC permission).
        collector_topic, _, was_created, _ = collector_emit_observation(
            title=title,
            evidence={
                "source": "mhr_radar",
                "radar_topic_id": radar_topic_id,
                "source_url": source_url,
            },
            source_message_id=source_message_id,
            languages=[language] if language else None,
            paths=paths,
        )
        existing = collector_topic
        bootstrap_happened = True
    topic, evt = forum_v2.append_event(
        topic_id=existing.topic_id,
        agent="radar",
        event_type="SOURCE_UPDATE",
        payload=_wrap_payload_forum(payload),
        evidence={"source_url": source_url, "source_name": source_name},
        paths=paths,
        next_status=forum_v2.TopicLifecycle.RADAR_TRACKING.value
            if existing.status == forum_v2.TopicLifecycle.NEW.value else None,
    )
    return topic, evt, bootstrap_happened


def radar_emit_classification_update(
    *,
    topic_id: str,
    classification: str,
    confidence: float = 1.0,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    """MHR Radar updates Topic classification."""
    paths = paths or forum_v2.ForumV2Paths()
    payload = {
        "classification": classification,
        "note": forum_i18n.radar_classification_note(classification),
    }
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="radar",
        event_type="CLASSIFICATION_UPDATE",
        payload=_wrap_payload_forum(payload),
        confidence=confidence,
        paths=paths,
    )
    return topic, evt


def radar_emit_cross_source_confirmation(
    *,
    topic_id: str,
    source_url: str,
    source_name: str,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    payload = {
        "url": source_url,
        "source_name": source_name,
        "note": forum_i18n.radar_cross_source_note(source_name),
    }
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="radar",
        event_type="CROSS_SOURCE_CONFIRMATION",
        payload=_wrap_payload_forum(payload),
        evidence=_wrap_evidence({"source_url": source_url, "source_name": source_name}),
        paths=paths,
    )
    return topic, evt


def radar_emit_momentum_update(
    *,
    topic_id: str,
    delta_score: float,
    window: str,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    payload = {
        "delta_score": delta_score,
        "window": window,
        "note": forum_i18n.radar_momentum_note(delta_score, window),
    }
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="radar",
        event_type="MOMENTUM_UPDATE",
        payload=_wrap_payload_forum(payload),
        paths=paths,
    )
    return topic, evt


# ---------------------------------------------------------------------------
# MHR Default integration (editorial decision owner)
# ---------------------------------------------------------------------------

def default_emit_editorial_review(
    *,
    topic_id: str,
    note: str,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="default",
        event_type="EDITORIAL_REVIEW",
        payload=_wrap_payload_forum({
            "note": forum_i18n.default_review_note(_classify_topic(topic_id, paths)),
        }),
        paths=paths,
        next_status=forum_v2.TopicLifecycle.EDITORIAL_REVIEW.value,
    )
    return topic, evt


def default_emit_publish(
    *,
    topic_id: str,
    canonical_url: str,
    slug: str,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    cls = _classify_topic(topic_id, paths)
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="default",
        event_type="PUBLISH",
        payload=_wrap_payload_forum({
            "canonical_url": canonical_url,
            "slug": slug,
            "note": forum_i18n.default_publish_note(canonical_url, slug, cls),
        }),
        paths=paths,
        next_status=forum_v2.TopicLifecycle.PUBLISHED.value,
    )
    return topic, evt


def default_emit_monitor(
    *,
    topic_id: str,
    note: str = "",
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="default",
        event_type="MONITOR",
        payload=_wrap_payload_forum({
            "note": forum_i18n.default_monitor_note(note or ""),
        }),
        paths=paths,
        next_status=forum_v2.TopicLifecycle.MONITORING.value,
    )
    return topic, evt


def default_emit_follow_up(
    *,
    topic_id: str,
    decision: str,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="default",
        event_type="FOLLOW_UP",
        payload=_wrap_payload_forum({
            "decision": decision,
            "note": forum_i18n.default_follow_up_note(decision),
        }),
        paths=paths,
        next_status=forum_v2.TopicLifecycle.FOLLOW_UP.value,
    )
    return topic, evt


def default_emit_close(
    *,
    topic_id: str,
    reason: str = "",
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="default",
        event_type="CLOSE",
        payload=_wrap_payload_forum({
            "reason": reason,
            "note": forum_i18n.default_close_note(reason or ""),
        }),
        paths=paths,
        next_status=forum_v2.TopicLifecycle.CLOSED.value,
    )
    return topic, evt


def default_update_article(
    *,
    topic_id: str,
    canonical_url: str,
    change_summary: str,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="default",
        event_type="UPDATE_ARTICLE",
        payload=_wrap_payload_forum({
            "canonical_url": canonical_url,
            "change_summary": change_summary,
            "note": forum_i18n.default_update_article_note(change_summary),
        }),
        paths=paths,
    )
    return topic, evt


def _classify_topic(topic_id: str, paths: Optional[forum_v2.ForumV2Paths]) -> str:
    """Helper: read a Topic's classification; return "" if not found."""
    t = forum_v2.get_topic(topic_id, paths=paths)
    if t is None:
        return ""
    return getattr(t, "classification", "") or ""


def get_full_thread(
    topic_id: str,
    *,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Optional[Dict]:
    """MHR Default reads the complete Thread of a Topic.

    Returns a dict with topic + chronological events + lifecycle summary,
    or None if the Topic does not exist.
    """
    paths = paths or forum_v2.ForumV2Paths()
    topic = forum_v2.get_topic(topic_id, paths=paths)
    if topic is None:
        return None
    events = forum_v2.get_events(topic_id, paths=paths)
    return {
        "topic": topic.to_dict(),
        "events": [e.to_dict() for e in events],
        "event_count": len(events),
    }


# ---------------------------------------------------------------------------
# MHR Performance integration (analysis only — no editorial decision)
# ---------------------------------------------------------------------------

def performance_emit_report(
    *,
    topic_id: str,
    velocity: str,
    engagement: str,
    window: str,
    source_message_id: Optional[str] = None,
    confidence: float = 1.0,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    payload = build_event_with_source_message(
        payload={
            "velocity": velocity,
            "engagement": engagement,
            "window": window,
            "note": forum_i18n.performance_report_note(velocity, engagement, window),
        },
        source_message_id=source_message_id,
    )
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="mhr_performance",
        event_type="PERFORMANCE_REPORT",
        payload=_wrap_payload_forum(payload),
        confidence=confidence,
        paths=paths,
    )
    return topic, evt


def performance_emit_sustained(
    *,
    topic_id: str,
    duration_hours: float,
    sources_increasing: bool,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    payload = {
        "duration_hours": duration_hours,
        "sources_increasing": sources_increasing,
        "note": forum_i18n.performance_sustained_note(duration_hours, sources_increasing),
    }
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="mhr_performance",
        event_type="SUSTAINED_SIGNAL",
        payload=_wrap_payload_forum(payload),
        paths=paths,
    )
    return topic, evt


def performance_emit_cooling(
    *,
    topic_id: str,
    window: str,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[forum_v2.Topic, forum_v2.Event]:
    paths = paths or forum_v2.ForumV2Paths()
    payload = {
        "window": window,
        "note": forum_i18n.performance_cooling_note(window),
    }
    topic, evt = forum_v2.append_event(
        topic_id=topic_id,
        agent="mhr_performance",
        event_type="COOLING_SIGNAL",
        payload=_wrap_payload_forum(payload),
        paths=paths,
    )
    return topic, evt


# ---------------------------------------------------------------------------
# High-level integration: load Radar output and integrate into Forum v2
# ---------------------------------------------------------------------------

def integrate_radar_output_into_forum(
    *,
    radar_output_path: Path = DEFAULT_RADAR_OUTPUT,
    paths: Optional[forum_v2.ForumV2Paths] = None,
    source_message_id: Optional[str] = None,
    max_topics: Optional[int] = None,
) -> Dict:
    """One-shot integration: read MY Hot Radar's radar_data/output/latest.json
    and push each Radar Topic into Forum v2.

    This is the integration entry point that ties the running Radar
    pipeline to the Forum v2 Topic layer.

    Returns a summary dict (count of topics integrated, count of source
    updates, topic_ids).
    """
    paths = paths or forum_v2.ForumV2Paths()
    paths.ensure_layout()
    radar_output_path = Path(radar_output_path)
    if not radar_output_path.exists():
        raise IntegrationError(f"radar output not found: {radar_output_path}")
    payload = json.loads(radar_output_path.read_text(encoding="utf-8"))

    integrated_topics: List[str] = []
    skipped = 0
    source_updates = 0
    classification_updates = 0

    topics = payload.get("topics", [])
    if max_topics is not None:
        topics = topics[:max_topics]

    for radar_topic in topics:
        try:
            title = radar_topic.get("title") or radar_topic.get("id") or "unknown"
            radar_topic_id = radar_topic.get("id") or radar_topic.get("topic_id") or ""
            status = radar_topic.get("status", "WATCH")
            # Map Radar status to Forum v2 classification
            cls_map = {
                "BREAKING": "BREAKING",
                "RISING": "RISING",
                "HOT": "HOT",
                "WATCH": "WATCH",
                "COOLING": "COOLING",
                "OLD": "COOLING",
                "EARLY_SPIKE": "RISING",
                "FAST_GROWTH": "RISING",
                "SUSTAINED": "HOT",
            }
            cls = cls_map.get(status, "WATCH")
            languages = []
            if "languages" in radar_topic and isinstance(radar_topic["languages"], list):
                languages = list(radar_topic["languages"])

            # Check if already integrated
            existing = find_topic_for_radar_topic(radar_topic_id, title, paths=paths)

            if existing is None:
                # Create via Collector bootstrap + initial Radar SOURCE_UPDATE
                topic, evt, _ = radar_emit_source_update(
                    radar_topic_id=radar_topic_id,
                    title=title,
                    source_url="(radar_pipeline)",
                    source_name="mhr_radar",
                    language=languages[0] if languages else "en",
                    source_message_id=source_message_id,
                    paths=paths,
                )
                # Initial classification update
                radar_emit_classification_update(
                    topic_id=topic.topic_id,
                    classification=cls,
                    paths=paths,
                )
                classification_updates += 1
            else:
                # Update existing topic's classification (idempotent)
                if existing.classification != cls:
                    radar_emit_classification_update(
                        topic_id=existing.topic_id,
                        classification=cls,
                        paths=paths,
                    )
                    classification_updates += 1
                topic = existing

            integrated_topics.append(topic.topic_id)
            source_updates += 1

        except Exception as e:
            skipped += 1
            continue

    return {
        "integrated_count": len(integrated_topics),
        "source_updates": source_updates,
        "classification_updates": classification_updates,
        "skipped": skipped,
        "topic_ids": integrated_topics,
    }


# ---------------------------------------------------------------------------
# v1 -> v2 bridge helper (lightweight)
# ---------------------------------------------------------------------------

def bridge_v1_message_to_v2_event(
    *,
    message: Dict,
    paths: Optional[forum_v2.ForumV2Paths] = None,
) -> Tuple[Optional[forum_v2.Topic], Optional[forum_v2.Event], bool, bool]:
    """Bridge a v1 Forum message into the v2 Topic layer.

    Reads the v1 message's `extra.signal_kind` and `extra.observation_id`
    (or falls back to body content) to determine what v2 Event to emit.
    Returns (topic, event, was_reactivated, was_created).
    """
    paths = paths or forum_v2.ForumV2Paths()
    message_id = message.get("message_id")
    sender = message.get("sender")
    subject = message.get("subject") or ""
    body = message.get("body") or ""
    extra = message.get("extra") or {}

    # Choose the linkage_key / title from subject or a tagged field
    title = subject.strip() or f"message {message_id}"

    # Determine the Agent mapping
    sender_to_agent = {
        "collector": "collector",
        "mhr_performance": "mhr_performance",
        "hermes": "default",
        "system": "default",
    }
    agent = sender_to_agent.get(sender, "default")

    # Use signal_kind if provided to choose event type
    signal_kind = (extra.get("signal_kind") or "").upper()
    evidence = {"v1_message_id": message_id, "v1_sender": sender, "v1_subject": subject}

    # If the body mentions PERFORMANCE SIGNAL, route via Performance
    if "PERFORMANCE SIGNAL" in body or agent == "mhr_performance":
        # Performance reports must attach to a known Topic; try by URL in body
        url_match = re.search(r"https?://\S+", body)
        url = url_match.group(0) if url_match else None
        if url:
            existing = find_topic_for_url(url, paths=paths)
            if existing is not None:
                topic, evt = performance_emit_report(
                    topic_id=existing.topic_id,
                    velocity="rising",
                    engagement="medium",
                    window="audit",
                    source_message_id=message_id,
                    paths=paths,
                )
                return topic, evt, False, False
        # If no Topic matches, create one with the subject as title
        topic, evt, was_reactivated, was_created = collector_emit_observation(
            title=title,
            evidence=_wrap_evidence(evidence),
            source_message_id=message_id,
            paths=paths,
        )
        # Then Performance report attaches
        performance_emit_report(
            topic_id=topic.topic_id,
            velocity="rising",
            engagement="medium",
            window="audit",
            source_message_id=message_id,
            paths=paths,
        )
        return topic, evt, was_reactivated, was_created

    # Default: Collector observation
    topic, evt, was_reactivated, was_created = collector_emit_observation(
        title=title,
        evidence=_wrap_evidence(evidence),
        source_message_id=message_id,
        paths=paths,
    )
    return topic, evt, was_reactivated, was_created


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="MHR Forum v2 agent integration")
    sub = p.add_subparsers(dest="cmd")

    # integrate-radar
    p_int = sub.add_parser("integrate-radar", help="Integrate current radar output into Forum v2")
    p_int.add_argument("--radar-output", default=str(DEFAULT_RADAR_OUTPUT))
    p_int.add_argument("--source-message-id", default=None)
    p_int.add_argument("--max-topics", type=int, default=None)

    # bridge-v1-message
    p_br = sub.add_parser("bridge-v1-message", help="Bridge a v1 message into Forum v2")
    p_br.add_argument("--message-path", required=True)

    args = p.parse_args(argv)

    if args.cmd == "integrate-radar":
        result = integrate_radar_output_into_forum(
            radar_output_path=Path(args.radar_output),
            source_message_id=args.source_message_id,
            max_topics=args.max_topics,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "bridge-v1-message":
        msg = json.loads(Path(args.message_path).read_text(encoding="utf-8"))
        topic, evt, was_reactivated, was_created = bridge_v1_message_to_v2_event(message=msg)
        if topic is None:
            print("[FAIL] could not bridge", file=sys.stderr)
            return 1
        print(json.dumps({
            "topic_id": topic.topic_id,
            "event": evt.to_dict(),
            "was_reactivated": was_reactivated,
            "was_created": was_created,
        }, ensure_ascii=False, indent=2))
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
