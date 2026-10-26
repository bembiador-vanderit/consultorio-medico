#Requires -Version 7
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$validator = Join-Path $PSScriptRoot 'atlas-task-validate.ps1'
$passed = 0

function New-Contract {
    return @{
        task_id = 'ATLAS-0001'; title = 'Actualizar guía sintética'; status = 'READY'
        task_type = 'DOCS'; priority = 'P2'; model = 'gpt-6.1-sol'; reasoning_level = 'MEDIUM'
        branch = 'feat/complete-care-context'; expected_base_sha = '9edf0ab85e9ac932ba18422b83bf45d637133e7f'
        scope = 'Documentación sintética'; allowed_paths = @('docs/**'); forbidden_paths = @('.env')
        acceptance_criteria = @('La guía describe el flujo'); validation_requirements = @('Comprobar enlaces locales')
        review_mode = 'AUTO_CONTINUE'; review_approved = $false
        depends_on = @(); blocks = @(); result = $null; commit_sha = $null; github_sync = 'NO'
        created_at = '2026-10-25T12:00:00Z'; started_at = $null; completed_at = $null
    }
}

function Invoke-Case {
    param([hashtable]$Contract, [string]$Name, [bool]$ShouldPass, [string]$ExpectedLine)
    $json = ConvertTo-Json -InputObject $Contract -Depth 20 -Compress
    $output = @(& pwsh -NoProfile -File $validator -Json $json)
    $success = ($LASTEXITCODE -eq 0 -and $output -contains 'RESULT=PASS')
    if ($success -ne $ShouldPass -or ($ExpectedLine -and $output -notcontains $ExpectedLine)) {
        throw "TEST_FAILED: $Name [$($output -join '; ')]"
    }
    $script:passed++
}

$c = New-Contract; Invoke-Case $c 'valid ready' $true 'READY_FOR_EXECUTION=YES'
$c = New-Contract; $c.task_id = 'TASK-1'; Invoke-Case $c 'invalid task id' $false 'RESULT=FAIL'
$c = New-Contract; $c.status = 'DONE'; Invoke-Case $c 'invalid status' $false 'RESULT=FAIL'
$c = New-Contract; $c.task_type = 'UNKNOWN'; Invoke-Case $c 'invalid type' $false 'RESULT=FAIL'
$c = New-Contract; $c.reasoning_level = 'ULTRA'; Invoke-Case $c 'invalid reasoning' $false 'RESULT=FAIL'
$c = New-Contract; $c.review_mode = 'SKIP'; Invoke-Case $c 'invalid review mode' $false 'RESULT=FAIL'
$c = New-Contract; $c.acceptance_criteria = @(); Invoke-Case $c 'missing acceptance' $false 'RESULT=FAIL'
$c = New-Contract; $c.validation_requirements = @(); Invoke-Case $c 'missing validation' $false 'RESULT=FAIL'
$c = New-Contract; $c.status = 'COMPLETED'; $c.started_at = $c.created_at; $c.completed_at = $c.created_at; $c.result = 'PASS'; $c.github_sync = 'YES'; Invoke-Case $c 'completed without commit' $false 'RESULT=FAIL'
$c = New-Contract; $c.status = 'COMPLETED'; $c.started_at = $c.created_at; $c.completed_at = $c.created_at; $c.result = 'PASS'; $c.commit_sha = $c.expected_base_sha; Invoke-Case $c 'completed without sync' $false 'RESULT=FAIL'
$c = New-Contract; $c.status = 'BLOCKED'; $c.result = 'Falta aprobación explícita del usuario'; Invoke-Case $c 'blocked valid' $true 'READY_FOR_EXECUTION=NO'
$c = New-Contract; $c.status = 'WAITING_FOR_REVIEW'; $c.review_mode = 'REVIEW_REQUIRED'; $c.started_at = $c.created_at; $c.result = 'PASS'; $c.commit_sha = $c.expected_base_sha; $c.github_sync = 'YES'; Invoke-Case $c 'review required waiting' $true 'NEXT_TASK_ALLOWED=NO'
$c = New-Contract; $c.status = 'COMPLETED'; $c.review_mode = 'REVIEW_REQUIRED'; $c.started_at = $c.created_at; $c.completed_at = $c.created_at; $c.result = 'PASS'; $c.commit_sha = $c.expected_base_sha; $c.github_sync = 'YES'; Invoke-Case $c 'review required without approval' $false 'RESULT=FAIL'
$c = New-Contract; $c.status = 'COMPLETED'; $c.review_mode = 'REVIEW_RECOMMENDED'; $c.started_at = $c.created_at; $c.completed_at = $c.created_at; $c.result = 'PASS'; $c.commit_sha = $c.expected_base_sha; $c.github_sync = 'YES'; Invoke-Case $c 'review recommended' $true 'USER_NOTIFICATION_RECOMMENDED=YES'
$c = New-Contract; $c.status = 'COMPLETED'; $c.started_at = $c.created_at; $c.completed_at = $c.created_at; $c.result = 'PASS'; $c.commit_sha = $c.expected_base_sha; $c.github_sync = 'YES'; Invoke-Case $c 'auto continue' $true 'NEXT_TASK_ALLOWED=YES'
$c = New-Contract; $c.depends_on = @(@{ task_id = 'ATLAS-0002'; status = 'IN_PROGRESS' }); Invoke-Case $c 'dependency incomplete' $false 'RESULT=FAIL'
$c = New-Contract; $c.depends_on = @(@{ task_id = 'ATLAS-0002'; status = 'COMPLETED' }); Invoke-Case $c 'dependency complete' $true 'READY_FOR_EXECUTION=YES'
$c = New-Contract; $c.forbidden_paths = @('docs/secrets/**'); Invoke-Case $c 'path conflict' $false 'RESULT=FAIL'
$c = New-Contract; $c.depends_on = @(@{ task_id = 'ATLAS-0001'; status = 'COMPLETED' }); Invoke-Case $c 'self dependency' $false 'RESULT=FAIL'
$c = New-Contract; $c.title = ' '; Invoke-Case $c 'blank title' $false 'RESULT=FAIL'
Write-Output "TESTS_PASSED=$passed"
