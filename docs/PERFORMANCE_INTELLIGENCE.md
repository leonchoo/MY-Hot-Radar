# Performance & Market Intelligence Agent — P1

**Status:** P1 (Foundation) — PASS
**Scope:** Data models, validation, deterministic IDs, atomic persistence,
analysis primitives, and synthetic fixtures. **No data collection, no
crawler, no LLM, no auto-publishing.**

---

## 1. Purpose

This module is the **observation layer** for MY Hot Radar. It collects
public metrics about MY Hot Radar's own content (and, in the future,
competitor / market content), and exposes a small, pure analysis API
over them.

It is NOT a prediction system. It does NOT recommend content. It does
NOT scrape Facebook, TikTok, YouTube, X, or any other platform.

The roadmap:

```
P1 (this batch)         data models, IDs, persistence, math, fixtures
P2 (next)               source adapters + public-metrics collectors
P3 (later)              market intelligence synthesis
P4 (later, optional)    closed-loop feedback into Radar (only if rules permit)
```

Each later batch must justify itself. P1 alone gives us a deterministic,
tested foundation that P2/P3 can build on without having to invent the
data model mid-stream.

---

## 2. Architecture

```
performance/
├── __init__.py            public API
├── enums.py               SourceType, Platform, PerformanceClass, InsightScope
├── validation.py          timestamp + URL safety + metric validation
├── models.py              dataclass models + to_dict / from_dict
├── models_validate.py     validate_* for each model
├── ids.py                 deterministic content_id / snapshot_id / ...
├── analysis.py            compute_observation, classify_performance,
│                          engagement_rate, extract_features
├── store.py               PerformanceStore (atomic JSON, no DB)
├── fixtures.py            clearly-tagged SYNTHETIC test fixtures
└── tests/
    ├── __init__.py
    ├── test_performance.py   49 tests
    └── run_all.py
```

Storage layout (under `performance_data/`, gitignored):

```
performance_data/
├── content/                ContentIdentity, one JSON per content_id
├── snapshots/              PerformanceSnapshot, filename includes captured_at
├── observations/          PerformanceObservation, derived from snapshot pairs
├── features/              ContentFeatureSnapshot, one per (content, time)
├── market/                MarketObservation, future P2
├── insights/              Insight, future P3
└── latest.json             index (counts only, no payload bodies)
```

This is intentionally file-based. There is no SQLite, no PostgreSQL,
no global lock. Each entity is its own JSON file. The store is
multi-read, single-write per file.

---

## 3. Data Model

### ContentIdentity
Represents a piece of content under observation.

| Field         | Type     | Notes |
|---------------|----------|-------|
| `content_id`  | string   | Deterministic, sha256[:32], `p_` prefix. |
| `source_type` | enum     | `OWN` or `MARKET`. |
| `publisher`   | string   | ≤ 200 chars. |
| `platform`    | enum     | `WEBSITE / FACEBOOK / INSTAGRAM / TIKTOK / YOUTUBE / X / OTHER`. |
| `url`         | string   | Must pass `is_valid_url`. |
| `title`       | string   | ≤ 500 chars. |
| `category`    | string   | ≤ 64 chars. |
| `topic_type`  | string   | ≤ 64 chars. |
| `language`    | string   | ≤ 16 chars. |
| `published_at`| timestamp| ISO 8601 (Z or offset) or RFC 2822. |

### PerformanceSnapshot
A single point-in-time observation.

| Field         | Type                | Notes |
|---------------|---------------------|-------|
| `content_id`  | string              | |
| `captured_at` | timestamp           | |
| `views`       | int or None         | None ≠ 0. None = unknown. |
| `likes`       | int or None         | |
| `comments`    | int or None         | |
| `shares`      | int or None         | |
| `reposts`     | int or None         | |

### PerformanceObservation
Change between two snapshots + derived velocity.

| Field              | Type                | Notes |
|--------------------|---------------------|-------|
| `content_id`       | string              | |
| `from_captured_at` | timestamp           | |
| `to_captured_at`   | timestamp           | |
| `elapsed_seconds`  | int                 | |
| `views_delta`      | int or None         | Negative deltas → None. |
| `..._delta`        | int or None         | Same convention. |
| `views_per_hour`   | float or None       | |
| `..._per_hour`     | float or None       | |

### PerformanceClassification
A descriptive label, not a prediction.

`EARLY_SPIKE | FAST_GROWTH | STEADY_GROWTH | LATE_BREAKOUT | COOLING | STABLE | INSUFFICIENT_DATA`

### ContentFeatureSnapshot
Frozen characteristics of a content item, captured once. Heuristic
headline features (person name, number, question, quote, etc.) +
publication time + radar context if available.

### MarketObservation
P1 schema only. Future P2 collectors will populate this. Required
fields: observation_id, publisher, platform, content_url, title,
published_at, captured_at, category, topic_type, metrics.

### Insight
P1 schema only. Future P3 synthesis will populate this. Required
fields: insight_id, generated_at, scope (OWN / MARKET / COMPARISON),
observation_window, sample_size, finding, evidence, limitations.

---

## 4. Snapshot Model

The snapshot model captures a single public metrics observation at a
single moment. It does NOT average, aggregate, or compute deltas. It
stores the observation as-is, even if values are missing.

```
PerformanceSnapshot:
  views, likes, comments, shares, reposts
  → each is either an int (observed) or None (not observable)
```

`None` is **not** `0`. A snapshot with `views=None` is different from
`snapshots with views=0`. Downstream code preserves this distinction
through every calculation.

---

## 5. Velocity Metrics

`compute_observation(snap_old, snap_new)` produces a `PerformanceObservation`:

```
views_per_hour = (snap_new.views - snap_old.views) * 3600 / elapsed_seconds
```

The same formula applies to likes / comments / shares. Each is
independent — missing either side of the snapshot pair yields
`None` for that metric, not `0`.

If `curr < prev` (negative delta), the result is also `None`. A later
snapshot showing fewer views than an earlier one is a data-integrity
signal and must be flagged, not silently zeroed.

---

## 6. Engagement Metrics

`engagement_total(snap)` = `likes + comments + shares + reposts`,
where None components are treated as 0 only for the sum (the
breakdown is preserved separately).

`engagement_rate(snap)` = `engagement_total / views`, **only** when
`views` is a positive int. If `views` is None, 0, or if all
engagement components are None, the rate is None — never 0.

A `None` rate is different from `0.0`. The former means "we can't
compute it"; the latter would mean "0% engagement", which is a
real observation that we must not invent.

---

## 7. OWN vs MARKET

`ContentIdentity.source_type` is one of `OWN` or `MARKET`.

| source_type | meaning |
|-------------|---------|
| `OWN`       | Content published by MY Hot Radar (or future MY Hot Radar content pipeline). |
| `MARKET`    | Content published by other publishers (future competitor / market observation). |

The PerformanceStore tracks OWN and MARKET content under separate paths.
The latest.json index counts both, but the `rebuild_latest()` method
refuses to include any payload tagged SYNTHETIC (see §11).

Cross-source comparison (e.g., "OUR average engagement vs MARKET
average engagement in same category") is **out of scope** for P1 and
must NOT be done in this batch.

---

## 8. Platform Separation

Platforms differ in their metric definitions. The current schema
covers the union:

- Facebook:    views / likes / comments / shares / reposts
- TikTok:      likes / comments / shares
- YouTube:     likes / comments
- Instagram:   likes / comments
- X:           likes / comments / shares / reposts
- Website:     views (typically); engagement is whatever the
               site analytics provider exposes

Every snapshot is bound to one platform via `ContentIdentity.platform`.
Aggregate / compare APIs MUST carry `platform` and MUST NOT silently
mix metrics across platforms. P1 does not implement cross-platform
aggregation; the rule is documented here so future P2/P3 implementations
follow it.

---

## 9. Observation vs Hypothesis

A central design principle: the Performance module produces
**observations**. It does not produce **causal explanations**.

Examples of what the module is allowed to say:

> "该文章在前 3 小时获得 52,000 views，shares 从 120 增至 680。"

> "该文章在观察样本中具有较高 share velocity。"

Examples of what the module must NOT say:

> "因为标题用了这个词，所以 Facebook 推送了它。"

> "作者选择下午 6 点发布是 viral 的原因。"

> "高 engagement rate 说明这条内容一定会爆。"

The reason is the same as for the News Radar: we have no internal
platform data. The Performance module mirrors this discipline.

Future batches that produce Insights MUST mark any causal or
predictive claim as a **hypothesis** with explicit
`evidence` + `alternative_explanations` + `limitations` fields. P1
defines the Insight schema; the discipline of distinguishing
observation from hypothesis is enforced at P3.

---

## 10. Future Market Intelligence

P2 will introduce:

- Source adapters (one per platform: Facebook Page Insights,
  TikTok public data, YouTube Data API v3, X public posts, etc.).
- A `MarketCollector` that produces `MarketObservation` records
  at scheduled intervals.
- A `MarketAggregator` that joins market observations with own
  performance snapshots under a common category / topic_type axis.

P3 will introduce:

- An `InsightBuilder` that produces `Insight` records from
  aggregated OWN and MARKET data.
- Strict neutrality enforcement (same rules as Radar politics).
- Strict observation-vs-hypothesis tagging.

P1 implements neither.

---

## 11. Synthetic Fixtures

The `performance.fixtures` module defines synthetic articles used by
tests. Every payload is tagged with `_synthetic: True`.

The `PerformanceStore` refuses to write any payload that carries
`_synthetic: True`. The `rebuild_latest()` method also excludes
synthetic payloads from its counts.

This guarantees that synthetic test data NEVER enters the production
performance store, even if a test path accidentally bypasses the
public API.

---

## 12. Privacy / Public Data Boundary

The Performance module only stores:

- Public metrics already exposed by the platform (views, likes,
  comments, shares, reposts).
- Public metadata (publisher name, content URL, title).
- Radar-side context (radar_status, verification_status, confidence,
  momentum) — these are MY Hot Radar's own internal data, not
  competitor data.

It does NOT store:

- Private user identifiers.
- Authenticated / non-public metrics.
- IP addresses, session data, or anything beyond what is publicly
  visible per the platform's data policy.
- Internal platform algorithms (engagement-boost coefficients,
  feed-ranking scores, etc.).

---

## 13. Limitations

- No real data is collected yet. P1 only stores synthetic fixtures
  used by tests.
- No market / competitor data exists in production. P1's
  `MarketObservation` and `Insight` are schemas, not data.
- Performance classification is descriptive, not predictive. It
  cannot say what will happen next.
- Confidence intervals are NOT computed. P1 returns a single
  `PerformanceClass` per observation, not a distribution.
- Cross-platform aggregation is intentionally not implemented. Any
  P2/P3 code that wishes to aggregate must justify it explicitly.
- The current heuristic feature extraction (person name, number,
  etc.) is conservative. It is meant to flag candidates for review,
  not to assert facts about the underlying news.

---

## 14. P1 Scope

What P1 DOES:

- Define all data models (`ContentIdentity`, `PerformanceSnapshot`,
  `PerformanceObservation`, `ContentFeatureSnapshot`,
  `MarketObservation`, `Insight`).
- Define validation rules for each model.
- Provide deterministic ID helpers.
- Provide pure analysis helpers (`compute_observation`,
  `classify_performance`, `engagement_rate`, `extract_features`,
  `classify_late_breakout`).
- Provide atomic, filesystem-backed persistence (`PerformanceStore`).
- Provide synthetic fixtures tagged `_synthetic: True`.
- Provide 49 unit tests covering model validation, null/zero
  distinction, negative-delta handling, classification, OWN/MARKET
  separation, platform separation, atomic-write failure preservation,
  and synthetic-data rejection by the production store.

What P1 does NOT do (deferred to later batches):

- Any data collection (no crawler, no API).
- Any LLM-based analysis.
- Any auto-publishing.
- Any change to Radar / Candidate / Website / public JSON.
- Any change to the political-neutral guardrail.
- Any cross-platform aggregation.
- Any Insight generation from real data.

---

## 15. Related Files

- `radar/candidate.py` — the previous observation layer (Article
  Candidates). Independent of Performance Intelligence; the two
  systems do not share data.
- `radar/sources_registry.py` — public source list (Tier A / B / C).
  Not directly used by Performance Intelligence; future batches
  may use it to derive publisher metadata.
- `CONTENT_RULES.md` — rules for published content. Performance
  data is observed; it is NOT "published content". Performance
  data must never appear on the website or on Facebook.

---

## 16. Future Batches (suggested)

1. **P2 — Source adapters + collectors.** Add platform-specific
   adapters (one per platform) that produce `PerformanceSnapshot`
   and `MarketObservation` records. Each adapter must be approved
   via documentation before it is added. Cron-driven collection.
2. **P3 — Insight builder.** Aggregate OWN + MARKET data under
   common axes; produce `Insight` records with strict observation
   / hypothesis / limitations split. Must integrate with the
   editorial review workflow.
3. **P4 — Optional Radar feedback.** Only after P2 + P3 are
   stable and proven safe, decide whether Performance data
   should feed back into Radar as additional evidence. This is
   explicitly out of scope for the next batches; do not propose
   it unless the editorial team approves.
