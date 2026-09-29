# Performance & Market Intelligence — P2: Story Clustering & Same-Story Comparison

**Status:** P2 (Story Clustering layer) — PASS
**Scope:** Same-story matching, packaging comparison, timing analysis,
observed-performance comparison across cluster members.

---

## 1. What P2 does

P2 adds an **observational story-clustering layer** on top of the P1
performance data layer. P2 helps answer one question:

> The same event is covered by multiple publishers in different
> ways — who said what, when, in what packaging, and what
> publicly-observable metrics did each piece of content get?

Concretely, P2 provides:

* `StoryCluster` — groups multiple content items covering the same
  underlying event.
* `StoryMatch` — explainable same-story decision with `matched`,
  `score`, and `reasons` (no LLM, no embedding API).
* `PackagingSnapshot` — descriptive features of how a publisher
  packaged a single piece of content (headline, caption, image
  metadata). All fields are descriptive. None is a quality score.
* `StoryComparison` — observed per-member metrics within a cluster,
  with `NORMALIZED_COMPARISON_UNAVAILABLE` flagged whenever the
  follower baseline is not present (which is always, in P2).
* Deterministic same-story matching with priority:
  1. exact `topic_id`
  2. exact `canonical_key`
  3. title similarity (prefix-4-stem Jaccard)
  4. entity overlap (>= 2 known entities)
  5. location overlap + title similarity (any strength)
  6. date/time proximity (within 168 hours)
  7. category compatibility
* Deterministic feature extraction for headline / caption / image.
* Five synthetic Story Clusters covering the required scenarios:
  same story / different packaging, same story / different timing,
  fast growth case, slow growth case, insufficient metrics, and a
  false-merge case (Sample 19 regression).

## 2. What P2 does NOT do

* ❌ No Facebook API / Instagram API / TikTok API / YouTube API / X API
* ❌ No cookie scraping, no browser automation
* ❌ No bypassing robots / rate limits / access controls
* ❌ No ranking publishers ("best", "top", "winner")
* ❌ No predicting virality
* ❌ No causal inference ("because the headline used X, the post did Y")
* ❌ No automatic copy of competitor content
* ❌ No modification of Radar / Candidate / verification / source registry
* ❌ No automatic publishing
* ❌ No political ranking ("politician A more popular than B")
* ❌ No electoral support inference from public engagement
* ❌ No LLM, no embedding API, no black-box AI for matching
* ❌ No fabricated performance data — all observed metrics are null
  until real observations arrive

## 3. Same-Story Matching (Deterministic, Explainable)

`match_stories(...)` returns a `StoryMatch` with:

* `matched: bool` — yes / no
* `score: float` — internal confidence (0.0 .. 1.0), not a quality score
* `reasons: List[str]` — machine-readable explanation

Strict matching rules:

* Different `category` ⇒ instant `matched=False` (`category_mismatch`).
* Unparseable timestamp ⇒ conservative `matched=False`.
* Date > 168 hours apart ⇒ `date_proximity` not granted.
* The same-stories must hit one of:
  * exact `topic_id` match
  * exact `canonical_key` match
  * category compatible + date proximity + named entity overlap (>=2)
  * category compatible + date proximity + location overlap + (strong OR weak title similarity)
  * category compatible + date proximity + strong title similarity alone

Title similarity uses Jaccard on a **prefix-4 stem** representation
plus an English-suffix stemmer, plus the raw stopword-stripped form.
The three signals are combined as `max(raw, stemmed, prefix4)` so
inflection noise ("charge" / "charged") and partial overlap don't
kill otherwise good matches.

### False-merge regression

The Chinese Editorial Review Sample 19 case ("AI crocodile image
leads to search operation" vs "Google faces EU antitrust action
over AI search") must NOT merge. Both titles mention `AI` and
`search`, but neither shares a known entity, location, or strong
content overlap. The matcher correctly returns `matched=False`
with `normalized_title_similarity_weak` in reasons.

## 4. Packaging Snapshot

`PackagingSnapshot` records:

* **Headline features**: length, has_person_name, has_location,
  has_number, has_question, has_quote, has_time_reference,
  has_exclamation, headline_style (INFORMATIVE / QUESTION /
  EXCLAMATORY / QUOTE).
* **Caption features**: same set, optional (None when no caption).
* **Image features**: image_count, primary_image_type (one of
  EVENT_SCENE / LOCATION_SCENE / CLOSE_UP / WIDE_SHOT /
  DOCUMENT_IMAGE / SCREENSHOT / GRAPHIC / COLLAGE / VIDEO_FRAME /
  OTHER), has_text_overlay, has_face, face_count, person_count,
  boolean flags per shot type.

**Image features are descriptive facts only.** Unknown image
features stay `None`. They are NEVER coerced to `False`. The
distinction matters because:
* `None` = "we did not observe / no data"
* `False` = "we observed and the image does not have this attribute"

Confusing them would let us silently drop real images from analysis.

## 5. Timing Analysis

`timing_offsets(cluster, story_first_seen=None)` returns
`{content_id: minutes_from_first_seen}` for every member.

`minutes_between(earlier, later)` returns the signed minute
difference or `None` on bad input. Negative values are returned
unchanged so the caller can spot ordering bugs; this module never
swaps arguments silently.

`story_cluster.first_seen_at` is the earliest published_at across
all members, by construction in `_mk_cluster`.

## 6. Same-Story Performance Comparison

`build_story_comparison(cluster, member_performance_rows, ...)`
returns a `StoryComparison` with:

* `publisher_count`, `platform_count` (count of distinct values)
* `first_publisher`, `first_publish_at` (earliest published_at)
* `member_performance[]` — per-content observed metrics, in input order
* `performance_window` — `[from, to]` over which metrics were observed
* `normalized_comparison_available: False`
* `unavailable_reason: "follower_baseline_unavailable"` (default) or
  `"no_observations"` (when zero rows given)

### What is NOT in the comparison

* No "best publisher", "worst publisher", "top competitor"
* No ranking of publishers against each other
* No `score` / `rank` / `winner` fields
* No cross-platform aggregation into a single number
* No normalized engagement rate (because follower / reach baseline
  is not collected in P2)
* No causal language ("Media B got more views because of ...")

### What IS in the comparison

* Absolute observed metrics, exactly as captured (null-safe)
* Per-platform separation: Facebook metrics stay in the FACEBOOK
  member row, TikTok metrics stay in the TIKTOK member row
* Honest flag: `normalized_comparison_available=False` whenever
  we cannot normalize — the module never silently fabricates a
  fair comparison

## 7. Spec coverage

| Spec requirement | Implementation | Test |
|---|---|---|
| §3 StoryCluster model | `performance/story.py` `StoryCluster` | `test_story_cluster_*` |
| §3 deterministic matching | `match_stories` | `test_match_*` |
| §4 explainable match result | `StoryMatch.matched/score/reasons` | `test_match_*` |
| §5 false-merge Sample 19 regression | matcher + `test_match_different_story_false_merge_sample_19` | same |
| §5 same-story / different-wording | matcher + `test_match_same_story_different_wording` | same |
| §6 PackagingSnapshot | `performance/story.py` `PackagingSnapshot` | `test_build_packaging_*` |
| §7 image features stay None when unknown | `build_packaging_snapshot` keeps `None` | `test_build_packaging_image_features_partial` |
| §7 image features preserved as-is | `build_packaging_snapshot` | `test_build_packaging_image_features_true` |
| §8 headline/caption features | `extract_headline_features` | `test_build_packaging_*` |
| §9 publication timing | `timing_offsets`, `minutes_between` | `test_timing_offsets_*`, `test_minutes_between_*` |
| §10 StoryComparison | `build_story_comparison` | `test_story_comparison_*` |
| §11 NORMALIZED_COMPARISON_UNAVAILABLE | always set when baseline missing | `test_story_comparison_normalized_unavailable` |
| §12 platform separation | member_performance preserves platform per row | `test_story_comparison_different_platform_kept_separate` |
| §13 no ranking | dict-shape test forbids ranking keys | `test_story_comparison_dict_shape_no_ranking_fields` |
| §14 five synthetic clusters | `_fixture_crocodile/subsidy/celebrity/food/world_story` | `test_synthetic_clusters_minimum_five` |
| §15 matching tests | full battery in `test_story.py` | 20+ matching tests |
| §16 docs | this file | n/a |

## 8. Relationship to Radar

P2 only **reads** Radar context fields via `ContentFeatureSnapshot`
from P1. It does **not**:

* modify Radar / Candidate / verification / source registry
* modify the politics guardrail
* modify the scheduler
* modify the website JSON

`PackagingSnapshot` and `StoryComparison` may carry Radar-derived
context (when used for OWN content), but only as **observations**.
They never write back.

## 9. Political content

Per spec §18, political / election content is **observational only**:

* Topic clustering is allowed
* Headline / caption comparison is allowed
* Timing comparison is allowed
* Public engagement metrics may be observed and recorded

Forbidden:

* "Politician A more popular than B"
* Inferring voter preference from engagement metrics
* Predicting election results
* Ranking candidates / parties
* Treating `engagement_rate` as political support

`PackagingSnapshot` and `StoryComparison` do not encode any of the
above, by design. They record what was observed, period.

## 10. Tests

| Suite | Count |
|---|---|
| P1 (existing, must remain green) | 49 |
| P2 (new, this batch) | 59 |
| **Total Performance tests** | **108** |
| **Radar tests** (no regression) | **396** |
| **Grand total** | **504** |
| **Failures** | **0** |

P2 test coverage:

* 13 story-matching tests (same-story, different-story, paraphrase,
  multilingual, false-merge Sample 19, exact topic_id override,
  exact canonical_key override, same-content-id auto-match,
  same-entity-different-event, same-location-different-event,
  unparseable timestamp, too-far-apart-in-time, score bounded,
  deterministic)
* 7 packaging tests (basic, question, exclamation, quote, caption,
  image features true, image features partial / null semantics)
* 4 packaging validation tests (bad style, negative counts,
  bad image type, validation accepts valid)
* 4 timing tests (basic, negative ordering, invalid, with explicit
  first_seen)
* 7 story-comparison tests (same-platform, different-platform,
  null metrics, normalized unavailable, first publisher, no
  observations, dict-shape no-ranking-fields)
* 5 story-cluster validation tests (basic, empty, duplicate
  content_id, invalid url, round-trip)
* 4 normalize/similarity/extract-location tests (drop stopwords,
  stemmer keeps root, jaccard, locations known / unknown / dedup)
* 2 entity extraction tests (dedup, non-string robustness)
* 5 deterministic-ID tests (cluster id, canonical key, order-independent)
* 5 synthetic fixture tests (>=5 clusters, each with >=3 publishers,
  distinct platforms, distinct categories, isolation)
* 1 end-to-end test (3 publishers, same event, different packagings)
* 1 packaging round-trip test

## 11. Production safety

P2 is purely additive on top of P1:

* ✅ `/performance_data/` is gitignored
* ✅ No new files in `radar_data/`
* ✅ No new files in `public/`
* ✅ No changes to website HTML / JS / CSS
* ✅ No changes to Radar / Candidate / scheduler
* ✅ No changes to source registry / politics guardrail
* ✅ No changes to AdSense / sitemap / legal pages
* ✅ Story clusters are NOT auto-published; they are observational only
* ✅ No automatic fetching of competitor data
* ✅ No background processes added

Production verification (after deploy):

* ✅ `https://myhotradar.com/` → 200
* ✅ `https://myhotradar.com/article/example/` → 200
* ✅ `https://myhotradar.com/public/radar/latest.json` → 200 (shape unchanged)

## 12. Limitations

* Multilingual title matching without translation is limited. Two
  titles in different languages that don't share a known entity
  (person name in Roman script, location in Roman script) will
  not match. This is a deliberate trade-off: cross-language
  matching without embeddings is unreliable, so we refuse to guess.
* Image features depend on upstream observations. P2 stores them
  as-is; it does not run any vision model. If a publisher does
  not supply `has_face`, that field stays `None`.
* The `NORMALIZED_COMPARISON_UNAVAILABLE` flag is **always** set
  in P2 because follower / reach baseline data is not collected.
  This is honest reporting: the comparison shows what was
  observed, without claiming equivalence across publishers of
  different sizes.
* Same-story matching is conservative. Stories that humans might
  judge as the "same event" but share no known entity or strong
  content-word overlap will not match. This is intentional —
  false merges are worse than false splits.

## 13. Next batch (suggestion only — not auto-started)

* **P3 (Source Adapters)**: per-platform collectors that feed
  `PerformanceSnapshot` and `MarketObservation` from public,
  documented APIs. Each adapter goes through its own review pass
  and is independent.
* **P4 (Insight builder)**: produces `Insight` records from a
  window of observations. Only when sample size >= threshold. No
  LLM.
* **P5 (Radar feedback)**: optional, only if editorial team
  approves. Treats observed engagement as one input among many.
