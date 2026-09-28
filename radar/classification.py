"""
Radar classification.

Given a Topic (already populated with momentum and verification), assign one
of: BREAKING, RISING, HOT, WATCH, COOLING.

The rules are stored in CLASSIFICATION_RULES below so anyone reading them can
see exactly why a topic got its status.

Order of evaluation:
  1. COOLING only if topic was previously HOT or RISING and growth_rate is below
     COOLING_DECLINE_FACTOR.
  2. BREAKING: first_seen within 3 hours AND >= BREAKING_MIN_PLATFORM_DIVERSITY
     distinct source origins have been seen.
  3. HOT: mention_count >= HOT_MENTION_FLOOR and either >=2 source types or
     growth_rate >= RISING_GROWTH_FACTOR.
  4. RISING: growth_rate >= RISING_GROWTH_FACTOR and mention_count >= RISING_MENTION_FLOOR,
     OR is_new with mention_count >= RISING_MENTION_FLOOR.
  5. WATCH: everything else (default).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple
import re

from .models import Topic, Status
from .thresholds import (
    RISING_GROWTH_FACTOR, HOT_MENTION_FLOOR, RISING_MENTION_FLOOR,
    COOLING_DECLINE_FACTOR, BREAKING_MAX_HOURS_SINCE_FIRST_SEEN,
    BREAKING_MIN_PLATFORM_DIVERSITY,
)


# Rule registry -- in evaluation order. Each tuple is (name, predicate).
# A predicate takes the topic and returns a Status|None or a (Status, reason) tuple.
CLASSIFICATION_RULES: List[Tuple[str, callable]] = []  # type: ignore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    # Accept "YYYY-MM-DDTHH:MM:SSZ" and "YYYY-MM-DD HH:MM:SS"
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            return datetime.fromisoformat(s)
    except ValueError:
        # last-resort: date-only
        try:
            return datetime.fromisoformat(s.split("T")[0])
        except ValueError:
            return None


def _rule_cooling(topic: Topic, prev: Topic | None) -> tuple[Status | None, str | None]:
    if prev is None:
        return None, None
    if prev.status not in (Status.HOT, Status.RISING):
        return None, None
    mom = topic.momentum
    if mom.growth_rate is None:
        return None, None
    if mom.current_mentions <= 0:
        return None, None
    ratio = mom.current_mentions / max(prev.mention_count, 1)
    if ratio <= COOLING_DECLINE_FACTOR and mom.current_mentions < prev.mention_count:
        return Status.COOLING, (
            f"prior status was {prev.status.value}; current/previous={ratio:.2f} <= {COOLING_DECLINE_FACTOR}"
        )
    return None, None


def _rule_breaking(topic: Topic, _prev: Topic | None) -> tuple[Status | None, str | None]:
    first = _parse_iso(topic.first_seen)
    if first is None:
        return None, None
    age_h = (_now() - first).total_seconds() / 3600.0
    if age_h < 0 or age_h > BREAKING_MAX_HOURS_SINCE_FIRST_SEEN:
        return None, None
    # distinct source origins in the topic
    origins = set()
    from urllib.parse import urlsplit
    for url in topic.related_urls:
        try:
            p = urlsplit(url)
            origins.add(f"{p.scheme}://{p.netloc}")
        except ValueError:
            origins.add(url)
    if len(origins) >= BREAKING_MIN_PLATFORM_DIVERSITY:
        return Status.BREAKING, (
            f"first_seen within {BREAKING_MAX_HOURS_SINCE_FIRST_SEEN}h ({age_h:.1f}h) "
            f"and {len(origins)} distinct sources"
        )
    return None, None


def _rule_hot(topic: Topic, _prev: Topic | None) -> tuple[Status | None, str | None]:
    if topic.mention_count < HOT_MENTION_FLOOR:
        return None, None
    types = len(topic.statuses_seen)
    growth = topic.momentum.growth_rate
    if types >= 2 or (growth is not None and growth >= (RISING_GROWTH_FACTOR - 1.0) * 100.0):
        return Status.HOT, (
            f">={HOT_MENTION_FLOOR} mentions and "
            + (f">=2 source types ({types})" if types >= 2 else f"growth={growth:.1f}%")
        )
    return None, None


def _rule_rising(topic: Topic, _prev: Topic | None) -> tuple[Status | None, str | None]:
    cur = topic.mention_count
    if cur < RISING_MENTION_FLOOR:
        return None, None
    growth = topic.momentum.growth_rate
    if topic.momentum.is_new:
        return Status.RISING, f"new topic with {cur} mentions"
    if growth is not None and growth >= (RISING_GROWTH_FACTOR - 1.0) * 100.0:
        return Status.RISING, f"growth={growth:.1f}% (>= {int((RISING_GROWTH_FACTOR-1)*100)}%)"
    return None, None


# Register rules in evaluation order
CLASSIFICATION_RULES = [
    ("cooling", _rule_cooling),
    ("breaking", _rule_breaking),
    ("hot", _rule_hot),
    ("rising", _rule_rising),
]


def classify(topic: Topic, prev: Topic | None = None) -> None:
    reasons: list[str] = []
    fallback = Status.WATCH
    for name, fn in CLASSIFICATION_RULES:
        status, reason = fn(topic, prev)
        if status is not None:
            topic.status = status
            reasons.append(f"{name}: {reason}")
            topic.classification_reasons = reasons
            return
    topic.status = fallback
    reasons.append(f"watch: no rule matched (mention_count={topic.mention_count}, "
                   f"growth_rate={topic.momentum.growth_rate}, "
                   f"is_new={topic.momentum.is_new})")
    topic.classification_reasons = reasons


def classify_all(topics: List[Topic], history_by_id: dict) -> None:
    """Apply classification to every topic in-place, reading prior status from history.

    history_by_id is keyed by `Topic.content_key()`, not the random id.
    """
    for t in topics:
        prev = history_by_id.get(t.content_key())
        classify(t, prev)
