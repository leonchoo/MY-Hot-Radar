"""
Momentum tests.

Covers:
- 0 -> 5  (NEW)
- 5 -> 5  (no growth)
- 5 -> 10 (+100%)
- 10 -> 5 (-50% decline)
- division-by-zero safety
"""
from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from radar.models import Topic, Momentum, Status
from radar.momentum import compute_momentum


def test_zero_to_five_is_new():
    cur = Topic(id="t1", mention_count=5)
    mom = compute_momentum(cur, None)
    assert mom.is_new is True
    assert mom.growth_rate is None  # previous was 0 -> undefined percent
    assert mom.growth == 5
    print("PASS test_zero_to_five_is_new")


def test_five_to_five_no_growth():
    cur = Topic(id="t1", mention_count=5)
    prev = Topic(id="t1", mention_count=5, status=Status.WATCH)
    mom = compute_momentum(cur, prev)
    assert mom.is_new is False
    assert mom.growth == 0
    assert mom.growth_rate == 0.0
    print("PASS test_five_to_five_no_growth")


def test_five_to_ten_doubles():
    cur = Topic(id="t1", mention_count=10)
    prev = Topic(id="t1", mention_count=5, status=Status.WATCH)
    mom = compute_momentum(cur, prev)
    assert mom.is_new is False
    assert mom.growth == 5
    assert mom.growth_rate == 100.0
    print("PASS test_five_to_ten_doubles")


def test_ten_to_five_declines():
    cur = Topic(id="t1", mention_count=5)
    prev = Topic(id="t1", mention_count=10, status=Status.HOT)
    mom = compute_momentum(cur, prev)
    assert mom.is_new is False
    assert mom.growth == -5
    assert mom.growth_rate == -50.0
    print("PASS test_ten_to_five_declines")


def test_previous_zero_current_zero():
    """When previous is 0 and current is 0, growth_rate must NOT be 0.0 -
    it should be None, signaling 'no comparable baseline'."""
    cur = Topic(id="t1", mention_count=0)
    prev = Topic(id="t1", mention_count=0, status=Status.WATCH)
    mom = compute_momentum(cur, prev)
    assert mom.is_new is False
    assert mom.growth_rate is None  # not 0.0 - undefined
    assert mom.growth == 0
    print("PASS test_previous_zero_current_zero")


def test_content_key_matches_by_canonical_url():
    """Regression: random ids change per scan, but content_key matches.
    This is what makes cross-scan momentum work."""
    a = Topic(id="t_aaa", title="Event X", canonical_url="https://example.com/x")
    b = Topic(id="t_bbb", title="Event X", canonical_url="https://example.com/x")
    assert a.content_key() == b.content_key(), \
        "topics with the same canonical_url must share content_key"
    assert "t_aaa" not in a.content_key() and "t_bbb" not in b.content_key(), \
        "content_key must not include random ids"
    print("PASS test_content_key_matches_by_canonical_url")


def test_content_key_falls_back_to_title():
    """When canonical_url is missing, content_key uses title (lower-cased)."""
    a = Topic(id="t1", title="Event X happened today")
    b = Topic(id="t2", title="Event X happened today")
    assert a.content_key() == b.content_key()
    print("PASS test_content_key_falls_back_to_title")


def test_content_key_distinct_for_different_events():
    a = Topic(id="t1", title="Flood in Bangkok", canonical_url="https://a.com/x")
    b = Topic(id="t2", title="Trump-Xi summit",  canonical_url="https://b.com/y")
    assert a.content_key() != b.content_key()
    print("PASS test_content_key_distinct_for_different_events")


if __name__ == "__main__":
    test_zero_to_five_is_new()
    test_five_to_five_no_growth()
    test_five_to_ten_doubles()
    test_ten_to_five_declines()
    test_previous_zero_current_zero()
    test_content_key_matches_by_canonical_url()
    test_content_key_falls_back_to_title()
    test_content_key_distinct_for_different_events()
    print("ALL MOMENTUM TESTS PASSED")
