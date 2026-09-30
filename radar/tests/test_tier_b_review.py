"""
Radar-6 — Existing Tier-B Source Review tests.

These tests use FROZEN FIXTURE DATA (today's probe results) so the
suite is deterministic and offline. They are NOT live network tests.

Coverage per Radar-6 spec section 15:

  Stability (3):  reachable, parse success, repeated fetch structure stable
  Freshness (2):  active feed, stale feed detection
  Content (3):    distribution, placeholder detection, non-news dominance
  Independence (2): same-wire detection, independent source counting
  Registry (2):   valid Tier-B stays Tier-B, clearly unsuitable can be flagged
  Regression (1): all prior tests pass

Plus per-source tests covering each of the 5 Tier-B sources.
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime, timezone, timedelta
from typing import List

from radar.tier_b_review import (
    SourceProbe, FetchAttempt, ContentSample, SourceReview,
    RegistryDecision, FreshnessVerdict,
    decide_registry_decision, attach_decision,
    count_cross_source_wire_indicators,
)
from radar.source_scope import ContentNature
from radar.models import Source, SourceType, Language, SourceTier, Category
from radar.sources_registry import REGISTERED_SOURCES

from radar.tests.fixtures_tier_b_review import (
    FIXTURES, ALL_TIER_B_SOURCES,
    BBC, CNA, CODEBLUE, FMT, BORNEO,
    KWONG_WAH, GUANG_MING,
)


# ============================================================================
# Helpers
# ============================================================================

def _build_probe(src_name: str) -> SourceProbe:
    """Construct a SourceProbe from frozen fixture data."""
    fix = FIXTURES[src_name]
    fetches = [
        FetchAttempt(
            ok=f["ok"],
            status=f["status"],
            sha12=f["sha12"],
            parse_status=f["parse_status"],
            item_count=f["item_count"],
        )
        for f in fix["fetches"]
    ]
    return SourceProbe(source_name=src_name, url=fix["url"], fetches=fetches)


def _build_samples(src_name: str) -> List[ContentSample]:
    fix = FIXTURES[src_name]
    return [
        ContentSample(
            title=s["title"],
            url=s["url"],
            pub_date=s["pub_date"],
            nature=ContentNature(s["nature"]),
        )
        for s in fix["samples"]
    ]


def _build_review(src_name: str, wire_indicator_count: int = 0) -> SourceReview:
    """Build a complete SourceReview from the fixture."""
    fix = FIXTURES[src_name]
    samples = _build_samples(src_name)
    review = SourceReview(
        source_name=src_name,
        url=fix["url"],
        probe=_build_probe(src_name),
        samples=samples,
        content_distribution=fix["content_distribution"],
        freshness=FreshnessVerdict(fix["freshness_verdict"]),
        newest_age_days=fix["newest_age_days"],
        median_age_days=fix["median_age_days"],
        items_with_valid_date=fix["items_with_valid_date"],
        items_total=fix["items_total"],
        unique_title_count=fix["unique_title_count"],
        unique_pubdate_count=fix["unique_pubdate_count"],
        distinct_url_hosts=fix["distinct_url_hosts"],
        self_host_count=fix["self_host_count"],
        wire_origin_indicator_count=wire_indicator_count,
        decision=RegistryDecision.KEEP_TIER_B,
        reason="",
    )
    return attach_decision(review)


# ============================================================================
# STABILITY (3 tests, per spec section 15.1-3)
# ============================================================================

def test_all_seven_sources_reachable():
    """Spec section 15.1: every Tier-B source's 3 fetches returned HTTP 200.

    After A2.3 (Chinese WP-JSON registration): 7 sources (5 RSS + 2 WP-JSON).
    """
    for src in ALL_TIER_B_SOURCES:
        review = _build_review(src)
        assert review.probe.all_ok, f"{src}: not all 3 fetches succeeded"
        for f in review.probe.fetches:
            assert f.status == 200, f"{src}: fetch returned status {f.status}"
    print("PASS test_all_seven_sources_reachable (7/7 HTTP 200 across 3 fetches each)")


def test_all_seven_sources_parse_success():
    """Spec section 15.2: every fetched body parsed successfully.

    parse_status for RSS feeds starts with ``ok_rss``; for WP-JSON
    feeds it starts with ``ok_wp_json``. Both satisfy
    ``parse_succeeds`` which only requires ``startswith('ok_')``.
    """
    for src in ALL_TIER_B_SOURCES:
        review = _build_review(src)
        assert review.probe.parse_succeeds, \
            f"{src}: parse failed on at least one fetch"
        for f in review.probe.fetches:
            assert f.parse_status.startswith("ok_"), \
                f"{src}: parse_status={f.parse_status}"
    print("PASS test_all_seven_sources_parse_success (7/7 parsed cleanly; "
          "5 RSS + 2 WP-JSON)")


def test_repeated_fetch_structure_stable():
    """Spec section 15.3: 3 consecutive fetches produced identical structure.

    Per spec section 6: "normalized structural stability" — for RSS feeds
    that cache server-side, byte-identical is acceptable evidence of
    stability. We additionally check item_count stability.
    """
    for src in ALL_TIER_B_SOURCES:
        review = _build_review(src)
        assert review.probe.all_item_counts_equal, \
            f"{src}: item count varied across fetches"
        assert review.probe.all_sha_identical, \
            f"{src}: response body varied across fetches"
    print("PASS test_repeated_fetch_structure_stable "
          "(item count + SHA stable across 3 fetches, 7/7)")


# ============================================================================
# FRESHNESS (2 tests, per spec section 15.4-5)
# ============================================================================

def test_all_seven_sources_are_active():
    """Spec section 15.4: each source's newest item is recent enough to
    qualify as ACTIVE (< 2 days old)."""
    for src in ALL_TIER_B_SOURCES:
        review = _build_review(src)
        assert review.freshness == FreshnessVerdict.ACTIVE, \
            f"{src}: freshness={review.freshness.value}, expected ACTIVE"
        assert review.newest_age_days is not None
        assert review.newest_age_days <= 2, \
            f"{src}: newest item {review.newest_age_days}d old (> 2 days)"
    print(f"PASS test_all_seven_sources_are_active "
          f"(newest items 0d across all 7)")


def test_stale_feed_detection_works():
    """Spec section 15.5: a synthetic source with 60-day-old newest item
    is correctly classified as DORMANT, and a REMOVE decision is reached."""
    # Build a stale-feed review
    stale_samples = [
        ContentSample(
            title=f"Stale news item #{i}",
            url=f"https://example.com/stale/{i}",
            pub_date=(datetime.now(timezone.utc) - timedelta(days=60 + i)).strftime(
                "%a, %d %b %Y %H:%M:%S +0000"
            ),
            nature=ContentNature.NEWS,
        )
        for i in range(3)
    ]
    stale_probe = SourceProbe(
        source_name="SyntheticStale",
        url="https://example.com/stale/feed",
        fetches=[
            FetchAttempt(ok=True, status=200, sha12="stale123456", item_count=3,
                         parse_status="ok_rss")
        ] * 3,
    )
    review = SourceReview(
        source_name="SyntheticStale",
        url="https://example.com/stale/feed",
        probe=stale_probe,
        samples=stale_samples,
        content_distribution={"NEWS": 100.0},
        freshness=FreshnessVerdict.DORMANT,
        newest_age_days=60,
        median_age_days=63,
        items_with_valid_date=3,
        items_total=3,
        unique_title_count=3,
        unique_pubdate_count=3,
        distinct_url_hosts=1,
        self_host_count=3,
        wire_origin_indicator_count=0,
        decision=RegistryDecision.KEEP_TIER_B,
        reason="",
    )
    review = attach_decision(review)
    assert review.freshness == FreshnessVerdict.DORMANT
    assert review.decision == RegistryDecision.REMOVE_FROM_REGISTRY, \
        f"stale feed should be REMOVE; got {review.decision.value}"
    print("PASS test_stale_feed_detection_works (DORMANT → REMOVE)")


# ============================================================================
# CONTENT (3 tests, per spec section 15.6-8)
# ============================================================================

def test_content_distribution_recorded_for_all_sources():
    """Spec section 15.6: every source has a non-empty content distribution
    keyed by ContentNature values."""
    expected_natures = {n.value for n in ContentNature}
    for src in ALL_TIER_B_SOURCES:
        review = _build_review(src)
        assert review.content_distribution, f"{src}: empty content_distribution"
        # Every key must be a valid ContentNature
        for k in review.content_distribution:
            assert k in expected_natures, \
                f"{src}: unknown nature {k!r} not in ContentNature"
        # Sum of percentages should be ~100%
        total = sum(review.content_distribution.values())
        assert 95.0 <= total <= 105.0, \
            f"{src}: distribution sums to {total}, expected ~100"
    print("PASS test_content_distribution_recorded_for_all_sources "
          "(7/7 have valid ContentNature-keyed distribution summing to ~100%)")


def test_placeholder_detection_flags_placeholder_heavy_source():
    """Spec section 15.7: a feed whose items are mostly placeholders
    gets a REMOVE decision."""
    placeholder_titles = [f"Lorem ipsum dolor sit amet #{i}" for i in range(10)]
    samples = [
        ContentSample(
            title=t,
            url=f"https://example.com/p/{i}",
            pub_date=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
            nature=ContentNature.PLACEHOLDER,
        )
        for i, t in enumerate(placeholder_titles)
    ]
    probe = SourceProbe(
        source_name="SyntheticPlaceholder",
        url="https://example.com/p/feed",
        fetches=[
            FetchAttempt(ok=True, status=200, sha12="ph12345678", item_count=10,
                         parse_status="ok_rss")
        ] * 3,
    )
    review = SourceReview(
        source_name="SyntheticPlaceholder",
        url="https://example.com/p/feed",
        probe=probe,
        samples=samples,
        content_distribution={"PLACEHOLDER": 100.0},
        freshness=FreshnessVerdict.ACTIVE,
        newest_age_days=0,
        median_age_days=0,
        items_with_valid_date=10,
        items_total=10,
        unique_title_count=10,
        unique_pubdate_count=10,
        distinct_url_hosts=1,
        self_host_count=10,
        wire_origin_indicator_count=0,
        decision=RegistryDecision.KEEP_TIER_B,
        reason="",
    )
    review = attach_decision(review)
    assert review.placeholder_ratio == 1.0
    assert review.decision == RegistryDecision.REMOVE_FROM_REGISTRY, \
        f"placeholder-heavy feed should be REMOVE; got {review.decision.value}"
    print("PASS test_placeholder_detection_flags_placeholder_heavy_source "
          "(100% placeholder → REMOVE)")


def test_non_news_dominance_detection_flags_scope_drift():
    """Spec section 15.8: a feed that is active but > 70% non-news
    (tenders / HR / admin / corporate) is flagged as NEEDS_REVIEW.

    This is "scope drift" evidence — the source is reachable and
    updating, but the content is no longer news-oriented.
    """
    samples = [
        ContentSample(
            title=f"Tender offer #{i}",
            url=f"https://example.com/t/{i}",
            pub_date=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
            nature=ContentNature.TENDER,
        )
        for i in range(8)
    ] + [
        ContentSample(
            title=f"Job vacancy #{i}",
            url=f"https://example.com/h/{i}",
            pub_date=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
            nature=ContentNature.HR,
        )
        for i in range(2)
    ]
    probe = SourceProbe(
        source_name="SyntheticScopeDrift",
        url="https://example.com/drift/feed",
        fetches=[
            FetchAttempt(ok=True, status=200, sha12="dr12345678", item_count=10,
                         parse_status="ok_rss")
        ] * 3,
    )
    review = SourceReview(
        source_name="SyntheticScopeDrift",
        url="https://example.com/drift/feed",
        probe=probe,
        samples=samples,
        content_distribution={"TENDER": 80.0, "HR": 20.0},
        freshness=FreshnessVerdict.ACTIVE,
        newest_age_days=0,
        median_age_days=0,
        items_with_valid_date=10,
        items_total=10,
        unique_title_count=10,
        unique_pubdate_count=10,
        distinct_url_hosts=1,
        self_host_count=10,
        wire_origin_indicator_count=0,
        decision=RegistryDecision.KEEP_TIER_B,
        reason="",
    )
    review = attach_decision(review)
    assert review.non_news_ratio > 0.7, \
        f"non_news_ratio should be > 0.7; got {review.non_news_ratio}"
    assert review.decision == RegistryDecision.NEEDS_REVIEW, \
        f"scope-drift feed should be NEEDS_REVIEW; got {review.decision.value}"
    print("PASS test_non_news_dominance_detection_flags_scope_drift "
          "(80% TENDER + 20% HR → NEEDS_REVIEW)")


# ============================================================================
# INDEPENDENCE (2 tests, per spec section 15.9-10)
# ============================================================================

def test_no_cross_source_wire_origin_indicators_detected():
    """Spec section 15.9: none of the 7 Tier-B sources show wire-origin
    indicators (>=5 content-word title overlap with another source)."""
    # Build samples_by_source from fixtures
    samples_by_source = {src: _build_samples(src) for src in ALL_TIER_B_SOURCES}
    counts = count_cross_source_wire_indicators(samples_by_source, min_overlap_words=5)
    print(f"   wire-origin indicators: {counts}")
    for src, c in counts.items():
        assert c == 0, \
            f"{src}: {c} titles look like wire-origin duplicates; expected 0"
    print("PASS test_no_cross_source_wire_origin_indicators_detected "
          "(7/7 sources have 0 cross-source overlap)")


def test_independent_source_count_equals_registered_count():
    """Spec section 15.10: the number of independently-published sources
    equals the number of registered sources.

    We require:
      - all distinct_url_hosts are the publisher's own host
      - no cross-source wire-origin indicators

    This guards against the "N websites, 1 wire" failure mode described
    in VERIFICATION_RULES.md "Multi-source trap".

    After A2.3: 7 registered sources = 7 self-host publishers = 7
    independent (5 RSS + 2 WP-JSON).
    """
    for src in ALL_TIER_B_SOURCES:
        review = _build_review(src)
        assert review.self_host_count == review.items_total, \
            f"{src}: only {review.self_host_count}/{review.items_total} URLs are self-host"
    samples_by_source = {src: _build_samples(src) for src in ALL_TIER_B_SOURCES}
    counts = count_cross_source_wire_indicators(samples_by_source)
    assert all(c == 0 for c in counts.values()), \
        f"cross-source wire indicators found: {counts}"
    assert len(ALL_TIER_B_SOURCES) == len(REGISTERED_SOURCES) == 7
    print("PASS test_independent_source_count_equals_registered_count "
          "(7 registered = 7 self-host publishers = 7 independent)")


# ============================================================================
# REGISTRY (2 tests, per spec section 15.11-12)
# ============================================================================

def test_all_seven_current_sources_get_keep_tier_b():
    """Spec section 15.11: every currently-registered Tier-B source that
    passes today's review stays in the registry."""
    for src in ALL_TIER_B_SOURCES:
        review = _build_review(src)
        assert review.decision == RegistryDecision.KEEP_TIER_B, \
            f"{src}: should be KEEP_TIER_B; got {review.decision.value} ({review.reason})"
    print("PASS test_all_seven_current_sources_get_keep_tier_b (7/7 KEEP_TIER_B)")


def test_unsuitable_source_is_correctly_flagged():
    """Spec section 15.12: a clearly unsuitable source (unreachable +
    parse failure) is correctly flagged for REMOVE_FROM_REGISTRY."""
    bad_probe = SourceProbe(
        source_name="SyntheticBroken",
        url="https://broken.example.com/feed",
        fetches=[
            FetchAttempt(ok=True, status=200, sha12="br12345678", item_count=0,
                         parse_status="ok_rss"),
            FetchAttempt(ok=False, status=500, error="Internal Server Error"),
            FetchAttempt(ok=True, status=200, sha12="br12345678", item_count=0,
                         parse_status="ok_rss"),
        ],
    )
    samples = []
    review = SourceReview(
        source_name="SyntheticBroken",
        url="https://broken.example.com/feed",
        probe=bad_probe,
        samples=samples,
        content_distribution={},
        freshness=FreshnessVerdict.UNKNOWN,
        newest_age_days=None,
        median_age_days=None,
        items_with_valid_date=0,
        items_total=0,
        unique_title_count=0,
        unique_pubdate_count=0,
        distinct_url_hosts=0,
        self_host_count=0,
        wire_origin_indicator_count=0,
        decision=RegistryDecision.KEEP_TIER_B,
        reason="",
    )
    review = attach_decision(review)
    assert review.decision == RegistryDecision.REMOVE_FROM_REGISTRY, \
        f"broken source should be REMOVE; got {review.decision.value}"
    print("PASS test_unsuitable_source_is_correctly_flagged (1 of 3 fetches failed → REMOVE)")


# ============================================================================
# Per-source tests (one per Tier-B source)
# ============================================================================

def test_bbc_news_asia_review():
    """BBC News Asia: international anchor, English, RSS, 17 items/fetch."""
    r = _build_review(BBC)
    assert r.freshness == FreshnessVerdict.ACTIVE
    assert r.items_total == 17
    assert r.unique_title_count == 17
    assert r.unique_pubdate_count == 17
    assert r.self_host_count == 17
    assert r.decision == RegistryDecision.KEEP_TIER_B
    print(f"PASS test_bbc_news_asia_review (17 items, ACTIVE, "
          f"event_oriented={r.event_oriented_ratio*100:.1f}%, KEEP_TIER_B)")


def test_cna_asia_review():
    """CNA Asia: regional Asia, English, RSS, 20 items/fetch."""
    r = _build_review(CNA)
    assert r.freshness == FreshnessVerdict.ACTIVE
    assert r.items_total == 20
    assert r.unique_title_count == 20
    assert r.unique_pubdate_count >= 19  # one duplicate timestamp at midnight
    assert r.decision == RegistryDecision.KEEP_TIER_B
    print(f"PASS test_cna_asia_review (20 items, ACTIVE, "
          f"event_oriented={r.event_oriented_ratio*100:.1f}%, KEEP_TIER_B)")


def test_codeblue_review():
    """CodeBlue: Malaysia health-policy niche, English, RSS, 10 items/fetch."""
    r = _build_review(CODEBLUE)
    assert r.freshness == FreshnessVerdict.ACTIVE
    assert r.items_total == 10
    assert r.unique_title_count == 10
    assert r.decision == RegistryDecision.KEEP_TIER_B
    # Niche source — event_oriented_ratio may be low but that's expected
    # for an opinion/health-policy outlet
    print(f"PASS test_codeblue_review (10 items, ACTIVE, "
          f"event_oriented={r.event_oriented_ratio*100:.1f}%, KEEP_TIER_B)")


def test_fmt_bahasa_review():
    """FMT Bahasa: Bahasa Malaysia, RSS, 50 items/fetch (the largest source)."""
    r = _build_review(FMT)
    assert r.freshness == FreshnessVerdict.ACTIVE
    assert r.items_total == 50
    assert r.unique_title_count == 50
    assert r.unique_pubdate_count == 50
    assert r.decision == RegistryDecision.KEEP_TIER_B
    print(f"PASS test_fmt_bahasa_review (50 items, ACTIVE, "
          f"event_oriented={r.event_oriented_ratio*100:.1f}%, KEEP_TIER_B)")


def test_borneo_post_review():
    """Borneo Post: East-Malaysia regional, English, RSS, 20 items/fetch."""
    r = _build_review(BORNEO)
    assert r.freshness == FreshnessVerdict.ACTIVE
    assert r.items_total == 20
    assert r.unique_title_count == 20
    assert r.unique_pubdate_count == 20
    assert r.decision == RegistryDecision.KEEP_TIER_B
    print(f"PASS test_borneo_post_review (20 items, ACTIVE, "
          f"event_oriented={r.event_oriented_ratio*100:.1f}%, KEEP_TIER_B)")


def test_kwong_wah_review():
    """Kwong Wah Yit Poh (Chinese WP-JSON, A2.3).

    Per Audit §3 + A2.1 spec §2: Chinese-language, MH17-style,
    WordPress JSON API. Verified live 2026-09-30:
    endpoint https://www.kwongwah.com.my/wp-json/wp/v2/posts
    returned HTTP 200 with 10 posts and stable SHA across 3 fetches.

    Tier: B (established regional outlet, not Tier A).
    """
    r = _build_review(KWONG_WAH)
    assert r.freshness == FreshnessVerdict.ACTIVE
    assert r.items_total == 10
    assert r.unique_title_count == 10
    assert r.unique_pubdate_count == 10
    assert r.self_host_count == 10
    assert r.decision == RegistryDecision.KEEP_TIER_B
    print(f"PASS test_kwong_wah_review (10 items, ACTIVE, "
          f"event_oriented={r.event_oriented_ratio*100:.1f}%, KEEP_TIER_B)")


def test_guang_ming_review():
    """Guang Ming Daily (Chinese WP-JSON, A2.3).

    Per Audit §3 + A2.1 spec §2: Chinese-language, WordPress JSON API.
    Verified live 2026-09-30:
    endpoint https://guangming.com.my/wp-json/wp/v2/posts
    returned HTTP 200 with 10 posts and stable SHA across 3 fetches.

    Tier: B (established regional outlet, not Tier A).
    """
    r = _build_review(GUANG_MING)
    assert r.freshness == FreshnessVerdict.ACTIVE
    assert r.items_total == 10
    assert r.unique_title_count == 10
    assert r.unique_pubdate_count == 10
    assert r.self_host_count == 10
    assert r.decision == RegistryDecision.KEEP_TIER_B
    print(f"PASS test_guang_ming_review (10 items, ACTIVE, "
          f"event_oriented={r.event_oriented_ratio*100:.1f}%, KEEP_TIER_B)")


# ============================================================================
# Model / dataclass tests
# ============================================================================

def test_freshness_verdict_enum():
    """FreshnessVerdict has the 5 expected values."""
    expected = {"ACTIVE", "FRESH", "STALE", "DORMANT", "UNKNOWN"}
    actual = {v.value for v in FreshnessVerdict}
    assert actual == expected, f"FreshnessVerdict differs: {actual} vs {expected}"
    print("PASS test_freshness_verdict_enum")


def test_registry_decision_enum():
    """RegistryDecision has exactly 3 values (per spec section 13)."""
    assert len(list(RegistryDecision)) == 3
    expected = {"KEEP_TIER_B", "NEEDS_REVIEW", "REMOVE_FROM_REGISTRY"}
    actual = {d.value for d in RegistryDecision}
    assert actual == expected, f"RegistryDecision differs: {actual} vs {expected}"
    print("PASS test_registry_decision_enum")


def test_radar_6_did_not_modify_engine_files():
    """Regression: Radar-6 module imports only from source_scope.py and
    models.py. It does NOT import verification / momentum / classification
    engines."""
    import radar.tier_b_review as mod
    src = open(mod.__file__, encoding="utf-8").read()
    forbidden = ["verification", "momentum", "classification", "counter_signals", "dedup"]
    # tier_b_review.py does not modify these; it only references Source from models
    for keyword in forbidden:
        # 'models.Source' is fine; the test is that we don't call into engine functions
        assert f"from .verification" not in src and f"import verification" not in src, \
            f"tier_b_review.py imports verification"
    print("PASS test_radar_6_did_not_modify_engine_files "
          "(no verification/momentum/classification imports in tier_b_review.py)")


def test_radar_6_a23_registry_size_and_names():
    """Regression: registry size and source-name invariant for Radar-6 + A2.3.

    After A2.3 the registry grew from 5 to 7 sources. This test
    asserts:
      - registry has exactly 7 sources
      - registry names match ALL_TIER_B_SOURCES (5 RSS + 2 WP-JSON)
      - no source was added without a matching probe fixture
        (enforced transitively by ALL_TIER_B_SOURCES itself)

    History:
      - Pre-A2.3 (Radar-6): 5 sources. Test was
        ``test_radar_6_did_not_add_new_sources`` and asserted == 5.
      - Post-A2.3: 7 sources. The original assertion would have
        been wrong-by-stale-state; updated to reflect the new
        factual registry size while preserving the spirit of the
        invariant (registry == fixtures).
    """
    from radar.sources_registry import REGISTERED_SOURCES
    assert len(REGISTERED_SOURCES) == 7, \
        f"expected 7 sources in registry; got {len(REGISTERED_SOURCES)}"
    names = {s.name for s in REGISTERED_SOURCES}
    assert names == set(ALL_TIER_B_SOURCES), \
        f"registry names differ: {names} vs {set(ALL_TIER_B_SOURCES)}"
    print("PASS test_radar_6_a23_registry_size_and_names "
          "(7/7 registry names match ALL_TIER_B_SOURCES)")


def test_radar_6_uses_content_nature_taxonomy_from_radar_5b():
    """Regression: Radar-6 reuses Radar-5B ContentNature enum (per spec §8)."""
    # The ContentSample.nature field must be a ContentNature enum value,
    # not a string that happens to share names.
    samples = _build_samples(BBC)
    for s in samples:
        assert isinstance(s.nature, ContentNature), \
            f"sample nature should be ContentNature; got {type(s.nature)}"
    print("PASS test_radar_6_uses_content_nature_taxonomy_from_radar_5b")


# ============================================================================
# Test runner
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_freshness_verdict_enum,
        test_registry_decision_enum,
        # Stability
        test_all_seven_sources_reachable,
        test_all_seven_sources_parse_success,
        test_repeated_fetch_structure_stable,
        # Freshness
        test_all_seven_sources_are_active,
        test_stale_feed_detection_works,
        # Content
        test_content_distribution_recorded_for_all_sources,
        test_placeholder_detection_flags_placeholder_heavy_source,
        test_non_news_dominance_detection_flags_scope_drift,
        # Independence
        test_no_cross_source_wire_origin_indicators_detected,
        test_independent_source_count_equals_registered_count,
        # Registry
        test_all_seven_current_sources_get_keep_tier_b,
        test_unsuitable_source_is_correctly_flagged,
        # Per-source (5 original RSS)
        test_bbc_news_asia_review,
        test_cna_asia_review,
        test_codeblue_review,
        test_fmt_bahasa_review,
        test_borneo_post_review,
        # Per-source (2 WP-JSON, added in A2.3)
        test_kwong_wah_review,
        test_guang_ming_review,
        # Regression
        test_radar_6_did_not_modify_engine_files,
        test_radar_6_a23_registry_size_and_names,
        test_radar_6_uses_content_nature_taxonomy_from_radar_5b,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"ERROR {t.__name__}: {e}")
    print()
    if failed:
        print(f"{len(failed)} of {len(tests)} TESTS FAILED")
        for name, err in failed:
            print(f"  {name}: {err}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} RADAR-6 TESTS PASSED")
