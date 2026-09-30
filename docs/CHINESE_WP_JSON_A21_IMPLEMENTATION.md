# CHINESE_WP_JSON_A21_IMPLEMENTATION

A2.1 — Chinese WP-JSON Source Adapter Implementation Report.

Status: **CHINESE_WP_JSON_A2_1 = PASS**

---

## 1. Scope

In scope (A2.1):

  - One new SourceAdapter: `WpJsonAdapter` (`radar/sources/wp_json.py`).
  - One new `SourceType` enum value: `SourceType.WP_JSON` (`radar/models.py`).
  - One new pipeline branch: `WP_JSON` → `WpJsonAdapter`
    (`radar/pipeline.py::_build_adapter`).
  - One new test file: `radar/tests/test_wp_json_adapter.py` (30 tests).
  - Two live-verified sources: Kwong Wah / Guang Ming (no production
    registration yet; consumed via `extra_sources` for tests).

Out of scope (deferred to A2.2 and later batches):

  - HTML listing adapter for Sin Chew / China Press / eNanyang.
  - Source registration in `REGISTERED_SOURCES`.
  - Adding probe fixtures to `radar/tests/fixtures_tier_b_review.py`.
  - Scheduler / Windows Task / production auto-update.
  - Modifying `radar/dedup.py` / `radar/normalize.py` /
    `radar/classification.py` / `radar/verification.py` /
    `radar/momentum.py` / `radar/thresholds.py`.

---

## 2. Exact Source Endpoints (live-verified)

| Source | URL | HTTP | Posts | Today |
|---|---|---|---|---|
| Kwong Wah / 光华日报 | https://www.kwongwah.com.my/wp-json/wp/v2/posts | 200 | 10 | 2026-09-30 |
| Guang Ming / 光明日报 | https://guangming.com.my/wp-json/wp/v2/posts | 200 | 10 | 2026-09-30 |

Live-verified at 2026-09-30 (Asia/Kuala_Lumpur). The endpoint
returns a top-level JSON array of post objects.

Each post contains at least:

  - `id` (int)
  - `date` (local ISO 8601, no tz marker)
  - `date_gmt` (UTC ISO 8601, no tz marker in practice — see §6)
  - `modified` / `modified_gmt`
  - `slug`
  - `link` (canonical permalink with URL-encoded Chinese slug)
  - `title.rendered` (HTML-encoded text)
  - `excerpt.rendered` (HTML — usually `<p>...</p>`)
  - `content.rendered` (rich HTML — may include `<figure>`, `<img>`)
  - `guid.rendered` (permalink form)
  - `status`, `type`, `link`, `author`, `featured_media`, …

Raw live-response samples saved to:
  `radar/tests/fixtures/wp_json/kwongwah_sample.json`
  `radar/tests/fixtures/wp_json/guangming_sample.json`

---

## 3. Fields Used

From the WP-JSON post object, `WpJsonAdapter._post_to_story`
consumes only:

| WP field | Adapter usage |
|---|---|
| `id` | `Story.id = "s_<sha1>"` (deterministic; matches RSSAdapter) |
| `title.rendered` | strip HTML → `Story.title` (≤ 300 chars) |
| `link` | `Story.url` |
| `date_gmt` | `Story.published_at` (with `Z` appended, see §6) |
| `date` | fallback if `date_gmt` missing |
| `excerpt.rendered` | strip HTML → `Story.summary` (≤ 1200 chars) |
| `content.rendered` | fallback if `excerpt.rendered` empty |

Not used: `modified`, `modified_gmt`, `slug`, `guid`, `status`,
`type`, `author`, `featured_media`. (These are audit-only /
metadata, not needed for the cluster pipeline.)

---

## 4. Normalization Mapping

| WP-JSON field | Story field | Adapter action |
|---|---|---|
| `title.rendered` | `title` | `_strip_html` (tag strip + entity unescape + whitespace collapse + space-before-punctuation strip) |
| `excerpt.rendered` | `summary` | `_strip_html`, then `.strip()`, then `[:1200]` |
| `content.rendered` | `summary` (fallback) | same as above |
| `link` | `url` | pass-through (URL-encoded slug preserved) |
| `date_gmt` | `published_at` | `_coerce_published_at` |
| `id` | `id` | `"s_" + sha1(prefix \| id \| url)` |
| (constant) | `source` | `Source.name` |
| (constant) | `source_type` | `SourceType.WP_JSON` |
| (constant) | `category` | passed to adapter |
| (constant) | `language` | `Language.ZH` (from source declaration) |
| (constant) | `country` | `Source.country` |
| (constant) | `discovered_at` | `_utcnow_iso()` (matches RSSAdapter) |

The HTML stripping uses an in-adapter entity table
(`_WP_ENTITIES`) covering `&amp;`, `&lt;`, `&gt;`, `&apos;`,
`&quot;`, `&nbsp;`, `&hellip;`, `&mdash;`, `&ndash;`,
`&ldquo;`, `&rdquo;`, `&lsquo;`, `&rsquo;`, `&laquo;`, `&raquo;`,
plus decimal / hex numeric entities (`&#NNN;`, `&#xHHHH;`).
`&hellip;` is rendered as the Unicode HORIZONTAL ELLIPSIS `…`
(U+2026), NOT three dots with spaces.

This intentionally does NOT use `normalize.unescape_html` because
its entity table is too narrow (only handles `amp|lt|gt|apos|quot|nbsp`).

---

## 5. Source Registry Entries

**NOT registered in `REGISTERED_SOURCES` for A2.1.**

Reason: the existing `test_tier_b_review.py` has hard-coded
invariant assertions:

```python
assert len(ALL_TIER_B_SOURCES) == len(REGISTERED_SOURCES) == 5
…
assert len(REGISTERED_SOURCES) == 5
```

These are Radar-6 contracts. Adding new sources requires updating
both the count assertions AND adding probe fixtures to
`radar/tests/fixtures_tier_b_review.py` for the new sources.
The latter would require running a multi-fetch probe sequence for
each source (3 fetches, 3 saved samples), which is exactly what
the Audit / Collector phase did — not what the Radar adapter
implementation phase should redo unilaterally.

Decision per strict file-scope rules:

  - `radar/sources_registry.py` NOT modified.
  - The two sources can be exercised via `extra_sources=` in
    `pipeline.run_scan()` (verified by
    `test_pipeline_run_scan_with_chinese_wp_json_sources`).
  - A follow-up batch (A2.3 or later) will register the sources
    and add the matching probe fixtures.

The 30 tests pass via the `extra_sources` path. The adapter is
production-ready; the registration step is a governance step that
should be bundled with proper probe data.

---

## 6. Critical Implementation Quirks Discovered & Fixed

### 6.1 `date_gmt` is timezone-naive in raw WP-JSON

WordPress emits `"date_gmt": "2026-09-30T08:34:23"` — a UTC ISO
8601 string WITHOUT a `Z` suffix or `+00:00`. Python's
`datetime.fromisoformat` parses it as a **naive** datetime.

When the cluster pipeline mixes this with aware datetimes (e.g.
`first_seen = datetime.now(timezone.utc)` from `_utcnow_iso`),
subtraction raises `TypeError: can't subtract offset-naive and
offset-aware datetimes`.

**Fix**: `WpJsonAdapter._coerce_published_at` appends `Z` to the
string when `date_gmt` was used. `2026-09-30T08:34:23` →
`2026-09-30T08:34:23Z`. The downstream parser now treats it as
timezone-aware UTC.

### 6.2 `str.rstrip(chars)` is a set operation, not a substring

Initial fix used `s.rstrip("Z").rstrip("+00:00")` to strip any
existing timezone marker before appending `Z`. Python's
`str.rstrip(chars)` treats its argument as a SET of characters,
not a substring. So `"2026-09-30T08:00:00".rstrip("+00:00")`
returns `"2026-09-30T08:"` (strips trailing `+`, `0`).

**Fix**: use `s.endswith("Z")` / `s.endswith("+00:00")` and
slice the fixed-length prefix instead. Documented in the source.

### 6.3 `&hellip;` rendering choice

`&hellip;` is U+2026 (HORIZONTAL ELLIPSIS). Rendering it as three
literal dots (`...`) is fine; rendering it as Unicode `…` is also
fine. We chose Unicode `…` for compactness and to match the
existing public-output truncation conventions. Tests assert this
explicitly.

---

## 7. Test Results

### 7.1 New A2.1 tests

`radar/tests/test_wp_json_adapter.py` — **30 / 30 PASS**:

| Group | Count | Result |
|---|---|---|
| Adapter contract (basic) | 5 | PASS |
| HTML cleaning | 4 | PASS |
| `published_at` coercion | 3 | PASS |
| Fail-closed (invalid input) | 4 | PASS |
| Dedup behavior (A1 alias compat) | 5 | PASS |
| Live-fixture round-trips | 2 | PASS |
| Real-fetch integration (pipeline) | 2 | PASS |
| Helpers (direct) | 5 | PASS |

### 7.2 Regression

| Suite | Pre-A2.1 | Post-A2.1 |
|---|---|---|
| `radar/tests/test_dedup_cjk` (A1) | 20 / 20 PASS | **20 / 20 PASS** |
| `radar/tests/test_dedup` | 5 / 5 PASS | **5 / 5 PASS** |
| `radar/tests/test_tier_b_review` | 22 / 22 PASS | **22 / 22 PASS** (sources_registry.py unchanged) |
| `radar/tests/test_stability` | 24 / 24 PASS | **24 / 24 PASS** |
| `radar/tests/test_failures` | 4 / 4 PASS | **4 / 4 PASS** |
| full Radar pytest (excluding stability/failures) | 385 / 385 PASS | **415 / 415 PASS** (385 + 30 new) |
| Performance | 42 / 42 PASS | **42 / 42 PASS** |

Total: **531 / 531 PASS**, 0 flaky added.

---

## 8. Live Verification (out-of-test sandbox)

Ran `WpJsonAdapter.fetch()` against the live endpoints from a
clean Python session:

  - Kwong Wah: 10 stories returned. First story title
    `'丹绒3中学安装75架电眼 林慧英冀"盯紧"校园安全'`,
    URL `https://www.kwongwah.com.my/20260930/<url-encoded-slug>/`,
    language `zh`, `published_at = 2026-09-30T08:55:58Z`.
  - Guang Ming: 10 stories returned. First story title
    `'北海天公坛首办 月老圣诞庆"圆缘"'`,
    URL `https://guangming.com.my/<url-encoded-slug>`,
    language `zh`, `published_at = 2026-09-30T08:50:36Z`.

Both responses are valid `application/json`; both are top-level
JSON arrays (NOT wrapped in `{posts: [...]}`); both contain all
required fields per §3.

---

## 9. Production Output Safety

  - `public/radar/latest.json` — UNCHANGED from HEAD
    (`git diff` empty; `git status` shows no `M public/radar/latest.json`).
  - Production URLs:
    - `https://myhotradar.com/` → 200
    - `https://myhotradar.com/public/radar/latest.json` → 200
  - No scheduler / Windows Task / cron was created or modified.
  - No production write happened (the live fetch in §8 was
    in-memory; no Stories were pushed to output).

---

## 10. Git

Commit (pending — see §11 for what will land):

  - `radar/models.py` — `+WP_JSON` enum value with comment.
  - `radar/pipeline.py` — `+WP_JSON` adapter branch.
  - `radar/sources/wp_json.py` — NEW adapter.
  - `radar/tests/test_wp_json_adapter.py` — NEW tests.
  - `radar/tests/fixtures/wp_json/` — NEW live-response fixtures.

NOT touched:

  - `radar/sources_registry.py`
  - `radar/dedup.py`, `radar/normalize.py`, `radar/thresholds.py`,
    `radar/verification.py`, `radar/classification.py`,
    `radar/momentum.py`
  - `radar/tests/fixtures_tier_b_review.py`
  - `radar/tests/test_tier_b_review.py`
  - `public/radar/latest.json`
  - `performance/`
  - `dashboard/` (Android Collector / HCB)
  - website / source configuration

---

## 11. Limitations & Follow-ups

1. **Not registered in `REGISTERED_SOURCES` yet.** Adapter is
   production-ready, but A2.3 must add the sources AND update
   `fixtures_tier_b_review.py` with matching probe data.
2. **`link` field carries URL-encoded Chinese slugs.** This is
   WordPress's standard behavior; the URLs are valid as-is and
   decode cleanly in browsers. The cluster pipeline compares
   canonical URL forms; encoding is preserved consistently.
3. **Chinese-specific HTML entities** not in `_WP_ENTITIES` are
   left as-is. Real-world WP-JSON responses have only used the
   15 entities currently mapped; if new entities appear in the
   wild, they will appear literally in the Story.title.
4. **`content.rendered` HTML stripping is conservative.** It
   collapses whitespace and strips tags but does NOT preserve
   paragraph boundaries. WordPress's excerpt.rendered is used
   preferentially; content.rendered is only a fallback.
5. **No retry/backoff in `_http_get`.** Adapter inherits the
   RSS adapter's `_http_get` (one attempt, 12 s timeout). A
   production deployment with intermittent WP-JSON 502/504
   should add retry — out of scope for A2.1.
6. **No CJK-specific URL canonicalization.** The existing
   `canonicalize_url` in `radar/dedup.py` is used unchanged.
   This works for the Chinese sources observed.

---

## 12. Final Verdict

CHINESE_WP_JSON_A2_1 = **PASS**

Adapter implemented. 30 new tests passing. No regressions. Live
endpoints verified. Production output untouched.

**STOP condition met.** Do NOT proceed to A2.2 / HTML adapter /
Sin Chew / China Press / eNanyang / scheduler in this batch.
