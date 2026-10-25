param(
    [Parameter(Mandatory)][string]$ManifestPath,
    [Parameter(Mandatory)][string]$BackupRoot,
    [Parameter(Mandatory)][string]$ReleaseRoot
)

$ErrorActionPreference = 'Stop'
$atlasUser = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($atlasUser)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator required to register SCM and protected ACLs.'
}
$atlasExpected = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$atlasBackup = Get-Content -LiteralPath (Join-Path $BackupRoot 'protected-original-hashes.json') -Raw | ConvertFrom-Json
$atlasUuid = [Guid]::Parse($atlasExpected.AgentUuid)
$atlasSource = [IO.Path]::GetFullPath([string]$atlasExpected.SourceRoot).TrimEnd('\')
if ($atlasUuid -eq [Guid]::Empty -or $atlasBackup.AgentUuid -ne $atlasUuid.ToString() -or
    $atlasBackup.SourceRoot -ne $atlasSource -or $atlasBackup.SourceUserSid -ne $atlasUser.User.Value -or
    $atlasBackup.IdentitySha256 -ne $atlasExpected.IdentitySha256 -or
    $atlasBackup.StationSha256 -ne $atlasExpected.StationSha256 -or
    $atlasExpected.AgentId -lt 1 -or @($atlasExpected.PrinterIds).Count -lt 1 -or
    @($atlasExpected.PrinterIds | Select-Object -Unique).Count -ne @($atlasExpected.PrinterIds).Count) {
    throw 'Station manifest, protected backup or source account mismatch.'
}
if ([Uri]::new([string]$atlasExpected.Endpoint).Scheme -ne 'https' -or
    -not ([string]$atlasExpected.Endpoint).EndsWith('/')) { throw 'HTTPS root endpoint required.' }
$atlasIdentity = Join-Path $atlasSource 'identity.json'
$atlasStation = Join-Path $atlasSource 'station.json'
$atlasLockPath = Join-Path $atlasSource 'service.lock'
if ((Get-Content -LiteralPath $atlasIdentity -Raw | ConvertFrom-Json).agentId -ne $atlasUuid.ToString() -or
    (Get-FileHash -LiteralPath $atlasIdentity).Hash -ne $atlasExpected.IdentitySha256 -or
    (Get-FileHash -LiteralPath $atlasStation).Hash -ne $atlasExpected.StationSha256) {
    throw 'Current source identity changed since the protected backup.'
}
foreach ($atlasRecord in @($atlasBackup.Files)) {
    $atlasSourceFile = Join-Path $atlasSource ([string]$atlasRecord.RelativePath)
    $atlasSavedFile = Join-Path (Join-Path $BackupRoot 'protected-original') ([string]$atlasRecord.RelativePath)
    if ((Get-FileHash -LiteralPath $atlasSourceFile).Hash -ne $atlasRecord.Sha256 -or
        (Get-FileHash -LiteralPath $atlasSavedFile).Hash -ne $atlasRecord.Sha256) {
        throw "Source/backup mismatch: $($atlasRecord.RelativePath)"
    }
}
if (Get-Service AtlasLocalAgent -ErrorAction SilentlyContinue) { throw 'Existing AtlasLocalAgent service must not be replaced.' }
$atlasBase = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'AtlasPergamo\LocalAgent'
$atlasBin = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'AtlasPergamo\LocalAgent\service'
$atlasBaseExists = Test-Path -LiteralPath $atlasBase
$atlasBinExists = Test-Path -LiteralPath $atlasBin
if ($atlasBaseExists -xor $atlasBinExists) { throw 'Incomplete service staging root.' }
$atlasReleaseDll = Join-Path $ReleaseRoot 'Atlas.LocalAgent.Service.dll'
$atlasReleaseExe = Join-Path $ReleaseRoot 'Atlas.LocalAgent.Service.exe'
if (-not (Test-Path -LiteralPath $atlasReleaseExe -PathType Leaf) -or
    (Get-FileHash -LiteralPath $atlasReleaseDll).Hash -ne $atlasExpected.ReleaseDllSha256) {
    throw 'Certified service release missing or hash mismatch.'
}
if ($atlasBaseExists) {
    if (@(Get-ChildItem -LiteralPath $atlasBase -Force).Count -ne 0) { throw 'Existing machine service root contains state.' }
    $atlasReleaseFiles = @(Get-ChildItem -LiteralPath $ReleaseRoot -Recurse -File)
    $atlasInstalledFiles = @(Get-ChildItem -LiteralPath $atlasBin -Recurse -File)
    if ($atlasReleaseFiles.Count -ne $atlasInstalledFiles.Count) { throw 'Partial binary staging differs from release.' }
    foreach ($atlasFile in $atlasReleaseFiles) {
        $atlasRelative = $atlasFile.FullName.Substring(([IO.Path]::GetFullPath($ReleaseRoot).TrimEnd('\')).Length).TrimStart('\')
        $atlasInstalled = Join-Path $atlasBin $atlasRelative
        if (-not (Test-Path -LiteralPath $atlasInstalled -PathType Leaf) -or
            (Get-FileHash -LiteralPath $atlasInstalled).Hash -ne (Get-FileHash -LiteralPath $atlasFile.FullName).Hash) {
            throw "Partial binary staging hash mismatch: $atlasRelative"
        }
    }
}
$atlasSourceLease = [IO.FileStream]::new($atlasLockPath, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
    $atlasRootAcl = (Get-Acl -LiteralPath $atlasSource).Sddl
    $atlasLockAcl = (Get-Acl -LiteralPath $atlasLockPath).Sddl
    [IO.File]::WriteAllText((Join-Path $BackupRoot 'source-root-acl.txt'), $atlasRootAcl)
    [IO.File]::WriteAllText((Join-Path $BackupRoot 'source-lock-acl.txt'), $atlasLockAcl)
}
finally { $atlasSourceLease.Dispose() }

function Invoke-AtlasSc([string[]]$Arguments) {
    & (Join-Path $env:SystemRoot 'System32\sc.exe') @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw ('SCM operation failed: ' + $Arguments[0]) }
}
function Set-AtlasDirectoryAcl([string]$Path, [hashtable]$Rules) {
    $atlasAcl = [Security.AccessControl.DirectorySecurity]::new()
    $atlasAcl.SetAccessRuleProtection($true, $false)
    $atlasAcl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    foreach ($atlasRule in $Rules.GetEnumerator()) {
        $atlasAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($atlasRule.Key), $atlasRule.Value,
            'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    }
    Set-Acl -LiteralPath $Path -AclObject $atlasAcl
}
$atlasAdmin = @{'S-1-5-32-544'='FullControl'; 'S-1-5-18'='FullControl'}
if (-not $atlasBaseExists) { New-Item -ItemType Directory -Path $atlasBase,$atlasBin -Force | Out-Null }
Set-AtlasDirectoryAcl $atlasBase $atlasAdmin
Set-AtlasDirectoryAcl $atlasBin $atlasAdmin
if (-not $atlasBinExists) { Copy-Item -Path (Join-Path $ReleaseRoot '*') -Destination $atlasBin -Recurse }
$atlasExe = Join-Path $atlasBin 'Atlas.LocalAgent.Service.exe'
$atlasConfig = Join-Path $atlasBase 'config\service.json'
$atlasCommand = '"' + $atlasExe + '" --windows-service "' + $atlasConfig + '"'
# The certified service begins stopped/demand-start. A separate verified cutover enables delayed automatic start.
New-Service -Name AtlasLocalAgent -BinaryPathName $atlasCommand -DisplayName 'Atlas Pérgamo Local Agent' -Description 'Atlas Local Agent: HTTPS heartbeat and SafeValidation only. No physical grant.' -StartupType Manual | Out-Null
Invoke-AtlasSc -Arguments @('config','AtlasLocalAgent','obj=','NT SERVICE\AtlasLocalAgent')
Invoke-AtlasSc -Arguments @('sidtype','AtlasLocalAgent','unrestricted')
Invoke-AtlasSc -Arguments @('privs','AtlasLocalAgent','SeChangeNotifyPrivilege')
$atlasServiceSid = ([Security.Principal.NTAccount]::new('NT SERVICE','AtlasLocalAgent')).Translate([Security.Principal.SecurityIdentifier]).Value
$atlasRead = @{} + $atlasAdmin; $atlasRead[$atlasServiceSid] = 'ReadAndExecute'
Set-AtlasDirectoryAcl $atlasBase $atlasRead
Set-AtlasDirectoryAcl $atlasBin $atlasRead
foreach ($atlasPart in @('config','data','logs','secrets')) { New-Item -ItemType Directory -Path (Join-Path $atlasBase $atlasPart) | Out-Null }
Set-AtlasDirectoryAcl (Join-Path $atlasBase 'config') $atlasRead
foreach ($atlasPart in @('data','logs')) {
    $atlasWrite = @{} + $atlasAdmin; $atlasWrite[$atlasServiceSid] = 'Modify'
    Set-AtlasDirectoryAcl (Join-Path $atlasBase $atlasPart) $atlasWrite
}
$atlasSecretsAcl = @{} + $atlasAdmin; $atlasSecretsAcl[$atlasServiceSid] = 'FullControl'
Set-AtlasDirectoryAcl (Join-Path $atlasBase 'secrets') $atlasSecretsAcl
# Only the legacy root and its zero-byte lock are opened to the service; its old secrets stay protected.
$atlasOldRootAcl = Get-Acl -LiteralPath $atlasSource
$atlasOldRootAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    [Security.Principal.SecurityIdentifier]::new($atlasServiceSid), 'ReadAndExecute', 'None', 'None', 'Allow'))
Set-Acl -LiteralPath $atlasSource -AclObject $atlasOldRootAcl
$atlasOldLockAcl = Get-Acl -LiteralPath $atlasLockPath
$atlasOldLockAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    [Security.Principal.SecurityIdentifier]::new($atlasServiceSid), 'Modify', 'Allow'))
Set-Acl -LiteralPath $atlasLockPath -AclObject $atlasOldLockAcl
$atlasSettings = [ordered]@{
    BasePath=$atlasBase; SourceRoot=$atlasSource; AgentUuid=$atlasUuid.ToString()
    SourceUserSid=$atlasUser.User.Value; ServiceSid=$atlasServiceSid; Endpoint=[string]$atlasExpected.Endpoint
    Phase='Synthetic'; IdentitySha256=[string]$atlasExpected.IdentitySha256
    StationSha256=[string]$atlasExpected.StationSha256; PrinterIds=@($atlasExpected.PrinterIds)
    ReplayJobId=$null; SafeValidation=$true; PhysicalGlobal=$false; AllowedJobId=$null
}
[IO.File]::WriteAllText($atlasConfig, ($atlasSettings | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
[pscustomobject]@{
    AgentId=$atlasExpected.AgentId; AgentUuid=$atlasUuid.ToString(); Service='AtlasLocalAgent'
    Account='NT SERVICE\AtlasLocalAgent'; ServiceSid=$atlasServiceSid
    State=(Get-Service AtlasLocalAgent).Status.ToString(); Config=$atlasConfig
    Executable=$atlasExe; PrinterCount=@($atlasExpected.PrinterIds).Count
    RealCredentialMigrated=$false; PhysicalPrintsSent=0
} | ConvertTo-Json
