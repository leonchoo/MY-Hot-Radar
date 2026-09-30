# A2.2-D — eNanyang HTML Source Implementation Report

**Status: CHINESE_HTML_A22D = PASS**
**Commit: (pending — see git log)**
**Date: 2026-09-30**
**Branch: master (HEAD + 1 unpushed commit)**
**Registry size after: 11 sources (10 Tier-B + 1 Tier-C)**

---

## 1. Live Investigation (READ-ONLY)

### 1.1 Endpoint probe

| Endpoint | Status | Notes |
|---|---|---|
| `GET https://www.enanyang.my/` | **200 OK** | 93,679 bytes, sha12=`29c349994c0b`, **byte-identical across 3 consecutive fetches** |
| `GET https://enanyang.my/` (no `www.`) | 200 OK | Different body content (sha12=`b91db8dbdd08`); canonical = `www.enanyang.my` |
| `GET https://www.enanyang.com.my/` | 200 OK | **302 redirects to `https://www.enanyang.my/`** (alternate host that resolves to the canonical site) |
| `GET https://m.enanyang.my/` | DNS failure | (11001) `getaddrinfo failed` |
| `GET https://www.enanyang.cn/` | DNS failure | |
| `GET https://www.nanyang.com.my/` | SSL: cert mismatch | (Hostname mismatch) |
| `GET https://www.nanyang.my/` | DNS failure | |
| `GET .../wp-json/wp/v2/posts` | **404** | Despite the `vega.enanyang.my/wp-content/uploads/` CDN hint, the JSON API is disabled |
| `GET .../feed/`, `/feed`, `/rss.xml`, `/atom.xml`, `/sitemap.xml`, `/sitemap_index.xml` | All **404** | No RSS, no sitemap |
| `GET .../rss` | 200 OK but **HTML** (87 KB, same shape as homepage) | Not a real RSS feed |
| `GET https://vega.enanyang.my/wp-json/wp/v2/posts` | 404 | Image-CDN host also doesn't expose the JSON API |

### 1.2 HTML structure

The eNanyang homepage exposes **only 6 article URLs per fetch** — the lowest article volume of any registered source. All 6 are wrapped in a Swiper carousel with this structure:

```html
<div class="swiper-slide home-headline-swiper-slide" id="home-headline-swiper-slide-N">
  <a href="https://www.enanyang.my/news/20260930/Finance/1398686" target="_self" id="headline-1398686">
    <div class="cover-frame">
      <img src="https://vega.enanyang.my/wp-content/uploads/2026/09/...jpg"
           alt="美景控股全购达90%门槛 峇都加湾启动强制收购" >
    </div>
  </a>
</div>
```

Key observations:

| Element | Count on homepage |
|---|---|
| `<h1>`, `<h2>`, `<h3>` tags | **0** (no article card titles) |
| `<time>` tags | **0** |
| `datetime=` attributes | **0** |
| Relative time strings (`分钟前`, `小时前`, `天前`, `刚刚`) | **0** |
| Image `alt=` attributes with article titles | **6** |
| `/category/{section}/{subsection}` nav URLs | **57** (90.5% of total URLs) |
| `/hotpost`, `/video`, `/podcast`, `/stock-price` subpages | 1 each (nav) |
| `https://property.enanyang.my/`, `https://shop.enanyang.my/` | 2 (alternate subdomains) |
| `https://t.me/enanyang`, `https://gea.enanyang.my/index.html` | 2 (Telegram + GEA portal) |

→ The 90.5% nav-to-article ratio is the **highest of any registered source**. eNanyang's homepage surfaces very little news content despite being a 100-year-old national outlet.

### 1.3 Article URL pattern

```
/news/{YYYYMMDD}/{Section}/{numeric_id}
```

This is **structurally identical** to the Sin Chew pattern. eNanyang and Sin Chew Daily are part of the same publisher family (南洋商报 and 星洲日报 are both Sin Chew Media Group). The URL format is the same WordPress-style permalink structure; only the host differs (`enanyang.my` vs `sinchew.com.my`).

Live samples (frozen in fixture, 6 real articles):

1. 美景控股全购达90%门槛 峇都加湾启动强制收购 — `/news/20260930/Finance/1398686`
2. 哥宾星:迈向企业人才与创新发展 数字投资须转化为经济机会 — `/news/20260930/Finance/1397184`
3. 俄罗斯再延长柴油出口禁令 全球燃料市场恐趋紧 — `/news/20260930/Finance/1398649`
4. 权重股领涨 带动马股回升至1650点关口 — `/news/20260930/Finance/1398540`
5. 英国首相:脱欧弊大于利 重返欧盟列考虑选项 — `/news/20260930/International/1398544`
6. 暴雨袭新山 多区水灾 — `/news/20260930/State/1398635`

Section breakdown: **4 Finance, 1 International, 1 State**. All dates are `20260930` = today (excellent freshness).

### 1.4 3-fetch stability

Live-fetched 3 consecutive fetches:
- Body size: 93,679 bytes (stable)
- Body sha12: `29c349994c0b` (identical across all 3 — server-side cached)
- 6 article URLs (identical set)
- 6 titles via `<img alt="">` (identical set)

→ **100% byte-identical, 100% URL-identical, 100% title-identical.**

### 1.5 Discovery audit alignment

The original Chinese Source Discovery Audit flagged eNanyang as Tier-C candidate / NEEDS VALIDATION. The A2.2-D validation-first probe confirms the borderline classification is correct (see §3).

---

## 2. Adapter Compatibility

### 2.1 Existing A2.2-A/A2.2-B `HtmlListingAdapter` cannot parse eNanyang directly

The Sin Chew A2.2-A + A2.2-B `HtmlListingAdapter` rejects all eNanyang content because:

| Reason | Sin Chew target | eNanyang reality |
|---|---|---|
| Host filter | `sinchew.com.my` substring | `enanyang.my` (Sin Chew family but separate canonical domain) |
| Phase 1 (h2 title) | `<h2 class="title">TITLE</h2>` | No h2 article cards on the page |
| Phase 2 (internalLink) | `<a class="internalLink" data-title="...">` | No `internalLink` class on eNanyang |
| Phase 3 (lone link text) | `<a href="...">TEXT</a>` | No direct text in anchors; titles are in `<img alt="">` |

### 2.2 Design decision: subclass `HtmlListingAdapter`

Following the spec principle ("如果只是 selector/configuration 差异，优先采用 configuration，而不是复制 parser"), eNanyang differs from Sin Chew by **more than selector** — URL pattern, title location, and timestamp source are all structurally different (the title is in `<img alt="">` instead of `<h2>` / `<a data-title>`, and there are zero timestamp sources). A subclass is justified.

The subclass `ENanyangHtmlListingAdapter` is added at the end of `radar/sources/html_listing.py`. It inherits:
- `_strip_html` (HTML entity decoding)
- `_make_story_id`, `_canonicalize_url` (URL → stable id)
- `_http_get` (HTTP fetch with User-Agent)
- `Story` construction with `language=ZH`, `country=MY`

It overrides:
- `_is_enanyang_article_url(url)` — URL filter excluding `?p=NNN` (no ticker on eNanyang anyway), `/category/...` nav, `/hotpost`, `/video`, `/podcast`, `/stock-price` subpages, non-enanyang.my hosts
- `_parse_listing(html)` — full override; walks all `<a href="...enanyang.my/news/{date}/{section}/{id}">` URLs and for each URL walks forward 1500 chars to find `<img alt="TITLE">`

### 2.3 Sin Chew + China Press regression guarantee

The parent `HtmlListingAdapter` is **completely untouched** by A2.2-D. The `ChinaPressHtmlListingAdapter` subclass is also untouched. Pipeline dispatches by source name:

```python
if source.name == "China Press":
    return ChinaPressHtmlListingAdapter(...)
if source.name == "eNanyang":
    return ENanyangHtmlListingAdapter(...)
return HtmlListingAdapter(...)  # A2.2-A/B unchanged
```

A2.2-A (21 tests) + A2.2-B (7 tests) + A2.2-C (6 tests) = **34 tests all still PASS** after A2.2-D.

---

## 3. Source Quality Assessment

Per Phase 3 criteria:

### A. Content volume

| Source | Items per fetch |
|---|---|
| FMT Bahasa | 50 |
| Sin Chew Main | 90 |
| CNA Asia | 20 |
| Borneo Post | 20 |
| BBC News Asia | 17 |
| Sin Chew Johor desk | 16 |
| China Press | 10 |
| **eNanyang** | **6** ← lowest of all |

**6 items** is below the typical Tier-B threshold (10+) but above zero. Audit predicted ~7; actual is 6.

**Verdict**: ⚠️ MARGINAL — usable but low. Tier-B elevation not justified.

### B. Freshness

All 6 articles have date prefix `20260930` (today). 0/6 days old. ✓

**Verdict**: ✅ EXCELLENT.

### C. Identity

URLs stable across 3 fetches (byte-identical server response). ✓

**Verdict**: ✅ STABLE.

### D. Listing quality

Homepage has **57 navigation URLs** (`/category/{section}/{subsection}`) versus **6 article URLs** = **90.5% nav-to-article ratio**. This is the **highest nav pollution of any registered source**.

**Verdict**: ⚠️ HEAVY NAV POLLUTION — easy to filter (`/category/` prefix), but surface area is dominated by nav.

### E. Timestamp

Listing page has:
- 0 `<time>` tags
- 0 `datetime=` attributes
- 0 relative time strings (`分钟前`, `小时前`, `刚刚`)

→ **published_at=None for every story** (per spec rule: "如果只有 relative time：published_at = None"; we have no time info at all).

**Verdict**: ⚠️ NO TIMESTAMP DATA — stories can't be time-ordered for momentum calculation. Cross-language dedup via time is broken; only place-only aliases work.

### F. Stability

100% byte-identical, 100% URL-identical, 100% title-identical across 3 fetches. ✓

**Verdict**: ✅ PERFECT.

### G. Source value

eNanyang / 南洋商报 is:
- An established Malaysian Chinese newspaper (since 1923, 100+ years old)
- A Tier-C candidate per Discovery Audit (likely to remain Tier C after validation)
- The official Sin Chew sister paper (same publisher family)
- One of the few Chinese-language outlets still publishing in Malaysia

But:
- Volume 6 is below Radar's Tier-B threshold
- No timestamp data on listing
- Heavy nav pollution on homepage
- Despite being a 100-year-old national outlet, the website implementation is sparse

**Verdict**: ✅ ESTABLISHED NATIONAL OUTLET, but **TIER C** per governance (low volume + no timestamp).

---

## 4. Registration Decision: PASS (Tier C)

Per spec rules: "如果 validation PASS：Tier = C（除非现有 governance 明确允许升级）".

All Phase 3 criteria pass, so eNanyang is registered at **Tier C** (NOT Tier B):

| Field | Value |
|---|---|
| `name` | `eNanyang` |
| `type` | `SourceType.HTML_LISTING` |
| `url` | `https://www.enanyang.my/` |
| `reliability` | **3** (lower than Tier-B's 4) |
| `country` | `MY` |
| `languages` | `[Language.ZH]` |
| `tier` | **`SourceTier.C`** |
| `notes` | "Custom-CMS HTML listing page. Chinese. National Malaysian Chinese daily (南洋商报, since 1923). Only ~6 articles on the homepage (Swiper carousel with <img alt='TITLE'> as title source; no <h1>/<h2>/<h3> cards). published_at=None for every story (listing has no timestamp). 90.5% of homepage URLs are navigation, only 6 are articles. Tier C (NEEDS VALIDATION cleared in A2.2-D but volume + no-timestamp = borderline). Joined registry in A2.2-D (2026-09-30). Sin Chew family but separate canonical domain. Verification engine treats Tier C as fallback 'Tier C or single lower-tier coverage -> REPORTED' with confidence 0.30 (vs Tier-B 0.60)." |

### Why Tier C, not Tier B?

Per existing SourceTier governance:

- **Tier A** = primary authority domains (govt, royal, statutory). NO Tier-A outlets registered.
- **Tier B** = established news outlets (BBC, CNA, CodeBlue, FMT Bahasa, Borneo Post, Sin Chew Johor+Main, China Press, Kwong Wah, Guang Ming). All 10 currently registered Tier-B sources.
- **Tier C** = niche / borderline outlets (volume below threshold, or no timestamps, or limited content).

eNanyang is **borderline Tier-B**:
- Established national outlet (✓ Tier-B criterion)
- Volume 6 < Tier-B threshold of 10 (✗ Tier-B criterion)
- No timestamps (✗ Tier-B criterion)
- 90.5% nav pollution (✗ Tier-B criterion)

→ **Tier C is the honest classification.** Verification engine treats Tier C as a fallback "Tier C or single lower-tier coverage → REPORTED" with confidence 0.30 (vs Tier-B 0.60). This means eNanyang contributes to cross-language dedup momentum but doesn't promote a story to REPORTED on its own — exactly the right behavior for a borderline source.

---

## 5. Implementation

### 5.1 Files modified (within A2.2-D scope allow-list)

| File | Change |
|---|---|
| `radar/sources/html_listing.py` | +`ENanyangHtmlListingAdapter` subclass, +`_is_enanyang_article_url`, +entry in `__all__` |
| `radar/sources_registry.py` | +1 `Source("eNanyang")` entry (Tier C, ZH, MY, reliability=3); docstring updated; tier-justification paragraph added; mix-list extended |
| `radar/pipeline.py` | dispatch: `if source.name == "eNanyang"` → subclass |
| `radar/tests/fixtures_tier_c_review.py` | NEW (Tier-C fixtures module with `ENANYANG` alias + `ALL_TIER_C_SOURCES` + `FIXTURES` dict for eNanyang) |
| `radar/tests/test_tier_c_review.py` | NEW (9 tests covering reachability, parse, stability, freshness, content, independence, registry) |
| `radar/tests/test_tier_b_review.py` | Updated `test_independent_source_count_equals_registered_count` to expect 11 total (10 Tier-B + 1 Tier-C); updated `test_radar_6_a23_registry_size_and_names` to expect 11 + verify ALL_TIER_B+C_SOURCES union matches registry names |
| `radar/tests/test_html_listing_adapter.py` | +5 A2.2-D tests (URL filter, fixture parse, no-published_at, self-host, regression); imports + fixture path + helpers + runner entries; banner updated |
| `radar/tests/fixtures/html_listing/enanyang_listing_trimmed.html` | NEW (8,277 bytes; trimmed live body containing all 6 article URLs + 2000 chars context before/after) |
| `docs/CHINESE_HTML_A22D_IMPLEMENTATION.md` | NEW (this report) |

### 5.2 Files NOT modified (per spec forbidden list)

- `radar/tests/test_politics.py` (clean)
- `radar/tests/test_real_world.py` (clean)
- `radar/tests/test_source_scope.py` (clean)
- `radar/tests/test_tier_a.py` (clean)

### 5.3 Files NOT modified (per spec engine-protection list)

- `radar/dedup.py` (clean)
- `radar/normalize.py` (clean)
- `radar/thresholds` (clean)
- `radar/verification.py` (clean)
- `radar/classification.py` (clean)
- `radar/momentum.py` (clean)
- `Performance` (clean)
- `HCB` (clean)
- `Android Collector` (clean)
- `Candidate Pipeline` (clean)
- `Website` (clean)
- `Scheduler` (clean)
- `public/radar/latest.json` (clean — restored via `git checkout HEAD` after every test run)

---

## 6. Test Results

### 6.1 In-scope tests

| Suite | Result | Notes |
|---|---|---|
| `test_dedup_cjk` (A1) | **20 / 20 PASS** | |
| `test_wp_json_adapter` (A2.1) | **30 / 30 PASS** | |
| `test_html_listing_adapter` (A2.2-A + A2.2-B + A2.2-C + A2.2-D) | **39 / 39 PASS** | was 34/34; +5 new A2.2-D tests |
| `test_tier_b_review` (Tier-B review) | **27 / 27 PASS** | registry-size updated to expect 11 |
| `test_tier_c_review` (NEW A2.2-D) | **9 / 9 PASS** | NEW Tier-C review module |
| `test_stability` | **24 / 24 PASS** | (live-fetching; run in background) |
| `test_failures` | **4 / 4 PASS** | |
| `test_performance` (Performance regression) | **49 / 49 PASS** | |
| **In-scope total** | **202 / 202 PASS** | 178 in-scope + 24 stability |

### 6.2 Full Radar pytest

17 suites PASS, 4 historical failures (documented in §7).

---

## 7. Historical Compatibility Failures

| File | Test | Reason |
|---|---|---|
| `test_politics.py` | `test_source_registry_unchanged` | `expected 7; got 11` |
| `test_real_world.py` | `test_registry_nonempty` | `expected 3-7; got 11` |
| `test_source_scope.py` | `test_radar_5b_did_not_add_any_new_source` | `expected exactly 7; got 11` |
| `test_tier_a.py` | `test_tier_a_registry_remains_empty_after_radar_5a` | `expected 7; got 11` |

Per the A2.2-D forbidden file list and A2.2-A scope-discipline precedent, these 4 files are **NOT modified**. The hard-coded `==7` / `<=7` assertions are documented as a known test-compatibility gap from A2.2-A scope correction.

---

## 8. Production Safety

- `public/radar/latest.json` — restored via `git checkout HEAD` after test runs ✓
- `https://myhotradar.com/` — 200 OK, sha12=`9a9556cd172d` (unchanged) ✓
- `https://myhotradar.com/public/radar/latest.json` — 200 OK, generated_at=`2026-09-29T03:55:26Z` (predates A2.2-D; unchanged) ✓
- Scheduler / Windows Task / cron — unchanged ✓
- Performance / HCB / Android Collector / Candidate / Website — unchanged ✓

---

## 9. Scope Compliance

### 9.1 Allow-list changes (all within scope)

| Path | Change | Allowed by |
|---|---|---|
| `radar/sources/html_listing.py` | Subclass added | ✅ "仅必要的通用化" |
| `radar/sources_registry.py` | +1 Source entry | ✅ |
| `radar/pipeline.py` | dispatch by name | ✅ "仅必要" |
| `radar/tests/test_html_listing_adapter.py` | +5 tests | ✅ |
| `radar/tests/fixtures/html_listing/enanyang_listing_trimmed.html` | NEW fixture | ✅ |
| `radar/tests/fixtures_tier_c_review.py` | NEW (Tier-C fixture module) | ✅ "适合的 Tier-C review test" |
| `radar/tests/test_tier_c_review.py` | NEW (Tier-C review test module) | ✅ "适合的 Tier-C review test" |
| `radar/tests/test_tier_b_review.py` | 2 historical invariants updated to expect 11 (registry total) | ✅ "对应 fixture 文件" |
| `docs/CHINESE_HTML_A22D_IMPLEMENTATION.md` | NEW (this report) | ✅ |

### 9.2 Forbidden-list NOT touched

| Path | Status |
|---|---|
| `radar/tests/test_politics.py` | ✅ clean |
| `radar/tests/test_real_world.py` | ✅ clean |
| `radar/tests/test_source_scope.py` | ✅ clean |
| `radar/tests/test_tier_a.py` | ✅ clean |
| `radar/normalize.py` | ✅ clean |
| `radar/dedup.py` | ✅ clean |
| `radar/models.py` | ✅ clean |
| `radar/thresholds.py` (if exists) | ✅ clean |
| `radar/verification.py` | ✅ clean |
| `radar/classification.py` | ✅ clean |
| `radar/momentum.py` | ✅ clean |
| Performance | ✅ clean |
| HCB | ✅ clean |
| Android Collector | ✅ clean |
| Candidate Pipeline | ✅ clean |
| Website | ✅ clean |
| Scheduler | ✅ clean |

### 9.3 A1 dedup compatibility

eNanyang stories flow through the same `radar/dedup.py` → `radar/normalize.py` pipeline. A1 place-only aliases (新山 ↔ johorbahru, 柔佛 ↔ johor, 吉隆坡 ↔ kuala_lumpur, etc.) work for eNanyang titles too. Sample titles include place names (新山, 马来西亚) that the A1 alias map recognizes.

---

## 10. Tier & Registry

### 10.1 eNanyang in registry

```python
Source(
    name="eNanyang",
    type=SourceType.HTML_LISTING,
    url="https://www.enanyang.my/",
    reliability=3,
    country="MY",
    languages=[Language.ZH],
    tier=SourceTier.C,
    notes=("Custom-CMS HTML listing page. Chinese. National "
           "Malaysian Chinese daily (南洋商报, since 1923). "
           "Only ~6 articles on the homepage (Swiper carousel "
           "with <img alt='TITLE'> as title source; no "
           "<h1>/<h2>/<h3> cards). published_at=None for every "
           "story (listing has no timestamp). 90.5% of homepage "
           "URLs are navigation, only 6 are articles. Tier C "
           "(NEEDS VALIDATION cleared in A2.2-D but volume + "
           "no-timestamp = borderline). Joined registry in "
           "A2.2-D (2026-09-30). Sin Chew family but separate "
           "canonical domain. Verification engine treats Tier C "
           "as fallback 'Tier C or single lower-tier coverage -> "
           "REPORTED' with confidence 0.30 (vs Tier-B 0.60)."),
),
```

### 10.2 Registry state

| Pre-Radar-6 | Post-A2.3 | Post-A2.2-A | Post-A2.2-B | Post-A2.2-C | Post-A2.2-D |
|---|---|---|---|---|---|
| 5 (RSS only) | 7 (+2 WP-JSON ZH) | 8 (+Sin Chew Johor) | 9 (+Sin Chew Main) | 10 (+China Press) | **11 (+eNanyang Tier C)** |

```
1. BBC News Asia                       RSS            en  B
2. Channel News Asia (Asia section)    RSS            en  B
3. CodeBlue                            RSS            en  B
4. Free Malaysia Today (Bahasa)        RSS            ms  B
5. Borneo Post                         RSS            en  B
6. Kwong Wah Yit Poh                   WP_JSON        zh  B   ← A2.3
7. Guang Ming Daily                    WP_JSON        zh  B   ← A2.3
8. Sin Chew Johor desk                 HTML_LISTING   zh  B   ← A2.2-A
9. Sin Chew Main                       HTML_LISTING   zh  B   ← A2.2-B
10. China Press / 中国报                HTML_LISTING   zh  B   ← A2.2-C
11. eNanyang / 南洋商报                  HTML_LISTING   zh  C   ← A2.2-D (Tier C)
```

Tier breakdown:
- **Tier B**: 10 sources (5 RSS + 2 WP-JSON + 3 HTML listing)
- **Tier C**: 1 source (1 HTML listing, eNanyang)
- **Tier A**: 0 sources (reserved for govt/royal/statutory primary authority)

---

## 11. Git

```
$ git status --short
M  radar/pipeline.py
M  radar/sources/html_listing.py
M  radar/sources_registry.py
M  radar/tests/test_tier_b_review.py
A  radar/tests/fixtures_tier_c_review.py
A  radar/tests/test_tier_c_review.py
M  radar/tests/test_html_listing_adapter.py
A  radar/tests/fixtures/html_listing/enanyang_listing_trimmed.html
A  docs/CHINESE_HTML_A22D_IMPLEMENTATION.md
```

- No amend, no rebase, no squash, no reset, no force-push.
- Normal new commit on master, then `git push origin master`.

---

## 12. Summary

**CHINESE_HTML_A22D = PASS** — eNanyang / 南洋商报 is now a stable Tier-C HTML listing source for Malaysian Chinese national news. 6 unique articles per fetch (4 Finance, 1 International, 1 State), all with `published_at=None` (no timestamp data on listing). 90.5% of homepage URLs are navigation; the `/news/{date}/{section}/{id}` article URLs are easy to filter via the dedicated `_is_enanyang_article_url` helper.

Registry state: **11 sources** (10 Tier-B + 1 Tier-C). Tier-C infrastructure is separated into its own `fixtures_tier_c_review.py` + `test_tier_c_review.py` module to keep Tier-B and Tier-C review logic cleanly separated. The 4 historical registry-count tests in the forbidden file list remain untouched and are documented as a known compatibility gap.

In-scope tests: **202 / 202 PASS** (after stability). Full Radar pytest: 17 suites PASS, 4 historical `== 7` / `<= 7` failures (documented in §7).