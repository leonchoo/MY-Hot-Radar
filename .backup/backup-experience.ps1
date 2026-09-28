# MY Hot Radar - Daily Experience Backup
#
# Runs at 23:30 daily (Windows Task Scheduler).
# Backs up the six Project Memory MDs to GitHub master.
# NEVER writes content into EXPERIENCE.md.
# Creates a commit ONLY when tracked MD files have changed.
#
# Safe against:
#  - daily double-run (idempotent via git diff --name-only HEAD)
#  - GitHub unreachable (stops cleanly, local files untouched)
#  - dirty working tree beyond the MDs (refuses to commit)
#  - accidental force-push (never invokes --force, never resets, never rebases)

param(
    [string]$RepoPath    = 'C:\MY-Hot-Radar',
    [string]$Remote      = 'origin',
    [string]$Branch      = 'master',
    [string[]]$TrackedFiles = @(
        'EXPERIENCE.md',
        'PROJECT_CONTEXT.md',
        'DEVELOPMENT_RULES.md',
        'NEWS_RADAR.md',
        'CONTENT_RULES.md',
        'VERIFICATION_RULES.md'
    )
)

$ErrorActionPreference = 'Stop'
$dateStr = Get-Date -Format 'yyyy-MM-dd'

# ----- 1. Switch to repo -----
if (-not (Test-Path $RepoPath)) {
    Write-Host '[FAIL] Repo path not found: ' $RepoPath
    exit 1
}
Set-Location $RepoPath

# ----- 2. Pre-flight: branch + remote -----
$currentBranch = git branch --show-current
if ($currentBranch -ne $Branch) {
    Write-Host ''
    Write-Host '[FAIL] Branch mismatch: expected ' $Branch ' / got ' $currentBranch
    exit 1
}
$remoteUrl = git remote get-url $Remote 2>$null
if (-not $remoteUrl) {
    Write-Host ''
    Write-Host '[FAIL] Remote ' $Remote ' not configured'
    exit 1
}

# ----- 3. Refuse if working tree has changes outside the watched MDs -----
$dirtyRaw = (git status --porcelain) -as [string[]]
$unrelated = @()
if ($dirtyRaw) {
    foreach ($line in $dirtyRaw) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line.Length -lt 4) { continue }
        $st = $line.Substring(0, 2).Trim()
        $nm = $line.Substring(3).Trim()
        if ($TrackedFiles -notcontains $nm) {
            $unrelated += ($st + ' ' + $nm)
        }
    }
}
if ($unrelated.Count -gt 0) {
    Write-Host ''
    Write-Host 'Experience backup refused: working tree has unrelated changes:'
    foreach ($u in $unrelated) { Write-Host '  ' $u }
    Write-Host 'Action Required: commit, stash, or discard those changes first.'
    Write-Host ''
    Write-Host 'MY Hot Radar - Daily Experience Backup'
    Write-Host "Date: $dateStr"
    Write-Host 'New verified experience: NO'
    Write-Host 'Git commit: NONE'
    Write-Host 'GitHub push: SKIPPED'
    Write-Host 'Working tree: DIRTY'
    Write-Host 'Reason: unrelated changes in working tree'
    exit 1
}

# ----- 4. Fetch (best effort; never fail the backup on fetch issues) -----
try {
    git fetch $Remote $Branch 2>&1 | Out-Null
    $fetchOk = $true
} catch {
    $fetchOk = $false
    Write-Host '[WARN] git fetch failed; push will still be attempted.'
}

# ----- 5. Detect changes to the tracked MDs -----
$changed = @()

# 5a. Already-tracked files that diverge from HEAD
foreach ($f in $TrackedFiles) {
    $out = git diff --name-only HEAD -- $f 2>$null
    if ($out) { $changed += $f }
}

# 5b. Untracked files that match a watched name
$untrackedRaw = git ls-files --others --exclude-standard 2>$null
if ($untrackedRaw) {
    foreach ($u in $untrackedRaw) {
        $nm = $u.Trim()
        if ($TrackedFiles -contains $nm) {
            $changed += $nm
        }
    }
}
$changed = $changed | Sort-Object -Unique

if ($changed.Count -eq 0) {
    Write-Host ''
    Write-Host 'No new verified experience. No backup commit required.'
    Write-Host ''
    Write-Host 'MY Hot Radar - Daily Experience Backup'
    Write-Host "Date: $dateStr"
    Write-Host 'Time: 23:30'
    Write-Host 'Experience files checked: PASS'
    Write-Host 'New verified experience: NO'
    Write-Host 'Git commit: NONE'
    Write-Host 'GitHub push: SKIPPED'
    Write-Host 'Working tree: CLEAN'
    Write-Host 'Reason: no changes'
    exit 0
}

# ----- 6. Stage the changed MDs only -----
foreach ($f in $changed) {
    git add -- $f
}

# Sanity check: confirm only MD files are staged.
$stagedRaw = (git diff --cached --name-only) -as [string[]]
$stagedOutside = @()
foreach ($s in $stagedRaw) {
    $s = $s.Trim()
    if (-not $s) { continue }
    if ($TrackedFiles -notcontains $s) {
        $stagedOutside += $s
    }
}
if ($stagedOutside.Count -gt 0) {
    Write-Host ''
    Write-Host '[FAIL] Refusing to commit - non-MD files staged:'
    foreach ($o in $stagedOutside) { Write-Host '  ' $o }
    Write-Host 'Action Required: reset staged area, then rerun.'
    git reset HEAD 2>&1 | Out-Null
    exit 1
}

# ----- 7. Commit -----
$commitMsg = "docs: backup verified experience $dateStr"
git commit -m $commitMsg -m "Files: $($changed -join ', ')" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host '[FAIL] git commit failed. Local files untouched.'
    Write-Host 'Action Required: inspect git status, fix manually.'
    exit 1
}

$commitSha = (git rev-parse HEAD).Substring(0, 7)

# ----- 8. Push -----
$pushOutcome = ''
try {
    git push $Remote $Branch 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $pushOutcome = 'PASS' }
    else { $pushOutcome = 'FAILED' }
} catch {
    $pushOutcome = 'FAILED'
}

# ----- 9. Final report -----
Write-Host ''
Write-Host '===================================================='
Write-Host 'MY Hot Radar - Daily Experience Backup'
Write-Host "Date: $dateStr"
Write-Host 'Time: 23:30'
Write-Host '===================================================='
Write-Host 'Experience files checked: PASS'
Write-Host 'New verified experience:  YES'
Write-Host 'Files changed:           ' ($changed -join ', ')
Write-Host 'Git commit:              ' $commitSha
Write-Host 'GitHub push:             ' $pushOutcome
Write-Host 'Working tree:            CLEAN'
Write-Host '===================================================='

if ($pushOutcome -ne 'PASS') {
    Write-Host ''
    Write-Host 'Backup completed locally but remote push did not succeed.'
    Write-Host 'Local commit is preserved at ' $commitSha '.'
    Write-Host 'Reason: ' (git remote -v) ' may be unreachable or auth failed.'
    Write-Host 'Action Required: rerun backup once remote is reachable.'
    exit 2
}

exit 0
