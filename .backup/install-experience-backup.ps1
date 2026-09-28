# MY Hot Radar - Experience Backup: install/uninstall Windows Task Scheduler job
#
# Creates a daily Task Scheduler entry that runs the backup script at 23:30.
#  - If the PC is off, task runs "as soon as possible after a scheduled start is missed"
#    via the settings' StartWhenAvailable flag.
#  - Runs as current user; if no user session is active at run time, the task
#    will fail (set LogonType to 'Password' to change).
#
# Usage (elevated PowerShell):
#   .\install-experience-backup.ps1            # install
#   .\install-experience-backup.ps1 -Uninstall # remove

param([switch]$Uninstall)

$taskName = 'MY Hot Radar Daily Experience Backup'
$taskDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$script   = Join-Path $taskDir 'backup-experience.ps1'

if ($Uninstall) {
    $existing = schtasks /Query /TN $taskName 2>$null
    if ($LASTEXITCODE -eq 0) {
        schtasks /Delete /TN $taskName /F | Out-Null
        Write-Host "Uninstalled scheduled task: $taskName"
    } else {
        Write-Host "No existing scheduled task named: $taskName"
    }
    return
}

# Refuse if not elevated: Register-ScheduledTask fails with "Access is denied" otherwise.
$isElevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]'Administrator')
if (-not $isElevated) {
    Write-Host ''
    Write-Host '===================================================='
    Write-Host '[FAIL] This installer requires an elevated PowerShell.'
    Write-Host ''
    Write-Host 'Please re-run from an Administrator PowerShell:'
    Write-Host '  1. Search "PowerShell" in the Start menu'
    Write-Host '  2. Right-click -> "Run as administrator"'
    Write-Host "  3. cd $taskDir"
    Write-Host '  4. .\install-experience-backup.ps1'
    Write-Host '===================================================='
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$script`""

# Daily at 23:30
$trigger = New-ScheduledTaskTrigger -Daily -At '23:30'

# Settings: run missed-start at next opportunity, ignore new if already running,
# allow during battery, time-limit 10 minutes.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

# Principal: runs as current user, can run with no full token (S4U).
# Change LogonType to 'Password' if you want a background-scheduler run
# that does not require an active user session.
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U
$principal.RunLevel = 'Highest'

try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description 'Backs up verified-experience Project Memory MDs to GitHub master. Runs only when files change (idempotent). Never writes into the files itself.' `
        -Force -ErrorAction Stop | Out-Null
} catch {
    Write-Host ''
    Write-Host '===================================================='
    Write-Host '[FAIL] Scheduled-task registration failed.'
    Write-Host ("Reason: " + $_.Exception.Message)
    Write-Host '===================================================='
    exit 1
}

Write-Host ''
Write-Host "Installed scheduled task: $taskName"
Write-Host "  Script:    $script"
Write-Host "  Schedule:  Daily at 23:30"
Write-Host "  Behavior:  If PC was off at 23:30, runs at next startup (StartWhenAvailable)."
Write-Host ''
Write-Host "To verify: schtasks /Query /TN '$taskName' /V /FO LIST"
Write-Host "To run now: schtasks /Run /TN '$taskName'"
Write-Host "To remove: .\.backup\install-experience-backup.ps1 -Uninstall"
Write-Host ''
Write-Host "Note: if you want it to run while no user is logged on, edit the script"
Write-Host "and change `-LogonType S4U` to `-LogonType Password`."
