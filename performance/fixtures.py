"""
Synthetic test fixtures for Performance Intelligence.

These are EXPLICITLY SYNTHETIC. They are used only by tests. The
production PerformanceStore refuses to persist anything tagged
synthetic (see store.SYNTHETIC_FLAG and SyntheticFixtureError).

The fixtures are designed to cover the spec §22 cases (15m / 30m /
1h observation windows for a sample article) plus boundary cases
for classification and engagement math.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from .enums import Platform, SourceType
from .ids import content_id_for, snapshot_id_for
from .models import ContentIdentity, PerformanceSnapshot


# Tag attached to every synthetic dict so the store can reject it.
SYNTHETIC_TAG = "_synthetic"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tag(payload: dict) -> dict:
    """Attach the synthetic tag. Use only in tests / fixtures."""
    payload[SYNTHETIC_TAG] = True
    return payload


# ============================================================================
# Article A — 15m / 30m / 1h windows, classic breakout curve
# ============================================================================

def make_synthetic_article_a() -> dict:
    """Article A: classic breakout curve across 3 windows.

    Article A:
      15m: views 1000, likes 30, comments 4, shares 2
      30m: views 3000, likes 90, comments 12, shares 10
       1h: views 12000, likes 500, comments 60, shares 80
    """
    base = _now_utc() - timedelta(hours=1)
    t15 = base + timedelta(minutes=15)
    t30 = base + timedelta(minutes=30)
    t60 = base + timedelta(hours=1)

    cid = content_id_for(
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar (synthetic)",
        url="https://example.com/synthetic/article-a",
        title="Synthetic Article A (test fixture)",
    )
    content = ContentIdentity(
        content_id=cid,
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar (synthetic)",
        url="https://example.com/synthetic/article-a",
        title="Synthetic Article A (test fixture)",
        category="MALAYSIA",
        topic_type="NEWS",
        language="en",
        published_at=_iso(base),
    )

    snapshots = [
        PerformanceSnapshot(
            content_id=cid, captured_at=_iso(t15),
            views=1000, likes=30, comments=4, shares=2,
        ),
        PerformanceSnapshot(
            content_id=cid, captured_at=_iso(t30),
            views=3000, likes=90, comments=12, shares=10,
        ),
        PerformanceSnapshot(
            content_id=cid, captured_at=_iso(t60),
            views=12000, likes=500, comments=60, shares=80,
        ),
    ]
    return {
        "content": _tag(content.to_dict()),
        "snapshots": [_tag(s.to_dict()) for s in snapshots],
    }


# ============================================================================
# Article B — flat / cooling
# ============================================================================

def make_synthetic_article_b() -> dict:
    """Article B: small growth, then near-flat (COOLING / STABLE)."""
    base = _now_utc() - timedelta(hours=2)
    t1 = base + timedelta(minutes=30)
    t2 = base + timedelta(hours=2)

    cid = content_id_for(
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar (synthetic)",
        url="https://example.com/synthetic/article-b",
        title="Synthetic Article B (test fixture)",
    )
    content = ContentIdentity(
        content_id=cid,
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar (synthetic)",
        url="https://example.com/synthetic/article-b",
        title="Synthetic Article B (test fixture)",
        category="WORLD",
        topic_type="NEWS",
        language="en",
        published_at=_iso(base),
    )
    snapshots = [
        PerformanceSnapshot(
            content_id=cid, captured_at=_iso(t1),
            views=200, likes=10, comments=2, shares=1,
        ),
        PerformanceSnapshot(
            content_id=cid, captured_at=_iso(t2),
            views=210, likes=11, comments=2, shares=1,
        ),
    ]
    return {
        "content": _tag(content.to_dict()),
        "snapshots": [_tag(s.to_dict()) for s in snapshots],
    }


# ============================================================================
# Article C — early spike (1m, 5m, 30m)
# ============================================================================

def make_synthetic_article_c() -> dict:
    """Article C: very fast early spike, strong first hour."""
    base = _now_utc() - timedelta(minutes=30)
    t1 = base + timedelta(minutes=1)
    t5 = base + timedelta(minutes=5)
    t30 = base + timedelta(minutes=30)

    cid = content_id_for(
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar (synthetic)",
        url="https://example.com/synthetic/article-c",
        title="Synthetic Article C (test fixture)",
    )
    content = ContentIdentity(
        content_id=cid,
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar (synthetic)",
        url="https://example.com/synthetic/article-c",
        title="Synthetic Article C (test fixture)",
        category="VIRAL",
        topic_type="NEWS",
        language="en",
        published_at=_iso(base),
    )
    snapshots = [
        PerformanceSnapshot(
            content_id=cid, captured_at=_iso(t1),
            views=50, likes=2, comments=0, shares=0,
        ),
        PerformanceSnapshot(
            content_id=cid, captured_at=_iso(t5),
            views=500, likes=20, comments=3, shares=2,
        ),
        PerformanceSnapshot(
            content_id=cid, captured_at=_iso(t30),
            views=5000, likes=200, comments=30, shares=40,
        ),
    ]
    return {
        "content": _tag(content.to_dict()),
        "snapshots": [_tag(s.to_dict()) for s in snapshots],
    }


# ============================================================================
# Article D — missing metrics (null vs zero)
# ============================================================================

def make_synthetic_article_d_missing_metrics() -> dict:
    """Article D: views and shares known, likes and reposts None.

    Tests the null-vs-zero distinction in the engagement helpers.
    """
    base = _now_utc() - timedelta(hours=1)
    t1 = base + timedelta(minutes=15)
    t2 = base + timedelta(hours=1)

    cid = content_id_for(
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar (synthetic)",
        url="https://example.com/synthetic/article-d",
        title="Synthetic Article D (test fixture)",
    )
    content = ContentIdentity(
        content_id=cid,
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar (synthetic)",
        url="https://example.com/synthetic/article-d",
        title="Synthetic Article D (test fixture)",
        category="FOOD",
        topic_type="LIFESTYLE",
        language="en",
        published_at=_iso(base),
    )
    snapshots = [
        PerformanceSnapshot(
            content_id=cid, captured_at=_iso(t1),
            views=100, likes=None, comments=None, shares=5,
        ),
        PerformanceSnapshot(
            content_id=cid, captured_at=_iso(t2),
            views=500, likes=None, comments=None, shares=15,
        ),
    ]
    return {
        "content": _tag(content.to_dict()),
        "snapshots": [_tag(s.to_dict()) for s in snapshots],
    }


# ============================================================================
# Article E — OWN vs MARKET separation
# ============================================================================

def make_synthetic_own_content() -> dict:
    base = _now_utc() - timedelta(minutes=20)
    cid = content_id_for(
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar (synthetic)",
        url="https://example.com/synthetic/own",
        title="Synthetic OWN Content (test fixture)",
    )
    content = ContentIdentity(
        content_id=cid,
        source_type=SourceType.OWN,
        platform=Platform.WEBSITE,
        publisher="MY Hot Radar (synthetic)",
        url="https://example.com/synthetic/own",
        title="Synthetic OWN Content (test fixture)",
        category="MALAYSIA",
        topic_type="NEWS",
        language="en",
        published_at=_iso(base),
    )
    snap = PerformanceSnapshot(
        content_id=cid, captured_at=_iso(base + timedelta(minutes=15)),
        views=1000, likes=30, comments=4, shares=2,
    )
    return {
        "content": _tag(content.to_dict()),
        "snapshots": [_tag(snap.to_dict())],
    }


def make_synthetic_market_content() -> dict:
    base = _now_utc() - timedelta(minutes=20)
    cid = content_id_for(
        source_type=SourceType.MARKET,
        platform=Platform.FACEBOOK,
        publisher="A hypothetical market publisher (synthetic)",
        url="https://example.com/synthetic/market",
        title="Synthetic MARKET Content (test fixture)",
    )
    content = ContentIdentity(
        content_id=cid,
        source_type=SourceType.MARKET,
        platform=Platform.FACEBOOK,
        publisher="A hypothetical market publisher (synthetic)",
        url="https://example.com/synthetic/market",
        title="Synthetic MARKET Content (test fixture)",
        category="MALAYSIA",
        topic_type="NEWS",
        language="en",
        published_at=_iso(base),
    )
    snap = PerformanceSnapshot(
        content_id=cid, captured_at=_iso(base + timedelta(minutes=15)),
        views=2000, likes=80, comments=10, shares=20,
    )
    return {
        "content": _tag(content.to_dict()),
        "snapshots": [_tag(snap.to_dict())],
    }


def all_synthetic_fixtures() -> List[dict]:
    """Return every synthetic fixture dict. Test-only helper."""
    return [
        make_synthetic_article_a(),
        make_synthetic_article_b(),
        make_synthetic_article_c(),
        make_synthetic_article_d_missing_metrics(),
        make_synthetic_own_content(),
        make_synthetic_market_content(),
    ]
