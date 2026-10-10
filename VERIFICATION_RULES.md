# MY Hot Radar — Verification Rules

> Rules the future Radar will apply when deciding if a topic — and the
> individual claims inside it — is real, accurate, and confidently
> conveyable to readers.

---

## Why this exists

The Radar's job is to **detect momentum**, but it is useless (and
actively harmful) if it surfaces misinformation at the same rate as
real news. Every topic that graduates past `WATCH` must carry
verifiable evidence.

---

## Per-topic minimum record

For every topic the Radar tracks, it must eventually carry at least:

| Field | Purpose |
|---|---|
| `topic_id` | Stable string id. |
| `title` | Neutral, factual, short. |
| `first_seen` | UTC timestamp. |
| `last_seen` | UTC timestamp. |
| `sources` | List of source ids. |
| `source_types` | official / media / social / aggregator. |
| `platforms` | facebook / tiktok / x / instagram / threads / news / ... |
| `status` | BREAKING / RISING / HOT / WATCH / COOLING. |
| `momentum_curve` | Per-window sample, not a single number. |
| `evidence` | Item ids and a one-line note per item. |
| `confidence` | 0.0–1.0, transparent weighting. |
| `notes` | Caveats, counter-signals, contradictions. |

This is the **minimum**. A real implementation may carry more.

---

## Source credibility tiers

When weighing evidence, classify each source:

| Tier | Examples |
|---|---|
| A — Official / authoritative | Government press release, police/media statement, BERNAMA wire, royal statement, statutory body's official account. |
| B — Established outlet | Major broadsheet or wire with documented corrections record. |
| C — Secondary or niche outlet | Smaller outlet, lower reach, weaker corrections history. |
| D — Social primary | First-hand eyewitness post from a verifiable individual account. |
| E — Social echo / forward | Other-than first-hand: someone sharing, quoting, or commenting. |
| F — Anonymous / unaccountable | Anonymous portals, content farms, no verifiable operator. |

Tier F sources may be used as **discovery** inputs only. They are not
admissible as evidence for any CONFIRMED claim.

---

## "Multi-source" trap (binding)

Two outlets repeating the same wire item is **one** source of origin,
not two.

A topic qualifies as multi-source-verified only if the underlying items
do not all trace back to a single originating source.

The Radar must store the **provenance** of each item, not just its URL,
to detect this.

---

## Cross-platform signal — what counts

Cross-platform presence is **signal**, not **proof**. Used alone, it is
not enough for CONFIRMED. Used together with source distribution, it
strengthens confidence.

A cross-platform signal is met when the same topic appears in at least
two platforms (e.g. Twitter + Facebook + Reddit), ideally with first-hand
items, not just shares.

A first-hand eyewitness item on even one verified account carries more
weight than a hundred re-shares.

---

## Timestamp discipline

Each item must carry a `published_at` (UTC). Detection of:

- Coordinated bursts (many items, identical timestamps).
- Delayed re-surfacing (old item reposted with new context).
- Stale aggregators (cached item republished by an aggregate).

Each of these situations is a known anti-pattern. The Radar should
either flag them explicitly or down-weight them.

---

## Counter-signals (binding — must be looked for)

When classifying a topic as `RISING` or above, the Radar must **search
for**, not assume absent:

- Official clarification / denial of the claim.
- A competing credible account of the same event.
- A corrections notice from a primary source.

If a credible counter-signal exists, the topic drops at least one
status rung. A confirmed official denial = topic is `RUMOUR` /
`UNVERIFIED`, regardless of how viral the claim ran.

---

## Status ladder vs. confidence

The status (`RISING`, `HOT`, ...) and the confidence score are two
different dimensions:

| Status says | "How fast is this spreading?" |
| Confidence says | "How sure are we this is what we say it is?" |

A topic can be `RISING` (fast spreading) with **low** confidence (the
underlying claim is contested). In that case, the fact-status label on
published copy must reflect low confidence, while the Radar label
reflects spread.

---

## Minimum evidence for status promotion

| Promotion | Minimum evidence (binding) |
|---|---|
| `WATCH` → `RISING` | At least two independent platforms or sources, one of which is Tier B or above. |
| `RISING` → `HOT` | At least three independent platforms or sources, with at least one Tier A or B; no open official counter-signal. |
| Any → `BREAKING` | Tier A statement, plus one other independent corroboration. Plus recency window respected. |
| Demotion to `COOLING` | Decay curve. No human approval needed. |

Where "independent" means: not all items trace to a single origin.

---

## Prohibited claims regardless of status

A claim cannot be published under MY Hot Radar brand, even if `RISING`,
in any of the following scenarios:

- Only Tier F sources support it.
- The only "evidence" is shares, not new first-hand items.
- A Tier A source has officially denied or corrected the claim.
- The claim relies on a single photo or video that cannot be
  independently verified through time, location, or provenance.
- The claim requires identifying a private individual, and no Tier A
  or B source has identified that individual by name.

---

## What verification is NOT

- Not a political-judgment call. Verification does not endorse or
  oppose; it answers "is the claim consistent with current public
  evidence?".
- Not a permanent verdict. Verification decays; topics must be
  re-checked.
- Not a sentiment or popularity judgment.

---

## Implementation note

This document is the **target** for verification behavior. The Radar
must enforce these rules **at the time of publishing**, not after.
A topic that has not met the minimum-evidence bar must not appear in a
publishable view — it stays in an internal `WATCH` state.

---

## 发布后线上验收（binding，适用于每篇发布文章）

每篇文章发布后，Agent 必须亲自检查**真实线上页面**，而不能只看本地文件或 Git 操作结果。

至少检查：

- 文章详情页是否显示正确正文。
- 对应分类页是否实际显示该文章。
- 首页是否按照现有收录规则展示文章。
- Sitemap 是否包含正确 URL。
- 点击分类列表中的文章，是否能打开正确详情页。
- 页面是否仍存在占位内容、错误导航、旧列表或缓存问题。

每项必须报告 `PASS / FAIL / UNKNOWN`，并提供实际 URL 和证据。

**文章详情页可访问，不代表分类收录成功；Git push 成功，也不代表发布验收通过。**
如果文章应该出现在分类页却没有出现，必须调查分类数据源、索引生成和部署流程，
不能直接宣布发布成功。
