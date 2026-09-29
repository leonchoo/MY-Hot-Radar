# MY Hot Radar — Radar-5B: Scope & Content Relevance

> Final documentation for the **Radar-5B** batch.
> Read alongside `NEWS_RADAR.md`, `VERIFICATION_RULES.md`,
> `docs/RADAR_5A_TIER_A_DISCOVERY.md`, and `docs/RADAR_4A_STABILITY.md`.

This document records the **authority vs scope vs relevance separation**
work. Radar-5B does NOT introduce new sources or modify the registry.
It establishes the model and rules that prevent the next batch from
re-introducing the "official authority = news source" conflation.

---

## 1. Objective

Radar-5A surfaced three borderline candidates — SPR, KPM, Agrobank —
each of which is a primary authority AND has a stable, parseable feed,
yet is NOT a good fit as a **general** MY Hot Radar source.

The Radar-5A 5-condition rule (identity + relevance + access +
stability + independence) was sufficient to identify these candidates
as Tier-A on the authority axis, but conflated two distinct questions:

- **Authority** — is the publisher a primary authority?
- **Radar-relevance** — is this authority useful for the general
  news radar?

Radar-5B separates those two dimensions so a source can be:

```
authority_tier = A
source_scope = ELECTION
radar_relevance = MEDIUM
registration_decision = NEEDS_FURTHER_VALIDATION
```

…without being REGISTERED, despite passing the Radar-5A authority
check.

---

## 2. Problem discovered in Radar-5A

Per `docs/RADAR_5A_TIER_A_DISCOVERY.md` §5.1, Radar-5A noted:

> The 5-condition rule treats Agrobank as QUALIFIED. A human reviewer
> flagged a separate concern: Agrobank is a state-owned development
> bank whose entire feed is self-promotional press releases about its
> own programs. It does not publish regulatory decisions, fiscal
> policy, or general-interest news.

Radar-5B encodes the human-review concern as a **first-class
dimension** so the rule does not have to drift to include a sixth soft
"scope" condition. The scope classification is documented in code, has
its own tests, and does not affect the Radar-5A 5-condition authority
check.

```
authority ≠ radar relevance
```

This separation is the main architectural contribution of Radar-5B.

---

## 3. Model

The new types live in `radar/source_scope.py`. They are independent
of `radar/tier_a_qualification.py` (Radar-5A) and of the verification
/ momentum / classification engines (Radar-3, Radar-4A).

### 3.1 Enums

```python
class SourceScope(str, Enum):
    GENERAL_NEWS       # general Malaysian news outlet
    GOVERNMENT_NEWS    # government press releases on general topics
    REGULATORY         # regulatory body decisions, circulars
    ELECTION           # election commission, electoral boundaries
    EDUCATION          # ministry of education, schools
    HEALTH             # ministry of health, hospitals
    FINANCE            # finance ministry, central bank
    CORPORATE          # corporate / state-owned enterprise PR
    NICHE              # very narrow scope
    UNKNOWN            # insufficient evidence

class RadarRelevance(str, Enum):
    HIGH        # general topics the radar surfaces regularly
    MEDIUM      # specific high-interest domain (election, education)
    LOW         # narrow / self-promotional / niche
    UNKNOWN     # insufficient evidence

class RegistrationDecision(str, Enum):
    REGISTERED
    NOT_REGISTERED
    NEEDS_FURTHER_VALIDATION

class ContentNature(str, Enum):
    PRESS
    NEWS
    ADMIN_NOTICE
    REGULATORY_NOTICE
    TENDER
    HR
    CORPORATE
    PUBLIC_SERVICE
    PLACEHOLDER
    UNKNOWN
```

### 3.2 Decision pipeline

```
                    observed evidence
                          │
                          ▼
                ┌─────────────────────┐
                │  classify_scope     │  → SourceScope
                │  (publisher + content)│
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │  classify_relevance │  → RadarRelevance
                │  (scope + event_fraction)│
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ decide_registration │  → RegistrationDecision
                │ (scope + relevance + │
                │  authority)         │
                └─────────────────────┘
```

### 3.3 What Radar-5B does NOT change

- `radar/tier_a_qualification.py` (Radar-5A) is untouched.
- `radar/verification.py`, `radar/momentum.py`, `radar/classification.py`,
  `radar/counter_signals.py` (Radar-3 / Radar-4A) are untouched.
- `radar/sources_registry.py` is untouched (no new Tier-A added).
- The 5 existing Tier-B sources are unchanged.
- No new heuristics were added to verification confidence.

---

## 4. SPR — Suruhanjaya Pilihan Raya

### Re-probe (today, fresh)

3 successive fetches of `https://www.spr.gov.my/feed/` returned
bit-identical responses (same SHA-256 each time).

- **Items**: 10
- **Content distribution**:

| Nature | Count | % |
|---|---:|---:|
| ADMIN_NOTICE | 10 | 100.0% |
| PRESS | 0 | 0% |
| NEWS | 0 | 0% |

- **Recency**: newest item 6 days old, oldest 10+ months old.

### Sample titles

All 10 items are `PEMBUKAAN KAUNTER PENDAFTARAN PEMILIH` (counter
openings for voter registration) or `KUNJUNGAN HORMAT` (courtesy
visits). One example: `PEMBUKAAN KAUNTER PENDAFTARAN PEMILIH SEMPENA
PROGRAM HARI BERSAMA AGENSI SURUHANJAYA PILIHAN RAYA DAN JABATAN
PENDAFTARAN NEGARA`.

### Decision

```
authority_tier           = A          (passes Radar-5A 5-condition rule)
source_scope             = ELECTION   (publisher = Suruhanjaya Pilihan Raya)
radar_relevance          = MEDIUM     (constitutional body, election events matter)
registration_decision    = NEEDS_FURTHER_VALIDATION
```

### Why NEEDS_FURTHER_VALIDATION (not NOT_REGISTERED, not REGISTERED)

- NOT_REGISTERED would be a strong claim that SPR can never enter the
  registry. That is a stronger statement than the evidence supports:
  during an actual election period, SPR's feed could carry election
  results and major announcements that ARE general-news-relevant.
- REGISTERED would require the content to be useful for the radar's
  general registry today. The current content is 100% admin notices
  with no event-level information.
- NEEDS_FURTHER_VALIDATION is the conservative default that defers a
  permanent decision while acknowledging the source's authority and
  baseline relevance.

### Politics handling (per spec section 16)

SPR is election-related. Radar-5B's classification of SPR
explicitly **does not** evaluate:
- any candidate or party;
- any election outcome;
- any political sentiment.

It only classifies the source on (scope, relevance, decision). The
classification is the same regardless of who is currently Chairman,
who is contesting, or which party is in government.

---

## 5. KPM — Kementerian Pendidikan Malaysia

### Re-probe (today, fresh)

3 successive fetches of `https://www.moe.gov.my/feed` returned
bit-identical responses.

- **Items**: 340
- **Format**: Atom 1.0
- **Content distribution**:

| Nature | Count | % |
|---|---:|---:|
| TENDER | 145 | 42.6% |
| UNKNOWN | 96 | 28.2% |
| NEWS | 40 | 11.8% |
| CORPORATE | 34 | 10.0% |
| HR | 18 | 5.3% |
| ADMIN_NOTICE | 5 | 1.5% |
| REGULATORY_NOTICE | 1 | 0.3% |
| PUBLIC_SERVICE | 1 | 0.3% |

- **Recency**: most items carry an `<updated>` timestamp from today,
  but actual event dates are encoded inside HTML summaries (e.g.
  "22 JUN 2026"). The feed is active but event-date parsing requires
  HTML extraction.

### Sample items

- TENDER: "Tawaran Tender Perkhidmatan Kebersihan Bangunan dan Kawasan
  (KBK) Tahun 2027"
- NEWS: "Pembentangan Dapatan Terkini Southeast Asia Primary Learning
  Metrics (SEA-PLM) 2024"
- CORPORATE: "Majlis Pelancaran Rancangan Pendidikan Negara 2026–2035"
- HR: "Iklan Kekosongan Jawatan Pegawai Kaunseling dan Pensyarah
  Akademik di Kolej Matrikulasi"

### Decision

```
authority_tier           = A
source_scope             = EDUCATION
radar_relevance          = LOW
registration_decision    = NOT_REGISTERED
```

### Why LOW relevance

`fraction_event_oriented = fraction_press + fraction_news +
fraction_regulatory_notice = 0 + 0.118 + 0.003 = 0.121` (12.1%).

The classify_relevance threshold for EDUCATION requires
`fraction_event_oriented > 0.4` for MEDIUM. KPM is below this. Most
items are tenders, HR, or administrative — useful for procurement
professionals but not for a general Malaysian news radar.

### Why NOT_REGISTERED (not NEEDS_FURTHER_VALIDATION)

Per the decide_registration rule: NICHE/CORPORATE scope OR LOW
relevance → NOT_REGISTERED. The 12% event-oriented fraction is well
below any plausible threshold that would flip a future batch's
decision. Future batches that want to revisit KPM should either
(a) improve the content mix or (b) document a separate radar
pipeline that filters the feed to only the `fraction_news` subset.

---

## 6. Agrobank

### Re-probe (today, fresh)

3 successive fetches of `https://www.agrobank.com.my/feed/` returned
bit-identical responses.

- **Items**: 10
- **Recency**: all 10 items dated within the last 7 days.
- **Content distribution**:

| Nature | Count | % |
|---|---:|---:|
| CORPORATE | 8 | 80.0% |
| PUBLIC_SERVICE | 1 | 10.0% |
| UNKNOWN | 1 | 10.0% |

### Sample titles

- "Agrobank Engages Entrepreneurs at Kuala Lumpur Night Market Fiesta"
- "Six Proton X50 Vehicles Awarded to Mega Million 3.0 Winners at MAHA 2026"
- "Agrobank and BHPetrol Strengthen the Ecosystem for Service Station
  Operators in Agricultural and Rural Areas"
- "Agrobank Empowers Young Agropreneur Talent Through Agro Quest 2026"
- "Muka Sama, Suara pun Sama, Tapi Betul Ke? Awas Deepfake Scam!"
- "Agrobank, BIMAT and KPKM Allocate RM100 Million to Develop a New
  Generation of Agropreneurs"

### Decision

```
authority_tier           = A          (state-owned via MOF Inc., passes Radar-5A)
source_scope             = CORPORATE  (self-promotional, fraction_corporate=0.8)
radar_relevance          = LOW        (event_fraction=0)
registration_decision    = NOT_REGISTERED
```

### Why CORPORATE not FINANCE

The classifier's Rule 6 fires when `is_self_promotional=True` AND
`fraction_corporate > 0.5`. Agrobank's feed is 80% its own programs /
sponsorships / partnerships / RM-allocation announcements. This
matches the CORPORATE pattern (own-program PR), not FINANCE
(treasury / central bank policy).

The distinction is meaningful: a FINANCE source publishes policy
decisions (tax, fiscal, monetary); a CORPORATE source publishes
"Agrobank did X". Both can be state-owned; the content nature
determines scope.

### Why LOW relevance

`fraction_event_oriented = 0` (no press / news / regulatory content
in the 10-item feed). Even though the source is active, the content
mix is entirely self-promotional. A general radar would not surface
these items as news.

### Why NOT_REGISTERED (not NEEDS_FURTHER_VALIDATION)

Same logic as KPM: scope=CORPORATE + relevance=LOW → NOT_REGISTERED.
Agrobank could become useful if it published policy decisions (then
scope=FINANCE, relevance=MEDIUM), but that would require a content
mix change, not just a labelling change.

---

## 7. Rules (the new model)

All rules below are encoded in `radar/source_scope.py` and locked by
`radar/tests/test_source_scope.py`.

### 7.1 Scope classification

Rule-based classifier (in priority order):

1. `is_general_news_outlet == True` → GENERAL_NEWS
2. Publisher contains "pilihan raya" / "election commission" → ELECTION
3. Publisher contains "pendidikan" / "education" / "kpm" / "moe" → EDUCATION
4. Publisher contains "kewangan" / "treasury" / "bank negara" → FINANCE
5. Publisher contains "suruhanjaya" / "regulator" + `fraction_regulatory > 0.3` → REGULATORY
6. `is_self_promotional == True` + `fraction_corporate > 0.5` → CORPORATE
7. `fraction_tender + fraction_hr + fraction_admin_notice > 0.7` → NICHE
8. Otherwise → UNKNOWN

### 7.2 Relevance classification

```
GENERAL_NEWS                                  -> HIGH
GOVERNMENT_NEWS + fraction_event_oriented >0.5 -> HIGH
GOVERNMENT_NEWS + fraction_event_oriented ≤0.5 -> MEDIUM
ELECTION                                      -> MEDIUM
EDUCATION + fraction_event_oriented > 0.4     -> MEDIUM
EDUCATION + fraction_event_oriented ≤ 0.4    -> LOW
REGULATORY + fraction_regulatory_notice > 0.3 -> MEDIUM
REGULATORY + fraction_regulatory_notice ≤ 0.3 -> LOW
FINANCE                                       -> MEDIUM
CORPORATE                                     -> LOW
NICHE                                         -> LOW
UNKNOWN                                       -> UNKNOWN
```

`fraction_event_oriented` = `fraction_press + fraction_news +
fraction_regulatory_notice` (operational / corporate / tender / HR
content does NOT count as event-oriented).

### 7.3 Registration decision

```
authority_qualifies == False                          -> NOT_REGISTERED
GENERAL_NEWS + HIGH relevance                          -> REGISTERED
GOVERNMENT_NEWS + HIGH relevance                       -> REGISTERED
scope in (NICHE, CORPORATE)                            -> NOT_REGISTERED
relevance == LOW                                       -> NOT_REGISTERED
relevance == UNKNOWN                                   -> NEEDS_FURTHER_VALIDATION
MEDIUM + non-GENERAL scope                             -> NEEDS_FURTHER_VALIDATION
otherwise                                              -> NEEDS_FURTHER_VALIDATION
```

The default for anything not explicitly REGISTERED or NOT_REGISTERED
is NEEDS_FURTHER_VALIDATION. This is the conservative default: when
the rules don't give a clear answer, defer.

### 7.4 Important caveats

- These thresholds are **engineering heuristics**, not probability of
  user interest. They are documented as such in code.
- They are NOT calibrated against any user-behavior data. They are
  calibrated against internal consistency (does the model give
  defensible answers on the three borderline cases?).
- They are NOT editorial judgments. "Relevance = LOW" means "the
  current MY Hot Radar general registry has no slot for this content",
  not "this content is unimportant to anyone".

---

## 8. Tests

A new test module `radar/tests/test_source_scope.py` adds **25 tests**:

| Category | Count |
|---|---:|
| Model (enum + dimensional-independence) | 6 |
| Per-source classification (SPR / KPM / Agrobank) | 3 |
| Content nature per-item | 6 |
| Registration decision rules | 5 |
| Registry integrity / regression | 3 |
| Edge cases | 2 |
| **Total** | **25** |

All 25 tests pass.

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
| **`test_source_scope` (Radar-5B, new)** | **25** | **PASS** |
| **Total** | **139** | **ALL PASS** |

Zero regressions in Radar-1 → Radar-5A tests.

---

## 9. Registry impact

| Source | Status | Reason |
|---|---|---|
| SPR | **NOT added** | NEEDS_FURTHER_VALIDATION — content is admin-only today; may become useful during election periods |
| KPM | **NOT added** | NOT_REGISTERED — content is dominated by tenders / HR; not general-news-relevant |
| Agrobank | **NOT added** | NOT_REGISTERED — self-promotional scope; not general-news-relevant |

The `radar/sources_registry.py` file is unchanged. The 5 Tier-B
sources (BBC News Asia, Channel News Asia, CodeBlue, Free Malaysia
Today Bahasa, Borneo Post) remain the only registered sources.

`test_existing_tier_b_registry_unchanged` and
`test_radar_5b_did_not_add_any_new_source` lock this in.

---

## 10. Limitations

- **Content classification is heuristic** (regex keyword matching).
  Errors are possible on titles that mix multiple signals. The
  classifier is multi-language (Malay + English) but not exhaustive.
- **Sample size is the current feed**, not a historical window.
  SPR's current 10 items are all admin notices; during an election
  period the mix could change significantly. Radar-5B's
  NEEDS_FURTHER_VALIDATION outcome for SPR reflects this.
- **`source_scope` is a coarse taxonomy.** Adding finer scopes
  (e.g. SPORTS, TECHNOLOGY) requires an independent batch with new
  evidence and tests for each new value.
- **`radar_relevance` is not user-interest data.** It is an internal
  engineering judgement about whether the source's content would
  plausibly be surfaced by a general radar. It does NOT predict how
  many users would click, share, or trust items from the source.
- **The rule does not consider source-quality dynamics.** A source
  could publish reliably today and stop tomorrow; the rule does not
  detect this. Stability checks remain Radar-5A / Radar-4A
  territory.
- **Politics neutral by construction, not by enforcement.** The
  rule has no opinions about candidates, parties, or election
  outcomes. Any future change to the rule must preserve this.

---

## 11. Experience governance

Per Radar-5B spec section 23:

> Default: NO NEW EXPERIENCE. Do not promote to EXPERIENCE.md just
> because this code looks good. Candidate Experience is fine to
> record in the report; promotion requires independently reproduced,
> reusable, verified knowledge.

Observations from Radar-5B:

| Observation | Status |
|---|---|
| `authority ≠ radar_relevance` is a useful separation | **Not promoted to EXPERIENCE.md** — first observation in this batch; needs reproduction. |
| The 5-condition rule + scope/relevance/decision pipeline separates three orthogonal questions cleanly. | **Not promoted** — design-time observation, not yet a repeated rule. |
| `fraction_event_oriented = press + news + regulatory` is a useful heuristic. | **Not promoted** — heuristic; subject to change. |

`EXPERIENCE.md` is **unchanged** by Radar-5B.

---

## 12. Files changed in Radar-5B

| File | Status | Lines |
|---|---|---:|
| `radar/source_scope.py` | **new** | +535 |
| `radar/tests/test_source_scope.py` | **new** | +677 |
| `radar/tests/run_all.py` | modified | +1 |
| `docs/RADAR_5B_SCOPE_RELEVANCE.md` | **new** | (this file) |
| `radar/tier_a_qualification.py` (Radar-5A) | **untouched** | — |
| `radar/sources_registry.py` | **untouched** | — |
| `radar/verification.py`, `momentum.py`, `classification.py`, `counter_signals.py` | **untouched** | — |
| `radar/models.py` | **untouched** | — |
| **Total** | | **+1213 / -0** |

No website files, Cloudflare config, AdSense, Facebook, source
registry, or Radar engine code modified.

---

## 13. Git

| Step | Result |
|---|---|
| Working tree before | clean |
| Files staged | 3 (2 new, 1 modified) |
| Files NOT staged | `radar_data/` (gitignored) |
| Commit (Radar-5B) | (recorded in batch report) |
| Push | (recorded in batch report) |
| `git amend` / rebase / squash / force-push / reset | **none used** |

---

## 14. Conclusion

Radar-5B established the **scope / relevance / registration** layer
that Radar-5A identified as missing. The new model:

1. Keeps the existing Tier-A authority check unchanged (Radar-5A).
2. Adds independent scope + relevance + decision dimensions.
3. Re-evaluates the 3 borderline candidates under the new rules.
4. Documents why each borderline candidate ends up where it does.
5. Locks the rules in 25 new tests with zero regression.
6. Leaves the registry unchanged.

Result: **0 new Tier-A registered**, but the *process* by which a
candidate becomes registered is now documented, testable, and
explicit about its assumptions.
