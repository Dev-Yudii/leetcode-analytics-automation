# ---------------------------------------------------------------------------
# Registers the daily notebook sync in the Windows Task Scheduler.
#
# The root of the Task Scheduler refuses a programmatic registration for a
# standard user ("Acesso negado"), so this script has to run elevated.
#
#   1. Right-click this file -> "Run with PowerShell"  (or open an
#      Administrator PowerShell and run it from there)
#   2. It creates the task "LeetCode Notebook Sync" and prints the result.
#
# It is safe to run it more than once: the task is overwritten, not
# duplicated.
#
# The paths below are specific to this machine, the same way
# scripts\sync_notebook.cmd is.
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

$project = "C:\Dev\Projects\leetcode-analytics-automation"
$taskName = "LeetCode Notebook Sync"

$service = New-Object -ComObject Schedule.Service
$service.Connect()
$root = $service.GetFolder("\")

$task = $service.NewTask(0)

$task.RegistrationInfo.Description = "Pull the daily challenge, push the solution and update the ledger in Neon. Runs once a day at 06:00."
$task.RegistrationInfo.Author = "$env:USERDOMAIN\$env:USERNAME"

# Interactive token: the task runs as the logged-in user, no password
# is stored and no credential ever leaves the machine.
$task.Principal.UserId = "$env:USERDOMAIN\$env:USERNAME"
$task.Principal.LogonType = 3    # TASK_LOGON_INTERACTIVE_TOKEN
$task.Principal.RunLevel = 0     # TASK_RUNLEVEL_LUA

$action = $task.Actions.Create(0)   # TASK_ACTION_EXEC
$action.Path = "$project\scripts\sync_notebook.cmd"
$action.WorkingDirectory = $project

$trigger = $task.Triggers.Create(2) # TASK_TRIGGER_DAILY
$trigger.StartBoundary = "2026-11-06T06:00:00"
$trigger.DaysInterval = 1
$trigger.Enabled = $true

$settings = $task.Settings
$settings.StartWhenAvailable = $true          # run right after a missed start
$settings.MultipleInstances = 2               # TASK_INSTANCES_IGNORE_NEW
$settings.RunOnlyIfNetworkAvailable = $true
$settings.DisallowStartIfOnBatteries = $false
$settings.StopIfGoingOnBatteries = $false
$settings.RestartCount = 3
$settings.RestartInterval = "PT1M"
$settings.ExecutionTimeLimit = "PT2H"
$settings.Enabled = $true

# TASK_CREATE_OR_UPDATE = 6, TASK_LOGON_INTERACTIVE_TOKEN = 3
$root.RegisterTaskDefinition($taskName, $task, 6, $null, $null, 3, $null)

Write-Host ""
Write-Host "Task '$taskName' registered." -ForegroundColor Green
Write-Host ""
Write-Host "  trigger    : every day at 06:00"
Write-Host "  action     : $project\scripts\sync_notebook.cmd"
Write-Host "  start in   : $project"
Write-Host "  settings   : run after a missed start, never in parallel,"
Write-Host "               network required, restart 3 times every 1 minute"
Write-Host ""
Write-Host "Test it now:  Start-ScheduledTask -TaskName '$taskName'"
Write-Host "Then read:   $project\logs\sync-task.log"
