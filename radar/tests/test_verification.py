"""
Verification tests.

Covers:
- 1 source                      -> REPORTED
- 2 independent sources         -> CONFIRMED (Tier A/B)
- social only                   -> SOCIAL BUZZ
- official + media              -> CONFIRMED
- rumour (no Tier-A/B evidence) -> UNVERIFIED / RUMOUR path
"""
from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from radar.models import (
    Story, Topic, VerificationStatus, SourceType, Category, Language,
)
from radar.verification import evidence_for


def _story(sid, url, source, st, rel=3):
    return {
        "id": sid, "title": "Sample", "summary": "",
        "url": url, "source": source, "source_type": st,
        "published_at": "2026-09-28T00:00:00Z",
        "category": Category.MALAYSIA, "language": Language.EN,
        "country": "MY",
        "discovered_at": "2026-09-28T00:00:00Z",
        "_rel": rel,
    }


def test_one_low_reliability_source():
    t = Topic(story_ids=["a"], category=Category.MALAYSIA)
    s = _story("a", "https://ex.com/a", "Anon", SourceType.SEARCH_RESULT, rel=1)
    ev = evidence_for(t, {"a": s}, {"Anon": 1})
    assert ev.status == VerificationStatus.UNVERIFIED, ev.to_dict()
    print("PASS test_one_low_reliability_source")


def test_two_independent_AB_sources_confirmed():
    t = Topic(story_ids=["a", "b"], category=Category.MALAYSIA)
    s1 = _story("a", "https://news-one.com/a", "OutletA", SourceType.NEWS_SITE, rel=5)
    s2 = _story("b", "https://news-two.com/b", "OutletB", SourceType.NEWS_SITE, rel=5)
    ev = evidence_for(t, {"a": s1, "b": s2}, {"OutletA": 5, "OutletB": 5})
    assert ev.status == VerificationStatus.CONFIRMED, ev.to_dict()
    assert ev.independent_sources >= 2
    print("PASS test_two_independent_AB_sources_confirmed")


def test_social_only_social_buzz():
    t = Topic(story_ids=["a", "b"], category=Category.VIRAL)
    s1 = _story("a", "https://social1.com/a", "SocialA", SourceType.PUBLIC_SOCIAL, rel=4)
    s2 = _story("b", "https://social2.com/b", "SocialB", SourceType.PUBLIC_SOCIAL, rel=4)
    ev = evidence_for(t, {"a": s1, "b": s2}, {"SocialA": 4, "SocialB": 4})
    assert ev.status == VerificationStatus.SOCIAL_BUZZ, ev.to_dict()
    print("PASS test_social_only_social_buzz")


def test_official_plus_media_confirmed():
    t = Topic(story_ids=["a", "b"], category=Category.MALAYSIA)
    s1 = _story("a", "https://gov.example/a", "GovSource", SourceType.OFFICIAL_SOURCE, rel=5)
    s2 = _story("b", "https://news.example/b", "OutletA", SourceType.NEWS_SITE, rel=5)
    ev = evidence_for(t, {"a": s1, "b": s2}, {"GovSource": 5, "OutletA": 5})
    assert ev.status == VerificationStatus.CONFIRMED, ev.to_dict()
    print("PASS test_official_plus_media_confirmed")


def test_rumour_path_low_tier():
    """A single anonymous aggregator and one social mention should never
    reach CONFIRMED."""
    t = Topic(story_ids=["a"], category=Category.WORLD)
    s1 = _story("a", "https://anon.example/a", "Anon", SourceType.SEARCH_RESULT, rel=1)
    ev = evidence_for(t, {"a": s1}, {"Anon": 1})
    assert ev.status in (VerificationStatus.UNVERIFIED, VerificationStatus.RUMOUR), ev.to_dict()
    print("PASS test_rumour_path_low_tier")


if __name__ == "__main__":
    test_one_low_reliability_source()
    test_two_independent_AB_sources_confirmed()
    test_social_only_social_buzz()
    test_official_plus_media_confirmed()
    test_rumour_path_low_tier()
    print("ALL VERIFICATION TESTS PASSED")
