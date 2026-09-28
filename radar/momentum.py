"""
Momentum computation.

A Topic's momentum is computed by comparing its current mention count against
the previous scan's count for the same topic (matched by topic id).

We DO NOT compute a velocity purely from intra-scan timing: that needs a
windowed historical DB we do not yet have. Phase 1 uses pairwise comparison
between successive scans.
"""

from __future__ import annotations

from typing import Dict, Optional

from .models import Topic, Momentum


def compute_momentum(current: Topic, previous: Optional[Topic]) -> Momentum:
    cur = int(current.mention_count or 0)
    if previous is None:
        previous_count = 0
        is_new = cur > 0
    else:
        previous_count = int(previous.mention_count or 0)
        is_new = previous_count == 0 and cur > 0

    growth = cur - previous_count
    if previous_count <= 0:
        rate = None
    else:
        rate = (cur - previous_count) / previous_count * 100.0

    return Momentum(
        current_mentions=cur,
        previous_mentions=previous_count,
        growth=growth,
        growth_rate=round(rate, 2) if rate is not None else None,
        is_new=is_new,
    )


def attach_momentum(topics_now: list, topic_history: Dict[str, Topic]) -> None:
    """Mutates each topic with `.momentum` based on the previous scan's snapshot.

    `topic_history` is keyed by `Topic.content_key()` (canonical URL or
    title), so consecutive scans of the same event match even though
    random `Topic.id`s differ.
    """
    for t in topics_now:
        prev = topic_history.get(t.content_key())
        t.momentum = compute_momentum(t, prev)
