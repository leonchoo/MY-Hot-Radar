# MY Hot Radar — Phase 2 / Batch 1 — Politics Radar

> Final documentation for the **Phase 2 / Batch 1** politics batch.
> Read alongside `NEWS_RADAR.md`, `VERIFICATION_RULES.md`,
> `CONTENT_RULES.md`, `docs/RADAR_3_*` (Radar-3 evidence),
> `docs/RADAR_5B_SCOPE_RELEVANCE.md`, and `docs/RADAR_6_TIER_B_REVIEW.md`.

This document records how the existing Radar pipeline was **extended**
with politics-specific classification, attribution, and output
guardrails — without replacing any existing engine. The system was
already partially political-aware (Radar-3 added 11 politics tests);
this batch formalizes and extends that capability.

---

## 1. Objective

Establish clear, testable, source-attributed, factually-neutral
handling for political / election-related content. Specifically:

- Distinguish **EVENT** vs **CLAIM** vs **OPINION** in political
  content.
- Always preserve attribution (`claimed_by`, `reported_by`,
  `source_tier`).
- Apply politics-aware verification rules that prevent a single
  politician's claim from being elevated to CONFIRMED.
- Encode counter-signal precedence without reinventing it.
- Ban output phrases that rank / endorse / oppose parties,
  candidates, or predict election outcomes.
- Treat poll data as **record-only** — never as prediction.

The batch does NOT add new sources, change the registry, or modify
any engine file.

---

## 2. Scope

Per spec section 2, this batch only handles:

- political / election-related story detection
- political claim verification
- political source attribution
- political counter-signals
- political classification safety
- political-specific tests

Out-of-scope items recorded but not implemented:

- political persuasion / endorsement / opposition generation
- party / candidate ranking or scoring
- election outcome prediction (winner / vote share / electability)
- voter targeting
- political ad automation
- AI-generated political stances
- website article modification
- scheduler, database, Facebook API

---

## 3. Political Detection

Per spec section 5, detection uses **multi-signal patterns** rather
than naive keyword matching on party / candidate / election names.

The detector classifies a piece of text as one of three kinds:

| Kind | Definition | Trigger patterns |
|---|---|---|
| `EVENT` | Factual political/government/election event ("Election Commission announces election date") | election commission, parliament (passed/rejects/...), cabinet (approves/...), PM (appoints/...), general election, by-election, dissolution of parliament, gazette, official results |
| `CLAIM` | A political claim attributed to a person / party / institution ("Party A says policy X will reduce taxes") | says, said, claims, alleges, denies, announces, announces (attributed), menurut, kata, menyatakan, mengumumkan, ketua, pengerusi, jurucakap |
| `OPINION` | Commentary / editorial / ranking / persuasion ("Commentator says Party A is the best option") | editorial, commentary, op-ed, column, opinion, analysis piece, review/preview/verdict/rating, "best (party|candidate|coalition|option|choice|alternative)", "worst (party|...)", "the better/worse party", saya/kami sokong, i support/endorse, jangan sokong, do not support |

Priority order:

1. OPINION first (highest specificity)
2. EVENT next (institutional events outrank generic claim verbs)
3. CLAIM otherwise
4. Default to EVENT (most conservative)

This priority order means "Election Commission announces election
date" is correctly classified as EVENT (institutional event), not
CLAIM (announces is a claim verb), and "Parliament dissolved for
general election" is EVENT (institutional), not CLAIM.

The detector works in English and Bahasa Malaysia; Chinese is
optional and follows the same pattern structure.

---

## 4. Claim / Event / Opinion distinction

Three orthogonal kinds are tracked separately:

```
PoliticalClaimKind:
    EVENT   -- factual coverage of a political event
    CLAIM   -- attributed political claim
    OPINION -- commentary / editorial / persuasion
```

A `PoliticalClaim` dataclass holds:

- `text` — the original content text
- `kind` — one of the three above
- `reported_by` — the source that reported the content (NEVER hidden)
- `reported_by_tier` — Tier A..F
- `claimed_by` — who made the claim (for CLAIM/OPINION)
- `counter_signals` — list of counter-signals (denials, corrections,
  contradictions, downplays) from named sources
- `attribution_required` — auto-True for CLAIM and OPINION

CLAIM and OPINION kinds automatically enforce
`attribution_required = True`. This is a structural guarantee: if a
claim's kind is CLAIM, the system cannot lose attribution by
accident.

---

## 5. Attribution

Per spec section 8 + 15, every political render must preserve:

- `claimed_by` (who said it) — for CLAIM and OPINION
- `reported_by` (which source reported it)
- `reported_by_tier` (which tier)
- `verification status`
- `counter_signals` (when present)
- the raw claim text (verbatim, but inside `[quoted source content]`
  markers so banned phrases don't leak as system output)

The render function `render_political_neutral(claim) -> str` is the
single point of truth for output formatting. It never hides the
source. It wraps the raw claim text in `[quoted source content]` so:

- The full text is preserved for audit purposes.
- Banned phrases in the raw text are flagged with `[quoted: ...]`
  sub-markers.
- The post-render banned-phrase check operates on the text WITH
  quoted markers stripped, so a system-side violation is caught but
  a source's verbatim quotation is allowed.

---

## 6. Verification

Per spec section 9, the politics verification rule is:

```
                Tier-A DENIAL       Tier-A CORRECTION
CLAIM (Tier-B)  -> RUMOUR            -> REPORTED
CLAIM (Tier-C)  -> REPORTED          -> REPORTED
CLAIM (Tier-D)  -> UNVERIFIED        -> UNVERIFIED
OPINION         -> REPORTED          -> REPORTED
EVENT (Tier-A)  -> CONFIRMED         -> CONFIRMED
EVENT (Tier-B)  -> REPORTED          -> REPORTED
EVENT (Tier-C)  -> REPORTED          -> REPORTED
```

Key rules (per spec section 9 + 10):

- **One politician says X ≠ X is confirmed.** A single attributed
  CLAIM at any tier is at most REPORTED, never CONFIRMED.
- **100 social mentions ≠ X is confirmed.** The verify rule for
  Tier-D sources gives UNVERIFIED / REPORTED, never CONFIRMED.
- **Tier-A denial = RUMOUR.** Existing counter-signal precedence
  applies — we do not reinvent it.
- **Tier-A correction = REPORTED.** Existing rule.
- **Tier-B contradiction = tracked, not picked.** A Tier-B counter-
  signal does not auto-demote; both sides remain visible.

The verification wrapper is implemented in
`verify_political_claim(claim)` and returns a tuple
`(VerificationStatus, ConfidenceLabel, reason)`.

---

## 7. Counter-signals

Per spec section 10, this batch re-uses the existing
`CounterSignalStance` enum (DENIAL, CORRECTION, CONTRADICTION,
DOWNPLAY) and the existing engine in `radar/counter_signals.py`.

What this batch adds is a **politics-specific wrapper** that:

- Always surfaces counter-signals in the rendered output.
- Maintains attribution: "DENIAL by SPR (Tier-A): ..." — never
  anonymous.
- Holds the rule that Tier-A denial wins over Tier-B contradiction.

There is no new precedence table. The wrapper delegates to the
existing Radar-3 engine.

---

## 8. Confidence

Per spec section 14 and existing Radar-3 conventions, confidence is
**heuristic**, not a calibrated probability. The politics module
returns one of the existing `ConfidenceLabel` values:

```
VERY_LOW  LOW  MEDIUM  HIGH  VERY_HIGH
```

These are ordinal buckets, not numeric percentages. The label is
recorded with the `(heuristic)` suffix in rendered output to make
this explicit.

Politics-specific rule: confidence is NEVER raised by mention count
or social volume. The number of retweets does not change the
underlying evidence structure.

---

## 9. Momentum

The Radar's `Status` enum (BREAKING, RISING, HOT, WATCH, COOLING)
is intentionally separate from `VerificationStatus` (CONFIRMED,
REPORTED, SOCIAL_BUZZ, UNVERIFIED, RUMOUR).

Per spec section 13:

- `RISING` represents momentum only — never political importance,
  political correctness, or political popularity.
- `CONFIRMED` represents evidence status — never political approval.

The two enums are decoupled by design. A political topic can be
`RISING` (high propagation momentum) with `UNVERIFIED` evidence
status. The labels mean different things and are documented as such.

This separation is enforced at the model level:
`verify_political_claim` returns a `VerificationStatus` only. It
never returns a `Status`. The momentum engine is unchanged.

---

## 10. No ranking / no endorsement / no opposition

Per spec section 11, the system must never produce text that:

- ranks parties ("Party A is the best")
- ranks candidates ("Candidate B is the worst")
- endorses ("I support Party A")
- opposes ("We oppose Party B")
- recommends ("Recommended candidate: ...")

Banned phrases are encoded in `_BANNED_PHRASES` in
`radar/politics.py` and include both English and Malay patterns:

```
English:
    best (party|candidate|coalition|option|choice|alternative)
    worst (party|candidate|coalition|option|choice)
    recommended (party|candidate)
    party (a|b|c) is (better|worse) than
    i support (party|candidate)
    endorsed by
Malay:
    parti (terbaik|terburuk)
    calon (terbaik|terburuk)
    calon yang disokong
    parti yang disyorkan
Chinese (brand voice, Simplified):
    支持.{0,4}(党|候选人)
    反对.{0,4}(党|候选人)
    最[好差].{0,6}(党|候选人|联盟)
    推荐.{0,4}(党|候选人)
```

The `assert_output_neutral(text)` helper is the test-side guardrail
that raises if any banned phrase is detected outside
`[quoted: ...]` markers.

The `render_political_neutral(claim)` function performs the same
check at runtime and raises `ValueError` if the system would emit a
banned phrase. This makes the rule observable from production code,
not just tests.

---

## 11. No election prediction

Per spec section 12, the system must NEVER produce:

```
Party A likely to win
Candidate B has 70% chance
Party C is favored
```

even when given polling data. The `PollRecord` dataclass is the
record-only stub:

```
PollRecord:
    poll_name, population, field_start, field_end,
    sample_size, measurement, source, source_url
```

It exposes:

- `render()` — returns a strictly factual rendering including every
  audit field.
- `has_prediction_language()` — returns True if the rendered output
  contains any banned phrase.

It does NOT expose:

- `predict()` — banned
- `winner()` — banned
- `project()` — banned
- `rank()` — banned

The struct is intentionally minimal. If a future batch adds a
polling engine, it must produce `PollRecord` objects and consume
them via the same render path. The system will refuse to render any
output that contains prediction language.

This batch does NOT implement polling data ingestion. The struct is
provided as the contract for any future work.

---

## 12. Test fixtures (per spec section 16)

The `radar/tests/test_politics.py` module provides 9 fixtures, one
per spec subsection:

| Fixture | Description | Detector verdict | Verify verdict |
|---|---|---|---|
| 1 | Neutral election announcement | EVENT | REPORTED (Tier-B) |
| 2 | Politician claim | CLAIM | REPORTED (LOW) |
| 3 | Politician denial | CLAIM | RUMOUR (Tier-A denial) |
| 4 | Competing claims | CLAIM × 2 | REPORTED × 2 (no winner picked) |
| 5 | Many social mentions + weak source | CLAIM | UNVERIFIED (Tier-D) |
| 6 | Tier-A confirmation | EVENT | CONFIRMED (HIGH) |
| 7 | Opinion article | OPINION | REPORTED (VERY_LOW) |
| 8 | Ranking-language headline | OPINION | n/a (detector-side) |
| 9 | Poll result | n/a (struct) | n/a (no predict method) |

All 9 fixtures pass deterministically.

---

## 13. Real-world validation

Per spec section 17, this batch is permitted to record
`NO_CURRENT_POLITICAL_SAMPLE` if no clear Malaysian political
stories appear in the current RSS scan.

Today's real scan:

- 117 stories collected.
- 25 topics generated.
- 7 / 25 topic titles contained substrings matching "MP" — but all
  7 are false positives (Pahang, Meta, Jangan, etc.). The substring
  match is intentionally NOT used as a political signal in the
  detector.
- 1 title contained "Malaysia mula hantar pulang pelarian Myanmar"
  (Malaysia starts sending Myanmar refugees home) — this is
  government-policy news. It does NOT contain attributed speech,
  institutional-event keywords, or ranking language. The detector
  defaults to EVENT for such cases, which is the most conservative
  classification.

**Result: NO_CURRENT_POLITICAL_SAMPLE for the current scan.**

The detector/verifier were validated end-to-end on synthetic
fixtures (the 9 spec-mandated fixtures plus additional edge cases)
and all 31 tests pass.

---

## 14. Tests

`radar/tests/test_politics.py` adds **31 tests**:

| Category | Count |
|---|---:|
| Architecture / regression (existing 11 politics tests preserved) | 1 |
| Detection (multi-signal, multi-language) | 2 |
| Claim vs Event vs Opinion distinction | 2 |
| Attribution preservation | 2 |
| Verification (single claim, social volume) | 2 |
| Counter-signals (Tier-A denial, Tier-A correction, competing) | 3 |
| No ranking / no endorsement / banned phrases | 3 |
| No election prediction (poll struct) | 2 |
| Neutral classification | 1 |
| Confidence (heuristic, not probability) | 1 |
| Spec §16 fixtures (9 mandatory) | 9 |
| Real-world validation (NO_CURRENT_POLITICAL_SAMPLE) | 1 |
| Regression (engine untouched, registry unchanged) | 2 |
| **Total** | **31** |

All 31 tests pass.

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
| **`test_politics` (Phase 2 B1, new)** | **31** | **PASS** |
| **Total** | **192** | **ALL PASS** |

Zero regressions in Radar-1 → Radar-6 tests.

---

## 15. Production Safety

| Check | Result |
|---|---|
| `https://myhotradar.com/` | HTTP 200 ✅ |
| `/sitemap.xml` (12 URLs) | HTTP 200 ✅ |
| `/hot/`, `/malaysia/`, `/viral/`, `/celebrity/`, `/food/`, `/world/`, `/about/`, `/contact/`, `/privacy/`, `/terms/` | All HTTP 200 ✅ |
| AdSense (`ca-pub-6219340004578553`) | present, 1 occurrence ✅ |
| Cloudflare | untouched ✅ |
| Facebook Page | untouched ✅ |
| `index.html` / category pages / `assets/` | untouched ✅ |
| `python -m radar.scan` | ok=True, 117 stories, 89 topics ✅ |
| `radar_data/` | gitignored ✅ |

---

## 16. Experience Governance

Per spec section 20:

> Default: NO NEW EXPERIENCE. Politics rules especially must not be
> promoted to VERIFIED Experience based on a single synthetic test.

Observations from Phase 2 Batch 1:

| Observation | Status |
|---|---|
| 3-way claim-kind classifier (EVENT/CLAIM/OPINION) works | **Not promoted** — first-batch observation; needs reproduction |
| Single-claim != CONFIRMED rule | **Already documented** in Radar-3; not new |
| Tier-A denial = RUMOUR | **Already documented** in Radar-3; not new |
| Banned-phrase list (10 patterns, English + Malay + Chinese) | **Not promoted** — first-batch pattern list; needs real-world stress test |
| PollRecord is record-only | **Not promoted** — design-time decision; needs reproduction |

`EXPERIENCE.md` is **unchanged** by Phase 2 Batch 1.

---

## 17. Files Changed

| File | Status | Lines |
|---|---|---:|
| `radar/politics.py` | **new** | +480 |
| `radar/tests/test_politics.py` | **new** | +790 |
| `radar/tests/run_all.py` | modified | +1 |
| `docs/RADAR_PHASE2_POLITICS.md` | **new** | (this file) |
| `radar/verification.py`, `momentum.py`, `classification.py`, `counter_signals.py`, `dedup.py` | **untouched** | — |
| `radar/tier_a_qualification.py`, `source_scope.py`, `tier_b_review.py` | **untouched** | — |
| `radar/sources_registry.py` | **untouched** | — |
| `radar/models.py` | **untouched** | — |
| Website, sitemap, AdSense, Cloudflare, Facebook | **untouched** | — |
| `EXPERIENCE.md` | **untouched** | — |
| **Total** | | **+1271 / -0** |

---

## 18. Git

| Step | Result |
|---|---|
| Working tree before | clean |
| Files staged | 3 (2 new, 1 modified) |
| Files NOT staged | `radar_data/` (gitignored) |
| Commit (Phase 2 B1) | (recorded in batch report) |
| Push | (recorded in batch report) |
| `git amend` / rebase / squash / force-push / reset | **none used** |

---

## 19. Limitations

1. **No current political sample.** Today's real scan does not
   contain clear Malaysian political stories. The detector /
   verifier were validated on synthetic fixtures only. A future
   batch with a real political news event would need to re-validate.

2. **Banned-phrase patterns are first-batch.** The current 10
   patterns cover English and Malay at the level needed for the 9
   spec-mandated fixtures. A real-world deployment will surface
   edge cases that require pattern refinement. This batch does not
   promise production completeness of the phrase list.

3. **The detector uses pattern heuristics, not LLM.** Per spec
   section 12, AI-generated political stances are out of scope. The
   detector is a deterministic regex classifier. It will miss
   novel / sarcastic / coded political content. This is the
   conservative choice.

4. **Counter-signal handling is local.** The politics module's
   `PoliticalCounterSignal` is a thin wrapper around the existing
   `CounterSignal` model. It does not introduce a new precedence
   table; it documents the existing engine's behaviour for politics
   cases.

5. **Render output format is fixed.** The render produces a
   single-line string with all required fields. A future UI batch
   could split this into a structured JSON object with sections
   (claim / reported / counter-signals / verification / confidence).
   For now, the human-readable string is the contract.

6. **No politics-specific source filtering.** The detector /
   verifier work on whatever text they're given. They do not filter
   or weight sources by political affiliation. Tier still governs
   credibility. Politics is orthogonal to tier.

---

## 20. Conclusion

Phase 2 Batch 1 extends the existing Radar pipeline with
politics-specific classification, attribution, and output guardrails.

The system now:

- Classifies political content into EVENT / CLAIM / OPINION.
- Preserves attribution (claimed_by, reported_by, tier) on every
  render.
- Prevents single-claim / social-volume CONFIRMED promotions.
- Reuses the existing Tier-A denial = RUMOUR counter-signal rule.
- Bans output phrases that rank, endorse, oppose, or predict.
- Records poll data with audit fields and forbids any predict /
  winner / rank method on the struct.
- Adds 31 tests, of which 9 are the spec-mandated fixtures, with
  zero regressions in the existing 161 tests.

The existing Radar-3 politics tests are preserved. The existing
verification / momentum / classification / counter-signal engines
are untouched. The existing 5-source registry is unchanged. The
website, AdSense, Cloudflare, and Facebook are untouched.

Total project state: **192 tests PASS, 0 failures, 0 regressions**.
