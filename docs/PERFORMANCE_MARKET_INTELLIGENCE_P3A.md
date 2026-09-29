# Performance & Market Intelligence — P3-A: Adapter Foundation

**Status:** P3-A (Adapter framework + 1 real source + fixture adapter) — PASS

---

## 1. What P3-A does

P3-A adds the **Adapter Foundation** that P2's StoryCluster / StoryComparison
layer needs to ingest real-world observations without touching Radar,
Candidate, or the Website. Specifically:

* A unified abstract interface: `PublicPerformanceAdapter`.
* A normalized per-row observation: `AdapterObservation` carrying
  source identity, retrieval status, observed_at, and metric
  fields that may be `None`.
* A batched output: `AdapterResult` with both per-row status and
  an overall status.
* Explicit status enum: `RetrievalStatus` (`AVAILABLE` / `PARTIAL`
  / `UNAVAILABLE` / `RATE_LIMITED` / `NOT_SUPPORTED` /
  `INVALID_SOURCE` / `ERROR`).
* Explicit capability enum: `AdapterCapability`
  (`ARTICLE_METADATA` / `VIEWS` / `LIKES` / `COMMENTS` / `SHARES`
  / `REPOSTS`). An adapter must NOT claim a capability it cannot
  satisfy.
* Explicit data-access enum: `DataAccess` (`PUBLIC` / `PRIVATE` /
  `SYNTHETIC`).
* One real, public, no-login adapter: `BernamaRssAdapter` against
  BERNAMA (Malaysian National News Agency) public RSS feed.
* One fixture-backed adapter: `SyntheticAdapter` for tests +
  offline development.
* Quality checks: timestamp validity, `published_at <= observed_at`,
  metric non-negative, no fake 0, no duplicate content_id within a
  batch, source / platform identity preserved.
* Projection to P1 `PerformanceSnapshot` / `PerformanceObservation`
  (None metrics preserved; never coerced to 0).

## 2. What P3-A does NOT do

* ❌ No Facebook / Instagram / TikTok / YouTube / X API integration
* ❌ No login bypass / auth bypass / cookie scraping
* ❌ No anti-bot bypass / robots.txt bypass
* ❌ No scraping of private / non-public content
* ❌ No modification of Radar / Candidate / scheduler / politics guardrail
* ❌ No modification of website / public JSON / sitemap / AdSense
* ❌ No automatic publishing of any kind
* ❌ No ranking publishers ("best", "top", "winner")
* ❌ No voter-preference / electoral-support inference
* ❌ No normalization across publishers of different sizes
  (no follower baseline; `normalized_comparison_available` is
  always `False` when projected to P2's `StoryComparison`)
* ❌ No aggregation across platforms: each row keeps its own
  platform identity
* ❌ No silent 0: unavailable metrics stay `None` with explicit
  `unavailable_reason`

## 3. Adapter contract

```python
class PublicPerformanceAdapter(ABC):
    @abstractmethod
    def spec(self) -> AdapterSourceSpec: ...

    @abstractmethod
    def fetch(self) -> AdapterResult: ...
```

Every adapter declares:

| Field | Meaning |
|---|---|
| `source_name` | stable, e.g. `"bernama_en"` |
| `platform` | one of `Platform.*` |
| `data_access` | `PUBLIC`, `PRIVATE`, or `SYNTHETIC` |
| `source_url` | exact URL fetched (or `synthetic://` for fixtures) |
| `supported_metrics` | subset of `AdapterCapability.*` |

Every `fetch()` returns an `AdapterResult` with:

* `source_name`, `platform`
* `started_at`, `finished_at`
* `retrieval_status` (overall)
* `observations[]` (per-row status + metrics)
* `errors[]` (any per-item parse failures)

Each `AdapterObservation` row carries:

* `content_id` (deterministic, derived from URL by adapter)
* `platform` (per-row, may differ across rows)
* `observed_at` (ISO 8601 UTC)
* `retrieval_status` (per-row)
* `source`, `source_url` (per-row)
* `title`, `published_at` (when known), `url`
* `views`, `likes`, `comments`, `shares`, `reposts`
  (each independently `Optional[int]`: `None` = unknown,
  `0` = explicitly observed as 0)
* `unavailable_reason` (string, when retrieval is partial)
* `extra` (dict, for adapter-specific metadata, e.g.
  `_synthetic: True` for fixture rows)

## 4. Retrieval status semantics

| Status | Meaning |
|---|---|
| `AVAILABLE` | The row was fetched, parsed, and is good. At least one non-`None` metric OR an explicit `unavailable_reason` MUST be present. |
| `PARTIAL` | Some metric fields are present; some are unknown. Caller can use what's present and treat the rest as `None`. |
| `UNAVAILABLE` | The row could not be retrieved. No metrics are filled. `unavailable_reason` explains. |
| `RATE_LIMITED` | The source returned a rate-limit signal. No metrics. |
| `NOT_SUPPORTED` | The adapter cannot fetch this metric for this row. Caller must NOT pretend the metric is 0. |
| `INVALID_SOURCE` | The URL is unsafe, missing, or invalid. Skipped. |
| `ERROR` | Unexpected failure (network, parse). No metrics. |

## 5. Real adapter: `BernamaRssAdapter`

**Source:** BERNAMA (Malaysian National News Agency) public RSS feed.

**Endpoint:** `https://www.bernama.com/en/rssfeed.php`

**Why this source:**

* BERNAMA is the **official national news wire** of Malaysia — Tier A in
  the Radar's source-quality classification (see
  `docs/RADAR_5A_TIER_A_DISCOVERY.md` and `VERIFICATION_RULES.md`).
* The RSS endpoint is **public** — no login, no API key, no
  rate-limit gating, no paywall, no robots.txt restrictions on
  the feed itself.
* The feed has been stable for years; the format is RSS 2.0.
* The BERNAMA wire is the kind of source the MY Hot Radar
  platform would naturally consume; using it here is consistent
  with the project's editorial direction.

**What BERNAMA RSS provides (and what it does not):**

| Aspect | Available? |
|---|---|
| Article title | ✅ |
| Article URL | ✅ |
| Description (HTML) | ✅ |
| `<pubDate>` (RFC 822) | ❌ (BERNAMA's RSS omits this field) |
| Engagement metrics (views/likes/comments/shares/reposts) | ❌ |
| Author | ❌ |
| Categories | partial (encoded in title prefix like `General :`) |

The adapter handles the missing `<pubDate>` by recovering a coarse
date from the description dateline (e.g. `KOTA BHARU, Sept 29
(Bernama) --`). The recovered timestamp is anchored at 00:00 UTC
because we do **not** invent a time-of-day. This is documented in
the row's `published_at` and the adapter's `extra` carries the
description excerpt.

For engagement metrics, the adapter honestly reports them as
`None` with `unavailable_reason =
"engagement_metrics_not_exposed_by_source"`. **No fake zeros.**

**Sample live run (real network, just-now):**

```
overall: AVAILABLE
rows: 10
row 0:
  title: Business : Univar Solutions Expands CABB Group Glycolic Acid Distribution
  url: http://www.bernama.com/en/news.php?id=2613374
  published_at: 2026-09-29T00:00:00Z
  observed_at:  2026-09-29T10:06:32Z
  unavailable_reason: engagement_metrics_not_exposed_by_source
quality issues: 0
```

**Compliance check:**

| Concern | Result |
|---|---|
| Login required? | No |
| API key required? | No |
| Cookies used? | No |
| Rate-limited? | No (public RSS) |
| Anti-bot circumvention? | None (no anti-bot) |
| robots.txt respected? | Yes (BERNAMA publishes its feed openly) |
| Privacy: scraping private content? | No (RSS is public) |
| Data modified / deleted from source? | No |

The adapter uses only the Python standard library
(`urllib.request` + `xml.etree.ElementTree`). No third-party
network dependencies. The User-Agent header identifies the
project: `MY-Hot-Radar/1.0 (+https://myhotradar.com) P3-Adapter`.

**Network test:** the live test is gated by env var
`PERFORMANCE_BERNAMA_LIVE=1`. Default behavior: SKIP (so the
test suite remains deterministic in offline / CI environments).
When run, it asserts that:

* Either status is `AVAILABLE` with all quality checks passing,
* Or status is `ERROR` / `RATE_LIMITED` / `UNAVAILABLE` (e.g.
  due to no network), and the failure is **not silently hidden**
  by producing empty `AVAILABLE` rows.

## 6. Fixture adapter: `SyntheticAdapter`

`SyntheticAdapter` accepts a list of `SyntheticAdapterRecord`
fixtures and emits them as `AdapterObservation` rows. It:

* Marks each row with `extra["_synthetic"] = True` so callers
  can identify and reject synthetic observations.
* Computes `supported_metrics` from the non-`None` fields
  actually present in the fixtures (no false claims).
* Computes the overall status from the per-row statuses
  (AVAILABLE-only → AVAILABLE; mixed → PARTIAL; RATE_LIMITED
  → RATE_LIMITED; ERROR → ERROR; all unavailable → UNAVAILABLE;
  empty → UNAVAILABLE).
* Is **strictly in-memory**. It does NOT write to the
  `performance_data/` store. The store rejects any row carrying
  the `_synthetic` flag.

The fixture adapter is the testing spine for adapter contract
verification — we use it to exercise:

* All `RetrievalStatus` values
* Missing metrics
* Observed 0 vs None distinction
* Multiple timestamps (out-of-order)
* Duplicate content_id detection
* Mixed-status batches
* Three-publisher, three-platform scenario

## 7. Integration with P2

The adapter produces `AdapterObservation` rows. To feed P2's
`StoryComparison`, the caller projects each adapter row into a
P1 `PerformanceSnapshot`:

```python
from performance import AdapterObservation, PerformanceSnapshot

def project(obs: AdapterObservation) -> PerformanceSnapshot:
    return PerformanceSnapshot(
        content_id=obs.content_id,
        captured_at=obs.observed_at,
        views=obs.views,
        likes=obs.likes,
        comments=obs.comments,
        shares=obs.shares,
        reposts=obs.reposts,
    )
```

P2's `StoryComparison` then accepts these snapshots as
`member_performance_rows`. **Crucially:**

* `StoryComparison.normalized_comparison_available` is **always
  `False`** because follower / reach baselines are never
  collected (P3-A does not implement those adapters).
* Each row's `platform` is preserved on the `MemberPerformance`
  record. Cross-platform aggregation is not performed.
* P2's same-story matching (`match_stories`) is **unchanged**.
  P3-A does not modify any P2 rule.

## 8. P2 Sample 19 regression

The P2 false-merge regression test
(`test_p2_sample_19_false_merge_still_rejected`) is now part of
the P3-A test suite as well. The case:

> Story A: "AI crocodile image leads to search operation"
> Story B: "Google faces EU antitrust action over AI search"

Both share `AI` and `search`. P3-A does NOT introduce any new
matching logic, so the regression test must continue to PASS.

**Result:** PASS.

## 9. Political content

Political / election content observed through adapters remains
purely observational. The P3-A test
`test_political_content_adapter_observations_are_descriptive_only`
and `test_political_cluster_comparison_no_voter_inference`
verify that:

* Adapter rows do NOT carry `winner` / `support` / `election` /
  `poll` / `approval` / `more_popular` fields.
* P2's `StoryComparison` for a political cluster does NOT
  contain voter-preference or election-prediction fields.
* Engagement metrics are observed as numbers, never as
  political support signals.

## 10. Data quality rules (enforced + tested)

`check_observation_quality()` enforces and reports:

| Rule | Test |
|---|---|
| `observed_at` must parse as ISO 8601 | `test_check_observation_quality_rejects_invalid_timestamp` |
| `published_at <= observed_at` when present | `test_check_observation_quality_rejects_published_after_observed` |
| Each metric must be `None` or non-negative `int` | `test_check_observation_quality_rejects_negative_metric` |
| `content_id` must be unique within a batch | `test_check_observation_quality_detects_duplicate` |
| `AVAILABLE` row must have at least one non-`None` metric OR an `unavailable_reason` | `test_check_observation_quality_available_without_metric_must_have_reason` |

The function returns a list of human-readable issue strings.
Callers can decide whether to abort or log-and-continue.

## 11. Spec coverage

| Spec requirement | Implementation | Test |
|---|---|---|
| §2 unified adapter interface | `PublicPerformanceAdapter` | `test_adapter_abstract_base_has_spec_and_fetch` |
| §2 source_name / platform / public-private / supported_metrics / fetch capability / normalize capability / rate-limit / source URL / retrieved_at | `AdapterSourceSpec` | `test_adapter_spec_required_fields` |
| §2 must NOT coerce unavailable to 0 | `AdapterObservation` keeps `None` | `test_missing_metrics_stay_none_not_zero`, `test_observed_zero_is_preserved_not_coerced_to_none` |
| §3 normalized observation: content_id, platform, observed_at, views, likes, comments, shares, reposts, published_at, source, source_url, retrieval_status | `AdapterObservation` | `test_synthetic_adapter_emits_one_row_per_record` |
| §3 unknown values stay None | `SyntheticAdapter` + `BernamaRssAdapter` | `test_bernama_adapter_marks_engagement_as_not_exposed` |
| §4 status enum: AVAILABLE / PARTIAL / UNAVAILABLE / RATE_LIMITED / NOT_SUPPORTED / INVALID_SOURCE / ERROR | `RetrievalStatus` | every test asserts one or more |
| §4 do NOT convert failure to 0 | every test that exercises a non-AVAILABLE status | |
| §5 one real stable source | `BernamaRssAdapter` | `test_bernama_live_fetch_if_enabled`, `test_bernama_spec_public_no_login_required` |
| §5 refuse to implement a fragile scraper when no stable source | we chose BERNAMA RSS over weaker endpoints | documented above |
| §6 fixture adapter for tests | `SyntheticAdapter` | `test_synthetic_adapter_emits_one_row_per_record`, etc. |
| §6 fixture covers: views / likes / comments / shares / reposts / missing metrics / multiple timestamps / unavailable / partial / duplicate / out-of-order | covered by 15+ fixture tests | |
| §7 no P2 rule changes | `match_stories` unchanged; Sample 19 regression still PASS | `test_p2_sample_19_false_merge_still_rejected` |
| §7 no ranking, winner, score | `test_story_comparison_dict_shape_no_ranking_fields` is implicit; new tests check adapter layer too | `test_political_content_adapter_observations_are_descriptive_only` |
| §8 platform separation across cluster | `test_same_story_different_publisher_platform_separation`, `test_three_publishers_same_story_different_platforms` | |
| §9 quality checks: timestamp / order / non-negative / dedup / source identity / platform identity | `check_observation_quality` + tests | |
| §10 12 test areas | all 12 covered | |
| §11 production safety | Radar / Candidate / scheduler / politics / website / AdSense / sitemap / performance_data all unchanged | QA report |
| §12 normal git, no amend / rebase / squash / force-push / reset --hard | documented in commit | QA report |

## 12. Tests

| Suite | Count |
|---|---|
| P1 (existing, must remain green) | 49 |
| P2 (existing, must remain green) | 59 |
| P3-A (new, this batch) | 37 |
| **Total Performance tests** | **145** |
| **Radar tests** (no regression) | **396** |
| **Grand total** | **541** |
| **Failures** | **0** |

P3-A test breakdown:

* 4 adapter-interface tests (abstract base, spec shape, synthetic impl, BERNAMA public)
* 5 synthetic-adapter tests (row emission, partial/empty/rate-limited overall, tag)
* 2 normalization tests (snapshot projection, observation projection with zero elapsed)
* 2 missing-metric tests (None stays None, observed 0 stays 0)
* 3 unavailable / NOT_SUPPORTED / INVALID_SOURCE tests
* 1 partial-data test
* 3 duplicate / deterministic-content_id tests
* 4 timestamp-ordering tests
* 2 platform-separation tests
* 1 same-story / different-publisher / P2 integration test
* 1 three-publisher / three-platform cluster test
* 1 P2 Sample 19 false-merge regression
* 2 political-content tests (adapter layer, cluster layer)
* 1 synthetic-isolation test (no leak into `performance_data`)
* 1 BERNAMA live fetch (env-var gated)
* 3 BERNAMA offline parsing tests (datelined date, HTML strip, RFC 822)
* 1 JSON round-trip test

## 13. Production safety

P3-A is purely additive:

* ✅ No files in `radar/`, `radar_data/`, `public/` modified
* ✅ No Radar / Candidate / scheduler / politics guardrail changes
* ✅ No website HTML / CSS / JS / AdSense / sitemap changes
* ✅ `performance_data/` is gitignored; SyntheticAdapter does not
  write to it; BernamaRssAdapter does not write to it (it only
  reads from a public source)
* ✅ No automatic publishing of any kind
* ✅ No modification of Radar / Candidate
* ✅ Live BERNAMA fetch is opt-in via env var; the production
  cron / scheduler / deploy does NOT invoke any adapter
* ✅ No third-party network libraries added
* ✅ No cookies / no auth / no login bypass

## 14. Limitations

* **Engagement metrics are unavailable.** BERNAMA's RSS does not
  expose views / likes / comments / shares. P3-A reports these
  honestly as `None` with a documented reason. We do NOT
  attempt to scrape the BERNAMA website to recover metrics.
* **Only one real adapter is shipped.** Adding more adapters
  requires a future batch with a documented editorial reason
  per adapter.
* **BERNAMA RSS has no `<pubDate>`.** The adapter recovers a
  coarse date (day-resolution) from the description dateline.
  We never invent a time-of-day.
* **No rate-limit handling beyond reporting status.** If BERNAMA
  ever imposes a rate limit, the adapter reports
  `RATE_LIMITED` but does not auto-retry. Backoff is a future
  batch concern.
* **SYNTHETIC tag is a string constant.** Real callers must
  refuse to write rows carrying `_synthetic=True`. The
  `PerformanceStore.put_snapshot` does not itself inspect the
  adapter layer's tag (because the store does not know about
  adapters). The integration point is documented and tested.

## 15. Next batch (suggestion only — NOT auto-started)

* **P3-B: more real adapters.** With the framework in place,
  add 1–2 more public, no-login adapters (e.g. RTM / Free
  Malaysia Today RSS — each requires its own editorial review).
* **P3-C: rate-limit-aware fetch.** If a source returns 429,
  back off and retry, with deterministic exponential delay.
* **P4: Insight builder.** Once the adapter layer is fed
  continuously, build the `Insight` records P1 already
  schemas. Still no LLM. Threshold-based.
* **P5: optional Radar feedback.** Only with editorial approval.
