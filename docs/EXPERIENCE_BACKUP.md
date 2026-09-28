# MY Hot Radar - Daily Experience Backup

This document describes how the Project Memory is automatically backed up
to GitHub `master` once a day. It is meant to be read alongside
`PROJECT_CONTEXT.md` and `EXPERIENCE.md`.

---

## Goal

> Ensure **verified, durable** knowledge accumulated by MY Hot Radar
> is preserved across time, machines, and sessions.

What this means concretely:

1. Every day, the six Project Memory MD files are inspected for change.
2. If at least one of them genuinely changed, a single normal Git
   commit is created and pushed to `master`.
3. If nothing changed, **no commit is created** (no empty log noise).
4. The backup tool never writes content into `EXPERIENCE.md`. It only
   backs up what is already there.

---

## What gets backed up

| File | Why |
|---|---|
| `EXPERIENCE.md` | Verified Experience Library (the most important file). |
| `PROJECT_CONTEXT.md` | Long-lived project context. |
| `DEVELOPMENT_RULES.md` | Hard development rules. |
| `NEWS_RADAR.md` | Future Radar design (target spec). |
| `CONTENT_RULES.md` | Voice, status, banned phrases. |
| `VERIFICATION_RULES.md` | Verification bar. |

Anything else in the repo is **not** touched by this workflow.

---

## Schedule

- Frequency: every day
- Time: **23:30** local time
- If the PC was off at 23:30: runs at next startup
  (`StartWhenAvailable = true`)

---

## Implementation

| Piece | Where |
|---|---|
| Backup script | `.backup/backup-experience.ps1` |
| Installer (Task Scheduler) | `.backup/install-experience-backup.ps1` |
| Folder readme | `.backup/README.md` |
| Windows job name | `MY Hot Radar Daily Experience Backup` |

The Windows Task Scheduler job is created by running, in an elevated
PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.backup\install-experience-backup.ps1
```

To remove later:

```powershell
.\.backup\install-experience-backup.ps1 -Uninstall
```

---

## Behaviour matrix

| Situation | Action |
|---|---|
| All 6 MDs identical to `master` | No commit. Report `New verified experience: NO`. |
| One or more MDs changed | Stage only those MDs, single commit, push. |
| Working tree contains other edits (code, assets, etc.) | **Refuse to commit.** Print the offending paths; ask the user to clean up. |
| New MD file (untracked) matching a watched name | Stage and commit normally. |
| Staged area contains non-MD files (e.g. accidentally `git add .`) | **Refuse to commit.** Reset staged area; report. |
| `git commit` itself fails | Leave local files untouched. Print `Action Required:`. |
| `git push` fails | Local commit is preserved. Report push `FAILED` with `Action Required:`. |
| `git fetch` fails | Treat as warning only. Push is still attempted. |

Exit codes:
- `0` = clean (either no work, or work + successful push).
- `1` = refused (working tree dirty, branch/remote wrong, etc.).
- `2` = local commit succeeded but remote push failed.

---

## Commit shape

When a commit IS made, the form is fixed:

```
docs: backup verified experience YYYY-MM-DD
```

A second line lists the files included:

```
docs: backup verified experience 2026-09-28
Files: EXPERIENCE.md, CONTENT_RULES.md
```

No `chore:` prefix. No `daily backup` wording. No empty-message commits.

---

## Tested safety properties

The script was designed not to:

- push `--force`
- do `git reset --hard`
- do `git rebase`
- amend a commit
- destroy history
- write content into any MD itself

If any of those were ever required, the rule says: **stop and ask**.

---

## Manual override

To run the backup by hand (e.g. you just shipped a verified experience
and want it on GitHub now):

```powershell
.\.backup\backup-experience.ps1
```

To force-run the scheduled job ad-hoc:

```cmd
schtasks /Run /TN "MY Hot Radar Daily Experience Backup"
```

---

## What this is NOT

- Not a publish tool. It does not tweet, post, or push code live.
- Not a cron daemon. It piggybacks on Windows Task Scheduler.
- Not a content-author. It does not write content into any
  `*.md` itself. Adding an `EXP-###` entry is a **human** task done
  in `EXPERIENCE.md` by hand.

---

## One-time test on install

A first-time install run is recommended in this exact order:

1. Create a small, throwaway test marker (see
   `EXPERIENCE_BACKUP_TEST.md` if you want one — not required).
2. Run `.\.backup\backup-experience.ps1` by hand.
3. Confirm the script created exactly **one** commit and pushed it.
4. Reset the test marker.
5. Verify GitHub `master` shows the test commit.

After that, daily operation is hands-off.
