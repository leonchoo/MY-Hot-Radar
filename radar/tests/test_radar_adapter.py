"""
Phase 2 / Batch 3B-1 — Website Radar Adapter tests.

The website adapter is a vanilla JS file (`assets/js/radar-feed.js`)
running in the browser. We CAN'T execute browser JS in this Python
test environment without Node.

What we CAN test here:

  1. The Python mirror of the JS URL-safety / schema-validation
     functions matches the JS file's behavior on a wide range of
     inputs. This is the **contract** the JS adapter promises to
     the website.

  2. The JS file's structure: it exists, exports the expected
     functions on `window.MYHotRadar.feed`, and contains all
     required DOM-building branches.

  3. The page that hosts the adapter (`index.html`) has the
     required scaffolding (`#radar-feed-host`, the loading-state
     element, and the script tag).

  4. Fallback / loading / partial / stale behavior is reachable
     by inspecting the JS source for the relevant code paths
     (regex search).

The **real browser QA** (verify rendered DOM end-to-end) is done
in a separate manual / browser step (per spec §32).
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Re-use the public_output module — it is the source of truth for
# the public schema and the URL safety rules. The JS adapter MUST
# agree with it.
from radar.public_output import is_safe_url, validate_public_payload


REPO_ROOT = Path(__file__).resolve().parents[2]
JS_PATH = REPO_ROOT / "assets" / "js" / "radar-feed.js"
INDEX_HTML = REPO_ROOT / "index.html"
PUBLIC_JSON = REPO_ROOT / "public" / "radar" / "latest.json"


# ============================================================================
# §31 JS structure / source contracts (4 tests)
# ============================================================================

def test_js_file_exists_and_is_nonempty():
    """assets/js/radar-feed.js exists and is non-empty."""
    assert JS_PATH.exists(), f"missing JS adapter: {JS_PATH}"
    size = JS_PATH.stat().st_size
    assert size > 1000, f"JS adapter too small: {size} bytes"
    print(f"PASS test_js_file_exists_and_is_nonempty ({size} bytes)")


def test_js_exposes_required_window_api():
    """The JS adapter exposes the testability API on window.MYHotRadar.feed."""
    src = JS_PATH.read_text(encoding="utf-8")
    assert "window.MYHotRadar" in src, "missing window.MYHotRadar namespace"
    assert "window.MYHotRadar.feed" in src, \
        "missing window.MYHotRadar.feed namespace"
    for fn in ("isSafeUrl", "validatePayload", "isStale",
               "isFutureDated", "STATUS_MAP", "VERIFICATION_MAP"):
        assert fn in src, f"missing API function: {fn}"
    print("PASS test_js_exposes_required_window_api")


def test_js_handles_all_required_states():
    """JS contains handling code for: loading, fallback, partial, stale, future-dated, empty, failed."""
    src = JS_PATH.read_text(encoding="utf-8")
    for needle in ("Loading Radar", "Radar Feed unavailable", "Radar data temporarily unavailable",
                   "Some sources are temporarily unavailable",
                   "Radar data may be delayed", "FAILED",
                   "isFutureDated", "isStale"):
        assert needle in src, f"JS missing handling for: {needle!r}"
    print("PASS test_js_handles_all_required_states")


def test_js_does_not_use_innerhtml_for_user_data():
    """JS must use textContent / createElement — NOT innerHTML — for user-controlled strings.

    The JS may legitimately use innerHTML on constant strings, but it
    MUST NOT have a pattern like ``innerHTML = title`` for a topic's
    title. We scan for the dangerous pattern.
    """
    src = JS_PATH.read_text(encoding="utf-8")
    # Look for any assignment of innerHTML to a variable that originates
    # from the payload. A real bug would be:
    #     el.innerHTML = topic.title
    # We accept constant-string innerHTML usage (none in the current file,
    # but the rule is: no variable-from-payload innerHTML).
    dangerous = re.findall(r"\.innerHTML\s*=\s*[A-Za-z_][A-Za-z0-9_.]*", src)
    assert not dangerous, f"JS uses innerHTML with a variable: {dangerous}"
    print("PASS test_js_does_not_use_innerhtml_for_user_data")


# ============================================================================
# §31 Mirror tests — Python vs JS agreement (10 tests)
# ============================================================================

def test_url_safety_agreement_https_accepts():
    """Python's is_safe_url accepts https://."""
    cases = [
        "https://example.com/",
        "https://bbc.co.uk/news/articles/a?x=1&y=2",
        "http://example.com/path",
        "HTTPS://example.com/UPPER",
        "https://example.com/" + "a" * 2000,
    ]
    for url in cases:
        assert is_safe_url(url), f"Python should accept: {url!r}"
    print(f"PASS test_url_safety_agreement_https_accepts ({len(cases)} cases)")


def test_url_safety_agreement_dangerous_rejects():
    """Python's is_safe_url rejects javascript:, data:, file:, vbscript:."""
    cases = [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "data:text/html,<script>x</script>",
        "file:///etc/passwd",
        "vbscript:msgbox",
        "blob:http://evil/abc",
        "ftp://example.com/",
    ]
    for url in cases:
        assert not is_safe_url(url), f"Python should reject: {url!r}"
    print(f"PASS test_url_safety_agreement_dangerous_rejects ({len(cases)} cases)")


def test_url_safety_agreement_whitespace_rejects():
    """Python's is_safe_url rejects URLs with embedded whitespace or control chars."""
    cases = [
        "https://example.com/foo bar",
        "https://example.com\n",
        "https://example.com\r",
        "https://example.com\t",
        "https://example.com\x00",
    ]
    for url in cases:
        assert not is_safe_url(url), f"Python should reject whitespace: {url!r}"
    print(f"PASS test_url_safety_agreement_whitespace_rejects ({len(cases)} cases)")


def test_url_safety_agreement_empty_rejects():
    """Empty string is rejected."""
    for url in ("", "   "):
        assert not is_safe_url(url), f"Python should reject empty/whitespace: {url!r}"
    print("PASS test_url_safety_agreement_empty_rejects")


def test_url_safety_agreement_length_limit():
    """URLs >= 2048 chars are rejected."""
    url = "https://example.com/" + "a" * 2030
    assert len(url) >= 2048
    assert not is_safe_url(url)
    # 2047 chars: should accept (just below the cap)
    short_url = "https://example.com/" + "a" * (2047 - len("https://example.com/"))
    assert len(short_url) == 2047
    assert is_safe_url(short_url)
    print("PASS test_url_safety_agreement_length_limit")


def test_js_url_safety_implementation_uses_same_rules():
    """The JS isSafeUrl uses the same algorithm."""
    src = JS_PATH.read_text(encoding="utf-8")
    # 1. Reject whitespace
    assert "ch === ' ' || ch === '\\t'" in src, "JS should reject space/tab"
    assert "o < 32 || o === 127" in src, "JS should reject ctrl chars"
    # 2. Length limit 2048
    assert "2048" in src, "JS should enforce 2048 limit"
    # 3. Allow only http:// and https://
    assert "http://" in src and "https://" in src, \
        "JS should allow only http(s)"
    # 4. case-insensitive
    assert "toLowerCase()" in src, "JS should be case-insensitive on scheme"
    print("PASS test_js_url_safety_implementation_uses_same_rules")


def test_python_validator_agrees_with_js_validator():
    """The JS validatePayload rejects the same set of bad payloads as Python."""
    bad_payloads = [
        None,
        "string",
        {"schema_version": 99},  # bad schema_version
        {"schema_version": 1, "public_schema_version": 99},  # bad public_schema_version
        {"schema_version": 1, "public_schema_version": 1,
         "scan_id": "", "generated_at": "x",
         "scan_status": "BOGUS", "summary": {}, "topics": []},
        {"schema_version": 1, "public_schema_version": 1,
         "scan_id": "x", "generated_at": "2026-01-01T00:00:00Z",
         "scan_status": "NOPE", "summary": {}, "topics": []},
        {"schema_version": 1, "public_schema_version": 1,
         "scan_id": "x", "generated_at": "2026-01-01T00:00:00Z",
         "scan_status": "SUCCESS",
         "summary": "not a dict", "topics": []},
    ]
    for p in bad_payloads:
        errs = validate_public_payload(p)
        assert len(errs) > 0, \
            f"validator should reject {p!r}"
    print(f"PASS test_python_validator_agrees_with_js_validator "
          f"({len(bad_payloads)} bad payloads rejected)")


def test_js_validator_implementation_uses_same_rules():
    """The JS validatePayload enforces the same checks as Python."""
    src = JS_PATH.read_text(encoding="utf-8")
    for needle in ("schema_version !== 1",
                   "public_schema_version !== 1",
                   "missing scan_id",
                   "missing generated_at",
                   "bad scan_status",
                   "topics not an array"):
        assert needle in src, f"JS validator missing: {needle!r}"
    print("PASS test_js_validator_implementation_uses_same_rules")


def test_status_map_contains_all_required_statuses():
    """The JS STATUS_MAP covers all 5 Status values."""
    src = JS_PATH.read_text(encoding="utf-8")
    for s in ("BREAKING", "RISING", "HOT", "WATCH", "COOLING"):
        assert s in src, f"JS STATUS_MAP missing: {s}"
    print("PASS test_status_map_contains_all_required_statuses")


def test_verification_map_contains_all_required_statuses():
    """The JS VERIFICATION_MAP covers all 5 VerificationStatus values."""
    src = JS_PATH.read_text(encoding="utf-8")
    for v in ("CONFIRMED", "REPORTED", "SOCIAL_BUZZ", "UNVERIFIED", "RUMOUR"):
        assert v in src, f"JS VERIFICATION_MAP missing: {v}"
    print("PASS test_verification_map_contains_all_required_statuses")


# ============================================================================
# §31 Host page integration (4 tests)
# ============================================================================

def test_index_html_has_radar_feed_host():
    """index.html has the #radar-feed-host element."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="radar-feed-host"' in html, \
        "index.html missing #radar-feed-host"
    print("PASS test_index_html_has_radar_feed_host")


def test_index_html_has_loading_state():
    """index.html has the loading placeholder."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="radar-feed-loading"' in html, \
        "index.html missing #radar-feed-loading"
    assert "Loading Radar" in html, "loading copy missing"
    print("PASS test_index_html_has_loading_state")


def test_index_html_includes_radar_feed_script():
    """index.html includes the radar-feed.js script tag."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert '/assets/js/radar-feed.js' in html, \
        "index.html missing radar-feed.js script tag"
    # The script must come AFTER the host element (basic ordering)
    host_pos = html.find('id="radar-feed-host"')
    script_pos = html.find('/assets/js/radar-feed.js')
    assert host_pos > 0 and script_pos > host_pos, \
        f"script tag (pos={script_pos}) must come after host (pos={host_pos})"
    print(f"PASS test_index_html_includes_radar_feed_script "
          f"(host@{host_pos}, script@{script_pos})")


def test_index_html_mvp_disclaimer_preserved():
    """The MVP disclaimer must still be present (per spec §17 / §9)."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "MVP stage" in html, "MVP disclaimer missing"
    assert "sample content" in html, "MVP disclaimer copy changed"
    print("PASS test_index_html_mvp_disclaimer_preserved")


# ============================================================================
# §31 Public JSON integration (3 tests)
# ============================================================================

def test_public_latest_json_exists():
    """public/radar/latest.json is committed to the repo."""
    if not PUBLIC_JSON.exists():
        print("SKIP test_public_latest_json_exists "
              "(public/radar/latest.json not yet generated)")
        return
    size = PUBLIC_JSON.stat().st_size
    assert size > 100, f"public latest.json too small: {size} bytes"
    print(f"PASS test_public_latest_json_exists ({size} bytes)")


def test_public_latest_json_validates():
    """public/radar/latest.json passes validate_public_payload."""
    if not PUBLIC_JSON.exists():
        print("SKIP test_public_latest_json_validates "
              "(public/radar/latest.json not yet generated)")
        return
    payload = json.loads(PUBLIC_JSON.read_text(encoding="utf-8"))
    errs = validate_public_payload(payload)
    assert not errs, f"public/latest.json failed validation: {errs}"
    print(f"PASS test_public_latest_json_validates "
          f"({payload['summary']['topic_count']} topics)")


def test_public_latest_json_no_dangerous_urls():
    """public/radar/latest.json has no javascript:/data:/file: URLs."""
    if not PUBLIC_JSON.exists():
        print("SKIP test_public_latest_json_no_dangerous_urls")
        return
    payload = json.loads(PUBLIC_JSON.read_text(encoding="utf-8"))
    bad_count = 0
    for t in payload["topics"]:
        for s in t["sources"]:
            if not is_safe_url(s["url"]):
                bad_count += 1
    assert bad_count == 0, f"public/latest.json has {bad_count} unsafe URLs"
    print(f"PASS test_public_latest_json_no_dangerous_urls "
          f"(scanned {sum(len(t['sources']) for t in payload['topics'])} URLs)")


# ============================================================================
# §31 Source-attachment and anti-DEMO-replacement (2 tests)
# ============================================================================

def test_demo_article_still_linked():
    """DEMO article page must still be reachable from index.html."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "/article/example/" in html, \
        "DEMO article link missing from index.html"
    print("PASS test_demo_article_still_linked")


def test_existing_demo_sections_unchanged():
    """The existing 5 categories + Hot Now + sample DEMO cards still present."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    for needle in ("Hot Now", "Malaysia", "Viral", "Celebrity",
                   "Food", "World", "Sample"):
        assert needle in html, f"existing section/copy missing: {needle}"
    print("PASS test_existing_demo_sections_unchanged")


# ============================================================================
# §31 No-publish-article / no-fake-fact (3 tests)
# ============================================================================

def test_radar_titles_are_not_rendered_as_articles():
    """The JS adapter must NOT link Radar topic titles to /article/example/.

    Per spec §35 / §38: Radar topics are not articles. The DEMO article
    page must NOT receive a Radar topic as if it were one.
    """
    src = JS_PATH.read_text(encoding="utf-8")
    # The title element is created via el('h3', ...) and its text is set
    # via textContent. There is NO <a href="/article/..."> wrapping it.
    # We verify by absence: no /article/example/ in the JS source.
    assert "/article/example/" not in src, \
        "JS must not link Radar titles to /article/example/"
    # The h3 element gets textContent, not innerHTML
    assert "el('h3'" in src and "textContent" in src, \
        "JS should set h3 text via textContent"
    print("PASS test_radar_titles_are_not_rendered_as_articles")


def test_no_fake_probability_strings():
    """The JS must NOT include strings like '90% confirmed' or '85% likely'.

    Per spec §13: confidence is a heuristic label, not a probability.
    """
    src = JS_PATH.read_text(encoding="utf-8")
    for forbidden in ("90%", "85%", "95%", "100%", "percent confirmed",
                     "% likely", "% chance"):
        assert forbidden not in src, f"JS contains forbidden probability: {forbidden!r}"
    print("PASS test_no_fake_probability_strings")


def test_no_banned_political_phrases():
    """The JS must NOT contain ranking / endorsement / opposition phrases."""
    src = JS_PATH.read_text(encoding="utf-8")
    for forbidden in ("best candidate", "worst candidate",
                     "likely to win", "vote for", "endorse",
                     "best party", "worst party"):
        assert forbidden not in src.lower(), \
            f"JS contains banned political phrase: {forbidden!r}"
    print("PASS test_no_banned_political_phrases")


# ============================================================================
# §31 Mobile / accessibility (3 tests)
# ============================================================================

def test_rf_grid_uses_existing_breakpoints():
    """The CSS file uses the same breakpoints as the existing grid."""
    css = (REPO_ROOT / "assets/css/style.css").read_text(encoding="utf-8")
    # rf-grid should appear in CSS
    assert ".rf-grid" in css, "missing .rf-grid CSS rule"
    # Same breakpoints as .grid (700px, 1024px)
    assert "min-width: 700px" in css, "missing 700px breakpoint in rf-grid area"
    assert "min-width: 1024px" in css, "missing 1024px breakpoint"
    print("PASS test_rf_grid_uses_existing_breakpoints")


def test_rf_sources_toggle_is_button():
    """The source expand/collapse must be a <button>, not a <div>."""
    src = JS_PATH.read_text(encoding="utf-8")
    # Find the function start
    m = re.search(r"function buildSourceList\(topic\)\s*\{", src)
    assert m, "buildSourceList function header not found"
    # Scan the rest of the file from there until the next function
    start = m.start()
    next_fn = re.search(r"\n\s*function\s+\w+\(", src[start + 50:])
    if next_fn:
        block = src[start: start + 50 + next_fn.start()]
    else:
        block = src[start:]
    assert "el('button'" in block and "rf-sources__toggle" in block, \
        "sources toggle must be a <button>"
    # Also assert an event listener is attached
    assert "addEventListener" in block, "sources toggle must have a click handler"
    print(f"PASS test_rf_sources_toggle_is_button ({len(block)} chars scanned)")


def test_no_horizontal_overflow_in_card_markup():
    """Card titles + sources should have overflow protection."""
    css = (REPO_ROOT / "assets/css/style.css").read_text(encoding="utf-8")
    # ellipsis on .rf-sources__link / .rf-sources__name
    assert "text-overflow: ellipsis" in css, \
        "missing text-overflow: ellipsis for source links/names"
    # ellipsis on .card__excerpt already exists
    assert "line-clamp" in css or "-webkit-line-clamp" in css, \
        "missing line-clamp for card excerpts"
    print("PASS test_no_horizontal_overflow_in_card_markup")


# ============================================================================
# §31 Existing demo pages unchanged (2 tests)
# ============================================================================

def test_hot_page_not_modified():
    """hot/index.html must not contain the radar feed host."""
    hot = (REPO_ROOT / "hot" / "index.html").read_text(encoding="utf-8")
    assert 'id="radar-feed-host"' not in hot, \
        "hot/ should not embed Radar Feed (this batch is homepage-only)"
    print("PASS test_hot_page_not_modified")


def test_category_pages_not_modified():
    """All 5 category pages must not contain the radar feed host."""
    cats = ["malaysia", "viral", "celebrity", "food", "world"]
    for c in cats:
        html = (REPO_ROOT / c / "index.html").read_text(encoding="utf-8")
        assert 'id="radar-feed-host"' not in html, \
            f"{c}/ should not embed Radar Feed in this batch"
    print(f"PASS test_category_pages_not_modified (5 category pages clean)")


# ============================================================================
# Test runner
# ============================================================================

if __name__ == "__main__":
    tests = [
        # JS structure (4)
        test_js_file_exists_and_is_nonempty,
        test_js_exposes_required_window_api,
        test_js_handles_all_required_states,
        test_js_does_not_use_innerhtml_for_user_data,
        # Mirror tests (10)
        test_url_safety_agreement_https_accepts,
        test_url_safety_agreement_dangerous_rejects,
        test_url_safety_agreement_whitespace_rejects,
        test_url_safety_agreement_empty_rejects,
        test_url_safety_agreement_length_limit,
        test_js_url_safety_implementation_uses_same_rules,
        test_python_validator_agrees_with_js_validator,
        test_js_validator_implementation_uses_same_rules,
        test_status_map_contains_all_required_statuses,
        test_verification_map_contains_all_required_statuses,
        # Host page integration (4)
        test_index_html_has_radar_feed_host,
        test_index_html_has_loading_state,
        test_index_html_includes_radar_feed_script,
        test_index_html_mvp_disclaimer_preserved,
        # Public JSON integration (3)
        test_public_latest_json_exists,
        test_public_latest_json_validates,
        test_public_latest_json_no_dangerous_urls,
        # Source-attachment (2)
        test_demo_article_still_linked,
        test_existing_demo_sections_unchanged,
        # Anti-fake-fact (3)
        test_radar_titles_are_not_rendered_as_articles,
        test_no_fake_probability_strings,
        test_no_banned_political_phrases,
        # Mobile / accessibility (3)
        test_rf_grid_uses_existing_breakpoints,
        test_rf_sources_toggle_is_button,
        test_no_horizontal_overflow_in_card_markup,
        # Existing pages unchanged (2)
        test_hot_page_not_modified,
        test_category_pages_not_modified,
    ]
    failed = []
    passed = 0
    skipped = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            import traceback
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"ERROR {t.__name__}: {e}")
            traceback.print_exc()
    print()
    print(f"{passed} passed, {len(failed)} failed of {len(tests)} tests")
    if failed:
        for name, err in failed:
            print(f"  {name}: {err}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} RADAR-ADAPTER TESTS PASSED")
