"""
Deterministic fixtures used by both the test suite and the on-ramp CLI
(--inject-fixture). They describe synthetic stories for unit-testable
categories ONLY. They are not real news.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List

from ..models import Story, SourceType, Category, Language


def _ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def fixture_stories() -> List[Story]:
    """Hand-rolled fixture stories exercising dedup / verification / momentum.

    IMPORTANT: every title includes the literal word 'Sample'. The pipeline
    doesn't filter these out automatically. A real deployment must add a
    filter that drops any story whose title or source is marked test-only.
    Until then, do not run --inject-fixture against production-tagged
    outputs without clearly labeling them as test.
    """
    now = _ago(0.5)  # 30 minutes ago
    one = _ago(1.0)
    three = _ago(3.0)
    return [
        # === Topic A: Multiple outlets covering the same event (CONFIRMED path) ===
        Story(
            id="sA1",
            title="Sample Event A confirmed by officials",
            summary="Officials have made a statement about Sample Event A.",
            url="https://example.com/news/a-1",
            source="Outlet1",
            source_type=SourceType.NEWS_SITE,
            published_at=three,
            discovered_at=now,
            category=Category.MALAYSIA,
            language=Language.EN,
        ),
        Story(
            id="sA2",
            title="Same Sample Event A draws reaction",
            summary="Reaction to Sample Event A.",
            url="https://example.com/news/a-2",
            source="Outlet2",
            source_type=SourceType.NEWS_SITE,
            published_at=one,
            discovered_at=now,
            category=Category.MALAYSIA,
            language=Language.EN,
        ),
        Story(
            id="sA3",
            title="Official press release on Sample Event A",
            summary="Official statement.",
            url="https://example.gov.my/news/a-official",
            source="GovSource",
            source_type=SourceType.OFFICIAL_SOURCE,
            published_at=now,
            discovered_at=now,
            category=Category.MALAYSIA,
            language=Language.EN,
        ),
        Story(
            id="sA4",
            title="Sample Event A reactions",
            summary="Social chatter.",
            url="https://social.example/p/1234",
            source="SocialUser",
            source_type=SourceType.PUBLIC_SOCIAL,
            published_at=now,
            discovered_at=now,
            category=Category.MALAYSIA,
            language=Language.EN,
        ),

        # === Topic B: single social post (SOCIAL BUZZ, no media) ===
        Story(
            id="sB1",
            title="Viral claim B from a social account",
            summary="Unverified social media claim.",
            url="https://social.example/p/b-1",
            source="SocialUserB",
            source_type=SourceType.PUBLIC_SOCIAL,
            published_at=now,
            discovered_at=now,
            category=Category.VIRAL,
            language=Language.EN,
        ),
        Story(
            id="sB2",
            title="Discussion about viral claim B",
            summary="Repost and reaction.",
            url="https://social.example/p/b-2",
            source="SocialUserC",
            source_type=SourceType.PUBLIC_SOCIAL,
            published_at=now,
            discovered_at=now,
            category=Category.VIRAL,
            language=Language.EN,
        ),

        # === Topic C: high mention count, multi-source = HOT path ===
        Story(
            id="sC1", title="Big Sample Event C news 1",
            summary="Coverage 1", url="https://ex.com/c-1", source="O1",
            source_type=SourceType.NEWS_SITE, published_at=now,
            discovered_at=now, category=Category.WORLD, language=Language.EN),
        Story(
            id="sC2", title="Big Sample Event C news 2",
            summary="Coverage 2", url="https://ex.com/c-2", source="O2",
            source_type=SourceType.NEWS_SITE, published_at=now,
            discovered_at=now, category=Category.WORLD, language=Language.EN),
        Story(
            id="sC3", title="Big Sample Event C news 3",
            summary="Coverage 3", url="https://ex.com/c-3", source="O3",
            source_type=SourceType.NEWS_SITE, published_at=now,
            discovered_at=now, category=Category.WORLD, language=Language.EN),
        Story(
            id="sC4", title="Big Sample Event C news 4",
            summary="Coverage 4", url="https://ex.com/c-4", source="O4",
            source_type=SourceType.NEWS_SITE, published_at=now,
            discovered_at=now, category=Category.WORLD, language=Language.EN),
        Story(
            id="sC5", title="Big Sample Event C news 5",
            summary="Coverage 5", url="https://ex.com/c-5", source="O5",
            source_type=SourceType.NEWS_SITE, published_at=now,
            discovered_at=now, category=Category.WORLD, language=Language.EN),

        # === Topic D: same title EXACTLY (dedup severe case) ===
        Story(
            id="sD1", title="Sample Flash Quote from PM",
            summary="Quote 1", url="https://ex.com/d-1", source="O-A",
            source_type=SourceType.NEWS_SITE, published_at=now,
            discovered_at=now, category=Category.MALAYSIA, language=Language.EN),
        Story(
            id="sD2", title="Sample Flash Quote from PM",
            summary="Quote 2 same wording", url="https://ex.com/d-2", source="O-B",
            source_type=SourceType.NEWS_SITE, published_at=now,
            discovered_at=now, category=Category.MALAYSIA, language=Language.EN),

        # === Topic E: distinct unrelated story ===
        Story(
            id="sE1", title="Local Sample Cafe opens in KL",
            summary="Story unrelated to A/B/C/D.",
            url="https://ex.com/e-1", source="O-Z",
            source_type=SourceType.NEWS_SITE, published_at=now,
            discovered_at=now, category=Category.FOOD, language=Language.EN),
    ]
