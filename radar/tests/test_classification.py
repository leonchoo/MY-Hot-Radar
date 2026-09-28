"""
Classification tests.

Covers the five buckets:
- BREAKING (recent + multi-source)
- RISING (growth, new w/ enough mentions)
- HOT (high mentions + cross-source)
- WATCH (default)
- COOLING (declined after HOT/RISING)
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from radar.models import Topic, Momentum, Status, SourceType
from radar.classification import classify


def _now_minus(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_breaking_recent_multi_source():
    t = Topic(mention_count=3, first_seen=_now_minus(1.0), related_urls=[
        "https://ex1.com/a", "https://ex2.com/b", "https://ex3.com/c"
    ])
    classify(t, None)
    assert t.status == Status.BREAKING, t.classification_reasons
    print("PASS test_breaking_recent_multi_source")


def test_rising_growth_with_floor():
    t = Topic(mention_count=4)
    t.momentum = Momentum(current_mentions=4, previous_mentions=2, growth=2,
                         growth_rate=100.0, is_new=False)
    classify(t, None)
    assert t.status == Status.RISING, t.classification_reasons
    print("PASS test_rising_growth_with_floor")


def test_hot_multi_source_high_mentions():
    t = Topic(mention_count=8, statuses_seen=[SourceType.NEWS_SITE, SourceType.OFFICIAL_SOURCE])
    t.momentum = Momentum(current_mentions=8, previous_mentions=8, growth=0,
                         growth_rate=0.0, is_new=False)
    classify(t, None)
    assert t.status == Status.HOT, t.classification_reasons
    print("PASS test_hot_multi_source_high_mentions")


def test_watch_default():
    t = Topic(mention_count=1)
    t.momentum = Momentum(current_mentions=1, previous_mentions=0, growth=1,
                         growth_rate=None, is_new=True)
    classify(t, None)
    assert t.status == Status.WATCH, t.classification_reasons  # 1 mention < RISING floor
    print("PASS test_watch_default")


def test_cooling_after_hot():
    t = Topic(mention_count=3, statuses_seen=[SourceType.NEWS_SITE])
    t.momentum = Momentum(current_mentions=3, previous_mentions=10, growth=-7,
                         growth_rate=-70.0, is_new=False)
    prev = Topic(id=t.id, mention_count=10, status=Status.HOT)
    classify(t, prev)
    assert t.status == Status.COOLING, t.classification_reasons
    print("PASS test_cooling_after_hot")


def test_cooling_not_applicable_when_no_prior_status():
    """A decline with no prior HOT/RISING status should NOT force COOLING."""
    t = Topic(mention_count=3)
    t.momentum = Momentum(current_mentions=3, previous_mentions=10, growth=-7,
                         growth_rate=-70.0, is_new=False)
    prev = Topic(id=t.id, mention_count=10, status=Status.WATCH)
    classify(t, prev)
    # We didn't have a HOT/RISING status before, so cooling rule does not fire.
    assert t.status in (Status.WATCH, Status.RISING) and t.status != Status.COOLING, t.classification_reasons
    print("PASS test_cooling_not_applicable_when_no_prior_status")


if __name__ == "__main__":
    test_breaking_recent_multi_source()
    test_rising_growth_with_floor()
    test_hot_multi_source_high_mentions()
    test_watch_default()
    test_cooling_after_hot()
    test_cooling_not_applicable_when_no_prior_status()
    print("ALL CLASSIFICATION TESTS PASSED")
