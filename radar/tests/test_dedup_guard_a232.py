"""
A2.3.2 — Cross-Language Entity Dedup Guard regression tests.

Reference: ``docs/CHINESE_DEDUP_GUARD_DESIGN.md`` (Investigation 1, 6, 7).

These tests verify the two new guards introduced in A2.3.2:

  Guard B — Entity-Conflict guard
    Strengthens the entity-overlap merge path. Previously, the entity
    path could trigger a merge whenever eo >= ENTITY_MIN_OVERLAP (=2)
    AND eo/smaller >= ENTITY_MIN_SHARE (=0.0, i.e. always true) AND
    _same_event_window returned True. The 0.0 share threshold made the
    share check vacuous, and _same_event_window defaulted to True when
    either published_at was missing. This combination caused the
    PH-Bersatu false merge.

  Guard C — Date-Confident Window
    Strengthens _same_event_window by:
      1. Trying to extract a date from URL path when published_at is missing
      2. Returning False (fail-closed) when only ONE side has a known date
         AND the merge trigger is the entity-overlap path
      3. Returning True (fallback) when BOTH sides have no date — i.e.
         neither side can contradict the other

  URL date extraction
    New helper ``_extract_date_from_url(url)`` extracts dates from URL
    paths matching ``/YYYYMMDD/`` or ``/YYYY/MM/DD/`` patterns with strict
    month/day validation. Invalid dates return None.

This test file does NOT modify Story.published_at and does NOT mutate
Story.url. URL-derived dates are passed as a separate signal to the dedup
match path.

Test cases required per A2.3.2 spec:

  Case 1 — PH-Bersatu (FALSE MERGE → NO MERGE)
  Case 2 — UM 200 (TRUE MERGE → MERGE)
  Case 3 — Existing entity merge preserved (entity overlap + same event date)
  Case 4 — Missing date (one side) — confirm strict behavior
  Case 5 — Both dates missing — confirm defined fallback
  Case 6 — URL date extraction (multiple patterns + invalid)
"""

from __future__ import annotations

from radar.models import Story, SourceType, Category, Language
from radar.dedup import _is_strong_match, _extract_date_from_url, cluster
from radar.normalize import normalize_title, extract_keywords
from radar.thresholds import (
    ENTITY_MIN_SHARE,
    ENTITY_MIN_OVERLAP,
    EVENT_WINDOW_DAYS,
)


# ============================================================================
# Test helpers
# ============================================================================

def _story(id_, title, *, source="TestSource", lang=Language.EN,
           url=None, published_at="2026-09-30T10:00:00+00:00",
           category=None, summary=""):
    """Build a Story for cluster() testing."""
    return Story(
        id=id_,
        title=title,
        summary=summary,
        url=url or f"https://{source}.example/{abs(hash(title + id_)) % 9999}",
        source=source,
        source_type=SourceType.NEWS_SITE,
        published_at=published_at,
        category=category or Category.MALAYSIA,
        language=lang,
        country="MY",
    )


# ============================================================================
# Case 6 — URL date extraction
# ============================================================================

def test_url_date_extract_yyyymmdd_pattern():
    """URLs containing /YYYYMMDD/ should yield ISO dates."""
    assert _extract_date_from_url("https://mysinchew.sinchew.com.my/news/20260928/mysinchew/7885171") == "2026-09-28"
    assert _extract_date_from_url("https://www.chinapress.com.my/20260930/some-article") == "2026-09-30"
    assert _extract_date_from_url("https://www.sinchew.com.my/news/20260930/entertainment/7896726") == "2026-09-30"
    assert _extract_date_from_url("https://www.kwongwah.com.my/20260930/some-article") == "2026-09-30"


def test_url_date_extract_yyyy_mm_dd_pattern():
    """URLs containing /YYYY/MM/DD/ should yield ISO dates."""
    assert _extract_date_from_url("https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/some-article") == "2026-09-30"
    assert _extract_date_from_url("https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/another") == "2026-09-28"


def test_url_date_extract_invalid_month_day_returns_none():
    """Invalid month/day in URL should NOT be interpreted as a date."""
    # Month 13 invalid
    assert _extract_date_from_url("https://example.com/news/20261301/article") is None
    # Day 32 invalid
    assert _extract_date_from_url("https://example.com/news/20260132/article") is None
    # Day 30 of February invalid
    assert _extract_date_from_url("https://example.com/news/20260230/article") is None
    # All zeros invalid
    assert _extract_date_from_url("https://example.com/news/20260000/article") is None
    # Garbage that happens to be 8 digits is OK if month/day valid; here 12345678 has month=12, day=34 → invalid
    assert _extract_date_from_url("https://example.com/news/12345678/article") is None


def test_url_date_extract_no_date_returns_none():
    """URLs without any date pattern should return None."""
    assert _extract_date_from_url("https://guangming.com.my/some-article") is None
    assert _extract_date_from_url("https://example.com/") is None
    assert _extract_date_from_url("") is None
    assert _extract_date_from_url("not-a-url") is None


def test_url_date_extract_does_not_mutate_url():
    """URL date extraction must be a pure read; the Story.url field is unchanged after dedup."""
    s = _story("u1", "test title",
               url="https://mysinchew.sinchew.com.my/news/20260928/mysinchew/7885171",
               published_at=None)
    original_url = s.url
    original_published_at = s.published_at
    extracted = _extract_date_from_url(s.url)
    assert extracted == "2026-09-28"
    assert s.url == original_url  # URL field unchanged
    assert s.published_at == original_published_at  # published_at field unchanged


def test_url_date_extract_yyyy_slash_pattern_at_path_root():
    """Edge case: date at very start of path."""
    assert _extract_date_from_url("https://example.com/2026/09/30/article") == "2026-09-30"
    # Date in deeper path
    assert _extract_date_from_url("https://example.com/news/section/2026/09/30/article") == "2026-09-30"


def test_url_date_extract_does_not_consume_8_digits_inside_longer_run():
    """8-digit runs inside larger numeric strings should not be misinterpreted."""
    # '123456789' has '12345678' as substring — should not match as date
    assert _extract_date_from_url("https://example.com/news/123456789/article") is None
    # But '20260928abc' should still match the /20260928/ pattern
    assert _extract_date_from_url("https://example.com/news/20260928abc/article") == "2026-09-28"


# ============================================================================
# Case 1 — PH-Bersatu (FALSE MERGE → NO MERGE)
# ============================================================================

def test_ph_bersatu_false_merge_blocked():
    """The PH-Bersatu false merge from Investigation 1 must NOT merge after Guard B+C.

    Pre-A2.3.2: merged via entity_overlap (ph, bersatu, eo=2) + vacuous share
                 (0.0) + permissive _same_event_window (default True on missing date).

    Post-A2.3.2:
      - FMT date = 2026-09-30 (known)
      - SCM URL date = 2026-09-28 (extractable from URL)
      - URL date != published_at-side date → 2-day gap → fail-closed
      - Entity path: eo/smaller = 2/11 = 0.18; with Guard B share check, may be
        acceptable, but the date-consistency check from Guard C catches it first.
    """
    fmt_ph_bersatu = _story(
        "fmt_ph", "Elak PH-Bersatu bertembung lebih realistik berbanding persefahaman rasmi, kata penganalisis",
        source="Free Malaysia Today (Bahasa)", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/elak-ph-bersatu-bertembung-lebih-realistik-berbanding-persefahaman-rasmi-kata-penganalisis",
        published_at="Wed, 30 Sep 2026 00:00:00 +0000",
    )
    scm_melaka = _story(
        "scm_melaka", "In Melaka and GE16, PH + Bersatu + Bersama+MUDA must team up to beat BN + PN",
        source="Sin Chew Main", lang=Language.ZH,
        url="https://mysinchew.sinchew.com.my/news/20260928/mysinchew/7885171",
        published_at=None,
    )
    # Run dedup
    topics, _ = cluster([fmt_ph_bersatu, scm_melaka])
    # Must be 2 separate topics
    assert len(topics) == 2, f"Expected 2 separate topics for PH-Bersatu, got {len(topics)}"
    # Sanity: pair-level check must also reject
    assert not _is_strong_match(fmt_ph_bersatu, scm_melaka), "PH-Bersatu must NOT match"


# ============================================================================
# Case 2 — UM 200 (TRUE MERGE → MERGE)
# ============================================================================

def test_um_200_true_merge_preserved():
    """UM 200 TRUE merge from Investigation 2 must still merge after Guard B+C.

    Pre-A2.3.2: merged via keyword_overlap = 1.0 (single shared digit `200`).

    Post-A2.3.2:
      - Both published_at known (same day)
      - Same URL date (both 2026-09-30)
      - The keyword-overlap path is NOT tightened by Guard B (only entity path)
      - Guard C only affects pairs where the date consistency fails
      - UM 200 has consistent dates → passes date check
      - KW=1.0 ≥ KEYWORD_OVERLAP_THRESHOLD(0.50) → merges
    """
    fmt_um = _story(
        "fmt_um", "UM universiti pertama Malaysia tembusi kelompok 200 terbaik dunia",
        source="Free Malaysia Today (Bahasa)", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/um-universiti-pertama-malaysia-tembusi-kelompok-200-terbaik-dunia",
        published_at="Tue, 29 Sep 2026 23:00:00 +0000",
    )
    cp_um = _story(
        "cp_um", "首相恭贺马大 跻身前200大学排名",
        source="China Press", lang=Language.ZH,
        url="https://www.chinapress.com.my/20260930/首相恭贺马大-跻身前200大学排名",
        published_at="2026-09-30T13:11:08Z",
    )
    # Run dedup
    topics, _ = cluster([fmt_um, cp_um])
    # Must be 1 topic
    assert len(topics) == 1, f"Expected 1 topic for UM 200, got {len(topics)}"
    # Sanity: pair-level check must match
    assert _is_strong_match(fmt_um, cp_um), "UM 200 must MATCH"


# ============================================================================
# Case 3 — Existing entity merge preserved (entity overlap + same event date)
# ============================================================================

def test_entity_merge_same_event_date_preserved():
    """A legitimate entity-overlap merge (eo >= 2, same date, real event) must still merge.

    This guards against Guard B over-tightening the entity path and killing
    real same-event merges.
    """
    # Two MS articles about Hasrat Umno (real cluster from Investigation 1)
    fmt1 = _story(
        "fmt1", "Hasrat Umno kekal kuasa utama boleh jejas kestabilan, kata penganalisis",
        source="Free Malaysia Today (Bahasa)", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/hasrat-umno-kekal-kuasa-utama-boleh-jejas-kestabilan-kata-penganalisis",
        published_at="Wed, 30 Sep 2026 00:30:00 +0000",
    )
    fmt2 = _story(
        "fmt2", "Elak PH-Bersatu bertembung lebih realistik berbanding persefahaman rasmi, kata penganalisis",
        source="Free Malaysia Today (Bahasa)", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/elak-ph-bersatu-bertembung-lebih-realistik-berbanding-persefahaman-rasmi-kata-penganalisis",
        published_at="Wed, 30 Sep 2026 00:00:00 +0000",
    )
    # Same date, same source, entity overlap (penganalisis)
    assert _is_strong_match(fmt1, fmt2), "Same-day same-source entity overlap must MERGE"
    topics, _ = cluster([fmt1, fmt2])
    assert len(topics) == 1, f"Expected 1 topic, got {len(topics)}"


def test_entity_merge_different_sources_same_event_preserved():
    """A cross-source entity merge with consistent date must still merge.

    Example: BBC + CodeBlue about the same event on the same day, sharing
    2+ entities.
    """
    bbc = _story(
        "bbc1", "Anwar meets Xi Jinping in Beijing for trade talks",
        source="BBC News Asia", lang=Language.EN,
        url="https://www.bbc.com/news/world-asia-1",
        published_at="2026-09-30T08:00:00+00:00",
    )
    cna = _story(
        "cna1", "Anwar Xi meeting highlights Belt and Road concerns",
        source="Channel News Asia", lang=Language.EN,
        url="https://www.channelnewsasia.com/news/anwar-xi",
        published_at="2026-09-30T09:00:00+00:00",
    )
    # Both about Anwar + Xi; same date; entities should overlap
    assert _is_strong_match(bbc, cna), "Cross-source same-event entity merge must MERGE"


# ============================================================================
# Case 4 — Missing date (one side) — strict behavior
# ============================================================================

def test_one_side_missing_date_entity_overlap_strict():
    """When only ONE side has a date AND the merge is via entity-overlap path
    AND the dates differ > EVENT_WINDOW_DAYS, must NOT merge.

    This is the structural equivalent of PH-Bersatu (without URL date).
    """
    a = _story(
        "a", "PH and Bersatu coalition analysis by Wong Chin Huat",
        source="FMT", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/1",
        published_at="2026-09-30T00:00:00+00:00",
    )
    b = _story(
        "b", "PH plus Bersatu plus MUDA team up analysis in Melaka GE16",
        source="Sin Chew", lang=Language.EN,
        url="https://www.sinchew.com.my/2",
        published_at=None,  # missing date, no date in URL
    )
    # No URL date for b, no published_at for b
    # FMT side has date 2026-09-30
    # Strict mode (Guard C) should reject entity-only merge with one-sided date
    assert not _is_strong_match(a, b), \
        "Entity-only merge with one-sided date must NOT match (strict mode)"


def test_one_side_date_other_side_url_date_within_window():
    """When one side has published_at and other has URL date within EVENT_WINDOW_DAYS,
    date check passes — pair can merge via entity path if share threshold passes."""
    a = _story(
        "a", "Anwar attends ASEAN summit Kuala Lumpur Monday",
        source="FMT", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/asean1",
        published_at="2026-09-30T10:00:00+00:00",
    )
    b = _story(
        "b", "Anwar chairs ASEAN summit in Kuala Lumpur",
        source="CNA", lang=Language.EN,
        url="https://www.channelnewsasia.com/news/asean-summit-20260930",
        published_at=None,
        # URL has /20260930/ — extractable
    )
    # Both dates extractable and within window
    # Entities overlap (anwar, asean, summit, kuala, lumpur)
    # → should match via entity path
    assert _is_strong_match(a, b), "Same-day entity overlap (with URL date fallback) must MATCH"


# ============================================================================
# Case 5 — Both dates missing
# ============================================================================

def test_both_dates_missing_fallback_to_permissive():
    """When BOTH sides lack dates (no published_at, no URL date), the merge is
    indeterminate; current dedup fallback allows it. This test pins that
    behavior.

    Behavior: BOTH sides missing date → _same_event_window returns True (fallback).
    This is intentionally permissive to avoid breaking historical merges when
    adapter data quality is poor. The Guard C strictness applies only when
    AT LEAST ONE side has a date that disagrees with the other.
    """
    a = _story(
        "a", "Malaysia election analysis political commentary today",
        source="TestA", lang=Language.EN,
        url="https://test-a.example/no-date-here",
        published_at=None,
    )
    b = _story(
        "b", "Election analysis Malaysia political commentary today",
        source="TestB", lang=Language.EN,
        url="https://test-b.example/no-date-either",
        published_at=None,
    )
    # Both share multiple entities + high keyword overlap → match via kw path
    # (kw path is independent of date)
    assert _is_strong_match(a, b), \
        "Both-sides-missing-date kw-overlap merge must still MATCH (fallback)"


def test_both_dates_missing_but_no_entity_overlap_no_merge():
    """When BOTH sides lack dates AND entity overlap is weak, must NOT merge."""
    a = _story(
        "a", "Malaysia elections different topic",
        source="TestA", lang=Language.EN,
        url="https://test-a.example/no-date",
        published_at=None,
    )
    b = _story(
        "b", "Singapore weather forecast today",
        source="TestB", lang=Language.EN,
        url="https://test-b.example/no-date",
        published_at=None,
    )
    # Different topics, no overlap
    assert not _is_strong_match(a, b), \
        "Both-sides-missing-date unrelated stories must NOT match"


# ============================================================================
# Case 7 — Guard B share threshold change is conservative
# ============================================================================

def test_entity_share_threshold_is_above_zero():
    """ENTITY_MIN_SHARE must be > 0 after Guard B (no longer vacuous).

    This pins the threshold as a guard contract.
    """
    assert ENTITY_MIN_SHARE > 0.0, \
        f"ENTITY_MIN_SHARE must be > 0 to fix PH-Bersatu; got {ENTITY_MIN_SHARE}"


def test_entity_overlap_min_unchanged():
    """ENTITY_MIN_OVERLAP must remain 2 (don't break existing entity merges).

    Guard B does not raise this threshold; it only adds the share constraint.
    """
    assert ENTITY_MIN_OVERLAP == 2, \
        f"ENTITY_MIN_OVERLAP must remain 2; got {ENTITY_MIN_OVERLAP}"


# ============================================================================
# Case 8 — Date window
# ============================================================================

def test_event_window_unchanged():
    """EVENT_WINDOW_DAYS is preserved."""
    assert EVENT_WINDOW_DAYS == 7, f"EVENT_WINDOW_DAYS should remain 7; got {EVENT_WINDOW_DAYS}"


# ============================================================================
# Case 9 — Integration: FMT#1 + FMT#2 + SCM (the actual PH-Bersatu topic)
# ============================================================================

def test_ph_bersatu_full_topic_does_not_cluster():
    """The full PH-Bersatu topic (FMT#1, FMT#2, SCM) must cluster into 2 topics
    (FMT#1+FMT#2 + SCM alone), not all 3 in one cluster."""
    fmt1 = _story(
        "fmt1", "Hasrat Umno kekal kuasa utama boleh jejas kestabilan, kata penganalisis",
        source="Free Malaysia Today (Bahasa)", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/hasrat-umno-kekal-kuasa-utama-boleh-jejas-kestabilan-kata-penganalisis",
        published_at="Wed, 30 Sep 2026 00:30:00 +0000",
    )
    fmt2 = _story(
        "fmt2", "Elak PH-Bersatu bertembung lebih realistik berbanding persefahaman rasmi, kata penganalisis",
        source="Free Malaysia Today (Bahasa)", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/elak-ph-bersatu-bertembung-lebih-realistik-berbanding-persefahaman-rasmi-kata-penganalisis",
        published_at="Wed, 30 Sep 2026 00:00:00 +0000",
    )
    scm = _story(
        "scm", "In Melaka and GE16, PH + Bersatu + Bersama+MUDA must team up to beat BN + PN",
        source="Sin Chew Main", lang=Language.ZH,
        url="https://mysinchew.sinchew.com.my/news/20260928/mysinchew/7885171",
        published_at=None,
    )
    topics, _ = cluster([fmt1, fmt2, scm])
    # Expected: 2 topics
    # FMT#1 + FMT#2 = 1 cluster (same date, same source, entity overlap)
    # SCM = 1 cluster (URL date 2026-09-28, 2 days before FMT)
    assert len(topics) == 2, f"Expected 2 topics for PH-Bersatu triple, got {len(topics)}"
    # Verify SCM is alone (not with FMT)
    topic_story_counts = sorted([len(t.story_ids) for t in topics])
    assert topic_story_counts == [1, 2], \
        f"Expected one topic with 2 stories (FMT) and one with 1 story (SCM); got {topic_story_counts}"


# ============================================================================
# Runner
# ============================================================================

def _run_all() -> int:
    test_funcs = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    passed = 0
    failed = []
    for name, fn in test_funcs:
        try:
            fn()
            passed += 1
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append((name, str(e) if str(e) else "<empty assertion>"))
            print(f"FAIL {name}: {e if str(e) else '<empty assertion>'}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"ERROR {name}: {e}")
            import traceback
            traceback.print_exc()
    print()
    print(f"{passed} passed, {len(failed)} failed of {len(test_funcs)} tests")
    if failed:
        for n, e in failed:
            print(f"  {n}: {e}")
        return 1
    print(f"ALL {len(test_funcs)} A2.3.2 DEDUP GUARD TESTS PASSED")
    return 0


def _should_run_main():
    import os, sys
    if __name__ != "__main__":
        return False
    this_file = os.path.abspath(__file__)
    argv0 = os.path.abspath(sys.argv[0]) if sys.argv else ""
    return argv0 == this_file


if _should_run_main():
    import sys as _sys
    _sys.exit(_run_all())
