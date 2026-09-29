# Phase 2 Batch 3B-2 — Article Candidate Pipeline

**Status:** PASS
**Commit:** (see git log)
**Scope:** Adds an INDEPENDENT Article Candidate layer between Radar Output and (future) Article Generation.

---

## 1. Objective

Build a deterministic, testable pipeline that converts a Radar topic into a
**structured Article Candidate**. The candidate is the unit that will
eventually flow into human / rule-based review. It is NOT an article.
It is NOT a draft. It is NOT publication-ready.

```
   Radar Engine
        ↓
   Radar Output (validated)
        ↓
   Article Candidate Pipeline
        ↓
   candidate JSON (radar_data/candidates/, gitignored)
        ↓
   [Future] Article Generation
   [Future] Human / Rule QA
   [Future] Publishing
```

---

## 2. Why `publishable ≠ article-ready ≠ published`

`radar.output.publishable = true` means only one thing:

> The current Radar output considers this topic safe to surface on the
> Radar Feed.

It does NOT mean:

- The topic is journalistically publishable.
- A human has reviewed it.
- An article draft exists.
- The topic is ready to go on MY Hot Radar's site.

The Candidate layer is the boundary that enforces this separation. The
feed layer (Phase 2 B3B-1) consumes `publishable` directly. The Candidate
layer requires an additional, independent set of gates before a topic
can become a `READY_FOR_REVIEW` candidate.

---

## 3. Architecture

```
radar_data/output/latest.json
        ↓
radar.candidate.run_candidate_pipeline()
        ↓
for each topic:
    evaluate_eligibility(topic)
        ↓
    build_candidate_from_topic(topic)
        ↓
    upsert into CandidateStore
        ↓
radar_data/candidates/by_day/<id>.json
        ↓
rebuild_latest()
        ↓
radar_data/candidates/latest.json
```

All writes are atomic (`os.replace` after fsync). All input goes through
validation. Failure preserves previous state.

---

## 4. Candidate Schema (Public to Internal Layer)

```json
{
  "schema_version": 1,
  "candidate_id": "cand_<stable-hash>",
  "content_key": "u:<canonical-url>",
  "created_at": "2026-09-29T03:55:26Z",
  "updated_at": "2026-09-29T05:04:39Z",
  "state": "CANDIDATE|BLOCKED|READY_FOR_REVIEW",
  "headline": "<from Radar topic.title>",
  "headline_origin": "RADAR_TOPIC",
  "category": "MALAYSIA",
  "language": "en",
  "radar_status": "RISING|BREAKING|WATCH|COOLING",
  "verification_status": "CONFIRMED|REPORTED|SOCIAL_BUZZ|UNVERIFIED|RUMOUR",
  "confidence_label": "VERY_HIGH|HIGH|MEDIUM|LOW|MINIMAL|NONE",
  "source_count": 2,
  "sources": [
    {
      "source_name": "...",
      "source_tier": "B",
      "source_type": "RSS",
      "country": "MY",
      "url": "https://...",
      "title": "...",
      "published_at": "..."
    }
  ],
  "momentum": { ... },
  "first_seen": "...",
  "last_seen": "...",
  "mention_count": 1,
  "counter_signals": [],
  "is_political": false,
  "claim_kind": "EVENT|CLAIM|OPINION|NOT_POLITICAL",
  "political_neutral": true,
  "eligibility": {
    "eligible": true,
    "reasons": ["publishable", "valid_title", "valid_source", "not_rumour", "not_unverified", "no_blocking_counter_signal"],
    "blocking_reasons": []
  },
  "pipeline_meta": {
    "pipeline_version": "phase2-batch3b2-v1",
    "freshness_hours": 48,
    "freshness_anchor": "last_seen"
  }
}
```

No `body` field. No `summary` field auto-generated. No LLM text.

---

## 5. Candidate States

| State              | Meaning                                                       |
| ------------------ | ------------------------------------------------------------- |
| `CANDIDATE`        | Eligible but data may have minor gaps; held for review.       |
| `BLOCKED`          | At least one blocking reason. Will not be surfaced.           |
| `READY_FOR_REVIEW` | All data present, source URLs valid, no blocking reason.       |

**`READY_FOR_REVIEW` is not `APPROVED`.** It means only that the candidate
deserves a human / rule-based review. Approval and publication are
out-of-scope for this batch.

---

## 6. Eligibility Rules

A topic is evaluated against the following gates. **ALL gates must pass**
for a `READY_FOR_REVIEW` candidate. Any failure produces a `BLOCKED` candidate
with a machine-readable `blocking_reasons` list.

| Gate                          | Required value                                       |
| ----------------------------- | ---------------------------------------------------- |
| `topic.publishable`           | `True`                                               |
| `topic.title`                 | non-empty, after sanitization                        |
| `topic.content_key`           | non-empty                                            |
| `topic.sources`               | at least one                                         |
| `topic.sources[*].url`        | passes `is_safe_url` (http/https, no whitespace)     |
| `topic.sources[*].source_tier`| not all F                                            |
| `topic.verification_status`   | not `RUMOUR`, not `UNVERIFIED`, not `SOCIAL_BUZZ`    |
| `topic.is_political`          | if `True`, then `political_neutral` must be `True`   |
| `topic.claim_kind`            | not `OPINION` if `is_political=True`                 |
| counter signals               | no Tier-A `DENIAL` or `CORRECTION`                   |
| freshness                     | `last_seen` within `freshness_hours` (default 48)    |

---

## 7. Blocking Reasons (Enum)

```
invalid_topic
not_publishable
missing_title
missing_source
invalid_source_url
unverified
rumour
social_buzz_only
tier_f_only
tier_a_denial
political_non_neutral
stale
malformed
```

These are **stable strings**, not free text. Future tooling can rely on them.

---

## 8. REPORTED Handling

`verification_status = REPORTED` + `publishable = True` is **NOT** auto-promoted
to `CONFIRMED`. The candidate's `verification_status` stays `REPORTED`. The
eligibility gate is **less strict** for `REPORTED` topics — they may reach
`READY_FOR_REVIEW` provided all other gates pass. The downstream reviewer
makes the actual call.

`REPORTED` is the most common case in real data (current 46/50). This is
correct: most publishable topics are reported-but-not-confirmed, and that
is exactly the right state for human review.

---

## 9. Political Handling

We **never re-judge** politics. The Radar layer's `is_political`,
`claim_kind`, and `political_neutral` are read directly.

| Radar state                       | Candidate outcome             |
| --------------------------------- | ----------------------------- |
| `is_political=True, neutral=True, claim_kind=EVENT/CLAIM` | eligible |
| `is_political=True, neutral=False, claim_kind=OPINION`   | BLOCKED (`political_non_neutral`) |
| `is_political=False`              | eligible (no political gate)  |

Banned phrases are never auto-injected into the candidate metadata
(`best candidate`, `worst candidate`, `likely to win`, `vote for`,
`endorse`, `best party`, `worst party`, ...). The candidate builder
contains no such generation logic.

---

## 10. Source Evidence

A candidate preserves the full Radar source-evidence row for every source.
Sources are dropped (silently) only if:

- The URL is unsafe (`javascript:`, `data:`, `file:`, `vbscript:`, leading
  whitespace, control characters, length ≥ 2048).
- The source name is empty after trim.
- The source tier is not a known tier (`A`–`F`).

Surviving sources are kept verbatim. **No URL rewriting. No name
inference. No fake corroboration.**

---

## 11. Candidate ID & Dedup

`candidate_id` is a deterministic hash of the content_key:

```
candidate_id = "cand_" + sha256(content_key + schema_version)[:16]
```

`content_key` is already a canonical form in the Radar output (e.g.
`u:<canonical_url>`), so the same logical topic always produces the same
candidate_id, regardless of how many scans re-process it.

**Dedup behaviour:** if a candidate with the same id already exists on
disk, the new payload is validated, the existing `created_at` is
preserved, and the file is atomically replaced. The on-disk count of
`<id>.json` files for any id is always exactly 1.

---

## 12. Freshness

The freshness anchor is `topic.last_seen` (RFC 2822 and ISO 8601 both
supported by the parser). A topic is considered stale when its
`last_seen` is older than `freshness_hours` (default: 48h,
configurable). Stale topics are blocked with `STALE`.

`freshness_hours` is a single, named constant. We do NOT hardcode 24h or
48h in multiple places.

---

## 13. Persistence & Atomic Safety

Layout:

```
radar_data/candidates/
    latest.json
    by_day/
        YYYY-MM-DD/
            <candidate_id>.json
```

Writes are atomic:

1. Build the candidate dict in memory.
2. Run `validate_candidate` (raise `OutputValidationError` on failure).
3. Write to a `.tmp` sibling file.
4. `flush()` + `os.fsync()`.
5. `os.replace(tmp, final)`.

If any step fails, the previous file content is preserved. A partial
write cannot appear as a valid candidate.

A write failure is also caught at the pipeline level: the previous
candidate store remains intact, and the failure is recorded as a
warning in the scheduler's `record.error`.

---

## 14. Scheduler Integration

`radar.scheduler.run_once` invokes the candidate pipeline **after** a
successful scan, in a `try/except`. The candidate pipeline:

- Does NOT change the scan's `status` (SUCCESS / PARTIAL / FAILED).
- Does NOT change the scan's `record.error` (only appends warnings).
- Does NOT touch the public website JSON.
- Does NOT touch git.

A candidate failure is recorded as
`candidate_generation_warning: <ExceptionClass>: <message>` in
`record.error`, but the scan is still marked SUCCESS.

---

## 15. Git Automation — Intentionally Excluded

`python -m radar.scheduler` does NOT execute `git add`, `git commit`,
or `git push`. The candidate layer lives in `radar_data/candidates/`,
which is gitignored. A future batch may add an external CI / Cloudflare
build hook for public artifact deployment, but that is NOT in scope
for Phase 2 B3B-2.

The candidate module is statically verified to contain no `subprocess`,
`os.system`, or git invocations (test
`test_no_git_commands_in_candidate_module`).

---

## 16. Security

- **URL safety** mirrors the public feed adapter (`is_safe_url`).
  Whitespace, control characters, dangerous schemes, and
  > 2048-char URLs are all rejected.
- **Title sanitization** strips control characters (ord < 32 or == 127).
  Printable Unicode (CJK, accents) is preserved verbatim. Length is
  clamped to 400.
- **No HTML execution** in the candidate layer. Rendering is the
  responsibility of the JS adapter, which uses `textContent` (auto-
  escaping).
- **Determinism** — same `content_key` → same `candidate_id`. No
  UUID, no time-based id.

---

## 17. Tests

64 new tests in `radar/tests/test_candidate.py`, plus 314 pre-existing.
All 378 tests pass.

Coverage:
- Candidate model (5)
- Eligibility (15)
- REPORTED handling (2)
- Politics (5)
- Dedup (5)
- Freshness (3)
- Persistence (6)
- Scheduler integration (3)
- Security (10)
- Regression / extras (10)

---

## 18. Real-World Validation

Three consecutive real runs against the live internal output:

| Run | Topics seen | Candidates on disk | READY_FOR_REVIEW | BLOCKED |
| --- | ----------- | ------------------ | ---------------- | ------- |
| T1  | 93          | 50                 | 47               | 3       |
| T2  | 93          | 50                 | 47               | 3       |
| T3* | 93          | 50                 | 47               | 3       |

* T3 simulated a verification change on a topic; the on-disk candidate
  updated, and no duplicate was created.

Stable candidate_id is verified: `cand_<sha256[:16]>` is deterministic
across runs.

---

## 19. Production Safety

- Website is unchanged. `index.html`, `hot/`, `malaysia/`, `viral/`,
  `celebrity/`, `food/`, `world/`, `article/example/` are byte-identical.
- `public/radar/latest.json` shows the expected time-based refresh
  from the re-scan, but no candidate data is exposed.
- `sitemap.xml`, AdSense verification, legal pages are untouched.
- No candidate metadata is exposed to website visitors.
- `radar_data/candidates/` is gitignored — the candidate store
  never enters the production repository.

---

## 20. Limitations

- The Candidate layer does not perform any LLM-based judgement. All
  decisions are deterministic rules.
- Confidence is a heuristic label inherited from Radar; we do not
  compute or display percentages.
- No article body, summary, or paraphrase is generated.
- "Independent source" calculation is delegated to the Radar layer; we
  only surface the already-computed result.
- The Candidate layer does not enforce a maximum number of candidates
  per day; it surfaces every eligible topic. Future editorial
  workflow (out of scope) will apply manual / rule-based filtering.

---

## 21. Future Publishing Architecture (NOT in this Batch)

```
   READY_FOR_REVIEW
        ↓
   [Future] Article Generation
        ↓
   Draft article (headline, body, sources, claims)
        ↓
   [Future] Human / Rule QA
        ↓
   [Future] Approved article
        ↓
   [Future] Publishing to /article/<slug>/
        ↓
   [Future] Facebook / TikTok / Instagram (separate batches)
```

Each step is its own future batch. **No step is part of Phase 2 B3B-2.**

---

## 22. Recommended Next Batch

Phase 2 B3B-3 (or equivalent) — but only after human review of
candidate behaviour. Suggested scope:

- Manual review of 10–20 candidates to confirm eligibility gates
  reflect real editorial standards.
- Optional: add a Candidate UI (admin-only) for human review workflow.
- Still: NO publication. NO CMS. NO social posting.
