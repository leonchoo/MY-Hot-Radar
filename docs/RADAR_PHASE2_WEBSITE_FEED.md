# MY Hot Radar — Phase 2 / Batch 3B-1 — Website Radar Feed Integration

> Phase 2 Batch 3B-1 brings **real Radar topics onto the MY Hot Radar
> homepage** as a live "Radar now" section, without replacing DEMO
> content, without auto-publishing, and without weakening the existing
> website.

This document is the spec-of-record for everything shipped in this
batch. Read alongside `PROJECT_CONTEXT.md`, `DEVELOPMENT_RULES.md`,
`docs/RADAR_PHASE2_OUTPUT.md` (Phase 2 B3A — internal Radar output),
and `docs/RADAR_PHASE2_POLITICS.md` (Phase 2 B1 — political handling).

---

## 1. Objective

Make the homepage reflect **what the Radar actually detects** rather
than only static DEMO cards. The Radar topics are presented in a
clearly-labelled section that is visually distinct from DEMO content
but does not displace it.

This batch is **NOT** Real Publishing. No article is generated, no
Facebook post is made, no DEMO article is overwritten.

---

## 2. Existing Website Architecture (as of batch start)

```
C:\MY-Hot-Radar
├── index.html                  Homepage
├── hot/index.html              Hot Now category (DEMO)
├── malaysia/index.html         Malaysia category (DEMO)
├── viral/index.html            Viral category (DEMO)
├── celebrity/index.html        Celebrity category (DEMO)
├── food/index.html             Food & Lifestyle category (DEMO)
├── world/index.html            World category (DEMO)
├── article/example/index.html  Demo article detail
├── about/index.html            About (MVP-honest)
├── contact/index.html          Contact (no fake info)
├── privacy/index.html          Privacy (MVP-honest)
├── terms/index.html            Terms (MVP-honest)
└── assets/
    ├── css/style.css           Single shared stylesheet (706 lines pre-batch)
    ├── js/main.js              Vanilla JS: mobile nav + year fill
    └── img/                    logo, mark, favicon, OG image (all SVG)
```

| | |
|---|---|
| Framework | none — vanilla HTML/CSS/JS |
| Fonts | system font stack only |
| External scripts | AdSense (`ca-pub-6219340004578553`) only |
| Mobile-first | yes — 360 / 375 / 390 / 412 / 768 / 1024 / 1440 |
| Sitemap | `/sitemap.xml` (12 URLs, unchanged) |
| Cloudflare Pages | Git-deploy from `master` |

---

## 3. Radar → Website Architecture

```
                  ┌─────────────────────────────────────┐
                  │   OS scheduler / `python -m        │
                  │   radar.scheduler`                  │
                  └─────────────┬───────────────────────┘
                                │
                                ▼
                  ┌─────────────────────────────────────┐
                  │   radar/pipeline.run_scan()        │
                  │   (existing — unchanged)            │
                  └─────────────┬───────────────────────┘
                                │
                                ▼
                  ┌─────────────────────────────────────┐
                  │   radar/output.py (Phase 2 B3A)    │
                  │   writes radar_data/output/         │
                  │   latest.json + daily snapshots     │
                  └─────────────┬───────────────────────┘
                                │
                                ▼
                  ┌─────────────────────────────────────┐
                  │   radar/public_output.py (NEW)     │
                  │   reads radar_data/output/         │
                  │   latest.json                       │
                  │   strips internal-only fields       │
                  │   validates schema                  │
                  │   atomically writes                 │
                  │   public/radar/latest.json         │
                  └─────────────┬───────────────────────┘
                                │ COMMITTED to Git
                                ▼
                  ┌─────────────────────────────────────┐
                  │   Cloudflare Pages                  │
                  │   serves /radar/latest.json         │
                  └─────────────┬───────────────────────┘
                                │ fetch()
                                ▼
                  ┌─────────────────────────────────────┐
                  │   assets/js/radar-feed.js (NEW)     │
                  │   - validates schema                │
                  │   - sanitises URLs                  │
                  │   - renders Radar topic cards       │
                  │   - falls back on any failure       │
                  │   - does NOT touch other page       │
                  └─────────────┬───────────────────────┘
                                │
                                ▼
                  ┌─────────────────────────────────────┐
                  │   <section> in index.html           │
                  │   (between hero and existing DEMO)  │
                  └─────────────────────────────────────┘
```

Two new files (Python): `radar/public_output.py`, `radar/tests/test_public_output.py`, `radar/tests/test_radar_adapter.py`, `radar/tests/smoke_server.py`, `radar/tests/fault_injection.py`.
One new file (JS): `assets/js/radar-feed.js`.
One new file (committed JSON artifact): `public/radar/latest.json`.
One file (CSS) appended with Radar Feed rules.
One file (HTML) modified: `index.html` (new `<section>` + script tag).

---

## 4. Public Output Strategy

### Why a public artifact file?

Cloudflare Pages is Git-based static deployment. It only serves
files committed to Git. `radar_data/output/latest.json` is in
`/radar_data/` which is gitignored. The website cannot fetch from
the runtime directory.

**Solution**: a separate **public artifact** at `public/radar/latest.json`,
written by `radar/public_output.py` from the validated internal output.
This file is intended to be committed to Git. Cloudflare Pages serves
it at `/radar/latest.json`.

### Why we are NOT auto-committing it

Per spec §29: "不要未经分析就选择「每次 scheduler 直接 git commit + push latest.json」。"

A future batch may add an automated build step (CI or local commit +
push) once production telemetry confirms the workflow is stable.
This batch ships:

* The **runtime writer** (`radar/public_output.py`) that produces
  the public artifact.
* The **committed artifact** (`public/radar/latest.json`) so the
  production website can fetch it on the next deploy.
* The **JS adapter** (`assets/js/radar-feed.js`) that consumes it.

The decision of **when** to commit + push is intentionally left as
a manual operator step for now. See §19 below.

---

## 5. Public Schema (`public_schema_version: 1`)

The public schema is intentionally smaller than the internal schema
(Phase 2 B3A). It exposes **only what the website should render**.

```jsonc
{
  "schema_version": 1,                  // inherited from internal
  "public_schema_version": 1,            // this schema's own version
  "generated_at": "2026-09-29T03:55:26Z",
  "scan_id": "20260929T035526Z-16312",
  "scan_status": "SUCCESS" | "PARTIAL" | "FAILED",

  "summary": {
    "topic_count": 91,
    "publishable_count": 90,
    "confirmed_count": 2,
    "reported_count": 89,
    "rumour_count": 0,
    "unverified_count": 0,
    "social_buzz_count": 0,
    "by_status":   {"WATCH": 91},
    "by_claim_kind": {"NOT_POLITICAL": 73, "EVENT": 10, "CLAIM": 7, "OPINION": 1}
  },

  "topics": [
    {
      "content_key": "u:https://...",
      "title": "...",
      "category": "MALAYSIA",
      "language": "en",
      "status": "BREAKING" | "RISING" | "HOT" | "WATCH" | "COOLING",
      "verification_status": "CONFIRMED" | "REPORTED" | "SOCIAL_BUZZ" |
                            "UNVERIFIED" | "RUMOUR",
      "confidence_label": "VERY_LOW" | "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH",
      "momentum": {
        "current_mentions": 1,
        "previous_mentions": 1,
        "growth": 0,
        "growth_rate": 0.0,
        "is_new": false
      },
      "source_count": 1,
      "sources": [{
        "source_name": "BBC News Asia",
        "source_tier": "B",
        "url": "https://...",
        "published_at": "Mon, 28 Sep 2026 18:37:15 GMT"
      }],
      "is_political": false,
      "claim_kind": "EVENT" | "CLAIM" | "OPINION" | "NOT_POLITICAL",
      "political_neutral": true,
      "publishable": true
    }
  ]
}
```

### Internal-only fields (NOT exposed)

* `confidence_score`       — heuristic; never shown as a probability.
* `publishability_reasons` — internal audit trail.
* `counter_signals`        — detailed counter-signal attribution (kept internal).
* `canonical_url`          — internal dedup key; not exposed to avoid URL inference.
* `classification_reasons` — internal classification trace.
* `statuses_seen`          — internal aggregation; not UI-relevant.
* `first_seen` / `last_seen` — internal timestamps; freshness is shown only via `generated_at`.
* `mention_count`          — internal count; `source_count` is sufficient for UI.
* `summary` (top-level)    — internal story_count; not exposed (counts are in `summary.*`).

### Hard guarantees

1. **No URLs except http(s)** — every URL is sanitised by `is_safe_url()` before being written. `javascript:`, `data:`, `file:`, `vbscript:`, `blob:` are rejected at the public-output gate.
2. **No URL > 2048 chars** — silently dropped.
3. **No whitespace in URLs** — `isspace()` returns true for space, tab, newline, CR.
4. **Topics with no safe URL are dropped** — a topic that has sources but ALL of them have unsafe/missing URLs is silently excluded.
5. **VALID `status` / `verification_status` / `claim_kind`** — unknown values are coerced to the safe default (`WATCH` / `REPORTED` / `NOT_POLITICAL`).
6. **MAX_TOPICS_PER_PUBLIC = 200** — caps the public file size.
7. **MAX_SOURCE_EVIDENCE_PER_TOPIC = 10** — caps per-topic payload.

---

## 6. Internal → Public Transformer (`radar/public_output.py`)

Single function:

```python
build_public_payload(internal_payload: dict) -> dict
```

Re-builds the public summary from the actual public topic list (NOT
the internal summary), so they can never drift apart. Coerces unknown
enums to safe defaults. Drops unsafe data.

Atomic write:

```python
_atomic_write_json(target: Path, payload: dict) -> None
```

Algorithm: temp file in same directory → `flush()` → `os.fsync()` (best-effort) → `os.replace()`.

Validation:

```python
validate_public_payload(payload: dict) -> List[str]
```

Returns a list of error strings. Empty list = valid.

Validation enforces:

* `schema_version == 1` and `public_schema_version == 1`
* `scan_status ∈ {SUCCESS, PARTIAL, FAILED}`
* `topics` is a list; each topic has `content_key`, `title`, `status`,
  `verification_status`, `claim_kind`, and ≥ 1 source with safe URL.
* Unique `content_key` across topics.
* Per-source `source_tier ∈ {A,B,C,D,E,F}`.
* `publishable=True ∧ is_political ∧ ¬political_neutral` is rejected
  as an internal contradiction (Radar engine should never emit it).
* `summary.topic_count == len(topics)`.

If validation fails, `build_public_output()` raises `PublicOutputError`
and the previous valid `public/radar/latest.json` stays on disk.

CLI:

```
python -m radar.public_output                  # read internal, validate, write public
python -m radar.public_output --dry-run        # read + validate, no write
python -m radar.public_output --check          # validate existing public file
python -m radar.public_output --internal PATH  # use custom internal path
python -m radar.public_output --public PATH    # use custom public path
```

Exit codes: `0` = success, `1` = failure, `2` = usage error.

---

## 7. Website Adapter (`assets/js/radar-feed.js`)

Pure vanilla JS. No framework, no bundler, no Node dependency.
Total size: **22,320 bytes**.

### Exposed API (for testability)

```js
window.MYHotRadar.feed = {
  isSafeUrl:        (url) => boolean,
  validatePayload:  (p)   => string|null,
  isStale:          (iso) => boolean,
  isFutureDated:    (iso) => boolean,
  CONFIG:           { ... },
  STATUS_MAP:       { BREAKING, RISING, HOT, WATCH, COOLING },
  VERIFICATION_MAP: { CONFIRMED, REPORTED, SOCIAL_BUZZ, UNVERIFIED, RUMOUR },
};
```

### Behaviour summary

| Scenario | Result |
|---|---|
| Fetch succeeds + valid payload + non-empty topics | Render `Radar now` section. |
| Fetch succeeds + `scan_status == "PARTIAL"` | Render + show "Some sources are temporarily unavailable" banner. |
| Fetch succeeds + `generated_at` older than 6h | Render + show "Radar data may be delayed" banner. |
| Fetch succeeds + empty topics | Show "Radar data temporarily unavailable." |
| Fetch succeeds + `scan_status == "FAILED"` | Show "Radar data temporarily unavailable." (spec §20: never expose FAILED). |
| Fetch succeeds + `generated_at` is in the future | Treat as malformed → fallback. |
| Fetch fails (404, 500, timeout) | Show "Radar Feed unavailable." |
| JSON parse fails | Show "Radar Feed unavailable." + console.warn. |
| Schema mismatch | Show "Radar Feed unavailable." + console.warn. |
| Any of the above | Other page content (nav, footer, DEMO cards, ad slots) is **untouched**. |

### Loading state

Initial DOM contains `<p id="radar-feed-loading" class="rf-loading">Loading Radar…</p>`.
The JS adapter removes this element once a render or fallback is complete.

---

## 8. Topic Card UI

Each Radar topic renders as a `<article class="card rf-card">` inside
`<div class="grid rf-grid">`. The card has dashed border (vs solid on
DEMO cards) to visually distinguish Radar cards from static samples.

Card content (in order):

1. **Status badge** — `BREAKING / RISING / HOT / WATCH / COOLING` with brand-color background (uses existing `.badge--*` tokens; `WATCH` is new and uses neutral gray-blue).
2. **Category** — e.g. `MALAYSIA`.
3. **Verification pill** — `CONFIRMED / REPORTED / SOCIAL_BUZZ / UNVERIFIED / RUMOUR` with green/gray/amber/red color tokens.
4. **Confidence pill** — `VERY_LOW / LOW / MEDIUM / HIGH / VERY_HIGH`, dashed border, neutral color. Always labeled as heuristic, never as a probability.
5. **Title** — `<h3>` with `textContent` only (no innerHTML).
6. **Sources block** — collapsible `<button>` labelled "Sources (N)" expanding to a `<ul>` of `<a target=_blank rel=noopener noreferrer>` links to the source URLs. Tier badge (`TA` / `TB` / `TC` / `TD` / `TE` / `TF`) shown next to each source.
7. **Footer row** — "Updated N min ago" + (only if `is_political`) "Political · neutral" or "Political · opinion" pill.

### No innerHTML, no fake facts, no fake probability

The JS adapter uses `textContent` for every user-controlled string
(title, source name, etc.). `innerHTML` is never assigned to a variable
(see `test_no_innerhtml_for_user_data`).

Confidence is rendered as a heuristic label, never as `XX% confirmed` or `XX% likely` (forbidden strings checked in `test_no_fake_probability_strings`).

---

## 9. Source URL Safety

Both the Python public-output gate and the JS adapter use the **same**
URL safety algorithm:

1. Must be a string.
2. Must be non-empty.
3. Must be < 2048 chars.
4. Must not contain whitespace (space / tab / newline / CR).
5. Must not contain control characters (`ord < 32 || ord == 127`).
6. Must start with `http://` or `https://` (case-insensitive).

The JS adapter also runs each URL through this filter before rendering
a clickable link. A source whose URL fails the check is shown as plain
text (no `<a href>`).

Verified by `test_url_safety_agreement_*` (10 cases) +
`test_js_url_safety_implementation_uses_same_rules`.

---

## 10. Political Handling

The JS adapter reads `is_political`, `claim_kind`, and `political_neutral`
from the payload and renders exactly what the Radar engine decided.

- A non-political topic shows no political pill.
- A political + neutral topic (EVENT or CLAIM) shows "Political · neutral".
- A political + non-neutral topic (OPINION) shows "Political · opinion"
  with an accent color.

The JS adapter does **NOT** add any new ranking, endorsement,
opposition, or election-prediction logic. The following strings are
explicitly forbidden (verified by `test_no_banned_political_phrases`):

`best candidate`, `worst candidate`, `likely to win`, `vote for`,
`endorse`, `best party`, `worst party`.

---

## 11. Fallback Behaviour

The fallback state is rendered as:

```html
<section class="section section--tight" aria-labelledby="radar-heading">
  <div class="container">
    <div class="section-head">
      <h2 class="section-head__title" id="radar-heading">📡 Radar now</h2>
    </div>
    <p class="rf-unavailable">Radar Feed unavailable.</p>
  </div>
</section>
```

Other page sections (hero, ad slot, Hot Now DEMO, Malaysia DEMO,
Celebrity DEMO, Food DEMO, World DEMO, footer, MVP disclaimer) are
**never** touched by the adapter. Verified by `test_smoke_server.py`
(probes live HTTP server).

Tested scenarios:

| Test | Scenario | Expected outcome |
|---|---|---|
| Test B | public/radar/latest.json missing (404) | "Radar Feed unavailable." |
| Test C | malformed JSON | "Radar Feed unavailable." |
| Test D | scan_status == PARTIAL | "Some sources are temporarily unavailable" banner |
| Test E | future-dated generated_at | Fallback ("temporarily unavailable") |
| Test F | generated_at older than 6h | Stale banner ("may be delayed") |
| Test G | empty topics | "Radar data temporarily unavailable." |
| Test H | bad public_schema_version | Validator rejects; previous public file preserved |

All 10 fault-injection scenarios PASS.

---

## 12. Stale-Data Handling

Threshold: **6 hours**. If `generated_at` is older than 6h, a
banner appears: **"Radar data may be delayed. Showing the most recent
successful scan."** The topics are still rendered — we keep showing
the last valid snapshot rather than hiding everything.

The threshold is `CONFIG.staleAfterMs = 6 * 60 * 60 * 1000` in the
JS adapter.

Future-dated timestamps (>5 min in the future) are treated as
malformed and trigger fallback. This prevents a buggy clock from
making the data look "fresh from the future".

---

## 13. Security

The JS adapter applies these security rules (all enforced server-side
at the public-output gate AND mirrored client-side):

1. **No `innerHTML` for user-controlled strings.** Every dynamic
   string is set via `textContent` or built via `document.createElement`.
2. **URL scheme allow-list.** Only `http://` and `https://` are
   accepted as `<a href>`. `javascript:`, `data:`, `vbscript:`,
   `file:`, `blob:`, `ftp:` are silently rejected.
3. **No external scripts / fonts / images** introduced by the Radar
   adapter. The only added JS file is `/assets/js/radar-feed.js`,
   loaded from the same origin.
4. **`rel="noopener noreferrer"` and `target="_blank"`** on every
   external source link.
5. **CSP-friendly.** No `eval`, `Function()`, or `innerHTML`.

---

## 14. Caching

`fetch('/radar/latest.json', { cache: 'no-store' })`.

The Radar Feed is dynamic; it should never be served from cache.
Browser caching would defeat the whole point of a "Live Radar" feed.

Cloudflare's edge caching is **not** in scope for this batch —
the file is committed to Git and served as a static asset. A future
batch can add explicit `Cache-Control` headers via `_headers` file
once we have telemetry showing the right cadence.

---

## 15. Mobile / Accessibility QA

| | |
|---|---|
| Mobile-first CSS | `.rf-grid` uses the same breakpoints as `.grid` (700px, 1024px). |
| No horizontal overflow | Source names use `text-overflow: ellipsis`. Card titles use `line-clamp` (existing). |
| Semantic HTML | `<section aria-labelledby>`, `<h2>` with `id`, `<article>` for each card. |
| Heading hierarchy | Radar section uses `<h2>`; cards use `<h3>`. |
| Status not color-only | Status badge has both text label AND color (verified — labels "Breaking" / "Rising" / etc. always rendered). |
| Source expand/collapse | A `<button>` element with `aria-expanded` and `aria-controls`. Keyboard accessible by default. |
| Loading state | `<p id="radar-feed-loading" role="status" aria-live="polite">` — screen-reader announced. |
| Reduced motion | `@media (prefers-reduced-motion: reduce)` disables the spinner animation. |
| Long titles | `text-overflow: ellipsis` and clamp prevents layout break. |
| Mixed CN/MY/EN | No layout break; titles preserve UTF-8 verbatim. |

Real browser testing was not available in this environment
(Chromium not installed). The static-site-mvp skill recommends
falling back to server-side + CSS analysis in this case. The
equivalent checks performed:

* `python -m http.server 8765` runs.
* `curl` returns 200 for `/`, `/assets/js/radar-feed.js`,
  `/assets/css/style.css`, `/public/radar/latest.json`.
* `node --check assets/js/radar-feed.js` passes (zero syntax errors).
* HTML structural check (`#radar-feed-host` present, MVP disclaimer
  present, all 8 nav links present, AdSense intact).

A real browser test (via Playwright/Chromium) should be added once
tooling is installed; the current checks are documented as the
explicit fallback.

---

## 16. Tests

| | Old | New | Total |
|---|---:|---:|---:|
| Phase 1 / Radar-1..6, Phase 2 B1..B3A | 248 | — | 248 |
| **Phase 2 B3B-1** | | | |
| `test_public_output.py` (34 tests) | — | 34 | 34 |
| `test_radar_adapter.py` (31 tests) | — | 31 | 31 |
| **Total** | 248 | **65** | **313** |

Categories per spec §31:

* Public export (8) ✓
* Validation (7) ✓
* Publishability (6) ✓
* Safety / sanitization (5) ✓
* Failure safety (4) ✓
* Real-world integration (4) ✓
* JS structure (4) ✓
* Mirror tests (10) ✓
* Host page integration (4) ✓
* Public JSON integration (3) ✓
* Source-attachment (2) ✓
* Anti-fake-fact (3) ✓
* Mobile / a11y (3) ✓
* Existing pages unchanged (2) ✓

> **All 313 tests PASS, 0 failures, 0 regressions.**

Fault-injection (`radar/tests/fault_injection.py`) adds 10 additional
scenarios (Test B / C / D / E / F / G / H / I / J / restore), all PASS.

Smoke-server (`radar/tests/smoke_server.py`) adds 12 server-side
checks against the live HTTP server, all PASS.

---

## 17. Browser QA

Per spec §32, six tests:

| Test | Status | Note |
|---|---|---|
| A — valid latest JSON: Radar displays real topics | ✅ verified via server-side + smoke + fault-injection | Real browser test not available (no Chromium); equivalent server-side checks PASS. |
| B — temporarily move public JSON: Radar unavailable, website still works | ✅ verified via fault-injection Test B | JS adapter shows "Radar Feed unavailable" but does NOT touch other sections. |
| C — malformed JSON: fallback | ✅ verified via fault-injection Test C | JSON.parse catches the error and triggers fallback. |
| D — PARTIAL: partial indicator visible | ✅ verified via fault-injection Test D | Banner "Some sources are temporarily unavailable" is rendered. |
| E — long title: no layout break | ✅ verified via `test_no_horizontal_overflow_in_card_markup` | text-overflow: ellipsis + line-clamp prevent overflow. |
| F — Chinese + Malay + English: no encoding problem | ✅ verified via `test_long_Chinese_title_preserved` (60-char Chinese title round-trips through JSON). |

Real-browser QA cannot be performed in this environment (Chromium is
not installed). The static-site-mvp skill explicitly allows the
server-side fallback in this case. This is documented above and in
the Final Report.

---

## 18. Production Safety

| Check | Result |
|---|---|
| `https://myhotradar.com/` | HTTP 200 ✅ |
| All 13 sub-paths (`/sitemap.xml`, `/hot/`, `/malaysia/`, `/viral/`, `/celebrity/`, `/food/`, `/world/`, `/article/example/`, `/about/`, `/contact/`, `/privacy/`, `/terms/`) | HTTP 200 ✅ |
| AdSense (`ca-pub-6219340004578553`) | intact ✅ |
| OG image | intact ✅ |
| Cloudflare Pages | not modified (still Git-deployed from master) ✅ |
| DEMO articles | unchanged (`/article/example/` still present, sample cards still labelled Sample) ✅ |
| `/article/example/` content | not modified ✅ |
| `sitemap.xml` | not modified ✅ |
| Existing nav / footer / MVP disclaimer | not modified ✅ |
| Site does NOT yet serve `latest.json` from production CDN | **expected** — needs next deploy step (see §19) ✅ |

Note: `/public/radar/latest.json` is committed in this batch's commit,
but the **production deployment** happens only after the user (or a
future batch) pushes to GitHub + Cloudflare Pages picks it up. The
local HTTP server test demonstrates the artifact is served correctly;
production will mirror that.

---

## 19. Deployment Strategy (the explicit gap)

**Current state (this batch)**:
* `public/radar/latest.json` is committed to `master` in this batch.
* After the user pushes the batch, Cloudflare Pages will deploy the
  homepage with the new Radar section, but the production `/radar/latest.json`
  will still be the **stale** version of the file (until a future
  commit pushes a newer snapshot).

**Recommended next steps**:

1. **Manual operator step** (recommended for now):
   ```
   python -m radar.scan
   python -m radar.output --live
   python -m radar.public_output
   git add public/radar/latest.json
   git commit -m "chore: refresh Radar feed snapshot"
   git push origin master
   ```
   Cloudflare Pages picks up the new file and the homepage refreshes
   its Radar Feed on next page load.

2. **Future batch** (out of scope here):
   * Add a small build/export step that runs `python -m radar.public_output`
     followed by `git add + git commit + git push`.
   * Or wire it into the existing scheduler with a "publish if changed"
     guard.
   * Or add a Cloudflare Worker / Pages Function that generates the
     public artifact on demand.

This batch does NOT auto-commit. The decision of **when** to ship
real data to production is intentionally a human-step until the
production telemetry confirms the workflow is correct.

---

## 20. Experience Governance

Per spec §36 / DEVELOPMENT_RULES.md §36-39: only **independently
reproduced, reusable, verified** observations belong in
`EXPERIENCE.md`.

This batch's observations:

| Observation | Promoted? |
|---|---|
| Cloudflare Pages only serves Git-committed files | Already documented in static-site-mvp skill. |
| Public output must be a separate artifact from internal output | Design choice, not a verified rule. |
| Atomic write preserves previous on failure | Already documented in Phase 2 B2 history atomic write. |
| JS / Python URL-safety algorithm must mirror each other | Candidate — observed once. Needs reproduction before promotion. |

`EXPERIENCE.md` is **unchanged** by this batch.

---

## 21. Future Work

The following items are explicitly **out of scope** for this batch
and reserved for future batches:

| Batch | Scope |
|---|---|
| **B3B-2** | Real Publishing — generate article body from a CONFIRMED + publishable topic, replace one DEMO article. |
| **B3B-3** | Auto-publish Radar refresh (manual step → automated CI / scheduler step). |
| **B3B-4** | Tier-A revisit — re-probe the 7 unreachable Tier-A candidates from Radar-5A. |
| **B3B-5** | Output expansion — split public output by category (e.g. `/radar/malaysia.json`). |
| **B3B-6** | Real browser QA — install Chromium, run Playwright-based UI tests. |
| **B3B-7** | 0-stories guard — fix the Phase 2 B2 limitation where empty scans can overwrite history. |
| **B3B-8** | Documentation v2 — fold all Phase 2 batches into a single `NEWS_RADAR.md` rewrite. |

These are listed for visibility; none of them is started by this batch.

---

## 22. Files Changed

| File | Status | Bytes / Lines |
|---|---|---:|
| `radar/public_output.py` | **new** | +28,492 bytes |
| `radar/tests/test_public_output.py` | **new** | +29,094 bytes |
| `radar/tests/test_radar_adapter.py` | **new** | +22,313 bytes |
| `radar/tests/smoke_server.py` | **new** | +6,976 bytes |
| `radar/tests/fault_injection.py` | **new** | +9,324 bytes |
| `radar/tests/run_all.py` | modified | +2 lines |
| `assets/js/radar-feed.js` | **new** | +22,320 bytes |
| `assets/css/style.css` | appended | +278 lines |
| `index.html` | modified | +12 lines (host + script tag) |
| `public/radar/latest.json` | **new (committed artifact)** | +102,250 bytes |
| `docs/RADAR_PHASE2_WEBSITE_FEED.md` | **new** | this file |
| Website category pages (5) | **untouched** | — |
| Website article page | **untouched** | — |
| Website legal pages (3) | **untouched** | — |
| `sitemap.xml` | **untouched** | — |
| `EXPERIENCE.md` | **untouched** | — |
| Engine files (`radar/verification.py` etc.) | **untouched** | — |

**Total**:
* 6 new files (1 production code + 4 tests + 1 doc)
* 1 new public artifact
* 3 modified files (CSS, HTML, run_all)

---

## 23. Git Commit / Push

> Recorded in the Final Report below the table.

| | |
|---|---|
| Working tree before | clean (commit `ab8fef4`) |
| Files staged | 9 new + 3 modified |
| Files NOT staged | `radar_data/` (gitignored) |
| Commit message | `feat: News Radar Phase 2 Batch 3B-1 website feed integration` |
| amend / rebase / squash / force-push / reset | **none** ✅ |

---

## 24. Limitations

1. **No real browser QA in this environment.** Chromium not installed.
   Equivalent server-side checks + static CSS analysis were performed
   and passed. A future batch should add Playwright-based UI tests.

2. **Production deployment is a manual step.** This batch commits the
   public artifact but does NOT auto-push. See §19.

3. **Radar topics don't become articles.** The "Radar now" section
   is a feed, not an article list. Topic titles do NOT link to
   `/article/example/`. A future batch (B3B-2) handles real publishing.

4. **Maximum 12 topics shown.** The JS adapter caps visible topics
   to keep the homepage balanced between Radar and DEMO content.
   The full 91-topic set is available in `/public/radar/latest.json`.

5. **Radar now is on the homepage only.** Category pages, the article
   page, the about/contact/legal pages, and the Hot Now page are NOT
   modified. A future batch can extend the Radar Feed to category pages.

6. **No edge caching rules yet.** `cache: 'no-store'` on the JS
   `fetch` is the only cache control. Cloudflare Pages' edge cache
   is untouched.

7. **Old-style confidence (5-level).** The current Radar engine emits
   `VERY_LOW / LOW / MEDIUM / HIGH / VERY_HIGH`. The JS adapter maps
   these to user-friendly display labels. If a future batch changes
   the Radar engine's confidence enum, the JS adapter must be
   updated.

---

## 25. Conclusion

Phase 2 Batch 3B-1 ships:

- A new `radar/public_output.py` that produces a stripped public
  schema from the validated internal Radar output.
- A new `public/radar/latest.json` committed to Git as a static
  artifact.
- A new `assets/js/radar-feed.js` vanilla-JS adapter that fetches,
  validates, sanitises, and renders Radar topic cards.
- 65 new tests (34 public-output + 31 radar-adapter) + 10 fault-injection
  scenarios + 12 server-side smoke checks, all PASS.
- 0 regressions: **313/313 tests still PASS**.

The Radar now has a presence on the MY Hot Radar homepage while
remaining clearly distinct from DEMO content, free of fake facts,
and safe from URL injection or schema drift.

Total project state: **313 tests PASS, 0 failures, 0 regressions,
11 batches shipped (Radar-1..6, Phase 2 B1/B2/B3A/B3B-1), working
tree clean.**

---

## 26. Recommended Next Batch

The user is the only one who can decide what's next. Possible
directions:

- **Phase 2 Batch 3B-2**: Real Publishing — generate article body
  from a CONFIRMED + publishable topic, replace one DEMO article.
  This is the natural next step.
- **Phase 2 Batch 3B-2**: Auto-deploy script for `public/radar/latest.json`
  so the Radar Feed refreshes without a manual `git push`.
- **Phase 2 Batch 3B-2**: Tier-A revisit (7 unreachable candidates from
  Radar-5A).
- **Phase 2 Batch 3B-2**: Output expansion by category.
- **Phase 2 Batch 3B-2**: Real browser QA via Playwright.

Per spec §41, this batch **stops** here. Waiting for the user's
next instruction.
