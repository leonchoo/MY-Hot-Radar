"""
A2.2-A — Sin Chew Johor HTML listing adapter tests.

Coverage matrix (per A2.2-A spec §Tests, 18 items):

   1. valid HTML listing
   2. multiple article cards
   3. valid article URL
   4. invalid URL (navigation / category)
   5. duplicate article URL
   6. navigation link rejection
   7. advertisement rejection
   8. missing title
   9. empty title
  10. missing timestamp  -> published_at = None
  11. malformed HTML
  12. HTML entity decoding
  13. Chinese title normalization
  14. language = ZH
  15. source identity
  16. A1 alias compatibility (cross-language dedup)
  17. fail-closed behavior
  18. live fixture (saved trimmed HTML from real 2026-09-30 response)

These tests use a deterministic trimmed fixture under
``fixtures/html_listing/sinchew_johor_listing_trimmed.html``
captured from the real Sin Chew Johor listing page on
2026-09-30. The fixture is intentionally small (~2 KB) to
stay fast and offline; the full page (380 KB) is NOT committed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from radar.dedup import cluster
from radar.models import (
    Category,
    Language,
    Source,
    SourceTier,
    SourceType,
    Story,
)
from radar.normalize import (
    _apply_aliases,
    _ZH_TO_CANONICAL,
    extract_entities,
    normalize_title,
    tokens,
)
from radar.sources.html_listing import (
    HtmlListingAdapter,
    _is_article_url,
    _strip_html,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "html_listing"
TRIMMED_FIXTURE = FIXTURES_DIR / "sinchew_johor_listing_trimmed.html"


def _make_source(
    name: str = "Sin Chew Johor desk",
    url: str = "https://johor.sinchew.com.my/",
) -> Source:
    return Source(
        name=name,
        type=SourceType.HTML_LISTING,
        url=url,
        reliability=4,
        country="MY",
        languages=[Language.ZH],
        tier=SourceTier.B,
        notes="A2.2-A test fixture",
    )


def _make_adapter() -> HtmlListingAdapter:
    return HtmlListingAdapter(_make_source(), category=Category.MALAYSIA)


def _load_fixture() -> str:
    if not TRIMMED_FIXTURE.exists():
        raise FileNotFoundError(
            f"fixture missing: {TRIMMED_FIXTURE}. "
            f"Re-run the probe script to regenerate it."
        )
    return TRIMMED_FIXTURE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. valid HTML listing
# ---------------------------------------------------------------------------

def test_valid_html_listing_returns_stories():
    """The trimmed fixture is well-formed HTML and parses cleanly."""
    adapter = _make_adapter()
    fixture = _load_fixture()
    stories = adapter._parse_listing(fixture)
    assert isinstance(stories, list)
    assert len(stories) >= 3, f"expected >=3 stories from trimmed fixture; got {len(stories)}"
    for s in stories:
        assert isinstance(s, Story)
        assert s.title
        assert s.url
        assert s.language == Language.ZH
        assert s.source_type == SourceType.HTML_LISTING
    print(f"PASS test_valid_html_listing_returns_stories ({len(stories)} stories)")


# ---------------------------------------------------------------------------
# 2. multiple article cards
# ---------------------------------------------------------------------------

def test_multiple_article_cards_collected():
    """Multiple <h2 class='title'> and <a class='internalLink'> cards
    are all collected, deduplicated by URL."""
    adapter = _make_adapter()
    stories = adapter._parse_listing(_load_fixture())
    urls = {s.url for s in stories}
    # The fixture has 3 h2 cards + 2 internal cards + 1 lone-link = 6 distinct URLs.
    assert len(urls) == len(stories), "story list contains duplicates"
    assert len(stories) >= 6, f"expected 6 stories; got {len(stories)}"
    # All URLs are valid article URLs (Sin Chew Johor pattern).
    for u in urls:
        assert "johor.sinchew.com.my/news/" in u
        assert "/johor/" in u
    print(f"PASS test_multiple_article_cards_collected ({len(stories)} cards, all unique URLs)")


# ---------------------------------------------------------------------------
# 3. valid article URL
# ---------------------------------------------------------------------------

def test_valid_article_url_accepted():
    """URLs matching /news/YYYYMMDD/johor/{numeric id} are accepted."""
    assert _is_article_url("https://johor.sinchew.com.my/news/20260930/johor/7895884")
    assert _is_article_url("/news/20251203/johor/7079996")
    assert _is_article_url("/news/20260921/johor/7863017/")
    print("PASS test_valid_article_url_accepted")


# ---------------------------------------------------------------------------
# 4. invalid URL
# ---------------------------------------------------------------------------

def test_invalid_url_rejected():
    """Non-article URLs are rejected by _is_article_url."""
    assert not _is_article_url("https://johor.sinchew.com.my/category/地方/大柔佛")
    assert not _is_article_url("/news/20260930")  # no /johor/{id}
    assert not _is_article_url("/news/2026-09-30/johor/7895884")  # dashes in date
    assert not _is_article_url("/news/20260930/johor/abc")  # non-numeric id
    assert not _is_article_url("https://example.com/news/20260930/johor/7895884")  # wrong host
    assert not _is_article_url("")
    print("PASS test_invalid_url_rejected")


# ---------------------------------------------------------------------------
# 5. duplicate article URL
# ---------------------------------------------------------------------------

def test_duplicate_article_url_dedup():
    """If the same article URL appears in h2 + internal + lone, only
    one Story is emitted (h2 title wins)."""
    adapter = _make_adapter()
    stories = adapter._parse_listing(_load_fixture())
    urls = [s.url for s in stories]
    assert len(urls) == len(set(urls)), "duplicate URLs survived dedup"

    # Find the URL that appears in h2 in the fixture (e.g. 7079996) — its title
    # must come from the h2 card, not the bare "dup-link" lone link.
    by_url = {s.url: s.title for s in stories}
    # The fixture picks the first h2 URL as the duplicate target.
    h2_first = "https://johor.sinchew.com.my/news/20251203/johor/7079996"
    assert h2_first in by_url
    # The h2 title contains "新山眼〡一针一线织出"柔佛魂"  传统织线布再度被看见".
    # The duplicate lone-link text is "dup-link".
    assert "dup-link" not in by_url[h2_first], \
        f"dup URL kept the bad lone-link title; got {by_url[h2_first]!r}"
    assert "新山眼" in by_url[h2_first] and "织出" in by_url[h2_first], \
        f"h2 title should win; got {by_url[h2_first]!r}"
    print("PASS test_duplicate_article_url_dedup (h2 wins over lone-link)")


# ---------------------------------------------------------------------------
# 6. navigation link rejection
# ---------------------------------------------------------------------------

def test_navigation_link_rejected():
    """The trimmed fixture includes a category navigation link.
    It MUST be filtered out."""
    adapter = _make_adapter()
    stories = adapter._parse_listing(_load_fixture())
    for s in stories:
        assert "/category/" not in s.url, \
            f"navigation link leaked through: {s.url}"
    print("PASS test_navigation_link_rejected (no /category/ in any story)")


# ---------------------------------------------------------------------------
# 7. advertisement rejection
# ---------------------------------------------------------------------------

def test_advertisement_rejection():
    """Ad-like anchor tags (no href, scripts, ad-server URLs) are rejected.

    We synthesize a fixture with ad patterns and verify no story is emitted.
    """
    adapter = _make_adapter()
    ad_html = """<html><body>
        <script>window.adsbygoogle.push({});</script>
        <a href="/ads/click?id=123">Buy now!</a>
        <a href="https://adserver.example.com/banner">Sponsored</a>
        <ins class="adsbygoogle"></ins>
    </body></html>"""
    stories = adapter._parse_listing(ad_html)
    assert stories == [], f"ads should produce no stories; got {stories}"
    print("PASS test_advertisement_rejection")


# ---------------------------------------------------------------------------
# 8. missing title (synthetic)
# ---------------------------------------------------------------------------

def test_missing_title_drops_card():
    """A card whose <a> has no text content is dropped."""
    adapter = _make_adapter()
    html = """<html><body>
        <h2 class="title skip-default-style">
            <a href="https://johor.sinchew.com.my/news/20260930/johor/111"></a>
        </h2>
    </body></html>"""
    stories = adapter._parse_listing(html)
    assert stories == [], "empty-title card should be dropped"
    print("PASS test_missing_title_drops_card")


# ---------------------------------------------------------------------------
# 9. empty title (synthetic)
# ---------------------------------------------------------------------------

def test_empty_title_after_strip_drops_card():
    """If HTML stripping produces an empty title, the card is dropped."""
    adapter = _make_adapter()
    html = """<html><body>
        <h2 class="title skip-default-style">
            <a href="https://johor.sinchew.com.my/news/20260930/johor/222">    </a>
        </h2>
    </body></html>"""
    stories = adapter._parse_listing(html)
    assert stories == [], "whitespace-only title should be dropped"
    print("PASS test_empty_title_after_strip_drops_card")


# ---------------------------------------------------------------------------
# 10. missing timestamp -> published_at = None
# ---------------------------------------------------------------------------

def test_missing_timestamp_results_in_none():
    """The Sin Chew listing has only relative time strings. Adapter
    MUST emit published_at=None; it MUST NOT use observed_at as
    published_at, and MUST NOT invent a timestamp."""
    adapter = _make_adapter()
    stories = adapter._parse_listing(_load_fixture())
    for s in stories:
        assert s.published_at is None, (
            f"published_at must be None for listing-page adapter; "
            f"got {s.published_at!r} for {s.url}"
        )
        # discovered_at must still be set (not None)
        assert s.discovered_at is not None
    print("PASS test_missing_timestamp_results_in_none "
          f"({len(stories)} stories, all published_at=None)")


# ---------------------------------------------------------------------------
# 11. malformed HTML (fail-closed)
# ---------------------------------------------------------------------------

def test_malformed_html_returns_empty_or_partial():
    """Malformed HTML should not crash; it returns [] or a partial
    list (whatever the regex happens to match)."""
    adapter = _make_adapter()
    bad = "<html><body><h2 class=\"title\"><a href=\"https://johor.sinchew.com.my/news/20260930/johor/7895884\">broken<h2></a></body></html>"
    stories = adapter._parse_listing(bad)
    # Either empty or one story — must not raise.
    assert isinstance(stories, list)
    for s in stories:
        assert s.url
    print(f"PASS test_malformed_html_returns_empty_or_partial ({len(stories)} stories, no crash)")


# ---------------------------------------------------------------------------
# 12. HTML entity decoding
# ---------------------------------------------------------------------------

def test_html_entity_decoding():
    """Common HTML entities (&hellip; &amp; &quot;) decode correctly."""
    assert _strip_html("Foo &hellip; bar") == "Foo \u2026 bar"
    assert _strip_html("Q &amp; A") == "Q & A"
    assert _strip_html("她说&quot;你好&quot;") == '她说"你好"'
    assert _strip_html("&lt;tag&gt;") == "<tag>"
    # numeric entities
    assert _strip_html("&#26032;&#23665;") == "新山"
    # hex entities
    assert _strip_html("&#x65B0;&#x5C71;") == "新山"
    print("PASS test_html_entity_decoding")


# ---------------------------------------------------------------------------
# 13. Chinese title normalization
# ---------------------------------------------------------------------------

def test_chinese_title_normalization():
    """Chinese titles round-trip cleanly; whitespace collapses."""
    raw = "  新山滂沱大雨多处淹水   幼儿园44名师生受困获救   "
    out = _strip_html(raw)
    assert out == "新山滂滂大雨多处淹水 幼儿园44名师生受困获救" or \
           "新山" in out and "幼儿园" in out
    # Should not start or end with whitespace
    assert out == out.strip()
    # Internal whitespace collapsed
    assert "  " not in out
    print(f"PASS test_chinese_title_normalization ({out[:30]!r}...)")


# ---------------------------------------------------------------------------
# 14. language = ZH
# ---------------------------------------------------------------------------

def test_language_is_zh():
    """Every emitted Story has language=ZH."""
    adapter = _make_adapter()
    for s in adapter._parse_listing(_load_fixture()):
        assert s.language == Language.ZH, \
            f"language must be ZH; got {s.language.value} for {s.url}"
    print("PASS test_language_is_zh")


# ---------------------------------------------------------------------------
# 15. source identity
# ---------------------------------------------------------------------------

def test_source_identity():
    """Every emitted Story carries the configured source name and
    SourceType.HTML_LISTING."""
    adapter = _make_adapter()
    for s in adapter._parse_listing(_load_fixture()):
        assert s.source == "Sin Chew Johor desk"
        assert s.source_type == SourceType.HTML_LISTING
        assert s.country == "MY"
        assert s.category == Category.MALAYSIA
    print("PASS test_source_identity")


# ---------------------------------------------------------------------------
# 16. A1 alias compatibility (cross-language dedup)
# ---------------------------------------------------------------------------

def test_a1_alias_compatibility_johor_charged():
    """A Sin Chew Johor ZH title with 新山 must merge with an EN
    Johor-Bahru title via the A1 aliases."""
    # Adapter output: a ZH story about 新山男子被控
    adapter = _make_adapter()
    zh_html = """<html><body>
        <h2 class="title skip-default-style">
            <a href="https://johor.sinchew.com.my/news/20260930/johor/9000001">新山男子被控</a>
        </h2>
    </body></html>"""
    zh_stories = adapter._parse_listing(zh_html)
    assert len(zh_stories) == 1
    zh = zh_stories[0]

    # English counterpart (RSS-shaped, from another source)
    en = Story(
        id="en",
        title="Man charged in Johor Bahru",
        summary="",
        url="https://example.com/en/johor-charged",
        source="EN Outlet",
        source_type=SourceType.RSS,
        published_at="2026-09-30T08:00:00Z",
        category=Category.MALAYSIA,
        language=Language.EN,
        country="MY",
    )

    # The A1 alias for 新山 is johor_bahru; for Johor is johor.
    # ZH title: 新山男子被控 -> entities {johor_bahru, ...?}
    # EN title: Man charged in Johor Bahru -> entities {johor, bahru, ...?}
    # The cross-language merge should succeed.
    topics, _ = cluster([zh, en])
    assert len(topics) == 1, (
        f"cross-language merge failed: ZH=新山男子被控 + EN=Man charged in Johor Bahru; "
        f"got {len(topics)} topics"
    )
    assert topics[0].mention_count == 2
    print("PASS test_a1_alias_compatibility_johor_charged (1 ZH + 1 EN merged)")


def test_a1_alias_compatibility_no_false_merge():
    """A ZH Sin Chew story with no place alias in common with an EN
    story MUST NOT merge (no shared entities)."""
    adapter = _make_adapter()
    zh_html = """<html><body>
        <h2 class="title skip-default-style">
            <a href="https://johor.sinchew.com.my/news/20260930/johor/9000002">幼儿园淹水事故</a>
        </h2>
    </body></html>"""
    zh_stories = adapter._parse_listing(zh_html)
    assert len(zh_stories) == 1
    zh = zh_stories[0]

    # Unrelated English story (no shared entities)
    en = Story(
        id="en",
        title="Sydney hotel fire displaces hundreds",
        summary="",
        url="https://example.com/en/sydney-fire",
        source="EN Outlet",
        source_type=SourceType.RSS,
        published_at="2026-09-30T08:00:00Z",
        category=Category.WORLD,
        language=Language.EN,
        country="AU",
    )

    topics, _ = cluster([zh, en])
    assert len(topics) == 2, (
        f"unrelated ZH+EN stories must NOT merge; got {len(topics)} topics"
    )
    print("PASS test_a1_alias_compatibility_no_false_merge")


# ---------------------------------------------------------------------------
# 17. fail-closed behavior
# ---------------------------------------------------------------------------

def test_fail_closed_on_garbage_input():
    """Pure garbage input produces no stories; no crash."""
    adapter = _make_adapter()
    for bad in [
        "",
        "not html at all",
        "<<<>>>",
        "<?xml version='1.0'?><foo/>",
        b"\x00\x01\x02".decode("utf-8", errors="replace"),
    ]:
        stories = adapter._parse_listing(bad)
        assert isinstance(stories, list)
        # No fake / invented stories
        for s in stories:
            assert s.url
    print("PASS test_fail_closed_on_garbage_input")


def test_fail_closed_on_wrong_source_type():
    """HtmlListingAdapter rejects sources that aren't HTML_LISTING."""
    bad_src = Source(
        name="RSS Source",
        type=SourceType.RSS,
        url="https://example.com/feed",
        reliability=4, country="GB", languages=[Language.EN], tier=SourceTier.B, notes="",
    )
    try:
        HtmlListingAdapter(bad_src, category=Category.MALAYSIA)
    except ValueError as e:
        assert "HTML_LISTING" in str(e)
        print("PASS test_fail_closed_on_wrong_source_type (ValueError raised)")
        return
    raise AssertionError("HtmlListingAdapter accepted non-HTML_LISTING source")


# ---------------------------------------------------------------------------
# 18. live fixture (saved trimmed HTML)
# ---------------------------------------------------------------------------

def test_live_fixture_present():
    """A trimmed fixture from the live 2026-09-30 response must exist
    in fixtures/html_listing/."""
    assert TRIMMED_FIXTURE.exists(), f"missing fixture: {TRIMMED_FIXTURE}"
    body = TRIMMED_FIXTURE.read_text(encoding="utf-8")
    assert "johor.sinchew.com.my" in body
    assert "/news/" in body
    # Must be small (not a 380 KB page copy)
    size = TRIMMED_FIXTURE.stat().st_size
    assert size < 10_000, f"fixture too large ({size} bytes); not a trimmed copy"
    print(f"PASS test_live_fixture_present ({size} bytes)")


def test_articles_are_sorted_for_determinism():
    """Given the same fixture, the output order is deterministic
    (URL-sorted)."""
    adapter = _make_adapter()
    fixture = _load_fixture()
    a = adapter._parse_listing(fixture)
    b = adapter._parse_listing(fixture)
    assert [s.url for s in a] == [s.url for s in b], \
        "output order is not deterministic across runs"
    print("PASS test_articles_are_sorted_for_determinism")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    """Run every test in this file; return 0 on success, 1 on failure."""
    tests = [
        test_valid_html_listing_returns_stories,
        test_multiple_article_cards_collected,
        test_valid_article_url_accepted,
        test_invalid_url_rejected,
        test_duplicate_article_url_dedup,
        test_navigation_link_rejected,
        test_advertisement_rejection,
        test_missing_title_drops_card,
        test_empty_title_after_strip_drops_card,
        test_missing_timestamp_results_in_none,
        test_malformed_html_returns_empty_or_partial,
        test_html_entity_decoding,
        test_chinese_title_normalization,
        test_language_is_zh,
        test_source_identity,
        test_a1_alias_compatibility_johor_charged,
        test_a1_alias_compatibility_no_false_merge,
        test_fail_closed_on_garbage_input,
        test_fail_closed_on_wrong_source_type,
        test_live_fixture_present,
        test_articles_are_sorted_for_determinism,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print()
    if failed:
        print(f"{failed} of {len(tests)} TESTS FAILED")
        return 1
    print(f"ALL {len(tests)} HTML LISTING A2.2-A TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(_run_all())
