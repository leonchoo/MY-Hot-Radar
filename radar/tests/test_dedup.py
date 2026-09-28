"""
Dedup tests.

Covers:
- Same URL        -> 1 topic
- Same title      -> 1 topic
- Different titles, same event -> 1 topic (token-jaccard >= threshold)
- Unrelated stories -> 2 topics
"""
from __future__ import annotations

import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from radar.models import Story, SourceType, Category, Language
from radar.dedup import cluster, canonicalize_url


def s(id_, title, url, src="Outlet", category=Category.MALAYSIA, st=SourceType.NEWS_SITE):
    return Story(
        id=id_,
        title=title,
        summary="",
        url=url,
        source=src,
        source_type=st,
        category=category,
        language=Language.EN,
    )


def test_same_url_dedups():
    stories = [
        s("a", "Same headline A", "https://example.com/news/x?utm_source=tw", src="Outlet1"),
        s("b", "Same headline A duplicated", "https://example.com/news/x", src="Outlet2"),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 1, f"expected 1 topic, got {len(topics)}"
    assert topics[0].mention_count == 2
    print("PASS test_same_url_dedups")


def test_same_title_dedups():
    stories = [
        s("a", "Sample Flash Quote from PM", "https://ex.com/1"),
        s("b", "Sample Flash Quote from PM", "https://ex.com/2", src="Outlet2"),
        s("c", "Sample Flash Quote from PM", "https://ex.com/3", src="Outlet3"),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 1
    assert topics[0].mention_count == 3
    print("PASS test_same_title_dedups")


def test_different_titles_same_event_dedups():
    stories = [
        s("a", "Anwar announces cabinet reshuffle", "https://ex.com/1"),
        s("b", "Cabinet reshuffle announced by PM", "https://ex.com/2"),
        s("c", "Malaysia cabinet reshuffle takes effect", "https://ex.com/3"),
    ]
    topics, _ = cluster(stories)
    # These titles share enough tokens; expect 1 topic. If thresholds raise,
    # this becomes the test that fails first.
    assert len(topics) == 1, f"expected 1 topic, got {len(topics)}"
    print("PASS test_different_titles_same_event_dedups")


def test_unrelated_stories_dont_merge():
    stories = [
        s("a", "Local cafe opens in KL",  "https://ex.com/1", category=Category.FOOD),
        s("b", "Heavy rain floods KL",    "https://ex.com/2", category=Category.MALAYSIA),
        s("c", "PM announces reshuffle",  "https://ex.com/3", category=Category.WORLD),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 3, f"expected 3 topics, got {len(topics)}"
    print("PASS test_unrelated_stories_dont_merge")


def test_canonicalize_url_strips_tracking():
    a = "https://example.com/news/x?utm_source=x&fbclid=yy&q=hi"
    b = "https://example.com/news/x?q=hi"
    assert canonicalize_url(a) == canonicalize_url(b)
    print("PASS test_canonicalize_url_strips_tracking")


if __name__ == "__main__":
    test_canonicalize_url_strips_tracking()
    test_same_url_dedups()
    test_same_title_dedups()
    test_different_titles_same_event_dedups()
    test_unrelated_stories_dont_merge()
    print("ALL DEDUP TESTS PASSED")
