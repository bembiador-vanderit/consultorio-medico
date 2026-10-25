param(
    [string]$Message,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$validator = Join-Path $PSScriptRoot 'atlas-validate.ps1'
$created = 'NO'; $pushed = 'NO'; $synced = 'NO'; $blocker = ''
$localHead = ''; $remoteHead = ''; $ahead = ''; $behind = ''

function Invoke-SyncGit {
    param([string[]]$Arguments)
    $ErrorActionPreference = 'Continue'
    $output = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "GIT_COMMAND_FAILED: $($Arguments[0])" }
    return @($output | ForEach-Object { [string]$_ })
}

try {
    if ([string]::IsNullOrWhiteSpace($Message)) { throw 'EMPTY_COMMIT_MESSAGE' }
    Push-Location $repoRoot
    try {
        $validation = @(& $validator)
        if ($LASTEXITCODE -ne 0 -or $validation -notcontains 'RESULT=PASS') { throw "PREVALIDATION_FAILED: $($validation -join '; ')" }
        if ($DryRun) {
            Write-Output 'DRY_RUN=YES'
            Write-Output 'RESULT=PASS'
            Write-Output 'COMMIT_CREATED=NO'
            Write-Output 'PUSH_COMPLETED=NO'
            Write-Output 'GITHUB_SYNC=NO'
            return
        }

        $branch = Invoke-SyncGit @('symbolic-ref', '--quiet', '--short', 'HEAD')
        $candidates = @(
            Invoke-SyncGit @('-c', 'core.quotepath=false', 'diff', '--name-only', '--no-renames', 'HEAD')
            Invoke-SyncGit @('-c', 'core.quotepath=false', 'ls-files', '--others', '--exclude-standard')
        ) | Where-Object { $_ } | Sort-Object -Unique
        Invoke-SyncGit @('add', '-A') | Out-Null
        $staged = @(Invoke-SyncGit @('-c', 'core.quotepath=false', 'diff', '--cached', '--name-only', '--no-renames'))
        if ($staged.Count -eq 0) { throw 'NOTHING_STAGED' }
        if (@(Compare-Object $candidates $staged).Count -gt 0) { throw 'CANDIDATES_CHANGED_DURING_STAGING' }
        $stagedValidation = @(& $validator -StagedOnly -SkipTests)
        if ($LASTEXITCODE -ne 0 -or $stagedValidation -notcontains 'RESULT=PASS') {
            $policy = Get-Content -LiteralPath (Join-Path $repoRoot 'automation/atlas-sync-policy.json') -Raw | ConvertFrom-Json
            foreach ($path in $staged) {
                foreach ($pattern in $policy.forbiddenFilePatterns) {
                    if ($path.Replace('\', '/') -match $pattern) {
                        Invoke-SyncGit @('restore', '--staged', '--', $path) | Out-Null
                        break
                    }
                }
            }
            throw "STAGED_VALIDATION_FAILED: $($stagedValidation -join '; ')"
        }
        if (@(Invoke-SyncGit @('diff', '--name-only')).Count -gt 0) { throw 'WORKTREE_CHANGED_AFTER_STAGING' }
        Invoke-SyncGit @('diff', '--cached', '--check') | Out-Null
        Invoke-SyncGit @('commit', '-m', $Message) | Out-Null
        $created = 'YES'
        $localHead = Invoke-SyncGit @('rev-parse', 'HEAD')
        Invoke-SyncGit @('push', 'origin', $branch) | Out-Null
        $pushed = 'YES'
        Invoke-SyncGit @('fetch', 'origin', $branch) | Out-Null
        $remoteHead = Invoke-SyncGit @('rev-parse', "origin/$branch")
        $remoteLive = (Invoke-SyncGit @('ls-remote', '--heads', 'origin', $branch)).Split("`t")[0]
        $counts = ((Invoke-SyncGit @('rev-list', '--left-right', '--count', "HEAD...origin/$branch")) -split '\s+')
        $ahead = $counts[0]; $behind = $counts[1]
        if ($localHead -ne $remoteHead -or $localHead -ne $remoteLive -or $ahead -ne '0' -or $behind -ne '0') { throw 'POST_PUSH_VERIFICATION_FAILED' }
        $synced = 'YES'
    } finally { Pop-Location }
} catch {
    $blocker = $_.Exception.Message
}

Write-Output "RESULT=$(if ($blocker) {'FAIL'} else {'PASS'})"
Write-Output "COMMIT_CREATED=$created"
Write-Output "PUSH_COMPLETED=$pushed"
Write-Output "LOCAL_HEAD=$localHead"
Write-Output "REMOTE_HEAD=$remoteHead"
Write-Output "AHEAD=$ahead"
Write-Output "BEHIND=$behind"
Write-Output "GITHUB_SYNC=$synced"
if ($blocker) { Write-Output "BLOCKER=$blocker"; exit 1 }
