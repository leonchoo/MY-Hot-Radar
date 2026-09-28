# MY Hot Radar - Experience Backup: install/uninstall Windows Task Scheduler job
#
# Creates a daily Task Scheduler entry that runs the backup script at 23:30.
#  - If the PC is off, task runs "as soon as possible after a scheduled start is missed"
#    (StartWhenAvailable = true).
#  - Runs as current user; will not run if a user session is not active and the task is
#    set to "run only when user is logged on". Switch to "Run whether user is logged on
#    or not" below if you want the task to run unattended.
#
# Usage (elevated PowerShell):
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\.backup\install-experience-backup.ps1            # install
#   .\.backup\install-experience-backup.ps1 -Uninstall # remove

param([switch]$Uninstall)

$taskName = 'MY Hot Radar Daily Experience Backup'
$script   = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'backup-experience.ps1'

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

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$script`""

# Daily at 23:30
$trigger = New-ScheduledTaskTrigger -Daily -At '23:30'
$trigger.StartWhenAvailable = $true

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U
$principal.RunLevel = 'Highest'

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -StopOnBatteryEnd:$false `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

Write-Host "Installed scheduled task: $taskName"
Write-Host "  Script:    $script"
Write-Host "  Schedule:  Daily at 23:30"
Write-Host "  Computer must be powered on. If missed (e.g. laptop off), runs at next startup."
Write-Host ""
Write-Host "To verify: schtasks /Query /TN '$taskName' /V /FO LIST"
Write-Host "To run now: schtasks /Run /TN '$taskName'"
Write-Host "To remove: .\.backup\install-experience-backup.ps1 -Uninstall"
