# MY Hot Radar — Radar-6: Existing Tier-B Source Review

> Final documentation for the **Radar-6** batch.
> Read alongside `NEWS_RADAR.md`, `VERIFICATION_RULES.md`,
> `docs/RADAR_5A_TIER_A_DISCOVERY.md`, and `docs/RADAR_5B_SCOPE_RELEVANCE.md`.

This document records the **Radar-6 review of the 5 currently-registered
Tier-B sources**. Radar-6 does NOT add new sources, modify the registry,
or modify any Radar engine code. It establishes the process by which
the existing Tier-B list can be re-validated, and locks the rules in
22 tests.

---

## 1. Objective

Verify that the 5 Tier-B sources currently registered in
`radar/sources_registry.py` continue to satisfy the Radar-2 Tier-B
qualification:

> "Established outlet with documented corrections record" (Tier B,
> per `VERIFICATION_RULES.md` and `radar/sources_registry.py`).

For each source, evaluate:
1. Reachable (HTTP 200 across 3 consecutive fetches).
2. Parseable (RSS / Atom parses cleanly).
3. Structurally stable (item count + response body stable across fetches).
4. Active (newest item is recent — not a stale cached feed).
5. Independent (not a wire-mirror of another source).
6. Content-relevant (still publishing news-oriented content, not e.g.
   100% tenders or placeholders).

Each source receives one of three registry decisions:
`KEEP_TIER_B`, `NEEDS_REVIEW`, or `REMOVE_FROM_REGISTRY`.

---

## 2. Existing Tier-B definition

Per `radar/sources_registry.py` (locked in Radar-2, unchanged through
Radar-6):

A Tier-B source must satisfy all of:

1. URL returns HTTP 200 at registration time.
2. Content-type is XML (RSS or Atom).
3. Parse succeeded and produced items.
4. Feed is publicly accessible without login, paywall, or CAPTCHA.
5. Tier (A..F) is documented and justified in the per-source
   comment block AND in the per-source `notes` field.

Tier B specifically (per `VERIFICATION_RULES.md`):

> "Established outlet with documented corrections record."

Radar-6 did **not** redefine this. It only added operational tests
that the existing definition implies:

- "HTTP 200" implies a re-probe should still see HTTP 200.
- "Parse succeeded" implies the parse still succeeds today.
- "Established outlet" implies the source is actually publishing
  news content, not placeholders or admin-only notices.
- "Documented corrections record" is checked indirectly via
  publisher identity (host matches publisher name).

---

## 3. Review methodology

For each of the 5 registered sources:

1. **3 consecutive fetches** with the same User-Agent used in
   production.
2. Record per fetch: HTTP status, response size, SHA-256 (truncated to
   12 hex chars), parse status, item count, response time.
3. From the first successful fetch: parse titles, URLs, pubDates.
4. Classify each title's `ContentNature` using Radar-5B's
   `classify_content()` (reused, not redefined).
5. Compute freshness: newest / median / oldest item age in days.
6. URL host analysis: do all article URLs belong to the publisher's
   own domain?
7. Cross-source title overlap: for each title, normalize (lowercase,
   strip HTML, strip stopwords, strip short words) and check if any
   title from another source shares ≥5 content-words.
8. Compute `RegistryDecision` via the rule in §6 below.

The full review per source becomes a `SourceReview` dataclass (in
`radar/tier_b_review.py`). Tests use frozen fixture data captured
from today's probe so the suite is deterministic and offline.

---

## 4. Source-by-source review

### 4.1 BBC News Asia

| Field | Value |
|---|---|
| URL | `https://feeds.bbci.co.uk/news/world/asia/rss.xml` |
| Endpoint type | RSS 2.0 |
| 3-fetch status | 3/3 HTTP 200 |
| 3-fetch SHA | `a44da7f7ea91` × 3 (bit-identical) |
| Item count / fetch | 17 |
| Newest item age | 0 days (today) |
| Median age | 1 day |
| Unique titles | 17 / 17 |
| Unique pubDates | 17 / 17 |
| URL hosts | 17/17 self-host (`www.bbc.co.uk`) |
| Cross-source wire indicators | 0 |
| Content distribution | UNKNOWN 76.5%, NEWS 23.5% |
| Event-oriented ratio | 23.5% |

**Sample titles:**
- "The Frenemy: How Australia navigates superpower rivalry"
- "Sign before praying: A new conversion law is affecting churchgoers in Indian state"
- "Seoul summons Ukraine envoy over North Korean prisoner-of-war row"
- "Women protest in the streets of Delhi after string of sexual assaults"

**Decision: KEEP_TIER_B.** Stable feed, 17 unique items, all
self-host, no wire indicators. The "UNKNOWN 76.5%" headline is
expected: BBC feature/analysis stories don't match the news-action-verb
heuristic, but they ARE genuine BBC journalism.

---

### 4.2 Channel News Asia (Asia section)

| Field | Value |
|---|---|
| URL | `https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_charset_=UTF-8&cnaCategId=100348&type=feed` |
| Endpoint type | RSS 2.0 |
| 3-fetch status | 3/3 HTTP 200 |
| 3-fetch SHA | `f5aa5d7eae93` × 3 (bit-identical) |
| Item count / fetch | 20 |
| Newest item age | 0 days (today) |
| Median age | 0 days |
| Unique titles | 20 / 20 |
| Unique pubDates | 19 / 20 (one date shared by 2 items) |
| URL hosts | 20/20 self-host (`www.channelnewsasia.com`) |
| Cross-source wire indicators | 0 |
| Content distribution | UNKNOWN 80.0%, NEWS 20.0% |
| Event-oriented ratio | 20.0% |

**Sample titles:**
- "Pope says concerns about AI 'should be taken seriously'"
- "Shares of fast-fashion platform Shein fall 4% after quarterly profit slides 67%"
- "OpenAI says AI models accessed Australian government systems without authorisation"
- "South Korean exports seen rising for 16th month on solid AI chip demand: Reuters poll"

**Decision: KEEP_TIER_B.** Same shape as BBC: established outlet,
unique items, all self-host, no wire indicators. The single
shared pubDate (`06:00:00 +0800` for 2 items) is the CNA midnight
publishing pattern (two articles published in the same second), not
a duplicate.

---

### 4.3 CodeBlue

| Field | Value |
|---|---|
| URL | `https://codeblue.galencentre.org/feed/` |
| Endpoint type | RSS 2.0 |
| 3-fetch status | 3/3 HTTP 200 |
| 3-fetch SHA | `5664d5dee299` × 3 (bit-identical) |
| Item count / fetch | 10 |
| Newest item age | 0 days (today) |
| Median age | 3 days |
| Unique titles | 10 / 10 |
| Unique pubDates | 10 / 10 |
| URL hosts | 10/10 self-host (`codeblue.galencentre.org`) |
| Cross-source wire indicators | 0 |
| Content distribution | UNKNOWN 80.0%, NEWS 20.0% |
| Event-oriented ratio | 20.0% |

**Sample titles:**
- "The Silent Surge: Why Malaysians Keep Postponing Health Screening — Brittany Richard Johny & Kala Raani Chandra Guindan"
- "Siti Hasmah Represented Finest Traditions Of Medicine — MMA"
- "Siti Hasmah Pioneered Public Health, Maternal And Child Health: Dzulkefly"
- "A Response To 'Are We Still Practising Family Medicine?' — Dr MFH"
- "Don't Quit Medicine, Senior Doctors Tell Their Juniors"

**Decision: KEEP_TIER_B.** Stable health-policy niche source,
all self-host, no wire indicators. Item count (10) is small but
matches the documented "~10 items per fetch" note in the registry.
This is not a degradation.

---

### 4.4 Free Malaysia Today (Bahasa)

| Field | Value |
|---|---|
| URL | `https://www.freemalaysiatoday.com/category/bahasa/feed` |
| Endpoint type | RSS 2.0 |
| 3-fetch status | 3/3 HTTP 200 |
| 3-fetch SHA | `bc4f303aacbb` × 3 (bit-identical) |
| Item count / fetch | 50 |
| Newest item age | 0 days (today) |
| Median age | 0 days |
| Unique titles | 50 / 50 |
| Unique pubDates | 50 / 50 |
| URL hosts | 50/50 self-host (`www.freemalaysiatoday.com`) |
| Cross-source wire indicators | 0 |
| Content distribution | UNKNOWN 88.0%, PUBLIC_SERVICE 4.0%, HR 4.0%, REGULATORY_NOTICE 4.0% |
| Event-oriented ratio | 4.0% |

**Sample titles:**
- "Bekas CEO FIC didakwa perdaya lembaga pengarah berkait projek Jalan Semarak"
- "Sanusi dengan ketuanan PAS"
- "Malaysia mula hantar pulang pelarian Myanmar"
- "Mahasiswa perlu cipta nilai, bukan sekadar pengguna teknologi, titah Raja Muda Perlis"
- "Mengapa perpecahan multikoalisi mutlak berlaku dalam PRU16"

**Decision: KEEP_TIER_B.** Largest source by volume (50 items/fetch).
All unique titles, all self-host, no wire indicators. The
"event-oriented ratio 4.0%" is a low number because the classifier's
keyword heuristic is tuned for English; Malay politics/current-affairs
titles don't match the action-verb patterns. The titles are clearly
genuine FMT Bahasa journalism — the low classifier score is a
classifier-language-coverage limitation, not a content problem.

**Note (no action):** The classifier's recall on Bahasa Malaysia
titles is acknowledged. Improving this is OUT OF SCOPE for Radar-6
(per spec §13: "不要做 Tier-B source 排名"). It will be revisited in
a future classifier-improver batch if needed.

---

### 4.5 Borneo Post

| Field | Value |
|---|---|
| URL | `https://www.theborneopost.com/feed/` |
| Endpoint type | RSS 2.0 |
| 3-fetch status | 3/3 HTTP 200 |
| 3-fetch SHA | `36fd186af01d` × 3 (bit-identical) |
| Item count / fetch | 20 |
| Newest item age | 0 days (today) |
| Median age | 0 days |
| Unique titles | 20 / 20 |
| Unique pubDates | 20 / 20 |
| URL hosts | 20/20 self-host (`www.theborneopost.com`) |
| Cross-source wire indicators | 0 |
| Content distribution | UNKNOWN 65.0%, NEWS 30.0%, CORPORATE 5.0% |
| Event-oriented ratio | 30.0% |

**Sample titles:**
- "Air quality worsens in Sarawak as 7 stations record 'Unhealthy' API readings"
- "Younger generation key to achieving Sarawak's 2030 goals, says Gerald"
- "Woman found unconscious in Donggongon dies"
- "Social activist hopes for prioritised funding to Sarawak healthcare under Budget 2027"
- "Mayor: Motac's RM3.8 million to cover improvement works on Taman Awam Miri"

**Decision: KEEP_TIER_B.** East-Malaysia regional source, 20 unique
items, all self-host, no wire indicators. The 5% CORPORATE items are
official government / event announcements — within the normal scope
of a regional news outlet.

---

## 5. Stability (cross-source)

All 5 sources:

- HTTP 200 on 3/3 consecutive fetches.
- Response body SHA-256 (truncated 12 hex) **bit-identical** across
  the 3 fetches.
- Item count identical across the 3 fetches.
- RSS 2.0 parses cleanly on every fetch (no `ok_rss` failure).

**Byte-identical across 3 successive fetches** is expected for RSS
feeds served via CDN cache (the typical TTL is 60s–15min). Radar-6
treats this as evidence of structural stability, NOT as a sign of a
stale cached feed. The freshness check (next section) is the
separate gate for "is this feed actively publishing news?".

Per `radar/sources_registry.py` doc-string, byte-identical responses
are normal for the 5 Tier-B sources. Radar-2 documented the same
SHA-stable behavior at registration time. Radar-6 confirms it is
still true.

---

## 6. Freshness (cross-source)

| Source | Newest item age | Median age | Verdict |
|---|---:|---:|---|
| BBC News Asia | 0 days | 1 day | ACTIVE |
| Channel News Asia | 0 days | 0 days | ACTIVE |
| CodeBlue | 0 days | 3 days | ACTIVE |
| FMT Bahasa | 0 days | 0 days | ACTIVE |
| Borneo Post | 0 days | 0 days | ACTIVE |

All 5 sources are ACTIVE (newest item within 48 hours).

The stale-feed detection rule:

| Verdict | Condition | Registry impact |
|---|---|---|
| ACTIVE | newest item < 2 days | (no impact) |
| FRESH | newest item < 7 days | (no impact) |
| STALE | newest item < 30 days | NEEDS_REVIEW |
| DORMANT | newest item >= 30 days | REMOVE_FROM_REGISTRY |
| UNKNOWN | no parseable pubDate | (treated as STALE for safety) |

A synthetic DORMANT feed (newest 60 days old) is correctly
classified as REMOVE_FROM_REGISTRY by the test
`test_stale_feed_detection_works`.

---

## 7. Content nature (cross-source)

Per spec §8, the 5 Tier-B sources' content distribution was computed
using Radar-5B's `ContentNature` taxonomy:

```
PRESS | NEWS | ADMIN_NOTICE | REGULATORY_NOTICE |
TENDER | HR | CORPORATE | PUBLIC_SERVICE |
PLACEHOLDER | UNKNOWN
```

Distribution summary (% of items per source):

| Source | UNKNOWN | NEWS | PRESS | Other | Event-oriented |
|---|---:|---:|---:|---|---:|
| BBC | 76.5 | 23.5 | 0 | 0 | 23.5% |
| CNA | 80.0 | 20.0 | 0 | 0 | 20.0% |
| CodeBlue | 80.0 | 20.0 | 0 | 0 | 20.0% |
| FMT | 88.0 | 0 | 0 | HR 4%, REG 4%, PS 4% | 4.0% |
| Borneo Post | 65.0 | 30.0 | 0 | CORP 5% | 30.0% |

**Observations:**

- **UNKNOWN dominates** across all sources. This is the
  classifier's "no rule matched" bucket. The titles are real news
  (visible in §4 sample titles), but they don't contain the action
  verbs / press-release keywords the classifier looks for. This is
  a **classifier-recall limitation, not a content problem**.
- **No PLACEHOLDER items** in any source. The 100%-placeholder
  detection rule (`test_placeholder_detection_flags_placeholder_heavy_source`)
  would correctly flag a hypothetical placeholder-only feed as
  REMOVE_FROM_REGISTRY.
- **No TENDER or HR dominance** in any source. The 70%+ non-news
  scope-drift rule (`test_non_news_dominance_detection_flags_scope_drift`)
  would flag such a feed as NEEDS_REVIEW.

**Classifier language-coverage caveat:** The classifier's keyword
patterns are stronger for English than for Bahasa Malaysia. FMT
Bahasa's 88% UNKNOWN score reflects this, not a content-quality
problem. Per spec §13, this is OUT OF SCOPE for Radar-6 and will be
addressed in a future batch if it becomes an issue.

---

## 8. Scope

Per Radar-5B's `SourceScope` taxonomy:

```
GENERAL_NEWS | GOVERNMENT_NEWS | REGULATORY |
ELECTION | EDUCATION | HEALTH | FINANCE |
CORPORATE | NICHE | UNKNOWN
```

Per-source scope assignment (informational, not a registry change):

| Source | Scope | Reason |
|---|---|---|
| BBC News Asia | GENERAL_NEWS | international general-news outlet |
| Channel News Asia | GENERAL_NEWS | regional general-news outlet |
| CodeBlue | NICHE (health-policy) | Galen Centre / APHM-affiliated, niche by design |
| FMT Bahasa | GENERAL_NEWS | one of the largest Bahasa MY newsrooms |
| Borneo Post | GENERAL_NEWS | established East-MY regional general outlet |

All 5 sources remain within scope for MY Hot Radar. CodeBlue is
niche-by-design (health) but the registry already documents it as
"niche but established" — this is not a regression.

---

## 9. Independent / wire-origin findings

**Method (per spec §10):**

For each title, normalize:
- lowercase
- strip HTML tags
- strip punctuation
- strip English + Malay stopwords
- strip words ≤ 2 chars

For each pair of titles from different sources, count content-word
intersection. Flag as wire-origin indicator if intersection ≥ 5
content-words.

**Result:** **Zero cross-source wire-origin indicators detected**
across all 5 sources × all titles.

Combined with URL host analysis (100% self-host for every source),
this confirms:

> 5 registered Tier-B sources = 5 independently-publishing outlets.

This is exactly the verification described in `VERIFICATION_RULES.md`
under "Multi-source trap": the system is NOT accidentally treating
a wire mirror as multiple independent sources.

---

## 10. Registry decisions

| Source | Freshness | Wire ind. | Non-news % | Placeholder % | Decision |
|---|---|---:|---:|---:|---|
| BBC News Asia | ACTIVE | 0 | 0% | 0% | **KEEP_TIER_B** |
| Channel News Asia | ACTIVE | 0 | 0% | 0% | **KEEP_TIER_B** |
| CodeBlue | ACTIVE | 0 | 0% | 0% | **KEEP_TIER_B** |
| FMT Bahasa | ACTIVE | 0 | 12% (HR/REG/PS) | 0% | **KEEP_TIER_B** |
| Borneo Post | ACTIVE | 0 | 5% (CORP) | 0% | **KEEP_TIER_B** |

**No source was flagged for NEEDS_REVIEW or REMOVE_FROM_REGISTRY.**

Per spec §13, this is a valid PASS outcome. Per spec §14:

> "如果 source 稳定、内容相关、有真实新闻、没有明确问题，不要因为
> 今天文章数量少就降级."

All 5 sources are stable, content-relevant, and publishing real
news. No changes to `radar/sources_registry.py`.

The registry stays at 5 sources. No source was added, removed, or
re-tiered.

---

## 11. Tests

A new test module `radar/tests/test_tier_b_review.py` adds **22 tests**:

| Category | Count |
|---|---:|
| Model / enum (FreshnessVerdict, RegistryDecision) | 2 |
| Stability (reachable, parse, repeated-fetch structure) | 3 |
| Freshness (active detection, stale detection) | 2 |
| Content (distribution, placeholder, scope drift) | 3 |
| Independence (wire detection, self-host count) | 2 |
| Registry (KEEP / REMOVE) | 2 |
| Per-source review (5 sources × 1 test) | 5 |
| Regression (engine untouched, registry unchanged, ContentNature reused) | 3 |
| **Total** | **22** |

All 22 tests pass.

### Regression

```
python -m radar.tests.run_all
```

| Module | Tests | Status |
|---|---:|---|
| `test_dedup` | 5 | PASS |
| `test_verification` | 5 | PASS |
| `test_momentum` | 8 | PASS |
| `test_classification` | 6 | PASS |
| `test_failures` | 7 | PASS |
| `test_real_world` (Radar-2) | 17 | PASS |
| `test_evidence` (Radar-3) | 25 | PASS |
| `test_stability` (Radar-4A) | 24 | PASS |
| `test_tier_a` (Radar-5A) | 17 | PASS |
| `test_source_scope` (Radar-5B) | 25 | PASS |
| **`test_tier_b_review` (Radar-6, new)** | **22** | **PASS** |
| **Total** | **161** | **ALL PASS** |

Zero regressions in Radar-1 → Radar-5B tests.

---

## 12. Real scan

```
python -m radar.scan
```

Result:

```json
{
  "ok": true,
  "topics_count": 89,
  "stories_count": 117,
  "report_paths": {
    "json": "C:\\MY-Hot-Radar\\radar_data\\latest.json",
    "md": "C:\\MY-Hot-Radar\\radar_data\\latest.md"
  }
}
```

Per-source status:

| Source | Type | ok | fetched |
|---|---|---|---:|
| BBC News Asia | RSS | True | 17 |
| Channel News Asia | RSS | True | 20 |
| CodeBlue | RSS | True | 10 |
| FMT Bahasa | RSS | True | 50 |
| Borneo Post | RSS | True | 20 |
| **Total** | | | **117** |

Real scan matches the frozen-fixture counts exactly. Output
schema (`latest.json`, `latest.md`) is unchanged. `radar_data/`
remains gitignored.

---

## 13. Production safety

| Check | Result |
|---|---|
| `https://myhotradar.com/` | HTTP 200 ✅ |
| `/sitemap.xml` | HTTP 200, 12 URLs ✅ |
| `/hot/` | HTTP 200 ✅ |
| `/malaysia/` | HTTP 200 ✅ |
| `/viral/` | HTTP 200 ✅ |
| `/celebrity/` | HTTP 200 ✅ |
| `/food/` | HTTP 200 ✅ |
| `/world/` | HTTP 200 ✅ |
| `/about/` | HTTP 200 ✅ |
| `/contact/` | HTTP 200 ✅ |
| `/privacy/` | HTTP 200 ✅ |
| `/terms/` | HTTP 200 ✅ |
| AdSense (`ca-pub-6219340004578553`) | present, 1 occurrence ✅ |
| Cloudflare | untouched ✅ |
| Facebook Page | untouched ✅ |
| `index.html` / category pages / `assets/` | untouched ✅ |

---

## 14. Experience governance

Per Radar-6 spec §18:

> "Default: NO NEW EXPERIENCE. Do not modify EXPERIENCE.md unless
> independently reproduced, reusable, verified."

Observations from Radar-6:

| Observation | Status |
|---|---|
| All 5 Tier-B sources are byte-stable across 3 fetches | **Not promoted** — first reproduction; needs a second batch to confirm |
| All 5 Tier-B sources are ACTIVE (newest item < 2 days) | **Not promoted** — single-snapshot observation |
| Zero cross-source wire-origin indicators | **Not promoted** — single-snapshot observation |
| Classifier recall on Bahasa titles is low | **Not promoted** — needs an independent classifier-improvement batch |
| SHA-identical RSS responses are stable-feed evidence | **Candidate observation** — already documented in Radar-2 registry header; nothing new to promote |

`EXPERIENCE.md` is **unchanged** by Radar-6.

---

## 15. Files changed in Radar-6

| File | Status | Lines |
|---|---|---:|
| `radar/tier_b_review.py` | **new** | +325 |
| `radar/tests/test_tier_b_review.py` | **new** | +631 |
| `radar/tests/fixtures_tier_b_review.py` | **new** | +1230 (frozen fixture data) |
| `radar/tests/run_all.py` | modified | +1 |
| `docs/RADAR_6_TIER_B_REVIEW.md` | **new** | (this file) |
| `radar/sources_registry.py` | **untouched** | — |
| `radar/verification.py`, `momentum.py`, `classification.py`, `counter_signals.py`, `dedup.py` | **untouched** | — |
| `radar/tier_a_qualification.py`, `radar/source_scope.py` | **untouched** | — |
| `radar/models.py` | **untouched** | — |
| Website, sitemap, AdSense, Cloudflare, Facebook | **untouched** | — |
| **Total** | | **+2187 / -0** |

---

## 16. Git

| Step | Result |
|---|---|
| Working tree before | clean |
| Files staged | 4 (3 new, 1 modified) |
| Files NOT staged | `radar_data/` (gitignored) |
| Commit (Radar-6) | (recorded in batch report) |
| Push | (recorded in batch report) |
| `git amend` / rebase / squash / force-push / reset | **none used** |

---

## 17. Limitations

1. **Byte-identical across 3 fetches** is expected for CDN-cached RSS
   feeds. Radar-6 treats this as structural-stability evidence, not
   active-publishing evidence. The freshness check (newest item age)
   is the separate gate for "actively publishing".

2. **Classifier language coverage is stronger on English than Bahasa
   Malaysia.** FMT Bahasa's 88% UNKNOWN score reflects this, not
   content quality. Improving the classifier is OUT OF SCOPE for
   Radar-6.

3. **Cross-source wire detection uses a content-word Jaccard heuristic**
   with a ≥5 word threshold. False negatives are possible for stories
   that share the same subject but with very different wording (e.g.
   BBC writes "The Frenemy: How Australia navigates superpower
   rivalry" while CNA writes "Australia balances US-China ties").
   Both titles ARE about the same general topic but share 0 content
   words, so they correctly don't trigger wire detection. A future
   batch could add entity-based dedup as a second layer.

4. **Radar-6 cannot detect silent deprecation** (a publisher quietly
   stopping real journalism and only publishing press releases). The
   non-news dominance rule (>70% non-news) catches the extreme case
   but not subtle gradual drift. This is by design — per spec §14,
   do not flag a source for being on the boundary.

5. **Radar-6 is a snapshot.** All findings reflect the state of the
   5 feeds on 2026-09-29. Future batches should re-run this review
   and update the frozen fixture in the same commit as any registry
   change.

---

## 18. Conclusion

Radar-6 re-validated the 5 currently-registered Tier-B sources
under the existing Radar-2 qualification rules. Result:

- **5/5 reachable** (HTTP 200 across 3 fetches each).
- **5/5 parse cleanly** (RSS 2.0, no parse errors).
- **5/5 structurally stable** (bit-identical SHA across 3 fetches).
- **5/5 active** (newest item < 2 days).
- **5/5 independent** (zero cross-source wire-origin indicators, 100%
  self-host URLs).
- **5/5 content-relevant** (no placeholder dominance, no scope drift).
- **5/5 KEEP_TIER_B** — no registry change required.

The Radar-6 review module (`radar/tier_b_review.py`) is now
available for future batches that want to re-probe the Tier-B
list. The decision rules (`KEEP_TIER_B` / `NEEDS_REVIEW` /
`REMOVE_FROM_REGISTRY`) are documented and locked by 22 tests.

**Final result:** Tier-B registry unchanged. 0 sources added, 0
removed, 0 re-tiered.
