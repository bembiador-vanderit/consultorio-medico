[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$IsccPath,
    [string]$PackageVersion = '1.2.0',
    [string]$BuildName = ('installer-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
)
$ErrorActionPreference = 'Stop'
if ($BuildName -notmatch '^[a-zA-Z0-9-]+$') { throw 'Invalid build name' }
if ($PackageVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid version' }
$agentRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $agentRoot ('artifacts\' + $BuildName)
if (Test-Path -LiteralPath $outputRoot) { throw 'Build directory already exists; never reuse a previous payload' }
$payload = Join-Path $outputRoot 'payload'
New-Item -ItemType Directory -Path $payload | Out-Null
foreach ($component in @('Service', 'Tray')) {
    $project = Join-Path $agentRoot "Atlas.LocalAgent.$component\Atlas.LocalAgent.$component.csproj"
    $destination = Join-Path $payload $component.ToLowerInvariant()
    & dotnet publish $project -c Release -r win-x64 --self-contained true -p:Version=$PackageVersion -o $destination
    if ($LASTEXITCODE -ne 0) { throw "Publish failed: $component" }
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LEEME.txt') -Destination $payload
# Only clean publish outputs are used. Runtime data must never enter an installer.
$forbidden = Get-ChildItem -LiteralPath $payload -Recurse -File | Where-Object {
    $_.Name -match '^(identity|station)\.json$|^secret\.|\.sqlite($|-)|\.db$|^\.env|authorization.*\.json$' -or
    $_.Extension -in @('.pdf', '.dump', '.pdb', '.trx')
}
if ($forbidden) {
    # PDBs are development symbols, not runtime data. Publish without shipping them.
    $other = @($forbidden | Where-Object Extension -ne '.pdb')
    if ($other.Count) { throw 'Runtime data or forbidden artifacts detected in payload' }
    foreach ($symbol in $forbidden) { Remove-Item -LiteralPath $symbol.FullName }
}
$manifest = @(Get-ChildItem -LiteralPath $payload -Recurse -File | Sort-Object FullName | ForEach-Object {
    [ordered]@{ path = [IO.Path]::GetRelativePath($payload, $_.FullName); bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
})
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $payload 'payload-sha256.json') -Encoding UTF8
& $IsccPath /Q "/DPayloadDir=$payload" "/DOutputDir=$outputRoot" "/DPackageVersion=$PackageVersion" "/DOutputName=AtlasLocalAgent-Setup-$PackageVersion-win-x64" (Join-Path $PSScriptRoot 'atlas-local-agent.iss')
if ($LASTEXITCODE -ne 0) { throw 'Installer compiler failed' }
$installer = Join-Path $outputRoot "AtlasLocalAgent-Setup-$PackageVersion-win-x64.exe"
Get-FileHash -LiteralPath $installer -Algorithm SHA256 | Format-List
Get-Item -LiteralPath $installer | Select-Object FullName, Length
