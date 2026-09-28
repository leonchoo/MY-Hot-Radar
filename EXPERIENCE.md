# MY Hot Radar — Verified Experience Library

> This is the **Verified Experience Library** for MY Hot Radar.
> Read alongside `PROJECT_CONTEXT.md` and `DEVELOPMENT_RULES.md`.

---

## Purpose

The library exists so that MY Hot Radar can accumulate **real,
repeatable**, **verified** lessons over time — instead of relearning the
same things each batch, or letting single observations drift into
permanent "rules".

It is not a notebook, not a changelog, and not a brainstorm scratchpad.

---

## Promotion ladder (binding)

```
Observed     a single-task observation, not yet a rule
    ↓
Investigated the observation has been reproduced OR its root cause is
             located
    ↓
Verified     the lesson has been independently reproduced AND has a
             documented verification path
    ↓
Reusable     the lesson is written into this file in the EXP-### format
```

Only entries at **Reusable** level live here.

`Observed` items belong in the temporary chat context or a scratchpad.
They MUST NOT be promoted to `Reusable` automatically.

A pattern must be observed at least twice in independent tasks before
promotion to `Verified`. (Single success ≠ rule.)

---

## Hard non-criteria

Never write into this file:

- a guess, even a confident one
- a single successful run
- an unconfirmed theory about why something works
- a workaround not yet validated as the right one
- a subjective preference ("I think X is cleaner than Y")
- a recurring pain that has not been traced to a cause
- any token, password, API key, or secret

If in doubt, do **not** write.

---

## Entry format (binding)

```
## EXP-### — Title

### Context
What happened, in one paragraph.

### Problem
What was wrong or what was the constraint.

### Investigation
What was actually checked / read / reproduced to understand it.

### Finding
The factual result of the investigation.

### Solution
The concrete change adopted (or rule adopted).

### Verification
How the solution was confirmed, with reproduction steps.

### Reuse Rule
In which future situations this rule should be applied.

### Date
YYYY-MM-DD

### Related Commit
<sha> or "N/A (rule, not code)"
```

No entry without all nine sections filled in.

---

## Daily backup governance

This file (and the four supporting memory files in `PROJECT_CONTEXT.md`)
is backed up daily to GitHub `master` via the workflow in
`docs/EXPERIENCE_BACKUP.md` and the script
`.backup/backup-experience.ps1` (Windows Task Scheduler, 23:30 daily).

**Automated backups only back up what's here.** They do **not** write
content into this file.

---

## Library contents

(empty)

The library is empty by design. Entries are added by hand (or under
human approval), and only at the `Verified` level.
