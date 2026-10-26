Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'atlas-validate.ps1') -SelfTest
. (Join-Path $PSScriptRoot 'atlas-sync.ps1') -SelfTest
$passed = 0
function Assert-Guard {
    param([bool]$Condition, [string]$Name)
    if (-not $Condition) { throw "TEST_FAILED: $Name" }
    $script:passed++
}

Assert-Guard ((Test-GuardContext 'main' $false 0 'https://github.com/bembiador-vanderit/consultorio-medico.git') -eq 'BRANCH_NOT_ALLOWED') 'main blocked'
Assert-Guard ((Test-GuardContext '' $true 0 'https://github.com/bembiador-vanderit/consultorio-medico.git') -eq 'DETACHED_HEAD') 'detached blocked'
Assert-Guard ((Test-GuardContext 'feat/example' $false 1 'https://github.com/bembiador-vanderit/consultorio-medico.git') -eq 'REMOTE_AHEAD') 'remote ahead blocked'
Assert-Guard (Test-ForbiddenPath 'frontend/.env.local') 'env blocked'
Assert-Guard (-not (Test-ForbiddenPath '.env.example')) 'example template allowed'
Assert-Guard (Test-ForbiddenPath 'agent/bin/Release/app.exe') 'bin blocked'
Assert-Guard (Test-ForbiddenPath 'backup.sqlite') 'sqlite blocked'
Assert-Guard ((Get-GuardProfile @('docs/guide.md')) -eq 'DOCS_ONLY') 'docs profile'
Assert-Guard ((Get-GuardProfile @('frontend/src/App.tsx')) -eq 'FRONTEND') 'frontend profile'
Assert-Guard ((Get-GuardProfile @('backend/app/main.py')) -eq 'BACKEND') 'backend profile'
Assert-Guard ((Get-GuardProfile @('agent/Atlas.LocalAgent.Tests/a.cs')) -eq 'AGENT') 'agent profile'
Assert-Guard ((Get-GuardProfile @('backend/alembic/versions/0071_example.py')) -eq 'MIGRATION') 'migration profile'
Assert-Guard ((Get-GuardProfile @('frontend/src/App.tsx', 'backend/app/main.py')) -eq 'CROSS_CUTTING') 'cross cutting profile'
$syncBody = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'atlas-sync.ps1') -Raw
Assert-Guard ($syncBody -match 'EMPTY_COMMIT_MESSAGE') 'empty message blocked'
Assert-Guard ($syncBody -match 'if \(\$DryRun\)' -and $syncBody -match 'DRY_RUN=YES') 'dry run guard'
Assert-Guard ($syncBody -notmatch '(?i)git\s+push\s+.*--force' -and $syncBody.Contains('@(''push'', ''origin'', $branch)')) 'force push impossible'
Assert-Guard ($syncBody -notmatch '(?i)alembic\s+upgrade|docker compose up') 'no migration activation'
$before = @(Get-SyncPathSet @('docs/guia.md', 'scripts/atlas-task-validate.ps1'))
$after = @(Get-SyncPathSet @('scripts/atlas-task-validate.ps1', 'docs/guia.md'))
Assert-Guard (@(Compare-Object $before $after).Count -eq 0) 'same paths pass'
Assert-Guard (@(Compare-Object $before $after).Count -eq 0) 'different order passes'
$slashes = @(Get-SyncPathSet @('"DOCS\guia.md"', 'scripts/atlas-task-validate.ps1'))
Assert-Guard (@(Compare-Object $before $slashes).Count -eq 0) 'slash casing and quote normalization'
$warning = [System.Management.Automation.ErrorRecord]::new([Exception]::new("warning: LF will be replaced by CRLF"), 'git-warning', [System.Management.Automation.ErrorCategory]::NotSpecified, $null)
$withWarning = @(Get-SyncPathSet @('docs/guia.md', $warning, 'scripts/atlas-task-validate.ps1'))
Assert-Guard (@(Compare-Object $before $withWarning).Count -eq 0) 'LF CRLF warning is not a path'
$extra = @(Get-SyncPathSet @('docs/guia.md', 'scripts/atlas-task-validate.ps1', 'extra.txt'))
Assert-Guard (@(Compare-Object $before $extra).Count -gt 0) 'extra staged fails'
$missing = @(Get-SyncPathSet @('docs/guia.md'))
Assert-Guard (@(Compare-Object $before $missing).Count -gt 0) 'lost candidate fails'
function git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    Write-Error 'warning: LF will be replaced by CRLF'
    Write-Output 'docs/guia.md'
    $global:LASTEXITCODE = 0
}
try {
    $onlyStdout = @(Get-SyncGitPaths @('diff', '--name-only'))
    Assert-Guard ($onlyStdout.Count -eq 1 -and $onlyStdout[0] -eq 'docs/guia.md') 'Git stderr warning ignored by path reader'
} finally {
    Remove-Item Function:\git
}
Write-Output "TESTS_PASSED=$passed"
