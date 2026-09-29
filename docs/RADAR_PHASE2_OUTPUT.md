# MY Hot Radar — Phase 2 / Batch 3A — Real Radar Output Layer

> Final documentation for the **Phase 2 / Batch 3A** batch.
> Read alongside `NEWS_RADAR.md`, `PROJECT_CONTEXT.md`,
> `docs/RADAR_PHASE2_POLITICS.md` (Phase 2 B1),
> `docs/RADAR_PHASE2_SCHEDULER.md` (Phase 2 B2), and
> `docs/RADAR_5A_TIER_A_DISCOVERY.md`.

This document records the Real Radar Output Layer: a structured,
audit-friendly JSON output that the existing Radar pipeline produces.
The output layer does NOT modify any engine file. It is a read-only
view over the post-pipeline Topic list.

---

## 1. Objective

Generate a **structured, versioned, validated JSON output** from the
existing Radar pipeline that downstream consumers (future article
generator, analytics, future CMS integration) can rely on.

This batch does NOT:

- Replace DEMO articles on `myhotradar.com`.
- Modify the website's HTML / CSS / Cloudflare config.
- Auto-publish to Facebook / TikTok / X.
- Generate article bodies or summaries.
- Modify the verification, momentum, classification, counter-signal,
  politics, dedup, scheduler, or source-registry code.

---

## 2. Architecture

```
                  ┌─────────────────────────────────────┐
                  │   OS scheduler / `python -m        │
                  │   radar.scheduler` (Phase 2 B2)    │
                  └─────────────┬───────────────────────┘
                                │ invokes
                                ▼
                  ┌─────────────────────────────────────┐
                  │   radar/pipeline.run_scan()        │
                  │   (existing, +return_internals     │
                  │    additive flag)                   │
                  └─────────────┬───────────────────────┘
                                │ returns in-memory
                                │ topics + stories_by_id
                                ▼
                  ┌─────────────────────────────────────┐
                  │   NEW: radar/output.py              │
                  │                                     │
                  │   build_output()                    │
                  │     ├─ SourceEvidence per topic    │
                  │     ├─ Publishability decision     │
                  │     ├─ Politics classification     │
                  │     │  (re-uses Phase 2 B1 logic)   │
                  │     ├─ Summary aggregation         │
                  │     ├─ Source summary              │
                  │     └─ schema_version = 1          │
                  │                                     │
                  │   validate_output()                 │
                  │     ├─ required keys               │
                  │     ├─ unique content_key          │
                  │     ├─ valid enums                 │
                  │     ├─ confidence range            │
                  │     ├─ summary consistency         │
                  │     └─ JSON-serializable           │
                  │                                     │
                  │   write_validated_output()          │
                  │     ├─ temp + flush + fsync +       │
                  │     │   os.replace (atomic)         │
                  │     ├─ latest.json                 │
                  │     └─ YYYY-MM-DD/<scan_id>.json   │
                  └─────────────┬───────────────────────┘
                                │
                                ▼
                  radar_data/output/
                    latest.json
                    2026-09-29/
                      <scan_id>.json
```

The output layer adds:

- `radar/output.py` (new)
- `radar/tests/test_output.py` (new, 35 tests)
- `radar_data/output/` directory structure (new, gitignored)

It does NOT add any source, change the source registry, or modify
any engine file beyond the additive `return_internals` flag on
`pipeline.run_scan`.

---

## 3. Output Schema (spec §5)

Schema version: **1**.

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-09-29T02:43:30Z",          // ISO8601 UTC
  "scan_id":       "20260929T024330Z-11548",        // unique per run
  "scan_status":   "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED_LOCKED",

  "source_summary": {
    "total":  5,
    "ok":     5,
    "failed": 0,
    "sources": [
      {"name": "BBC News Asia", "tier": "B", "type": "RSS",
       "ok": true, "fetched": 17, "error": null}
    ]
  },

  "summary": {                                    // derived from topics
    "story_count":      117,
    "topic_count":      89,
    "publishable_count": 88,
    "by_verification":  {"CONFIRMED": 3, "REPORTED": 86, ...},
    "by_status":        {"WATCH": 89, ...},
    "by_claim_kind":    {"NOT_POLITICAL": 70, "EVENT": 11, "CLAIM": 7, "OPINION": 1}
  },

  "topics": [
    {
      "content_key": "u:https://www.bbc.co.uk/news/articles/...",
      "title": "...",
      "summary": "...",
      "canonical_url": "https://...",
      "category": "MALAYSIA",
      "language": "en",
      "status": "WATCH",
      "verification_status": "REPORTED",
      "confidence_label": "MEDIUM",
      "confidence_score": 0.4,

      "momentum": { /* existing Momentum.to_dict() */ },
      "classification_reasons": [...],
      "statuses_seen": [...],

      "first_seen": "...",
      "last_seen": "...",
      "mention_count": 1,

      "source_count": 1,
      "sources": [
        {
          "source_name": "BBC News Asia",
          "source_tier": "B",
          "source_type": "RSS",
          "country": "GB",
          "url": "https://www.bbc.co.uk/news/articles/...",
          "title": "The Frenemy: How Australia navigates superpower rivalry",
          "published_at": "Mon, 28 Sep 2026 18:37:15 GMT"
        }
      ],

      "counter_signals":   [...],   // existing CounterSignal.to_dict()
      "counter_signal_count": 0,

      "is_political":       false,
      "claim_kind":         "NOT_POLITICAL",
      "political_neutral":  true,

      "publishable":              true,
      "publishability_reasons":   ["valid_sources", "no_blocking_counter_signal", ...]
    }
  ]
}
```

Every field is either:

1. A passthrough from an existing dataclass's `to_dict()` (Topic,
   Story, Verification, Momentum, CounterSignal); OR
2. A deterministic aggregation across the topics list; OR
3. A NEW output-layer-only field (`publishable`, `publishability_reasons`,
   `claim_kind`, `political_neutral`, `source_count`, full `sources[]`).

The output layer **does NOT recompute** confidence, momentum,
verification, or classification. These come from the engine.

---

## 4. Evidence Model (spec §6)

Every topic carries a full `sources[]` array. Each source-evidence
record has:

```
source_name    -- the source that reported this evidence
source_tier    -- A / B / C / D / E / F (from registry, NOT from story)
source_type    -- RSS / NEWS_SITE / OFFICIAL_SOURCE / ...
country        -- MY / SG / GB / ...
url            -- exact URL from the Story object (NEVER fabricated)
title          -- exact title from the Story object (NEVER fabricated)
published_at   -- exact timestamp from the Story object (NEVER fabricated)
```

Rules enforced:

- **No fake URLs.** If a Story's URL is empty, that source-evidence
  record contributes a `MISSING_SOURCE_URL` reason and the topic is
  NOT publishable.
- **No fake sources.** A topic's `sources[]` only includes
  source-evidence records built from the actual `Story` objects that
  fed the cluster. `related_urls` alone does NOT contribute sources.
- **Tier-F alone blocks publishability.** If every source is Tier-F,
  there is no independent evidence chain.
- **Multiple stories from same source dedupe to one source-evidence**
  (per (source_name, url) pair).
- **Counter-signals are preserved** with full source attribution
  (source name + tier + stance + summary + URL + observed_at).

Verified by 6 evidence tests.

---

## 5. Publishability (spec §7)

`publishable` is a **NEW boolean field, not a verification-status
alias**. It is computed by `evaluate_publishability()` per topic.

### Conservative rules (Phase 2 B3A version 1)

A topic is publishable IF AND ONLY IF none of the following negative
gates fire:

| Gate | Reason label |
|---|---|
| `verification_status == RUMOUR` | `verification_rumour` |
| `verification_status == UNVERIFIED` | `verification_unverified` |
| `verification_status == SOCIAL_BUZZ` (only) | `verification_social_buzz_only` |
| Tier-A DENIAL counter-signal present | `blocking_tier_a_denial` |
| `is_political and not political_neutral` | `political_non_neutral` |
| Title empty | `missing_title` |
| Any source URL empty | `missing_source_url` |
| All sources are Tier-F | `insufficient_independent_sources` |

A topic that passes ALL gates gets positive reasons appended:

```
confirmed_evidence        (verification_status == CONFIRMED)
valid_sources             (at least one source has a non-empty URL)
no_blocking_counter_signal (no Tier-A DENIAL)
valid_title               (non-empty title)
content_complete          (at least one source has a non-empty title)
politically_neutral       (political_neutral == True)
```

### REPORTED is NOT auto-blocked

A topic with `verification_status == REPORTED` is publishable if all
other gates pass. The `verification_status` field is preserved
unchanged so downstream consumers see the actual evidence state.

This is verified by `test_reported_remains_representable`.

---

## 6. Political Neutrality (spec §9)

The output layer does NOT introduce any new political-judgement
logic. It re-uses the **Phase 2 Batch 1 politics module**:

- `is_political` -- derived from multi-signal pattern matching on
  the topic's title + summary.
- `claim_kind` -- one of `EVENT | CLAIM | OPINION | NOT_POLITICAL`,
  produced by `radar.politics.detect_political_kind()`.
- `political_neutral` -- True iff claim_kind is EVENT or CLAIM
  (i.e. NOT OPINION).

A topic that is `political_neutral == False` is **never** publishable
(per spec §7 + Phase 2 B1).

The politics rules from Phase 2 B1 are not modified:
- No ranking / endorsement / opposition / election prediction.
- No banned-phrase detection in the output layer itself (the render
  layer in Phase 2 B1 owns that).

---

## 7. Validation (spec §12)

`validate_output(out) -> List[str]` returns a list of error messages.
Empty list = valid.

The validator checks:

- Top-level required keys (`schema_version`, `generated_at`, `scan_id`,
  `source_summary`, `summary`, `topics`).
- `schema_version == 1`.
- `scan_id`, `generated_at` non-empty.
- `topics` is a list.
- For each topic:
  - `content_key` non-empty AND unique across topics.
  - `title` non-empty.
  - `verification_status`, `status`, `confidence_label` are valid
    enum values.
  - `confidence_score` in [0.0, 1.0] if present.
  - Per-source `source_tier` valid, URL well-formed (http://, https://,
    or file://).
  - `publishable=True` implies no blocking reasons present.
  - `is_political=True` + `political_neutral=False` implies
    `claim_kind == OPINION`.
- Summary consistency:
  - `summary.topic_count == len(topics)`.
  - `summary.by_verification` counts == `len(topics)`.
  - `summary.by_status` counts == `len(topics)`.
- Source summary consistency:
  - `source_summary.total == len(source_summary.sources)`.
  - `source_summary.ok + source_summary.failed == total`.
- Output is JSON-serializable.

**Failure behavior** (per spec §12):

If validation fails, `write_validated_output()` raises
`OutputValidationError` and **does NOT replace `latest.json`**.

The previous valid `latest.json` (if any) remains on disk. The
sentinel-preservation is verified by
`test_failed_validation_does_not_replace_latest`.

---

## 8. Atomic Write (spec §10, §14)

`_atomic_write_json(target, payload)`:

1. Create temp file at `<target>.tmp` via `tempfile.mkstemp` in the
   same directory.
2. Write JSON to temp file.
3. `flush()` + `os.fsync()` (best-effort; fsync may not be available
   on some platforms).
4. `os.replace(tmp, target)` — atomic on POSIX and Windows.

If the process is killed mid-write:

- `target` is unchanged (the previous snapshot is intact).
- A stale `.tmp` may remain; it is harmless and will not be picked
  up by any consumer.

Verified by `test_atomic_write_failure_preserves_previous_latest`.

---

## 9. Latest Output Behavior (spec §11)

`latest.json` is updated on every successful write. It is **never**
overwritten with empty / failed data:

- **Successful scan**: latest.json replaced atomically with the new
  payload.
- **Validation failure**: latest.json NOT replaced; sentinel preserved.
- **Scan raised exception**: latest.json NOT replaced (the scheduler
  handles this; the output layer only writes on success).
- **PARTIAL scan**: latest.json IS replaced, but the `scan_status`
  field is set to `"PARTIAL"`. Downstream consumers can opt to
  ignore PARTIAL outputs if desired.

Per spec §17: failed scan must NOT replace latest. The scheduler
guards this; the output layer raises before write if validation
fails.

---

## 10. Failure Safety (spec §12)

| Failure mode | Behavior |
|---|---|
| Validation error | `OutputValidationError` raised; latest.json unchanged |
| Atomic write mid-failure | Previous file intact (sentinel preserved) |
| PARTIAL scan | Written with `scan_status=PARTIAL`; failed sources visible |
| Tier-A denial CS | Topic marked `publishable=False`; reason recorded |
| Missing URL | Topic marked `publishable=False`; `missing_source_url` reason |
| RUMOUR status | Topic marked `publishable=False`; `verification_rumour` reason |
| OPINION political | Topic marked `publishable=False`; `political_non_neutral` reason |
| Tier-F only | Topic marked `publishable=False`; `insufficient_independent_sources` |

Per spec §19 / §21: the output layer does NOT publish to the
website. It only writes JSON files inside `radar_data/`, which is
gitignored.

---

## 11. Tests

`radar/tests/test_output.py` adds **35 tests**:

| Category | Count |
|---|---:|
| Output generation | 6 |
| Evidence | 6 |
| Publishability | 7 |
| Validation | 5 |
| Failure safety | 4 |
| Regression | 2 |
| Bonus | 5 |
| **Total** | **35** |

All 35 tests pass.

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
| `test_tier_b_review` (Radar-6) | 22 | PASS |
| `test_politics` (Phase 2 B1) | 31 | PASS |
| `test_scheduler` (Phase 2 B2) | 21 | PASS |
| **`test_output` (Phase 2 B3A, new)** | **35** | **PASS** |
| **Total** | **248** | **ALL PASS** |

Zero regressions in any earlier batch.

---

## 12. Three-Run Real Validation (spec §17)

Today's manual validation:

| Run | scan_id | sources | topics | stories | publishable | latest.json |
|---|---|---:|---:|---:|---:|---|
| 1 | 20260929T032412Z-15652 | 5/5 | 89 | 117 | 88 | replaced |
| 2 | 20260929T032415Z-6132 | 5/5 | 89 | 117 | 88 | replaced |
| 3 | 20260929T032417Z-4552 | 5/5 | 89 | 117 | 88 | replaced |

- 3 distinct scan_ids.
- `latest.json` always points to the most recent valid output.
- All 3 outputs pass validation.
- Real stories > 0, real topics > 0, 5/5 sources OK.
- Source evidence preserved (every topic has `sources[]` with the
  original URL + title + published_at).
- Publishability calculated (88/89 publishable — REPORTED + valid
  source + no blocking CS).
- Politics: 70 NOT_POLITICAL + 11 EVENT + 7 CLAIM + 1 OPINION.
- Verification: 86 REPORTED + 3 CONFIRMED.

The scheduler (`python -m radar.scheduler`) ALSO produces the
structured output (verified after the manual runs). The scheduler's
output generation is best-effort: a failure does not flip the
scheduler's status from SUCCESS to FAILED.

---

## 13. Production Safety

| Check | Result |
|---|---|
| `https://myhotradar.com/` | HTTP 200 ✅ |
| All 13 sub-paths (`/sitemap.xml`, `/hot/`, `/malaysia/`, `/viral/`, `/celebrity/`, `/food/`, `/world/`, `/article/example/`, `/about/`, `/contact/`, `/privacy/`, `/terms/`) | HTTP 200 ✅ |
| AdSense (`ca-pub-6219340004578553`) | present, 1 occurrence ✅ |
| Cloudflare | untouched ✅ |
| Facebook Page | untouched ✅ |
| DEMO articles | still present ✅ |
| Site references `latest.json` | NO (0 matches; site doesn't read radar output) ✅ |
| `python -m radar.scan` (existing entry point) | still works ✅ |
| `python -m radar.output --live` (new entry point) | works ✅ |
| `python -m radar.scheduler` (existing entry point) | works AND generates output ✅ |
| `radar_data/` | gitignored ✅ |

---

## 14. Experience Governance

Per spec §19:

> Don't auto-promote to EXPERIENCE.md. Promotion requires
> independently reproduced, reusable, verified observations.

Observations from Phase 2 B3A:

| Observation | Status |
|---|---|
| `publishable` is independent of `verification_status` | **Not promoted** — design choice; needs reproduction |
| Atomic write via temp + os.replace preserves previous on failure | **Already documented** in Phase 2 B2 (history atomic write); not new |
| Tier-F alone blocks publishability | **Candidate** — design choice; needs reproduction |
| REPORTED is publishable if all other gates pass | **Candidate** — design choice; needs reproduction |
| Politics neutral rules unchanged | **Documented** — reuses Phase 2 B1 |

`EXPERIENCE.md` is **unchanged** by Phase 2 B3A.

---

## 15. Files Changed

| File | Status | Lines |
|---|---|---:|
| `radar/output.py` | **new** | +950 |
| `radar/tests/test_output.py` | **new** | +750 |
| `radar/pipeline.py` | modified (additive `return_internals` flag only) | +17 / -2 |
| `radar/scheduler.py` | modified (calls output layer best-effort) | +20 / -0 |
| `radar/tests/run_all.py` | modified | +1 |
| `docs/RADAR_PHASE2_OUTPUT.md` | **new** | (this file) |
| `radar/verification.py`, `momentum.py`, `classification.py`, `counter_signals.py`, `dedup.py` | **untouched** | — |
| `radar/tier_a_qualification.py`, `source_scope.py`, `tier_b_review.py`, `politics.py` | **untouched** | — |
| `radar/sources_registry.py`, `radar/history.py`, `radar/models.py`, `radar/report.py` | **untouched** | — |
| Website, sitemap, AdSense, Cloudflare, Facebook | **untouched** | — |
| `EXPERIENCE.md` | **untouched** | — |
| **Total** | | **+1738 / -2** |

The `pipeline.py` change is the **only** engine-touching change in
this batch. It is purely additive: a new `return_internals=False`
keyword arg, plus an optional `if return_internals:` block that adds
two keys to the return dict. Existing callers are unaffected.

---

## 16. Git

| Step | Result |
|---|---|
| Working tree before | clean |
| Files staged | 5 (2 new, 3 modified) |
| Files NOT staged | `radar_data/` (gitignored) |
| Commit (Phase 2 B3A) | (recorded in batch report) |
| Push | (recorded in batch report) |
| `git amend` / rebase / squash / force-push / reset | **none used** |

---

## 17. Limitations

1. **Output is for INTERNAL use.** It is a structured view of the
   Radar's evidence. It is NOT a publishable article. Downstream
   consumers (future article generator, etc.) must apply additional
   editorial + safety review before publishing.

2. **Publishability is conservative.** 88/89 real-network topics
   pass today, but real-world edge cases (e.g. a CONFIRMED topic
   with one source URL accidentally trimmed) would NOT pass. This
   is by design — a future batch can tune thresholds when there
   is real editorial demand.

3. **No deduplication across `sources[]`.** If two stories from the
   same source have different URLs (e.g. BBC + BBC variant), both
   appear. Spec §6 permits this. Future batch may add canonical
   URL-based dedup.

4. **Politics classifier uses title + summary.** If a topic's
   title and summary are both empty, the politics classifier
   returns NOT_POLITICAL (vacuously true). This is the safe default.

5. **No JSON Schema formal validation.** The validator is a
   hand-written Python function. A future batch could add a
   `jsonschema` library check, but the current hand-written version
   is intentionally minimal (no new dependency).

6. **Output schema version is 1.** Future schema changes will bump
   this. The validator rejects any version != 1.

7. **The `pipeline.run_scan` modification is the only engine
   touch.** This was unavoidable to allow the output layer to
   receive full in-memory Topic + Story data. The change is
   strictly additive (new optional kwarg, new optional return
   keys) and verified non-breaking by all 213 prior tests.

---

## 18. Future Publishing Separation (per spec §19, §24)

This batch is **read-and-write-to-radar_data only**. The following
are out of scope and reserved for a future batch:

- Replacing DEMO articles on `myhotradar.com` with real radar output.
- Generating article bodies.
- Auto-publishing to Facebook / TikTok / X.
- Any kind of branded content automation.

The output layer writes only to `radar_data/output/`. The website
source (`index.html`, category pages, article page, sitemap, assets/)
was NOT modified by this batch.

---

## 19. Conclusion

Phase 2 B3A adds a Real Radar Output Layer on top of the existing
pipeline. The system now produces:

- A versioned JSON output (`schema_version: 1`).
- Per-topic evidence chains (URL + title + published_at + tier +
  country + type) preserved verbatim from the Story objects.
- A new `publishable` boolean with explicit `publishability_reasons`.
- Politics classification (`is_political`, `claim_kind`,
  `political_neutral`) re-using Phase 2 B1 logic.
- Counter-signal attribution preserved with full source info.
- Atomic writes (temp + flush + fsync + os.replace).
- Validation that REJECTS bad output before `latest.json` is
  overwritten.
- A CLI entry point (`python -m radar.output --live`) and
  integration with the existing scheduler.

35 new tests, all pass. Zero regressions in the 213 prior tests.

Total project state: **248 tests PASS, 0 failures, 0 regressions**.
