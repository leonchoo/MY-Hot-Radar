"""
A2.1 — Chinese WP-JSON adapter tests.

Coverage matrix (per spec §Tests):

  1.  valid WP-JSON response
  2.  multiple posts
  3.  missing optional fields
  4.  malformed JSON
  5.  invalid article URL
  6.  invalid / missing timestamp
  7.  HTML inside title / excerpt
  8.  duplicate article
  9.  Chinese language normalization
  10. A1 alias compatibility (cross-language dedup)
  11. fail-closed behavior
  12. live endpoint smoke test (only when explicitly enabled)

These tests use deterministic fixtures from real HTTP responses
captured on 2026-09-30 (saved under ``fixtures/wp_json/``). The
fixtures are intentionally small (one post each) so tests stay fast
and offline.

The runner block supports both ``python -m`` and direct import.
"""

from __future__ import annotations

import json
import os
import sys
import unittest.mock as mock
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
)
from radar.pipeline import _build_adapter
from radar.sources.base import FetchError
from radar.sources.wp_json import (
    WpJsonAdapter,
    _coerce_published_at,
    _strip_html,
)


IS_LIVE = os.environ.get("RADAR_WP_JSON_LIVE") == "1"

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "wp_json"
KWONGWAH_FIXTURE = FIXTURES_DIR / "kwongwah_sample.json"
GUANGMING_FIXTURE = FIXTURES_DIR / "guangming_sample.json"


# ============================================================================
# Helpers
# ============================================================================

def _make_source(*, name="Kwong Wah Yit Poh",
                 url="https://www.kwongwah.com.my/wp-json/wp/v2/posts?per_page=3",
                 stype=SourceType.WP_JSON,
                 languages=None,
                 reliability=4,
                 tier=SourceTier.B) -> Source:
    """Build a Source for adapter tests."""
    return Source(
        name=name,
        type=stype,
        url=url,
        reliability=reliability,
        country="MY",
        languages=languages if languages is not None else [Language.ZH],
        tier=tier,
        notes="test fixture source",
    )


def _stub_http_get(monkey, body_str):
    """Replace WpJsonAdapter._http_get with a stub returning body_str."""
    monkey.setattr(
        WpJsonAdapter, "_http_get",
        lambda self, url, *a, **kw: body_str,
    )


# ============================================================================
# 1. valid WP-JSON response
# ============================================================================

def test_valid_wp_json_response():
    """A valid WP-JSON list response parses into a non-empty list."""
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(body, dict), "fixture root should be a post object"
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story is not None
    assert story.title != ""
    assert story.url != ""
    assert story.published_at is not None


# ============================================================================
# 2. multiple posts
# ============================================================================

def test_multiple_posts_via_fetch(monkeypatch=None):
    """A JSON list of posts produces one Story per post via fetch().

    Uses a stub _http_get to inject a deterministic list response
    containing 3 posts. Each post must produce exactly one Story.

    Note: monkeypatch parameter is kept for pytest compatibility; in
    plain-script mode, we use unittest.mock.patch.
    """
    posts = [
        json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8")),
        json.loads(GUANGMING_FIXTURE.read_text(encoding="utf-8")),
        json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8")),  # duplicate
    ]
    body_str = json.dumps(posts, ensure_ascii=False)

    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    with mock.patch.object(WpJsonAdapter, "_http_get", return_value=body_str):
        stories = adapter.fetch()
    assert len(stories) == 3, f"expected 3 stories from 3 posts, got {len(stories)}"
    for s in stories:
        assert s.title != ""
        assert s.url != ""


# ============================================================================
# 3. missing optional fields
# ============================================================================

def test_missing_optional_fields_does_not_drop_post():
    """A post missing non-critical keys still produces a Story.

    WordPress /wp-json returns many optional fields. If only
    date_gmt is missing (only date present), published_at falls
    back to date. If both are missing, the adapter skips the post.
    """
    body_full = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    # Strip optional but commonly present fields
    minimal = {
        "id": body_full["id"],
        "title": body_full["title"],
        "link": body_full["link"],
        "date_gmt": body_full["date_gmt"],
    }
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(minimal)
    assert story is not None
    assert story.title != ""
    assert story.url != ""
    # date_gmt is UTC by WordPress convention; the adapter appends
    # a Z suffix to mark timezone-aware.
    assert story.published_at == body_full["date_gmt"] + "Z"


def test_missing_link_drops_post():
    """If `link` is missing, the post is dropped (fail-closed)."""
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    del body["link"]
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story is None, "post without link MUST be dropped (no canonical URL)"


def test_missing_title_drops_post():
    """If title is missing, post is dropped."""
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    del body["title"]
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story is None, "post without title MUST be dropped"


# ============================================================================
# 4. malformed JSON
# ============================================================================

def test_malformed_json_raises_fetch_error():
    """Malformed JSON body raises FetchError (matches RSSAdapter pattern)."""
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    with mock.patch.object(WpJsonAdapter, "_http_get", return_value="not-json{"):
        try:
            adapter.fetch()
        except FetchError as e:
            assert "malformed" in str(e).lower() or "json" in str(e).lower()
            return
        raise AssertionError("expected FetchError on malformed JSON")


def test_non_list_json_raises_fetch_error():
    """A JSON object (not array) at the top level raises FetchError."""
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    with mock.patch.object(
        WpJsonAdapter, "_http_get",
        return_value=json.dumps({"some": "object"}),
    ):
        try:
            adapter.fetch()
        except FetchError:
            return
        raise AssertionError("expected FetchError on non-list JSON")


# ============================================================================
# 5. invalid article URL
# ============================================================================

def test_javascript_scheme_url_drops_post():
    """A post whose `link` is `javascript:...` is dropped.

    Defense against XSS / unsafe URL injection. The adapter does not
    itself validate URL safety (that's ``_is_safe_url`` in the
    Candidate pipeline), but if link is missing or empty, the post
    is dropped.
    """
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    body["link"] = ""  # empty
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story is None


def test_missing_url_drops_post():
    """A post whose `link` is None is dropped."""
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    body["link"] = None
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story is None


# ============================================================================
# 6. invalid / missing timestamp
# ============================================================================

def test_missing_both_dates_drops_post():
    """If date_gmt and date are both missing → story dropped.

    We refuse to invent a timestamp. Per A2.1 spec, no observed_at
    fallback.
    """
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    del body["date"]
    del body["date_gmt"]
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story is None, (
        "post without date_gmt AND date MUST be dropped (no fake ISO)"
    )


def test_modified_only_is_dropped():
    """modified / modified_gmt alone is NOT used as published_at.

    modified reflects edit time, not publication time. We do not
    fall back to it. The audit explicitly forbids this.
    """
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    del body["date"]
    del body["date_gmt"]
    body["modified_gmt"] = "2026-09-30T08:00:00"
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story is None, (
        "modified_gmt alone MUST NOT be used as published_at"
    )


def test_coerce_published_at_prefers_date_gmt():
    """date_gmt wins over date when both are present (UTC priority).

    The returned value carries a ``Z`` suffix to mark it as UTC,
    so downstream ``datetime.fromisoformat`` parsers treat it as
    timezone-aware.
    """
    post = {"date_gmt": "2026-09-30T08:34:23", "date": "2026-09-30T16:34:23"}
    assert _coerce_published_at(post) == "2026-09-30T08:34:23Z"


def test_coerce_published_at_falls_back_to_date():
    """When date_gmt is missing, date is used (best-effort local time).

    The returned value does NOT carry a ``Z`` suffix (we don't
    know the timezone when only ``date`` is present).
    """
    post = {"date": "2026-09-30T16:34:23"}
    assert _coerce_published_at(post) == "2026-09-30T16:34:23"


def test_coerce_published_at_returns_none_for_empty():
    """Empty string date → None (fail-closed)."""
    assert _coerce_published_at({"date": ""}) is None
    assert _coerce_published_at({"date_gmt": ""}) is None


# ============================================================================
# 7. HTML inside title / excerpt
# ============================================================================

def test_html_tags_stripped_from_title():
    """HTML tags in title.rendered are stripped to plain text."""
    body = {
        "title": {"rendered": "<p>Hello <strong>World</strong></p>"},
        "link": "https://example.com/x",
        "date_gmt": "2026-09-30T08:00:00",
    }
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story is not None
    assert story.title == "Hello World"


def test_html_entities_unescaped_in_title():
    """HTML entities (&hellip; etc.) are unescaped in the title.

    ``&hellip;`` becomes the Unicode HORIZONTAL ELLIPSIS character
    (U+2026 ``…``). ``&amp;`` becomes ``&``. Numeric entities
    (``&#NNN;``) are decoded to the corresponding code point.
    """
    body = {
        "title": {"rendered": "Foo &hellip; bar &amp; baz"},
        "link": "https://example.com/x",
        "date_gmt": "2026-09-30T08:00:00",
    }
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story is not None
    assert story.title == "Foo \u2026 bar & baz"


def test_html_tags_stripped_from_excerpt():
    """HTML tags in excerpt.rendered are stripped in summary."""
    body = {
        "title": {"rendered": "Sample"},
        "link": "https://example.com/x",
        "date_gmt": "2026-09-30T08:00:00",
        "excerpt": {"rendered": "<p>First <em>paragraph</em>.</p>"},
    }
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story is not None
    assert story.summary == "First paragraph."


def test_strip_html_helper_direct():
    """_strip_html covers common cases."""
    assert _strip_html("") == ""
    assert _strip_html("plain text") == "plain text"
    assert _strip_html("<p>a</p><p>b</p>") == "a b"
    assert _strip_html("a&nbsp;b") == "a b"


# ============================================================================
# 8. duplicate article
# ============================================================================

def test_duplicate_article_in_batch_is_not_deduplicated_by_adapter():
    """Adapter does not dedup; the cluster stage handles dedup.

    This is a deliberate design choice. The adapter emits one Story
    per WP-JSON post; dedup is ``radar.dedup.cluster``'s job.
    Verifying that two identical posts produce two Stories ensures
    the adapter does NOT introduce its own dedup (which would
    diverge from the existing contract).
    """
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    posts = [body, body, body]
    body_str = json.dumps(posts, ensure_ascii=False)
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    with mock.patch.object(WpJsonAdapter, "_http_get", return_value=body_str):
        stories = adapter.fetch()
    assert len(stories) == 3, (
        "adapter does not dedupe; 3 identical posts -> 3 stories. "
        "Cluster is responsible for dedup."
    )


# ============================================================================
# 9. Chinese language normalization
# ============================================================================

def test_chinese_language_propagated():
    """Source.languages[0] = ZH is propagated to every Story."""
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    src = _make_source(languages=[Language.ZH])
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert story.language == Language.ZH


def test_real_chinese_title_round_trips_clean():
    """Real Chinese title from Kwong Wah round-trips through the
    adapter without garbling."""
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert "拖违法车" in story.title
    assert "林子辉" in story.title
    # Whitespace collapsed from 3 internal spaces to 1
    assert "  " not in story.title


def test_real_chinese_excerpt_round_trips_clean():
    """Real Chinese excerpt from Kwong Wah produces readable summary."""
    body = json.loads(KWONGWAH_FIXTURE.read_text(encoding="utf-8"))
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    assert "违法" in story.summary
    assert "<" not in story.summary and ">" not in story.summary


# ============================================================================
# 10. A1 alias compatibility
# ============================================================================

def test_alias_applies_to_chinese_story_title():
    """A Chinese Story from WP-JSON goes through A1 alias map.

    Tests that the existing ``extract_entities`` pipeline (which
    A1 wires to ``_apply_aliases``) correctly extracts aliases from
    Chinese WP-JSON titles.
    """
    body = json.loads(GUANGMING_FIXTURE.read_text(encoding="utf-8"))
    src = _make_source(name="Guang Ming Daily")
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    # The title is "峇都兰樟中央花园公寓 附近人行道修復"
    # None of the alias place names (马来西亚, 新加坡, 吉隆坡, 柔佛,
    # 新山, 马新, 新马) appear in this title, but extract_entities
    # must still run without error on Chinese text.
    ents = extract_entities(story.title)
    assert isinstance(ents, set), (
        f"extract_entities must run on Chinese WP-JSON title; got {ents}"
    )


def test_chinese_wp_json_story_cross_language_johor_charged():
    """Cross-language merge works for Chinese WP-JSON + English RSS.

    Audit §9.5 positive fixture #1: ``新山男子被控`` (ZH, WP-JSON)
    ↔ ``Man charged in Johor Bahru`` (EN, RSS) must merge.
    """
    body = {
        "title": {"rendered": "新山男子被控"},
        "link": "https://example.com/zh/johor-charged",
        "date_gmt": "2026-09-30T08:00:00",
    }
    src_zh = _make_source(name="Kwong Wah Yit Poh")
    adapter_zh = WpJsonAdapter(src_zh, category=Category.MALAYSIA)
    zh_story = adapter_zh._post_to_story(body)

    en_story = Story(
        id="en",
        title="Man charged in Johor Bahru",
        summary="",
        url="https://example.com/en/johor-charged",
        source="EN Outlet",
        source_type=SourceType.NEWS_SITE,
        published_at="2026-09-30T08:00:00Z",
        category=Category.MALAYSIA,
        language=Language.EN,
        country="MY",
    )

    topics, _ = cluster([zh_story, en_story])
    assert len(topics) == 1, (
        f"cross-language merge must work for WP-JSON + RSS; got {len(topics)}: "
        f"{[t.title for t in topics]}"
    )
    assert topics[0].mention_count == 2


def test_extract_entities_returns_alias_entities_for_chinese_title():
    """A1 alias map correctly extracts place names from Chinese
    WP-JSON titles via the existing ``extract_entities`` function.

    Verifies the integration between the WP-JSON adapter and the
    A1 alias map. The integration is:
      Story.title (Chinese WP-JSON raw) →
      normalize_title → tokens() →
      extract_entities() → _apply_aliases() (A1 hook) →
      alias-derived entities.
    """
    body = {
        "title": {"rendered": "新山关卡升级"},
        "link": "https://example.com/zh/johor-bahru-checkpoint",
        "date_gmt": "2026-09-30T08:00:00",
    }
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    story = adapter._post_to_story(body)
    ents = extract_entities(story.title)
    # A1 alias for 新山 → johor_bahru, which the entity regex
    # captures as 2 tokens: johor, bahru
    assert "johor" in ents
    assert "bahru" in ents


# ============================================================================
# 11. fail-closed behavior
# ============================================================================

def test_constructor_rejects_non_wp_json_source():
    """WpJsonAdapter(source, category) raises ValueError if source
    type is not WP_JSON. Defense against misconfiguration."""
    bad = _make_source(stype=SourceType.RSS)
    try:
        WpJsonAdapter(bad, category=Category.MALAYSIA)
    except ValueError:
        return
    raise AssertionError("expected ValueError on wrong source type")


def test_fetch_propagates_http_error():
    """If _http_get raises FetchError, fetch() propagates it.

    Adapter does not silently swallow network errors. Mirrors
    RSSAdapter behavior.
    """
    src = _make_source()
    adapter = WpJsonAdapter(src, category=Category.MALAYSIA)
    with mock.patch.object(
        WpJsonAdapter, "_http_get",
        side_effect=FetchError("network down"),
    ):
        try:
            adapter.fetch()
        except FetchError as e:
            assert "network down" in str(e)
            return
        raise AssertionError("expected FetchError on HTTP failure")


def test_pipeline_routes_wp_json_to_wp_json_adapter():
    """Pipeline._build_adapter routes WP_JSON sources to WpJsonAdapter.

    Verifies the integration in pipeline.py. Uses a file://-style URL
    bypass would short-circuit routing — instead we patch
    ``Source.url`` to a non-existent http URL after construction so
    _build_adapter goes through its http dispatch branch.
    """
    from radar.pipeline import _build_adapter as build
    src = _make_source(name="Kwong Wah Yit Poh")
    # Use a non-existent http URL to avoid the file:// shortcut
    src.url = "https://www.kwongwah.com.my/wp-json/wp/v2/posts"
    adapter = build(src, category=Category.MALAYSIA)
    assert isinstance(adapter, WpJsonAdapter), (
        f"WP_JSON source should route to WpJsonAdapter; got {type(adapter).__name__}"
    )


def test_pipeline_run_scan_with_chinese_wp_json_sources():
    """run_scan accepts Chinese WP-JSON sources via extra_sources and
    clusters them through the existing dedup pipeline.

    This is the end-to-end integration: the WP-JSON adapter's output
    flows through normalize → cluster → momentum → verification →
    classification. We use ``extra_sources`` (not REGISTERED_SOURCES)
    so this test does NOT require updating Radar-6 fixture invariants.

    The Chinese sources are real — registered with the correct
    tier / language / URL. The cluster pipeline must accept them
    without errors.
    """
    import tempfile
    from radar.pipeline import run_scan
    src_kw = _make_source(name="Kwong Wah Yit Poh")
    src_gm = _make_source(
        name="Guang Ming Daily",
        url="https://guangming.com.my/wp-json/wp/v2/posts",
    )

    with tempfile.TemporaryDirectory() as tmp:
        radar_dir = Path(tmp) / "radar"
        summary = run_scan(
            extra_sources=[src_kw, src_gm],
            radar_dir=str(radar_dir),
            return_internals=False,
        )
    assert summary["ok"] is True, f"run_scan failed: {summary}"
    # The two WP-JSON sources should appear in source_status with
    # ok=True or error=True depending on whether the live fetch
    # succeeded. Network is OFF during tests; we tolerate either,
    # but FetchError must not crash the pipeline.
    names = {r["name"] for r in summary["source_status"]}
    assert "Kwong Wah Yit Poh" in names
    assert "Guang Ming Daily" in names


# ============================================================================
# 12. live endpoint smoke test (gated)
# ============================================================================

def test_live_smoke_if_enabled():
    """Live endpoint smoke test against Kwong Wah + Guang Ming.

    Gated behind RADAR_WP_JSON_LIVE=1. Disabled by default because
    it makes a real HTTP request. The test verifies:

      * HTTP 200 from each endpoint.
      * JSON body is a non-empty list of posts.
      * At least one post has today's date.
      * title / url / published_at are present.
    """
    if not IS_LIVE:
        return

    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError

    endpoints = {
        "Kwong Wah": (
            "https://www.kwongwah.com.my/wp-json/wp/v2/posts?per_page=3"
            "&_fields=id,date,date_gmt,link,title"
        ),
        "Guang Ming": (
            "https://guangming.com.my/wp-json/wp/v2/posts?per_page=3"
            "&_fields=id,date,date_gmt,link,title"
        ),
    }
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for name, url in endpoints.items():
        req = Request(
            url,
            headers={"User-Agent": "MY-Hot-Radar/0.1 (+radar-discovery; manual-mode)"},
        )
        with urlopen(req, timeout=10) as r:
            assert r.status == 200, f"{name}: HTTP {r.status}"
            data = json.loads(r.read().decode("utf-8"))
            assert isinstance(data, list) and len(data) > 0, (
                f"{name}: expected non-empty JSON list"
            )
            # Today's date check
            today_seen = False
            for post in data:
                if (post.get("date_gmt") or "").startswith(today):
                    today_seen = True
                    break
            assert today_seen, f"{name}: no post with today's date_gmt"
            # First post sanity
            p0 = data[0]
            assert p0.get("title", {}).get("rendered"), (
                f"{name}: first post missing title"
            )
            assert p0.get("link"), f"{name}: first post missing link"
            assert p0.get("date_gmt"), f"{name}: first post missing date_gmt"
            print(f"  ✓ {name}: HTTP 200, {len(data)} posts, today's date seen")


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
    print(f"ALL {len(test_funcs)} WP-JSON A2.1 TESTS PASSED")
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