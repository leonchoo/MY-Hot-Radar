# .backup/

This directory holds the **Daily Experience Backup** tooling for MY Hot Radar.

The purpose is to back up the project's verified-experience memory
(`EXPERIENCE.md` and the supporting Project Memory MDs) to GitHub
`master` once per day. It does **not** create commits on days without
changes.

---

## Files in this folder

| File | Purpose |
|---|---|
| `backup-experience.ps1` | The actual backup script. Idempotent, safe, no auto-authored content. |
| `install-experience-backup.ps1` | Installs (or uninstalls, with `-Uninstall`) the Windows Task Scheduler job. |

---

## Schedule

- Frequency: every day
- Time: **23:30** local
- Behavior if PC was off: runs at next startup (`StartWhenAvailable = true`)

---

## Source files backed up

| File | Why |
|---|---|
| `EXPERIENCE.md` | Core. Verified Experience Library. |
| `PROJECT_CONTEXT.md` | Long-lived project context. |
| `DEVELOPMENT_RULES.md` | Hard rules for development. |
| `NEWS_RADAR.md` | Radar design (target). |
| `CONTENT_RULES.md` | Voice / status / banned phrases. |
| `VERIFICATION_RULES.md` | Verification bar. |

Other files in the repo are NOT touched by this workflow.

---

## GitHub repository

- Repo: `leonchoo/MY-Hot-Radar`
- Branch: `master`
- Remote URL: `https://github.com/leonchoo/MY-Hot-Radar.git`

The script **never** invokes:
- `git push --force`
- `git reset --hard`
- `git rebase`
- `git commit --amend`
- `git rebase` of any kind

If push fails, local commit is preserved and the report flags it as
FAILED with an `Action Required:` line.

---

## Failure handling

If the script fails, it prints a clear `Action Required:` line. The
user is the safety net:

- **Local files never deleted by the script.**
- **Local commit is kept** even if push fails.
- The script does not auto-retry beyond the next scheduled run.

---

## Secrets

No tokens, no API keys, no passwords in this folder. The repo currently
uses HTTPS for git push; credentials are managed by the user's existing
git credential helper (Windows Credential Manager) and never written into
Git by the script.

If Facebook API / Cloudflare API integration is added later, secrets
must live in:

- Windows Credential Manager
- Environment variables (process-level)

Never in `EXPERIENCE.md`, never in any Git-tracked file.
