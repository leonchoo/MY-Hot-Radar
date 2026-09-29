# Performance Intelligence — Android Bridge (Design Contract, pre-P3-B)

**Status:** Capability Assessment + Contract + Tests — PASS
**Stage:** Pre-P3-B design. **No real Android / Facebook integration.**
**Blocker for P3-B:** waiting for android-collector's first-stage
verification report to confirm what its public-page observation can
actually observe.

---

## A. Current Performance Capability (after P3-A)

The P3-A adapter framework is fully prepared to receive observations
from any source. The relevant layers:

| Layer | Component | Status |
|---|---|---|
| Status enum | `RetrievalStatus` (AVAILABLE / PARTIAL / UNAVAILABLE / RATE_LIMITED / NOT_SUPPORTED / INVALID_SOURCE / ERROR) | ready |
| Capability enum | `AdapterCapability` (ARTICLE_METADATA / VIEWS / LIKES / COMMENTS / SHARES / REPOSTS) | ready |
| Data-access enum | `DataAccess` (PUBLIC / PRIVATE / SYNTHETIC) | ready |
| Platform enum | `Platform` (WEBSITE / FACEBOOK / INSTAGRAM / TIKTOK / YOUTUBE / X / OTHER) | ready |
| Per-row shape | `AdapterObservation` (content_id, platform, observed_at, retrieval_status, source, source_url, title, published_at, url, views, likes, comments, shares, reposts, unavailable_reason, extra) | ready |
| Batched shape | `AdapterResult` (source_name, platform, started_at, finished_at, retrieval_status, observations[], errors[]) | ready |
| Quality check | `check_observation_quality` (timestamp valid, published_at ≤ observed_at, metric ≥ 0, no duplicate content_id, AVAILABLE rows must have metric or reason) | ready |
| Validation | `validate_adapter_result` | ready |
| Real adapter | `BernamaRssAdapter` (PUBLIC, RSS 2.0, BERNAMA National News Agency) | shipped |
| Fixture adapter | `SyntheticAdapter` (SYNTHETIC, in-memory only, tagged) | shipped |
| P2 story layer | `StoryCluster`, `StoryMatch`, `PackagingSnapshot`, `StoryComparison` | unchanged |
| P1 storage | `PerformanceStore` (gitignored `performance_data/`) | unchanged |

**Android observations can use the same `AdapterObservation` shape
without any schema change.** The Bridge layer in this document is a
**translation contract**, not a schema change.

## B. Android Collector Future Input Format

The android-collector Agent will hand MY Hot Radar rows in the shape
defined by `performance.android_bridge.AndroidObservationInput`:

```
{
  "observation_id": "...",      # per-capture id, distinct from post_id
  "platform": "FACEBOOK",       # Platform enum value
  "observed_at": "ISO 8601 UTC",
  "publisher": "Free Malaysia Today",
  "post_url": "https://...",
  "page_url": "...",            # optional, distinct from post_url
  "title": "...",
  "caption": "...",
  "published_at": "ISO 8601",   # optional
  "views": 15000,               # each independently Optional[int]
  "likes": 320,
  "comments": 42,
  "shares": 15,
  "reposts": null,              # not visible on this page
  "evidence": {                 # metadata only, NEVER binary
    "evidence_type": "SCREENSHOT",
    "reference": "/tmp/.../obs_001.png",
    "captured_at": "ISO 8601",
    "screen_width": 1080,
    "screen_height": 2400,
    "device_model": "Pixel 7",
    "os_version": "14",
    "notes": "..."
  },
  "retrieval_status": "AVAILABLE",
  "unavailable_reason": null,
  "notes": "..."
}
```

**Hard rules for Android Collector (and for the bridge):**

1. Every metric field is independently `Optional[int]`. If a page
   does not show "shares", the field is `None`, never `0`.
2. `retrieval_status` is one of the 7 P3-A enum values. The Bridge
   does not invent new statuses.
3. `evidence.reference` is a string (path or URI). **No base64 or
   binary blobs in JSON.** Screenshots, UI dumps, and OCR output
   live on the android-collector host filesystem.
4. `observation_id` is unique per capture event. The same post
   observed twice at two timestamps gets TWO different
   observation_ids but the SAME `content_id` (derived from
   `post_url`). This is how P1's `compute_observation` builds
   deltas.
5. Android Collector is forbidden from inventing engagement
   metrics by estimating from any non-public signal.

## C. Fields directly reused from P3-A

| Android input | P3-A AdapterObservation field | Notes |
|---|---|---|
| `platform` | `platform` | passed through |
| `observed_at` | `observed_at` | passed through |
| `retrieval_status` | `retrieval_status` | one of 7 values |
| `unavailable_reason` | `unavailable_reason` | passed through |
| `post_url` | `source_url`, `url` | passed through |
| `title` | `title` | passed through |
| `published_at` | `published_at` | passed through |
| `views`, `likes`, `comments`, `shares`, `reposts` | same names | `None` preserved |
| `page_url` | `extra["page_url"]` | no first-class field in P3-A |
| `caption` | `extra["caption"]` | no first-class field in P3-A |
| `publisher` | `extra["publisher"]` | no first-class field in P3-A |
| `evidence` | `extra["evidence"]` (as dict) | no first-class field |
| `notes` | `extra["notes"]` | diagnostic only |
| `observation_id` | `source = "android_bridge::<observation_id>"` | traceable |
| derived from `post_url` | `content_id` | deterministic SHA-256 prefix |

## D. Fields added by the bridge

The bridge does NOT extend `AdapterObservation` or any P1 model.
All Android-specific fields live in `AdapterObservation.extra` as
a JSON dict. This keeps P1 / P3-A schemas stable and ensures
**forward compatibility**: if P3-B later promotes some of these
fields to first-class, the bridge output still validates.

Future optional promotion candidates (deferred):

| Field | Would become | Why deferred |
|---|---|---|
| `publisher` | first-class on `AdapterObservation` | not in P3-A scope |
| `caption` | first-class | P3-A shape uses `title` |
| `evidence` | new `Evidence` field type on `AdapterObservation` | needs cross-cutting schema review |
| `observation_id` | first-class | P3-A uses `source` for trace |

## E. Evidence design

`Evidence` is metadata only:

```
Evidence(
    evidence_type=EvidenceType,        # SCREENSHOT | UI_TEXT | UI_NODE | OCR | COMPOSITE
    reference=str,                     # path on android-collector host
    captured_at=str,                   # ISO 8601 UTC
    screen_width=Optional[int],        # pixels
    screen_height=Optional[int],       # pixels
    device_model=Optional[str],
    os_version=Optional[str],
    notes=Optional[str],
)
```

**Contract**:

* `reference` is a path or URI. Binary content (PNG, raw UI dump
  XML, OCR text file) is NEVER inlined in Performance JSON.
* `evidence_type` is one of the 5 enum values; new types require a
  future batch with editorial approval.
* `captured_at` is parseable as ISO 8601.
* `screen_width` / `screen_height` are positive integers when
  present.

**Traceability**: every AdapterObservation produced by the bridge
carries the evidence record under `extra["evidence"]`. The
observation can be audited: "likes = 1234 was observed at
2026-09-29T12:30:00Z, evidence reference = /tmp/.../obs_001.png".

## F. None / 0 semantics

The bridge **inherits** P3-A's strict None-vs-0 rule:

* `None` = "android-collector did not observe this metric on the
  visible page" — explicitly distinct from `0`.
* `0` = "the page showed 0".
* The bridge never coerces a `None` to `0`. Tests
  `test_android_none_not_coerced_to_zero`,
  `test_android_observed_zero_preserved`,
  `test_android_all_metrics_missing_is_valid` lock this.

Per-metric independence:

* `likes=None` does NOT force `comments` or `shares` to None.
* A row can have any combination of present / missing metrics.
* `views`, `likes`, `comments`, `shares`, `reposts` are
  independently optional.

## G. Facebook / Instagram / YouTube platform isolation

The bridge enforces:

* Each row's `platform` is preserved (FACEBOOK / INSTAGRAM /
  YOUTUBE / X / TIKTOK / OTHER).
* No row is merged with another row's metrics across platforms.
* The bridge output (a list of dicts) is suitable for projection
  into P1 `PerformanceSnapshot` records; P2 `StoryComparison`
  keeps per-platform rows distinct (existing rule from P2).
* Tests `test_android_platform_identity_preserved_per_row`,
  `test_android_no_cross_platform_aggregation_in_bridge` lock
  this.

The bridge itself **does not compute** any aggregate, ranking,
or cross-platform signal. It is a translation layer, not an
analysis layer.

## H. Same Story → Different Publisher data flow

This is the future use case. The data flow the bridge prepares
for:

```
android-collector
  -> [AndroidObservationInput] (multiple rows)
       ├── observation_id: obs_fb_FMT_001
       ├── platform: FACEBOOK
       ├── publisher: "Free Malaysia Today"
       ├── post_url: https://facebook.com/FMT/posts/...
       └── likes: 1500
       ├── observation_id: obs_ig_somepage_001
       ├── platform: INSTAGRAM
       ├── publisher: "SomePage"
       ├── post_url: https://instagram.com/p/...
       └── likes: 2300
       ├── observation_id: obs_yt_somenews_001
       ├── platform: YOUTUBE
       ├── publisher: "SomeNews"
       ├── post_url: https://youtube.com/watch?v=...
       └── likes: 400
        ↓
to_adapter_observation() per row
        ↓
AdapterObservation[] (preserved publisher / platform / metrics)
        ↓
Project to PerformanceSnapshot (P1) for storage + delta math
        ↓
P2 match_stories() decides which posts cluster
        ↓
P2 StoryCluster + StoryComparison
        ↓
Observed comparison (no ranking, no aggregation)
```

Important: the bridge output preserves `publisher` (in
`extra["publisher"]`) and `platform` per row. P2's
`StoryComparison` already keeps publisher / platform identities
distinct. No future batch changes P2 to rank them.

## I. Data currently unobtainable

Per spec §2, the bridge **does not assume** the following can be
obtained from any platform:

| Field | Status |
|---|---|
| `likes` | optional; `None` if not visible |
| `comments` | optional; `None` if not visible |
| `shares` | optional; `None` if not visible |
| `views` | optional; `None` if not visible |
| `reposts` | optional; `None` if not visible |
| `followers` | NOT in scope for the bridge |
| `reach` | NOT in scope |
| `impressions` | NOT in scope |
| `comment text` | NOT in scope (PII / private content risk) |
| `historical engagement` | NOT in scope; computed via delta between two snapshots only |

Image-feature inference (`has_face`, `face_count`, `primary_image_type`,
etc.) is **out of scope** until android-collector's first-stage
verification confirms what UI / OCR can reliably produce. The
bridge does not invent these; the bridge forwards whatever the
android-collector hands over, and if android-collector returns
`None`, the bridge keeps `None`.

## J. P3-B implementation prerequisites

P3-B (the real Facebook / Instagram / YouTube adapter) can ONLY
start after:

1. **android-collector first-stage verification report** —
   concrete demonstration of:
   - What public pages it can reach (without login / cookie /
     token extraction).
   - What UI elements it can reliably extract
     (likes / comments / shares / views / reposts / etc.).
   - What image / video features it can identify vs. what it
     cannot.
   - Any known false-merge / misclassification risks.
2. **P3-B Adapter implementation** that consumes the verified
   Android output and produces `AdapterObservation[]` per the
   bridge contract defined here.
3. **P3-B tests** that:
   - Pin the verified capabilities to specific platform pages.
   - Confirm `None` vs `0` semantics for any missing metric.
   - Confirm `Sample 19` false-merge regression still PASS with
     Android-sourced observations.
   - Confirm political observations remain descriptive-only.

**Until step 1 completes, P3-B cannot be designed.** Speculative
P3-B based on assumed Facebook data would risk the exact
behaviors spec §2 forbids (fabricating engagement, treating
unknown as zero, inferring support).

---

## Summary

| Item | Decision |
|---|---|
| New code | `performance/android_bridge.py` (translation layer) + tests |
| Modified code | `performance/__init__.py` (additive exports) + `tests/run_all.py` (wire tests) |
| Modified P1 / P2 / P3-A | None — strictly additive |
| Modified Radar / Candidate / Website | None |
| Real Facebook / Instagram / YouTube integration | **NOT implemented.** Waiting on android-collector verification. |
| Schema version | Unchanged at 3 |
| New fields on `AdapterObservation` | None; all Android-specific data lives in `extra` |
| `None != 0` | Enforced and tested |
| Platform separation | Enforced and tested |
| Political safety | Enforced and tested |
| P3-A tests | Still PASS (zero regression) |
| P1 tests | Still PASS |
| P2 tests | Still PASS |

## Test count

| Suite | Count |
|---|---|
| P1 (existing) | 49 / 49 PASS |
| P2 (existing) | 59 / 59 PASS |
| P3-A (existing) | 37 / 37 PASS |
| Android Bridge (new) | 39 / 39 PASS |
| Radar (existing, no touch) | 396 / 396 PASS |
| **Total** | **580 / 580 PASS** |

Android Bridge test coverage includes all 15 areas from spec
§13:

1. complete observation
2. missing likes / comments / shares / views (each separately)
3. `None != 0` (and observed 0 preserved)
4. invalid negative metrics
5. invalid timestamp
6. evidence metadata (no binary in JSON)
7. screenshot reference (path only)
8. platform separation (per-row, no aggregation)
9. deterministic observation_id and content_id
10. duplicate observation protection (same id + same timestamp rejected; same id + different timestamp allowed)
11. political observation descriptive-only
12. synthetic observation cannot enter production
13. evidence type validation
14. JSON serialization round-trip
15. no new retrieval_status values; no forbidden metrics (followers / reach / etc.)
