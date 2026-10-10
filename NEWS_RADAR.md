# MY Hot Radar — News Radar (Design Spec, NOT Yet Implemented)

> Design-only specification. No source code, no scheduler, no crawler.
> This document exists so that the future Radar can be built intentionally
> instead of drifting into ad-hoc scripts.

---

## Status

**Stage**: Design / pre-implementation.

The website is live in **MVP** mode. The Radar pipeline described here
**does not exist** in code today. Do not describe any of these stages as
running on the site or in social posts.

---

## Why a Radar (and not just an RSS reader)

The Radar's job is to score **propagation momentum**, not to summarize
news. A topic being "important" is not the same as being "heating up".
The Radar exists to separate those two signals.

---

## Pipeline

```
Sources
  ↓
Discovery
  ↓
Normalize
  ↓
Deduplicate
  ↓
Topic Clustering
  ↓
Cross-source Verification
  ↓
Momentum Detection
  ↓
Status Classification
  ↓
Radar Score
  ↓
Human / Automated Review
  ↓
Website / Social Publishing
```

Each stage is described below.

---

## Stage descriptions (intent only)

| Stage | Intent |
|---|---|
| Sources | Maintain a documented list of ingestible sources per platform/category. Add a source only after a documented reason and a calibration period. |
| Discovery | Pull in raw items from each source. The goal here is breadth, not judgment. |
| Normalize | Convert each item to a common shape: `id`, `title`, `body`, `url`, `lang`, `timestamp`, `source_id`, `platform`. Strip tracking parameters. |
| Deduplicate | Identify which items describe the same underlying event. Two items are duplicates only if they describe the **same event**, not just the same wording. |
| Topic Clustering | Group related items into a single "topic". A topic can have many items, across many sources, across many days. |
| Cross-source Verification | For each topic, record evidence and confidence. See `VERIFICATION_RULES.md`. |
| Momentum Detection | Track propagation signals across sources and platforms over time. Output a per-topic momentum curve, not a single number. |
| Status Classification | Classify the topic into one of: `BREAKING`, `RISING`, `HOT`, `WATCH`, `COOLING`. **Status is momentum, not importance.** |
| Radar Score | A composite, transparent score. Each input to the score must be recordable and explainable. |
| Human / Automated Review | A gating step before any publishing action takes effect. Humans override is always allowed. |
| Website / Social Publishing | Write to a chosen channel under the rules in `CONTENT_RULES.md` and `DEVELOPMENT_RULES.md`. Auto-publishing is currently **disabled**. |

---

## Status definitions

The Radar classifies a topic into one of these states.
These describe **topic momentum / propagation signals**, not news
importance, not news worthiness, and not moral weight.

| Status | Meaning |
|---|---|
| `BREAKING` | Just emerged AND already showing cross-platform or cross-source signals within a short window. Must have ≥ 2 independent sources or ≥ 1 official source + 1 secondary signal. |
| `RISING` | Heat is observably increasing: new sources, new platforms, or fast comment velocity over a defined window. |
| `HOT` | Has already reached broad cross-platform presence. Not the same as "important". |
| `WATCH` | Has potential. Signals too weak or too few to claim momentum yet. |
| `COOLING` | Was warming earlier; signals now decay. Still real, just no longer spreading. |

A topic MUST NOT be promoted to `RISING` or `HOT` purely because the
underlying event is consequential. Promotion requires propagation
evidence.

A topic can be demoted from `HOT` to `COOLING` automatically; this must
not require human approval (it is non-destructive).

---

## Sources — types

Documents the Radar's eventual source palette. None of this is
configured today.

### Primary / official
- Government press releases, royal statements, police/media statements
- BERNAMA / national wire
- Statutory bodies' official social accounts

### News media (curated list)
- Per platform, keep a documented list of credible outlets per category
- Each source has an entry describing: cadence, language(s), known biases,
  reliability notes, and recent error history.

### Social platforms (curated, not exhaustive)
- Facebook public pages of named outlets and named public figures
- TikTok public videos from named accounts
- X public posts from named accounts
- Instagram public posts from named accounts

### Aggregation / search signals
- Trending-topic widgets provided by the platforms themselves
- Public social-listening dashboards
- Search trend widgets (Google Trends public data)

### Exclusion list
- Sources with no accountability (anonymous aggregators, content farms,
  unverifiable portals).
- Sources on any platform-specific safety advisory list.

---

## Per-topic record (target shape)

Each topic should eventually carry at least:

```yaml
topic_id        : stable string
title           : human-readable summary, neutral
first_seen      : UTC timestamp
last_seen       : UTC timestamp
sources         : list of source ids
source_types    : official | media | social | aggregator
platforms       : facebook | tiktok | x | instagram | threads | news | …
status          : BREAKING | RISING | HOT | WATCH | COOLING
momentum_curve  : [{ts, score}, ...]
confidence      : 0.0–1.0 (transparent weighting)
evidence        : list of item ids + brief justification
notes           : human-authored caveats
last_reviewed_by : human or model id
last_reviewed_at : UTC timestamp
```

The exact schema will be locked when implementation starts. The fields
above are a target, not a binding spec.

---

## What the Radar is NOT

- Not a fact-checking system — that is `VERIFICATION_RULES.md`'s job.
- Not a content generation system — copy is written by humans (or
  human-supervised automation) under `CONTENT_RULES.md`.
- Not a publishing system — publishing is a separate, gated step.
- Not a sentiment analyzer — sentiment is not what we measure.

---

## Implementation guardrails (when work begins)

- One stage at a time. Do not build the whole pipeline in one batch.
- Every stage must be observable: emit data you can inspect later.
- Every transition must be reversible from data alone (no in-place
  mutation that loses the prior state).
- Every score / status decision must be stored with the inputs that
  produced it (no black-box-only outputs).
- Every "publish" action must pass a review gate.

---

## 国际新闻选题与核实（编辑规则，binding）

> 本节是**编辑规则**，由人工 / Agent 在执行国际新闻选题与采编时遵守；
> 它不是 Radar 管线的实现规范，不依赖 Radar 代码存在与否。
> 选题核实通过后的写作要求见 `CONTENT_RULES.md → International news editorial rules`；
> 发布后的线上验收见 `VERIFICATION_RULES.md → 发布后线上验收`。

- 国际新闻不必抢时间，优先选择事实稳定、资料充分、具有持续阅读价值的事件。
- 优先使用可靠的中国和美国来源交叉核实核心事实。
- 不要求中国和美国对事件立场一致。双方报道不同的时候，明确说明差异。
- 区分已经确认的事实、官方立场、媒体报道、争议说法和未经证实的推测。
- 优先查阅原始公告、官方文件及可靠媒体报道。
- 核心事实无法核实，或关键来源相互矛盾且无法合理解释时，暂缓发布。
- 不编造事实、引述、数据、事件时间线或预测。
