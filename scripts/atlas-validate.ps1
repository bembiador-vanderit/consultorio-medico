param(
    [switch]$StagedOnly,
    [switch]$SkipTests,
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$policy = Get-Content -LiteralPath (Join-Path $repoRoot 'automation/atlas-sync-policy.json') -Raw | ConvertFrom-Json

function Invoke-GuardCommand {
    param([string]$Program, [string[]]$Arguments)
    $ErrorActionPreference = 'Continue'
    $output = & $Program @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "$Program failed ($LASTEXITCODE)" }
    return @($output | ForEach-Object { [string]$_ })
}

function Get-GitLines {
    param([string[]]$Arguments)
    return @(Invoke-GuardCommand git (@('-c', 'core.quotepath=false') + $Arguments) | Where-Object { $_ -ne '' })
}

function Get-GuardProfile {
    param([string[]]$Paths)
    if ($Paths.Count -eq 0) { return 'DOCS_ONLY' }
    $kinds = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($path in $Paths) {
        $p = $path.Replace('\', '/')
        if ($p -match '(^|/)(alembic/versions|migrations)/|^backend/alembic/') { [void]$kinds.Add('MIGRATION') }
        elseif ($p -match '(^|/)(auth|security|permissions|rbac|trusted_proxy)(/|\.|$)|^scripts/atlas-|^scripts/test-atlas-|^automation/') { [void]$kinds.Add('SECURITY') }
        elseif ($p -match '^frontend/') { [void]$kinds.Add('FRONTEND') }
        elseif ($p -match '^backend/') { [void]$kinds.Add('BACKEND') }
        elseif ($p -match '^agent/') { [void]$kinds.Add('AGENT') }
        elseif ($p -match '(^|/)(docs/|README|AGENTS\.md$)|\.(md|txt)$') { [void]$kinds.Add('DOCS_ONLY') }
        else { [void]$kinds.Add('CROSS_CUTTING') }
    }
    if ($kinds.Contains('CROSS_CUTTING') -or $kinds.Count -gt 1) { return 'CROSS_CUTTING' }
    return @($kinds)[0]
}

function Test-ForbiddenPath {
    param([string]$Path, $Policy = $policy)
    $p = $Path.Replace('\', '/')
    foreach ($pattern in $Policy.forbiddenFilePatterns) {
        if ($p -match $pattern) { return $true }
    }
    return $false
}

function Test-ObviousSecret {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -gt 2097152) { return $true }
    $bytes = [System.IO.File]::ReadAllBytes($item.FullName)
    if ([Array]::IndexOf($bytes, [byte]0) -ge 0) { return $true }
    $body = [System.Text.Encoding]::UTF8.GetString($bytes)
    if ($body -match '-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----') { return $true }
    if ($body -match '(?i)\b(?:ghp_|gho_|github_pat_|sk_live_|sk_test_)[A-Za-z0-9_\-]{16,}') { return $true }
    if ($body -match '(?im)^\s*(?:password|passwd|api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*["'']?([^\s"''#]{12,})' -and $Matches[1] -notmatch '(?i)^(?:example|dummy|placeholder|change[_-]?me|synthetic)') { return $true }
    return $false
}

function Test-CandidateWhitespace {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $body = [System.IO.File]::ReadAllText($Path)
    foreach ($line in ($body -split "`n")) {
        if ($line.TrimEnd("`r") -match '[ \t]+$') { return $true }
    }
    return $false
}

function Test-GuardContext {
    param([string]$Branch, [bool]$Detached, [int]$Behind, [string]$RemoteUrl, $Policy = $policy)
    if ($Detached) { return 'DETACHED_HEAD' }
    if ($Branch -in $Policy.forbiddenBranches -or $Branch -notmatch $Policy.allowedBranchPattern) { return 'BRANCH_NOT_ALLOWED' }
    if ($RemoteUrl -notmatch ('(?i)(?:github\.com[:/])' + [regex]::Escape($Policy.expectedRepository) + '(?:\.git)?$')) { return 'WRONG_REPOSITORY' }
    if ($Behind -gt 0) { return 'REMOTE_AHEAD' }
    return ''
}

function Test-DocLinks {
    param([string[]]$Paths)
    foreach ($path in $Paths) {
        if ($path -notmatch '\.md$' -or -not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) { continue }
        $file = Join-Path $repoRoot $path
        $content = Get-Content -LiteralPath $file -Raw
        foreach ($match in [regex]::Matches($content, '\]\(([^)]+)\)')) {
            $target = $match.Groups[1].Value.Split('#')[0]
            if (-not $target -or $target -match '^(?:[a-z]+:|#|/|\\)') { continue }
            $target = [uri]::UnescapeDataString($target)
            if (-not (Test-Path -LiteralPath (Join-Path (Split-Path $file) $target))) { throw 'BROKEN_DOC_LINK' }
        }
    }
}

function Invoke-ProfileTests {
    param([string]$Profile, [string[]]$Paths)
    Test-DocLinks $Paths
    if ($Profile -eq 'DOCS_ONLY') { return }
    if ($Profile -eq 'SECURITY') { Invoke-GuardCommand powershell.exe @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $repoRoot 'scripts/test-atlas-sync.ps1')) | Out-Null }
    if ($Profile -in @('FRONTEND', 'SECURITY', 'CROSS_CUTTING')) {
        Invoke-GuardCommand docker @('compose', 'exec', '-T', 'frontend', 'npm', 'test') | Out-Null
        Invoke-GuardCommand docker @('compose', 'exec', '-T', 'frontend', 'npm', 'run', 'build') | Out-Null
    }
    if ($Profile -in @('BACKEND', 'MIGRATION', 'SECURITY', 'CROSS_CUTTING')) {
        Invoke-GuardCommand docker @('compose', 'exec', '-T', 'backend', 'python', '-m', 'pytest', '-q') | Out-Null
        Invoke-GuardCommand docker @('compose', 'exec', '-T', 'backend', 'python', '-m', 'compileall', '-q', 'app') | Out-Null
    }
    if ($Profile -in @('AGENT', 'SECURITY', 'CROSS_CUTTING')) {
        Invoke-GuardCommand dotnet @('test', 'agent/Atlas.LocalAgent.slnx', '-c', 'Release', '--nologo') | Out-Null
        Invoke-GuardCommand dotnet @('build', 'agent/Atlas.LocalAgent.slnx', '-c', 'Release', '--nologo') | Out-Null
    }
}

if ($SelfTest) { return }

Push-Location $repoRoot
$profile = 'UNKNOWN'; $forbidden = 0; $secret = 'FAIL'; $diff = 'FAIL'; $headsCount = 0
$migrationChanged = 'NO'; $divergence = 'NO'; $blocker = ''
try {
    $top = Get-GitLines @('rev-parse', '--show-toplevel')
    $gitRoot = [System.IO.Path]::GetFullPath($top.Replace('/', '\')).TrimEnd('\')
    if (-not [string]::Equals($gitRoot, $repoRoot.TrimEnd('\'), [System.StringComparison]::OrdinalIgnoreCase)) { throw 'WRONG_WORKSPACE' }
    $branch = Get-GitLines @('rev-parse', '--abbrev-ref', 'HEAD')
    $url = Get-GitLines @('remote', 'get-url', 'origin')
    $guard = Test-GuardContext $branch ($branch -eq 'HEAD') 0 $url
    if ($guard) { throw $guard }
    $upstream = Get-GitLines @('rev-parse', '--abbrev-ref', '@{upstream}')
    if ($upstream -ne "origin/$branch") { throw 'WRONG_UPSTREAM' }
    Get-GitLines @('fetch', '--quiet', 'origin', $branch) | Out-Null
    $counts = ((Get-GitLines @('rev-list', '--left-right', '--count', 'HEAD...@{upstream}')) -split '\s+')
    $behind = [int]$counts[1]
    if ($behind -gt 0) { $divergence = 'YES'; throw 'REMOTE_AHEAD' }

    if ($StagedOnly) {
        $paths = @(Get-GitLines @('diff', '--cached', '--name-only'))
        $scanPaths = @(Get-GitLines @('diff', '--cached', '--name-only', '--diff-filter=ACMR'))
    }
    else {
        $paths = @(Get-GitLines @('diff', '--name-only', 'HEAD'))
        $scanPaths = @(Get-GitLines @('diff', '--name-only', '--diff-filter=ACMR', 'HEAD'))
        $untracked = @(Get-GitLines @('ls-files', '--others', '--exclude-standard'))
        $paths += $untracked
        $scanPaths += $untracked
        $paths = @($paths | Sort-Object -Unique)
        $scanPaths = @($scanPaths | Sort-Object -Unique)
    }
    $profile = Get-GuardProfile $paths
    $migrationChanged = if (@($paths | Where-Object { $_ -match '(^|/)(alembic/versions|migrations)/' }).Count -gt 0) { 'YES' } else { 'NO' }
    foreach ($path in $paths) {
        if (Test-ForbiddenPath $path) { $forbidden++ }
    }
    if ($forbidden -gt 0) { throw 'FORBIDDEN_FILES' }
    foreach ($path in $scanPaths) {
        if (Test-ObviousSecret (Join-Path $repoRoot $path)) { throw 'SECRET_OR_UNREVIEWABLE_FILE' }
        if (Test-CandidateWhitespace (Join-Path $repoRoot $path)) { throw 'CANDIDATE_WHITESPACE' }
    }
    $secret = 'PASS'
    Get-GitLines @('diff', '--check') | Out-Null
    Get-GitLines @('diff', '--cached', '--check') | Out-Null
    $diff = 'PASS'

    $headLines = @(Invoke-GuardCommand docker @('compose', 'exec', '-T', 'backend', 'alembic', 'heads') | Where-Object { $_ -match '^\S+ \(head\)' })
    $headsCount = $headLines.Count
    if ($headsCount -ne 1) { throw 'ALEMBIC_HEAD_COUNT' }
    $currentLines = @(Invoke-GuardCommand docker @('compose', 'exec', '-T', 'backend', 'alembic', 'current') | Where-Object { $_ -match '^\S+' })
    if ($currentLines.Count -ne 1) { throw 'ALEMBIC_CURRENT_COUNT' }
    $targetLine = @(Get-Content -LiteralPath (Join-Path $repoRoot '.env') | Where-Object { $_ -match '^ALEMBIC_TARGET_REVISION=' })
    if ($targetLine.Count -ne 1) { throw 'ALEMBIC_TARGET_MISSING' }
    $target = ($targetLine[0] -split '=', 2)[1].Trim().Trim('"', "'")
    $current = ($currentLines[0] -split '\s+')[0]
    $head = ($headLines[0] -split '\s+')[0]
    if ($current -ne $target) { throw 'ALEMBIC_CURRENT_TARGET_MISMATCH' }
    if ($migrationChanged -eq 'NO' -and $current -ne $head) { throw 'ALEMBIC_CURRENT_HEAD_MISMATCH' }
    if (-not $SkipTests) { Invoke-ProfileTests $profile $paths }
} catch {
    $blocker = $_.Exception.Message
} finally { Pop-Location }

$result = if ($blocker) { 'FAIL' } else { 'PASS' }
Write-Output "RESULT=$result"
Write-Output "VALIDATION_PROFILE=$profile"
Write-Output "REMOTE_DIVERGENCE=$divergence"
Write-Output "FORBIDDEN_FILES=$forbidden"
Write-Output "SECRET_SCAN=$secret"
Write-Output "DIFF_CHECK=$diff"
Write-Output "ALEMBIC_HEADS=$headsCount"
Write-Output "MIGRATION_CHANGED=$migrationChanged"
if ($blocker) { Write-Output "BLOCKER=$blocker"; exit 1 }
