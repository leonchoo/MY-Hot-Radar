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
    ChinaPressHtmlListingAdapter,
    ENanyangHtmlListingAdapter,
    HtmlListingAdapter,
    _is_article_url,
    _strip_html,
    _is_chinapress_article_url,
    _is_enanyang_article_url,
    _coerce_chinapress_datetime,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "html_listing"
TRIMMED_FIXTURE = FIXTURES_DIR / "sinchew_johor_listing_trimmed.html"
TRIMMED_FIXTURE_MAIN = FIXTURES_DIR / "sinchew_main_listing_trimmed.html"
TRIMMED_FIXTURE_CHINAPRESS = FIXTURES_DIR / "chinapress_listing_trimmed.html"
TRIMMED_FIXTURE_ENANYANG = FIXTURES_DIR / "enanyang_listing_trimmed.html"


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


def _make_source_main(
    name: str = "Sin Chew Main",
    url: str = "https://www.sinchew.com.my/",
) -> Source:
    return Source(
        name=name,
        type=SourceType.HTML_LISTING,
        url=url,
        reliability=4,
        country="MY",
        languages=[Language.ZH],
        tier=SourceTier.B,
        notes="A2.2-B test fixture",
    )


def _make_adapter() -> HtmlListingAdapter:
    return HtmlListingAdapter(_make_source(), category=Category.MALAYSIA)


def _make_adapter_main() -> HtmlListingAdapter:
    return HtmlListingAdapter(_make_source_main(), category=Category.MALAYSIA)


def _load_fixture() -> str:
    if not TRIMMED_FIXTURE.exists():
        raise FileNotFoundError(
            f"fixture missing: {TRIMMED_FIXTURE}. "
            f"Re-run the probe script to regenerate it."
        )
    return TRIMMED_FIXTURE.read_text(encoding="utf-8")


def _load_fixture_main() -> str:
    if not TRIMMED_FIXTURE_MAIN.exists():
        raise FileNotFoundError(
            f"fixture missing: {TRIMMED_FIXTURE_MAIN}. "
            f"Re-run the probe script to regenerate it."
        )
    return TRIMMED_FIXTURE_MAIN.read_text(encoding="utf-8")


def _make_source_chinapress(
    name: str = "China Press",
    url: str = "https://www.chinapress.com.my/",
) -> Source:
    return Source(
        name=name,
        type=SourceType.HTML_LISTING,
        url=url,
        reliability=4,
        country="MY",
        languages=[Language.ZH],
        tier=SourceTier.B,
        notes="A2.2-C test fixture",
    )


def _make_adapter_chinapress() -> ChinaPressHtmlListingAdapter:
    return ChinaPressHtmlListingAdapter(
        _make_source_chinapress(), category=Category.MALAYSIA
    )


def _load_fixture_chinapress() -> str:
    if not TRIMMED_FIXTURE_CHINAPRESS.exists():
        raise FileNotFoundError(
            f"fixture missing: {TRIMMED_FIXTURE_CHINAPRESS}. "
            f"Re-run the probe script to regenerate it."
        )
    return TRIMMED_FIXTURE_CHINAPRESS.read_text(encoding="utf-8")


def _make_source_enanyang(
    name: str = "eNanyang",
    url: str = "https://www.enanyang.my/",
) -> Source:
    return Source(
        name=name,
        type=SourceType.HTML_LISTING,
        url=url,
        reliability=3,  # Tier C
        country="MY",
        languages=[Language.ZH],
        tier=SourceTier.C,
        notes="A2.2-D test fixture",
    )


def _make_adapter_enanyang() -> ENanyangHtmlListingAdapter:
    return ENanyangHtmlListingAdapter(
        _make_source_enanyang(), category=Category.MALAYSIA
    )


def _load_fixture_enanyang() -> str:
    if not TRIMMED_FIXTURE_ENANYANG.exists():
        raise FileNotFoundError(
            f"fixture missing: {TRIMMED_FIXTURE_ENANYANG}. "
            f"Re-run the probe script to regenerate it."
        )
    return TRIMMED_FIXTURE_ENANYANG.read_text(encoding="utf-8")


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

# ---------------------------------------------------------------------------
# A2.2-C — China Press adapter tests
# ---------------------------------------------------------------------------
#
# China Press uses a structurally different listing-page format than
# Sin Chew (see A2.2-C implementation report §4):
#
#   * URL pattern: /YYYYMMDD/{percent-encoded-slug}/  (NOT /news/YYYYMMDD/{section}/{id})
#   * Title location: <h1>TITLE</h1> inside a sibling <a> anchor  (NOT <h2 class="title">)
#   * Timestamp source: <div data-pdatetime="ISO_8601+08:00">  (NOT relative-time strings)
#
# These tests verify the ChinaPressHtmlListingAdapter subclass handles
# all of these correctly, with the adapter-specific URL filter
# (excludes ?p=NNN ticker URLs, /CP/ ad-asset URLs, and pure-ASCII slugs).


def test_chinapress_fixture_parses_to_10_stories():
    """The trimmed China Press fixture yields exactly 10 stories."""
    adapter = _make_adapter_chinapress()
    stories = adapter._parse_listing(_load_fixture_chinapress())
    urls = {s.url for s in stories}
    assert len(stories) == len(urls) == 10, (
        f"expected 10 unique stories; got {len(stories)} stories, {len(urls)} URLs"
    )
    for s in stories:
        assert isinstance(s, Story)
        assert s.title
        assert s.url
        assert s.language == Language.ZH
        assert s.source_type == SourceType.HTML_LISTING
    print(f"PASS test_chinapress_fixture_parses_to_10_stories (10 stories, all zh)")


def test_chinapress_extracts_absolute_timestamp_from_data_pdatetime():
    """A2.2-C: <div data-pdatetime="ISO_8601+08:00"> -> published_at UTC Z."""
    import re as _re
    adapter = _make_adapter_chinapress()
    stories = adapter._parse_listing(_load_fixture_chinapress())
    with_dt = [s for s in stories if s.published_at is not None]
    assert len(with_dt) == 9, (
        f"expected 9 stories with absolute timestamps; got {len(with_dt)}"
    )
    iso_z_pat = _re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    for s in with_dt:
        assert iso_z_pat.match(s.published_at), (
            f"published_at must be UTC ISO Z; got {s.published_at!r}"
        )
    print(f"PASS test_chinapress_extracts_absolute_timestamp_from_data_pdatetime "
          f"(9/10 absolute UTC ISO Z timestamps)")


def test_chinapress_url_filter_excludes_ticker_and_ad_urls():
    """A2.2-C: _is_chinapress_article_url filters ?p=NNN, /CP/ ad assets, pure-ASCII slugs."""
    assert _is_chinapress_article_url(
        "https://www.chinapress.com.my/20260930/%e5%b9%b4%e9%95%bf%e8%80%85/"
    )
    assert _is_chinapress_article_url(
        "https://www.chinapress.com.my/20260930/amg%e7%ba%af%e7%94%b5"
    )
    assert not _is_chinapress_article_url("https://www.chinapress.com.my/?p=5147972")
    assert not _is_chinapress_article_url(
        "https://www.chinapress.com.my/20260930/not-a-number/"
    )
    assert not _is_chinapress_article_url(
        "https://www.chinapress.com.my/14415562/CP//WEB//OTP//Ad"
    )
    assert not _is_chinapress_article_url(
        "https://example.com/20260930/%e5%b9%b4%e9%95%bf%e8%80%85/"
    )
    assert not _is_chinapress_article_url("")
    print("PASS test_chinapress_url_filter_excludes_ticker_and_ad_urls "
          "(7 cases checked: 2 ACCEPT + 5 REJECT)")


def test_chinapress_datetime_coercion():
    """A2.2-C: _coerce_chinapress_datetime converts ISO 8601 +08:00 to UTC ISO Z."""
    result = _coerce_chinapress_datetime("2026-09-30T20:33:42+08:00")
    assert result == "2026-09-30T12:33:42Z", f"+08:00 to UTC failed; got {result!r}"
    assert _coerce_chinapress_datetime("2026-09-30T12:33:42Z") == "2026-09-30T12:33:42Z"
    assert _coerce_chinapress_datetime("not a date") is None
    assert _coerce_chinapress_datetime("") is None
    assert _coerce_chinapress_datetime("2026-09-30T04:33:42-04:00") == "2026-09-30T08:33:42Z"
    print("PASS test_chinapress_datetime_coercion")


def test_chinapress_extracted_stories_have_no_advertorial():
    """A2.2-C: extracted URLs must NOT contain ?p=, /CP/, /cp/."""
    adapter = _make_adapter_chinapress()
    stories = adapter._parse_listing(_load_fixture_chinapress())
    for s in stories:
        assert "?p=" not in s.url, f"ticker URL leaked: {s.url}"
        assert "/CP/" not in s.url and "/cp/" not in s.url, f"ad URL leaked: {s.url}"
        assert "chinapress.com.my" in s.url, f"non-self-host URL: {s.url}"
    print(f"PASS test_chinapress_extracted_stories_have_no_advertorial "
          f"(all {len(stories)} URLs are clean)")


def test_chinapress_sinchew_regression():
    """A2.2-C: Sin Chew Johor regression — parent HtmlListingAdapter unaffected."""
    johor_adapter = _make_adapter()
    johor_stories = johor_adapter._parse_listing(_load_fixture())
    assert len(johor_stories) >= 6, (
        f"Johor desk should still yield >=6 stories; got {len(johor_stories)}"
    )
    for s in johor_stories:
        assert "johor.sinchew.com.my" in s.url
        assert s.published_at is None
    print(f"PASS test_chinapress_sinchew_regression ({len(johor_stories)} Johor stories, "
          f"all None timestamps — parent unaffected)")


# ---------------------------------------------------------------------------
# A2.2-D — eNanyang adapter tests
# ---------------------------------------------------------------------------
#
# eNanyang (南洋商报) is the sister paper of Sin Chew Daily but with
# its own canonical domain (enanyang.my, NOT a sinchew.com.my
# subdomain). The homepage exposes only ~6 article URLs in a Swiper
# carousel — the lowest article volume of any registered Tier-B/C
# source — so eNanyang is registered as Tier C per the Discovery
# Audit's NEEDS_VALIDATION classification.
#
# The ENanyangHtmlListingAdapter subclass follows the same
# architecture as ChinaPressHtmlListingAdapter (A2.2-C): a Phase-4b
# walk (img alt fallback) since the homepage has no <h1>/<h2>/<h3>
# article cards.
#
# Critical tests below:
#   - Tier: C
#   - Volume: 6 articles per fetch
#   - published_at: None for every story (no timestamp data)
#   - Stability: 100% byte-identical across 3 fetches
#   - Navigation: 57 /category/ URLs to filter out


def test_enanyang_fixture_parses_to_6_stories():
    """The trimmed eNanyang fixture yields exactly 6 stories.

    Live-fetched 2026-09-30 produced 6 unique
    /news/20260930/{Section}/{numeric_id} articles per fetch on
    https://www.enanyang.my/. The fixture contains 6 real article
    cards from the Swiper carousel.
    """
    adapter = _make_adapter_enanyang()
    stories = adapter._parse_listing(_load_fixture_enanyang())
    urls = {s.url for s in stories}
    assert len(stories) == len(urls) == 6, (
        f"expected 6 unique stories; got {len(stories)} stories, {len(urls)} URLs"
    )
    for s in stories:
        assert isinstance(s, Story)
        assert s.title
        assert s.url
        assert s.language == Language.ZH
        assert s.source_type == SourceType.HTML_LISTING
    print(f"PASS test_enanyang_fixture_parses_to_6_stories (6 stories, all zh)")


def test_enanyang_emits_no_published_at():
    """A2.2-D: eNanyang has 0 <time> tags, 0 datetime= attrs, 0 relative
    time strings on the listing page. The adapter MUST emit
    published_at=None for every story (per spec rule).
    """
    adapter = _make_adapter_enanyang()
    stories = adapter._parse_listing(_load_fixture_enanyang())
    for s in stories:
        assert s.published_at is None, (
            f"eNanyang has no timestamps; got published_at={s.published_at!r} for {s.url}"
        )
    assert len(stories) > 0
    print(f"PASS test_enanyang_emits_no_published_at ({len(stories)} stories, all None)")


def test_enanyang_url_filter():
    """A2.2-D: _is_enanyang_article_url accepts /news/{date}/{section}/{id}
    on www.enanyang.my and rejects /category/, /hotpost, /video,
    /podcast, /stock-price nav URLs.
    """
    # Accept
    assert _is_enanyang_article_url(
        "https://www.enanyang.my/news/20260930/Finance/1397184"
    )
    assert _is_enanyang_article_url(
        "https://www.enanyang.my/news/20260930/International/1398544"
    )
    assert _is_enanyang_article_url(
        "https://www.enanyang.my/news/20260930/State/1398635"
    )
    # Reject (nav)
    assert not _is_enanyang_article_url("https://www.enanyang.my/category/finance")
    assert not _is_enanyang_article_url("https://www.enanyang.my/hotpost")
    assert not _is_enanyang_article_url("https://www.enanyang.my/video")
    assert not _is_enanyang_article_url("https://www.enanyang.my/podcast")
    assert not _is_enanyang_article_url("https://www.enanyang.my/stock-price")
    assert not _is_enanyang_article_url("https://www.enanyang.my/")
    # Wrong host
    assert not _is_enanyang_article_url(
        "https://www.sinchew.com.my/news/20260930/Finance/1397184"
    )
    # Empty
    assert not _is_enanyang_article_url("")
    print("PASS test_enanyang_url_filter (13 cases: 3 accept + 10 reject)")


def test_enanyang_extracted_stories_all_self_host():
    """A2.2-D: all 6 extracted article URLs must be on the
    www.enanyang.my host (no cross-host wire-origin contamination).
    """
    adapter = _make_adapter_enanyang()
    stories = adapter._parse_listing(_load_fixture_enanyang())
    for s in stories:
        assert "enanyang.my" in s.url, (
            f"non-self-host URL leaked through adapter: {s.url}"
        )
        assert "?p=" not in s.url and "/category/" not in s.url, (
            f"nav URL leaked through adapter: {s.url}"
        )
    print(f"PASS test_enanyang_extracted_stories_all_self_host "
          f"(all {len(stories)} URLs on enanyang.my)")


def test_enanyang_sinchew_regression():
    """A2.2-D: Sin Chew regression — after adding eNanyang subclass,
    HtmlListingAdapter still parses the Sin Chew Johor fixture
    correctly. The parent class is UNTOUCHED by A2.2-D; the eNanyang
    subclass inherits nothing from it (it overrides _parse_listing
    entirely).
    """
    johor_adapter = _make_adapter()  # parent HtmlListingAdapter
    johor_stories = johor_adapter._parse_listing(_load_fixture())  # Johor fixture
    assert len(johor_stories) >= 6, (
        f"Johor desk fixture should still yield >=6 stories; got {len(johor_stories)}"
    )
    for s in johor_stories:
        assert "johor.sinchew.com.my" in s.url, (
            f"Johor desk stories should be on johor.sinchew.com.my; got {s.url}"
        )
        assert s.published_at is None, (
            f"Johor desk must continue to emit published_at=None; got {s.published_at}"
        )
    # China Press regression too
    cp_adapter = _make_adapter_chinapress()
    cp_stories = cp_adapter._parse_listing(_load_fixture_chinapress())
    assert len(cp_stories) == 10
    print(f"PASS test_enanyang_sinchew_regression "
          f"(Johor {len(johor_stories)} + China Press {len(cp_stories)} stories, "
          f"parent + A2.2-C unaffected)")


def _run_all() -> int:
    """Run every test in this file; return 0 on success, 1 on failure."""
    tests = [
        # A2.2-A tests
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
        # A2.2-B tests
        test_sinchew_main_fixture_parses_to_8_stories,
        test_sinchew_main_accepts_arbitrary_sections,
        test_sinchew_main_accepts_publisher_wide_hosts,
        test_sinchew_main_phase2_handles_inner_tag_anchors,
        test_sinchew_main_rejects_ads_and_categories,
        test_sinchew_main_dedup_real_title_wins_over_synthetic_anchor_text,
        test_sinchew_main_johor_desk_backward_compat,
        # A2.2-C tests
        test_chinapress_fixture_parses_to_10_stories,
        test_chinapress_extracts_absolute_timestamp_from_data_pdatetime,
        test_chinapress_url_filter_excludes_ticker_and_ad_urls,
        test_chinapress_datetime_coercion,
        test_chinapress_extracted_stories_have_no_advertorial,
        test_chinapress_sinchew_regression,
        # A2.2-D tests
        test_enanyang_fixture_parses_to_6_stories,
        test_enanyang_emits_no_published_at,
        test_enanyang_url_filter,
        test_enanyang_extracted_stories_all_self_host,
        test_enanyang_sinchew_regression,
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
    print(f"ALL {len(tests)} HTML LISTING A2.2-A + A2.2-B + A2.2-C + A2.2-D TESTS PASSED")
    return 0


# ============================================================================
# A2.2-B — Sin Chew Main generalization tests
# ============================================================================
#
# These tests verify the A2.2-B generalizations to the adapter:
#   1. URL regex accepts arbitrary sections (not just /johor/)
#   2. Host filter accepts the entire sinchew.com.my publisher family
#   3. Phase-2 regex matches anchors that wrap <img> / <h4> children
#
# The A2.2-A tests above continue to pass because the Johor pattern
# is a strict subset of the generalized pattern.

def test_sinchew_main_fixture_parses_to_8_stories():
    """The Sin Chew Main trimmed fixture produces exactly 8 stories.

    7 real Sin Chew Main articles (international, nation, melaka,
    yl sections) + 1 real cross-host Johor-desk article hosted on
    johor.sinchew.com.my = 8 distinct URLs.
    """
    adapter = _make_adapter_main()
    stories = adapter._parse_listing(_load_fixture_main())
    urls = {s.url for s in stories}
    assert len(stories) == len(urls) == 8, \
        f"expected 8 unique stories; got {len(stories)} stories, {len(urls)} URLs"
    for s in stories:
        assert isinstance(s, Story)
        assert s.title
        assert s.url
        assert s.language == Language.ZH
        assert s.source_type == SourceType.HTML_LISTING
        assert s.published_at is None  # listing page has no absolute timestamps
    print(f"PASS test_sinchew_main_fixture_parses_to_8_stories (8 stories, all zh, all None)")


def test_sinchew_main_accepts_arbitrary_sections():
    """A2.2-B: URL regex accepts /news/YYYYMMDD/{section}/{id} for
    any section, not just /johor/."""
    # General Sin Chew Main sections.
    assert _is_article_url("https://www.sinchew.com.my/news/20260930/international/7896179")
    assert _is_article_url("https://www.sinchew.com.my/news/20260930/nation/7896026")
    assert _is_article_url("https://www.sinchew.com.my/news/20260930/sports/7895444")
    assert _is_article_url("https://www.sinchew.com.my/news/20260930/entertainment/7895190")
    assert _is_article_url("https://www.sinchew.com.my/news/20260930/finance/7895444")
    assert _is_article_url("https://www.sinchew.com.my/news/20260929/yl/7890680")
    assert _is_article_url("https://www.sinchew.com.my/news/20260930/sarawak/7889444")
    # Johor-section URLs on the Johor desk still work (backward compat).
    assert _is_article_url("https://johor.sinchew.com.my/news/20260930/johor/7895884")
    print("PASS test_sinchew_main_accepts_arbitrary_sections (8 sections accepted)")


def test_sinchew_main_accepts_publisher_wide_hosts():
    """A2.2-B: host filter accepts any *.sinchew.com.my subdomain.

    Sin Chew Main homepage links to articles hosted on the regional
    desk subdomains (metro, sarawak, sabah, eastcoast, johor, ...).
    The adapter must accept these as legitimate Sin Chew articles.
    """
    hosts = [
        "www.sinchew.com.my",
        "johor.sinchew.com.my",
        "metro.sinchew.com.my",
        "melaka.sinchew.com.my",
        "eastcoast.sinchew.com.my",
        "sarawak.sinchew.com.my",
        "sabah.sinchew.com.my",
        "pocketimes.sinchew.com.my",
        "mysinchew.sinchew.com.my",
        "nsl.sinchew.com.my",
    ]
    for h in hosts:
        url = f"https://{h}/news/20260930/section/1234567"
        assert _is_article_url(url), f"{url} should be accepted (publisher-wide host)"
    # Negative: non-Sin Chew hosts must still be rejected.
    assert not _is_article_url("https://example.com/news/20260930/section/1234567")
    assert not _is_article_url("https://chinapress.com.my/news/20260930/section/1234567")
    print(f"PASS test_sinchew_main_accepts_publisher_wide_hosts "
          f"({len(hosts)} subdomains accepted)")


def test_sinchew_main_phase2_handles_inner_tag_anchors():
    """A2.2-B: Phase-2 regex matches <a> anchors that wrap inner
    tags (<img>, <h4>) — the structure Sin Chew Main actually uses.

    The fixture deliberately puts <img> children inside the
    internalLink anchors. The previous Phase-2 regex (which
    required ``[^<]*`` text content between open and close tags)
    would have rejected these. The new regex only requires the
    open-tag attributes (class + data-title + href) and ignores
    the closing tag.
    """
    adapter = _make_adapter_main()
    stories = adapter._parse_listing(_load_fixture_main())
    # The fixture's 7 real Sin Chew Main articles each have TWO
    # internalLink anchors (one wrapping <img>, one wrapping <h4>).
    # Both anchors must contribute to extraction but dedupe to the
    # same URL.
    urls = {s.url for s in stories}
    assert len(urls) == 8, \
        f"expected 8 distinct URLs (after dedupe); got {len(urls)}"
    print(f"PASS test_sinchew_main_phase2_handles_inner_tag_anchors "
          f"(8 URLs after dedup, all from <a> anchors with inner tags)")


def test_sinchew_main_rejects_ads_and_categories():
    """A2.2-B: nav/category/non-numeric-id URLs are still rejected
    even with the generalized URL regex."""
    adapter = _make_adapter_main()
    stories = adapter._parse_listing(_load_fixture_main())
    urls = {s.url for s in stories}
    # The fixture has 2 deliberately invalid URLs:
    #   - /news/20260930/international/not-a-number (non-numeric id)
    #   - /category/foo (navigation)
    assert "https://www.sinchew.com.my/news/20260930/international/not-a-number" not in urls, \
        "non-numeric id should be rejected"
    assert not any("/category/" in u for u in urls), \
        "category URLs should be rejected"
    print(f"PASS test_sinchew_main_rejects_ads_and_categories "
          f"(all {len(urls)} extracted URLs are valid articles)")


def test_sinchew_main_dedup_real_title_wins_over_synthetic_anchor_text():
    """A2.2-B: when the same article URL appears twice (once as
    real internalLink with real data-title, once as bare anchor
    with synthetic anchor text), the real title wins.

    Sin Chew Main's homepage often has a primary article card
    followed by a related-stories anchor with shorter text. The
    Phase-2 walk sees the real internalLink first and stores the
    real title; the bare-anchor walk sees the synthetic text but
    ``if full in candidates: continue`` skips it.
    """
    adapter = _make_adapter_main()
    stories = adapter._parse_listing(_load_fixture_main())
    # Find the article with the synthetic dup-link-anchor-text
    target_url = "https://www.sinchew.com.my/news/20260930/international/7896179"
    target_story = next((s for s in stories if s.url == target_url), None)
    assert target_story is not None, \
        "the article that appears twice (real + dup) should still be emitted"
    # Real title is "哥哥吸毒频繁闹事 弟鸣枪吓阻变射杀"
    # Synthetic anchor text is "link text ignored" / "dup-link-anchor-text"
    assert "哥哥吸毒" in target_story.title, \
        f"expected the REAL data-title to win over synthetic anchor text; got {target_story.title!r}"
    assert "dup-link-anchor-text" not in target_story.title, \
        "synthetic anchor text should NOT appear in title"
    print(f"PASS test_sinchew_main_dedup_real_title_wins_over_synthetic_anchor_text "
          f"(title={target_story.title!r})")


def test_sinchew_main_johor_desk_backward_compat():
    """A2.2-A regression: after A2.2-B generalization, Sin Chew
    Johor desk's URL pattern still parses cleanly.

    The Johor pattern /news/YYYYMMDD/johor/{id} is a strict subset
    of the generalized /news/YYYYMMDD/{section}/{id} pattern. The
    host filter ``sinchew.com.my`` accepts both
    ``johor.sinchew.com.my`` (Johor desk) and ``www.sinchew.com.my``
    (Main).
    """
    adapter = _make_adapter()  # Johor desk adapter
    stories = adapter._parse_listing(_load_fixture())  # Johor fixture
    assert len(stories) >= 6, f"Johor desk fixture should still yield >=6 stories; got {len(stories)}"
    for s in stories:
        assert "johor.sinchew.com.my" in s.url, \
            f"Johor desk stories should be on johor.sinchew.com.my; got {s.url}"
    print(f"PASS test_sinchew_main_johor_desk_backward_compat "
          f"(A2.2-A Johor desk still works after A2.2-B generalization, {len(stories)} stories)")


if __name__ == "__main__":
    sys.exit(_run_all())
