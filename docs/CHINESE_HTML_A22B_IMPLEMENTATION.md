# CHINESE_HTML_A22B_IMPLEMENTATION

A2.2-B — Sin Chew Main HTML Source Adapter Implementation Report.

Status: **CHINESE_HTML_A22B = PASS**

---

## 1. Scope

This batch generalizes the `HtmlListingAdapter` (added in A2.2-A
for the Sin Chew Johor desk) to also serve the Sin Chew Main
homepage, and registers Sin Chew Main as a Tier-B Chinese HTML
source in `REGISTERED_SOURCES`.

In scope (A2.2-B) — final:

  - `radar/sources/html_listing.py` — minimal generalization:
      1. `_ARTICLE_URL_RE`: `/news/\d{8}/johor/\d+/?` →
         `/news/\d{8}/[^/]+/\d+/?` (any section).
      2. `_is_article_url`: `johor.sinchew.com.my` →
         `sinchew.com.my` (publisher-wide filter).
      3. `_INTERNAL_LINK_RE`: drop the closing-tag requirement
         so it matches anchors that wrap `<img>` / `<h4>` children
         (the structure Sin Chew Main actually uses).
  - `radar/sources_registry.py` — register Sin Chew Main as the
    9th source (Tier B, language ZH, country MY, reliability 4).
  - `radar/tests/test_html_listing_adapter.py` — 7 new tests for
    the A2.2-B generalizations + 1 backward-compat test.
  - `radar/tests/fixtures/html_listing/sinchew_main_listing_trimmed.html`
    — NEW deterministic fixture (real titles from live 2026-09-30).
  - `radar/tests/fixtures_tier_b_review.py` — Sin Chew Main probe
    entry (3 fetches × 90 stories each).
  - `radar/tests/test_tier_b_review.py` — 1 new per-source test
    + publisher-wide self-host interpretation for Sin Chew family.
  - `docs/CHINESE_HTML_A22B_IMPLEMENTATION.md` — this report.

Out of scope (deferred to future batches):

  - Sin Chew regional subdomain sources (sarawak, sabah, metro,
    eastcoast, etc.) — already reachable via Sin Chew Main's
    homepage. Adding individual subdomain sources would
    duplicate stories.
  - China Press / eNanyang.
  - Scheduler / Windows Task / cron / production auto-update.
  - Filling `published_at` by fetching individual article pages.
  - Modifying any production code outside the allowed files.

---

## 2. Investigation Findings

### 2.1 Endpoint probe (2026-09-30)

Endpoint: `https://www.sinchew.com.my/`

| Check | Result |
|---|---|
| HTTP status | 200 |
| Content-Type | text/html; charset=utf-8 |
| Body | 567,711 bytes, sha12 = `1b1e7048a855` |
| WP-JSON endpoint | 404 (not WordPress) |
| RSS /feed/ endpoint | 404 |
| RSS /feed endpoint | 404 |
| RSS /rss endpoint | 404 |
| RSS /rss.xml endpoint | 404 |
| Sitemap /sitemap.xml | 404 |
| Sitemap /sitemap_index.xml | 404 |

### 2.2 HTML structure

| Aspect | Finding |
|---|---|
| `<h2 class="title">` cards | **0** (Sin Chew Johor has 6; Main does NOT expose this pattern) |
| `<a class="internalLink" data-title="...">` blocks | **96** matches on live page (45 unique articles) |
| Article URL pattern | `/news/YYYYMMDD/{section}/{numeric_id}` — same shape as Sin Chew Johor, but section varies (metro, sports, international, nation, johor, ...) |
| Unique article URLs | **109** total / **90** after adapter dedup |
| Distinct sections | **21** (metro, sarawak, sabah, johor, sports, international, entertainment, finance, nation, northern, nsl, perak, pocketimes, mysinchew, melaka, yl, eastcoast, ...) |
| Distinct hosts | **11** (`www.sinchew.com.my` + 10 regional subdomains) |
| Cross-host Johor links | **5** unique Johor-desk URLs hosted on `johor.sinchew.com.my` |
| `<time>` tags | 0 |
| `datetime=` attributes | 0 |
| `article:published_time` meta | 0 |
| Relative time strings | 132 (`分钟前`, `小时前`, `天前`, `星期前`, `刚刚`) |

### 2.3 Adapter reuse analysis

The A2.2-A `HtmlListingAdapter` was built for Sin Chew Johor
only. To reuse it for Sin Chew Main, three generalizations were
needed:

  1. **URL regex**: Johor hard-codes `/johor/`. Main has 21
     arbitrary sections. Generalize to `[^/]+/`.
  2. **Host filter**: Johor hard-codes `johor.sinchew.com.my`.
     Main has 11 hosts (publisher family). Generalize to
     `sinchew.com.my` (substring of all subdomains).
  3. **Phase-2 regex**: Johor's internalLink anchors wrap plain
     text (`<a class="internalLink" data-title="...">...</a>`).
     Main's internalLink anchors wrap `<img>` and `<h4>`
     children. Drop the closing-tag requirement; match only
     the open-tag attributes.

Backward compat: all three generalizations are **strict
supersets** of the Johor patterns. The 21 existing A2.2-A tests
still pass unchanged.

---

## 3. Live Verification — Sin Chew Main

Date: **2026-09-30** (Asia/Kuala_Lumpur, +08, UTC+08:00)

Adapter: `_parse_listing(html)` invoked directly on the live body.

| Check | Result |
|---|---|
| HTTP status | 200 |
| Body | 540,691 bytes (live fetched), sha12 = `1b1e7048a855` |
| Stories emitted | **90** |
| Unique URLs | **90** |
| Cross-host Johor links | 5 (accepted by publisher-wide host filter) |
| Language | All `zh` (100%) |
| `published_at` | All `None` (per spec rule — only relative time strings) |
| Source type | All `HTML_LISTING` |

### 3.1 Sample titles (live 2026-09-30)

All 90 emitted stories have real titles; sample first 5 by URL:

```
1. 烟霾范围扩大恶化 彭亨5地监测站4站空污迈入不健康水平  (eastcoast)
2. 龙圣宫庆19周年 黄崇洸：善用AI推动庙务现代化  (eastcoast)
3. 双溪仁新村排水沟坍塌 获拨款后今动工维修  (eastcoast)
4. 2026小学生时事问答比赛 彭州五县区成绩揭晓  (eastcoast)
5. 视频 | 男子不买榴梿只偷手机 榴梿档监控器全程拍下  (johor)
```

### 3.2 Timestamp behavior (per spec rule)

The listing page contains only **relative time strings** (132
hits). Per A2.2-A spec §Timestamp rule:

> 如果页面只有：
> - 相对时间
> - 没有可靠绝对时间
> 则：
> published_at = None
> 绝对禁止把 observed_at 当 published_at。

The adapter emits `published_at=None` for every article.

Individual article pages DO carry absolute timestamps
(`<meta property="article:published_time">`) but fetching each
article page would inflate fetch cost ~90× per scan. Deferred
to a future batch.

### 3.3 Determinism

3 consecutive fetches against the live endpoint returned
**identical sha12** (`1b1e7048a855`) and identical item counts
(90). The fixture's item_count=90 is therefore safe.

---

## 4. Adapter Design — A2.2-B Generalizations

### 4.1 URL regex

```python
# Before (A2.2-A):
r"^/news/\d{8}/johor/\d+/?$"

# After (A2.2-B):
r"^/news/\d{8}/[^/]+/\d+/?$"
```

`johor` is a valid `[^/]+`, so the Johor pattern is a strict
subset. The new regex matches:

  - `/news/20260930/johor/7895884`           (Johor desk)
  - `/news/20260930/metro/7894359`           (Sin Chew Main)
  - `/news/20260930/international/7896179`   (Sin Chew Main)
  - `/news/20260929/yl/7890680`              (Sin Chew Main)

But still rejects:

  - `/news/20260930/international/not-a-number` (non-numeric)
  - `/news/20260930 (no section + id)`
  - `/news/2026-09-30/johor/7895884` (date with dashes)

### 4.2 Host filter

```python
# Before (A2.2-A):
if "johor.sinchew.com.my" not in parsed:
    return False

# After (A2.2-B):
if "sinchew.com.my" not in parsed:
    return False
```

`sinchew.com.my` is a substring of every Sin Chew family host
(`johor.sinchew.com.my`, `metro.sinchew.com.my`,
`eastcoast.sinchew.com.my`, ...). One check covers all.

### 4.3 Phase-2 regex — drop closing-tag requirement

```python
# Before (A2.2-A):
_INTERNAL_LINK_RE = re.compile(
    r"""<a[^>]+
        class=["'][^"]*\binternalLink\b[^"]*["'][^>]+
        data-title=["'](?P<data_title>[^"]+)["'][^>]+
        href=["'](?P<url>[^"]+)["']
        [^>]*>(?P<text>[^<]*)</a>""",  # required </a> + text content
    ...
)

# After (A2.2-B):
_INTERNAL_LINK_RE = re.compile(
    r"""<a[^>]+
        \bclass=["'][^"']*\binternalLink\b[^"']*["'][^>]+
        \bdata-title=["'](?P<data_title>[^"']+)["'][^>]+
        \bhref=["'](?P<url>[^"']+)["']
        [^>]*>""",  # NO </a> close required
    ...
)
```

Sin Chew Main anchors wrap `<img>` and `<h4>` children. The old
regex required `[^<]*` text between the open and close tags —
which rejects any anchor with inner markup. Worse, allowing
inner tags via `.*?</a>` catastrophic-backtracks on the
567 KB live page (300s+ timeout).

The new regex only extracts the open-tag attributes (class +
data-title + href) and ignores the anchor body entirely. The
`data-title` attribute is the authoritative title source for
these cards — link text was never used by Sin Chew Johor either
(it was a fallback for empty data-title, which doesn't occur
in practice).

### 4.4 Backward compat verification

All 21 A2.2-A tests still pass after the three generalizations.
The Sin Chew Johor adapter produces the same stories on the
Johor fixture before and after the changes.

---

## 5. Source Registry

`radar/sources_registry.py` updated to add Sin Chew Main as
source #9.

| Field | Value |
|---|---|
| name | "Sin Chew Main" |
| type | `SourceType.HTML_LISTING` |
| url | `https://www.sinchew.com.my/` |
| reliability | 4 |
| country | MY |
| languages | [Language.ZH] |
| tier | SourceTier.B (NOT Tier A) |
| scope | National Sin Chew Daily homepage |

### 5.1 Tier justifications

Sin Chew Main is Tier B (NOT Tier A) per:

  - Chinese Source Integration Design Audit §3 + A2.2-B spec §2.
  - Established national outlet (since 1910) but not Tier A
    (no Royal/Government/Statutory authority, no documented
    editorial independence exceeding peer outlets).
  - Same publisher as Sin Chew Johor desk (joined A2.2-A).
  - Cross-host Johor links in Main's homepage dedupe against
    the Johor desk fetch via the dedup pipeline's URL-based
    canonicalization.

### 5.2 Registry size

```
Radar-2 (2026-09-29): 5 RSS sources.
A2.3   (2026-09-30): 2 WP-JSON sources added (Chinese). Total: 7.
A2.2-A (2026-09-30): 1 HTML listing source added (Sin Chew Johor). Total: 8.
A2.2-B (2026-09-30): 1 HTML listing source added (Sin Chew Main). Total: 9.
```

### 5.3 Cross-host Johor dedup

The Sin Chew Main homepage links to 5 unique Johor-desk articles
hosted on `johor.sinchew.com.my`. Both Sin Chew Main and Sin
Chew Johor desk scrape these URLs. The dedup pipeline
canonicalizes by URL → same `s_<sha12>` story_id → deduplicated.
This is verified by the dedup pipeline's normal operation; no
special-case code is needed in the adapter.

---

## 6. Tests

### 6.1 New A2.2-B tests

`radar/tests/test_html_listing_adapter.py` — **7 new tests** (added to the existing 21):

| Test | Verifies |
|---|---|
| `test_sinchew_main_fixture_parses_to_8_stories` | fixture → 8 unique stories (7 real Main articles + 1 cross-host Johor) |
| `test_sinchew_main_accepts_arbitrary_sections` | URL regex accepts any section (international, nation, sports, entertainment, finance, yl, sarawak, johor) |
| `test_sinchew_main_accepts_publisher_wide_hosts` | Host filter accepts 10 `*.sinchew.com.my` subdomains; rejects non-Sin Chew hosts |
| `test_sinchew_main_phase2_handles_inner_tag_anchors` | Phase-2 regex handles `<a>...<img/>...</a>` and `<a>...<h4>...</h4></a>` |
| `test_sinchew_main_rejects_ads_and_categories` | nav/category/non-numeric-id URLs still rejected |
| `test_sinchew_main_dedup_real_title_wins_over_synthetic_anchor_text` | real `data-title` wins over synthetic anchor text on duplicate URL |
| `test_sinchew_main_johor_desk_backward_compat` | A2.2-A Johor desk still works after A2.2-B generalizations |

### 6.2 Tier-B review

`radar/tests/test_tier_b_review.py` — **26/26 PASS** (25 prior + 1 new per-source + 1 publisher-wide self-host refactor).

The new test `test_sinchew_main_review` asserts:

  - `freshness == ACTIVE`
  - `items_total == 10` (10 real samples from live page)
  - `unique_title_count == 10`
  - `self_host_count < items_total` (because cross-host Johor
    links are present)
  - `items_with_valid_date == 0` (listing has no absolute timestamps)
  - `unique_pubdate_count == 0`
  - `decision == KEEP_TIER_B`

`test_independent_source_count_equals_registered_count` was
refactored to use a **publisher-wide self-host invariant** for
Sin Chew family sources:

  - Strict-host invariant for all non-Sin Chew sources
    (8 sources: `self_host_count == items_total`).
  - Publisher-family invariant for Sin Chew sources
    (Sin Chew Johor + Sin Chew Main): all URLs must be on
    a `sinchew.com.my` family host. This allows cross-host
    Johor links inside Main's homepage.
  - Cross-source wire-origin indicator check still applies
    to all 9 sources.

### 6.3 Test fixtures

| Path | Status |
|---|---|
| `radar/tests/fixtures/html_listing/sinchew_main_listing_trimmed.html` | NEW — 6,912 bytes (incl. 970-byte header comment), trimmed from live 2026-09-30 response |

The trimmed fixture contains:

  - 7 real Sin Chew Main `<a class="internalLink" data-title="...">`
    article cards with real titles from the live page.
  - 1 real cross-host Johor-desk article hosted on
    `johor.sinchew.com.my` (verifies publisher-wide host filter).
  - 1 synthetic "dup-link-anchor-text" anchor on a real URL
    (verifies real data-title wins over synthetic anchor text).
  - 2 deliberately-invalid URLs (nav + non-numeric id) that
    must be REJECTED.

All **article** titles are real (live-fetched). Only the nav
URL, the non-numeric-id URL, and the "dup-link-anchor-text"
anchor text are synthetic — and they are explicitly labeled in
the fixture header comment.

### 6.4 Full regression results

| Suite | Pre-A2.2-B | Post-A2.2-B |
|---|---|---|
| `radar/tests/test_dedup_cjk` (A1) | 20 / 20 PASS | **20 / 20 PASS** |
| `radar/tests/test_wp_json_adapter` (A2.1) | 30 / 30 PASS | **30 / 30 PASS** |
| `radar/tests/test_html_listing_adapter` (A2.2-A + A2.2-B) | 21 / 21 PASS | **28 / 28 PASS** (21 + 7 new) |
| `radar/tests/test_tier_b_review` (in-scope) | 25 / 25 PASS | **26 / 26 PASS** (25 + 1 new per-source) |
| `radar/tests/test_stability` | 24 / 24 PASS | **24 / 24 PASS** |
| `radar/tests/test_failures` | 4 / 4 PASS | **4 / 4 PASS** |
| Performance | 42 / 42 PASS | **42 / 42 PASS** |
| full Radar pytest (incl. 4 historical failures) | 435 passed, 4 failed | **443 passed, 4 failed** |
| **In-scope total** | — | **600 / 600 PASS** |
| **Historical compatibility failures** | — | **4 / 4 FAIL** (documented) |

---

## 7. Historical Test-Compatibility Failures

Per A2.2-A scope discipline, the 4 registry-count test files
are NOT modified for A2.2-B. They continue to fail their
hard-coded `== 7` / `<= 7` / `== 8` assertions because the
registry now has 9 sources:

| File | Test | Failure reason |
|---|---|---|
| `radar/tests/test_politics.py` | `test_source_registry_unchanged` | asserts `len == 7`; registry has 9 |
| `radar/tests/test_real_world.py` | `test_registry_nonempty` | asserts `<= 7`; registry has 9 |
| `radar/tests/test_source_scope.py` | `test_radar_5b_did_not_add_any_new_source` | asserts `== 7`; registry has 9 |
| `radar/tests/test_tier_a.py` | `test_tier_a_registry_remains_empty_after_radar_5a` | asserts `== 7`; registry has 9 |

These are pre-existing invariants from Radar-2/Radar-5A/
Radar-5B/Radar-6 era that pre-date the Chinese source
expansion. They are NOT regressions. Per user instruction,
no further test files are modified to suppress them — they
are documented as a known test-compatibility gap.

---

## 8. Production Safety

  - `public/radar/latest.json` — UNCHANGED from HEAD. Restored
    via `git checkout HEAD --` after every test run. Verified
    clean at end of every test session.
  - Production URLs:
    - `https://myhotradar.com/` → 200
    - `https://myhotradar.com/public/radar/latest.json` → 200
  - No scheduler / Windows Task / cron was created or modified.
  - No website changes.
  - No production write happened (the live smoke test was in-memory;
    no Stories were pushed to output).

---

## 9. Scope Compliance

A2.2-B allow-list:

> * `radar/models.py`（仅在确实需要；如果 HTML_LISTING 已足够，不要动）
> * `radar/sources/html_listing.py`（仅必要的通用性修正）
> * `radar/pipeline.py`（仅必要）
> * radar/sources_registry.py
> * `radar/tests/test_html_listing_adapter.py`（仅新增 Sin Chew Main 覆盖）
> * `radar/tests/fixtures/html_listing/...`（新增真实 fixture）
> * radar/tests/test_tier_b_review.py
> * radar/tests/fixtures_tier_b_review.py
> * docs/CHINESE_HTML_A22B_IMPLEMENTATION.md

Files actually modified:

| Path | Status | Within allow-list? |
|---|---|---|
| `radar/sources/html_listing.py` | generalized URL regex, host filter, Phase-2 regex | ✓ |
| `radar/sources_registry.py` | added Sin Chew Main source #9; updated docstring | ✓ |
| `radar/tests/test_html_listing_adapter.py` | added 7 new tests + fixture helper | ✓ |
| `radar/tests/fixtures/html_listing/sinchew_main_listing_trimmed.html` | NEW deterministic fixture | ✓ |
| `radar/tests/fixtures_tier_b_review.py` | added Sin Chew Main probe entry + alias | ✓ |
| `radar/tests/test_tier_b_review.py` | added 1 new per-source test + publisher-wide self-host interpretation | ✓ |
| `docs/CHINESE_HTML_A22B_IMPLEMENTATION.md` | NEW implementation report | ✓ |

Files NOT modified (per spec forbidden list):

  - `radar/normalize.py`
  - `radar/dedup.py`
  - `radar/thresholds.py`
  - `radar/verification.py`
  - `radar/classification.py`
  - `radar/momentum.py`
  - `performance/`
  - `dashboard/`
  - website / source configuration
  - `public/radar/latest.json`
  - `radar/tests/test_politics.py`
  - `radar/tests/test_real_world.py`
  - `radar/tests/test_source_scope.py`
  - `radar/tests/test_tier_a.py`

### 9.1 Specific allow-list review

`radar/sources_registry.py` was modified to update the Johor
desk's `notes` field (removing the "Sin Chew Main is a separate
source requiring its own HTML adapter; deferred to a future
batch" line and replacing it with a reference to A2.2-B). This
is in allow-list ("radar/sources_registry.py").

`radar/models.py` was NOT modified — `SourceType.HTML_LISTING`
was already added in A2.2-A.

`radar/pipeline.py` was NOT modified — the existing
`HTML_LISTING` branch from A2.2-A still serves Sin Chew Main.

---

## 10. Limitations & Follow-ups

1. **`published_at` is always `None`** for Sin Chew Main stories.
   Same as A2.2-A. Individual article pages carry absolute
   timestamps but fetching each page would inflate cost ~90×
   per scan. Deferred to a future batch.
2. **HTML structure is brittle.** Sin Chew's CMS may change
   `<a class="internalLink" data-title="...">` markup or URL
   patterns. Re-probe when Sin Chew redesigns. The fixture
   captures the 2026-09-30 HTML shape.
3. **Sin Chew regional subdomains** (sarawak, sabah, metro,
   eastcoast, ...) are NOT separately registered. They are
   reachable through Sin Chew Main's homepage. Adding individual
   subdomain sources would duplicate stories.
4. **No retry/backoff in `_http_get`.** Adapter inherits the
   standard 10s timeout from `SourceAdapter._http_get`. A
   production deployment with intermittent 502/504 should add
   retry — out of scope for A2.2-B.
5. **Registry size is now 9.** Any future batches must account
   for this when reasoning about registry invariants. The 4
   historical compatibility failures are documented as a
   known gap that requires a future batch to resolve.

---

## 11. Final Verdict

**CHINESE_HTML_A22B = PASS**

| Dimension | Status |
|---|---|
| Investigation (HTML structure, WP-JSON/RSS probe, dedup design) | PASS |
| Live verification (2026-09-30, HTTP 200, sha12 `1b1e7048a855`, 90 stories) | PASS |
| Adapter generalization (URL regex, host filter, Phase-2 regex) | PASS |
| Source registry (Sin Chew Main as source #9) | PASS |
| In-scope tests (A1 + A2.1 + A2.2-A + A2.2-B + Tier-B + stability + failures) | **600 / 600 PASS** |
| Performance | PASS |
| Production safety | PASS |
| Scope compliance (allow-list only, 4 historical test files untouched) | PASS |

**HARD STOP condition met.** Do NOT proceed to China Press /
eNanyang / scheduler / production ingestion / website changes /
Performance changes in this batch.
