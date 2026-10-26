#Requires -Version 7
param(
    [string]$Path,
    [string]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$schemaPath = Join-Path $PSScriptRoot '../automation/orchestrator/task-contract.schema.json'
$taskId = ''; $status = ''; $reviewMode = ''; $blocker = ''
$ready = 'NO'; $notify = 'NO'; $next = 'NO'

function Get-PathPrefix {
    param([string]$Value)
    $normal = $Value.Trim().Replace('\', '/').TrimStart('./').ToLowerInvariant()
    $wildcard = $normal.IndexOfAny([char[]]@('*', '?', '['))
    if ($wildcard -ge 0) { $normal = $normal.Substring(0, $wildcard) }
    return $normal.TrimEnd('/')
}

function Test-PathConflict {
    param([string[]]$Allowed, [string[]]$Forbidden)
    foreach ($allow in $Allowed) {
        $a = Get-PathPrefix $allow
        foreach ($forbid in $Forbidden) {
            $f = Get-PathPrefix $forbid
            if (-not $a -or -not $f) { return $true }
            if ($a -eq $f -or $a.StartsWith("$f/") -or $f.StartsWith("$a/")) { return $true }
        }
    }
    return $false
}

try {
    if (([bool]$Path) -eq ([bool]$Json)) { throw 'PROVIDE_ONE_CONTRACT_SOURCE' }
    if ($Path) { $Json = Get-Content -LiteralPath $Path -Raw }
    if (-not (Test-Json -Json $Json -SchemaFile $schemaPath -ErrorAction SilentlyContinue)) { throw 'SCHEMA_INVALID' }
    $task = ConvertFrom-Json -InputObject $Json -AsHashtable
    $taskId = $task.task_id
    $status = $task.status
    $reviewMode = $task.review_mode
    if ($task.title.Trim().Length -eq 0) { throw 'TITLE_EMPTY' }
    if ($task.model.Trim().Length -eq 0) { throw 'MODEL_EMPTY' }
    if ($task.branch.Trim().Length -eq 0) { throw 'BRANCH_EMPTY' }
    if ($task.scope.Trim().Length -eq 0) { throw 'SCOPE_EMPTY' }
    if (@($task.allowed_paths).Count -eq 0) { throw 'ALLOWED_PATHS_EMPTY' }
    foreach ($item in @($task.allowed_paths) + @($task.forbidden_paths)) {
        if ($item.Trim().Length -eq 0 -or $item.StartsWith('/') -or $item -match '(^|[\\/])\.\.([\\/]|$)') { throw 'PATH_INVALID' }
    }
    foreach ($item in @($task.acceptance_criteria) + @($task.validation_requirements)) {
        if ($item.Trim().Length -eq 0) { throw 'CRITERION_EMPTY' }
    }
    if (Test-PathConflict $task.allowed_paths $task.forbidden_paths) { throw 'PATH_CONFLICT' }

    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $dependenciesComplete = $true
    foreach ($dependency in $task.depends_on) {
        if ($dependency.task_id -eq $taskId -or -not $seen.Add($dependency.task_id)) { throw 'DEPENDENCY_INVALID' }
        if ($dependency.status -ne 'COMPLETED') { $dependenciesComplete = $false }
    }
    if (@($task.blocks) -contains $taskId) { throw 'SELF_BLOCK' }
    if (-not $dependenciesComplete -and $status -in @('READY', 'IN_PROGRESS', 'VALIDATING', 'WAITING_FOR_REVIEW', 'COMPLETED')) { throw 'DEPENDENCY_INCOMPLETE' }

    if ($status -in @('IN_PROGRESS', 'VALIDATING', 'WAITING_FOR_REVIEW', 'COMPLETED') -and -not $task.started_at) { throw 'STARTED_AT_REQUIRED' }
    if ($status -eq 'BLOCKED') {
        if (-not $task.result -or $task.result.Trim().Length -lt 10 -or $task.result -in @('PASS', 'FAIL', 'BLOCKED')) { throw 'BLOCKER_EXPLANATION_REQUIRED' }
    }
    if ($status -eq 'WAITING_FOR_REVIEW') {
        if ($reviewMode -ne 'REVIEW_REQUIRED' -or $task.result -ne 'PASS' -or -not $task.commit_sha -or $task.github_sync -ne 'YES' -or $task.review_approved -or $task.completed_at) { throw 'REVIEW_WAIT_INVALID' }
    }
    if ($status -eq 'COMPLETED') {
        if ($task.result -ne 'PASS' -or -not $task.commit_sha -or $task.github_sync -ne 'YES' -or -not $task.completed_at) { throw 'COMPLETION_INCOMPLETE' }
        if ($reviewMode -eq 'REVIEW_REQUIRED' -and -not $task.review_approved) { throw 'REVIEW_APPROVAL_REQUIRED' }
        if ($reviewMode -eq 'REVIEW_RECOMMENDED') { $notify = 'YES' }
        if ($reviewMode -eq 'AUTO_CONTINUE' -and $dependenciesComplete) { $next = 'YES' }
    }
    if ($status -eq 'READY' -and $dependenciesComplete) { $ready = 'YES' }
} catch {
    $blocker = $_.Exception.Message
}

Write-Output "RESULT=$(if ($blocker) {'FAIL'} else {'PASS'})"
Write-Output "TASK_ID=$taskId"
Write-Output "STATUS=$status"
Write-Output "REVIEW_MODE=$reviewMode"
Write-Output "READY_FOR_EXECUTION=$ready"
Write-Output "USER_NOTIFICATION_RECOMMENDED=$notify"
Write-Output "NEXT_TASK_ALLOWED=$next"
if ($blocker) { Write-Output "BLOCKER=$blocker"; exit 1 }
