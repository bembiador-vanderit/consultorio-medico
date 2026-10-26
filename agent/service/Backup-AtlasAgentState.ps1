param(
    [Parameter(Mandatory)][Guid]$ExpectedUuid,
    [Parameter(Mandatory)][string]$SourceRoot,
    [Parameter(Mandatory)][string]$BackupRoot
)

$ErrorActionPreference = 'Stop'
$atlasOwner = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($atlasOwner)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator required for the protected local backup.'
}
$SourceRoot = [IO.Path]::GetFullPath($SourceRoot).TrimEnd('\')
$BackupRoot = [IO.Path]::GetFullPath($BackupRoot).TrimEnd('\')
if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container) -or
    $BackupRoot.StartsWith($SourceRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $BackupRoot)) {
    throw 'Source must exist; backup must be new and outside the source.'
}
$atlasIdentityPath = Join-Path $SourceRoot 'identity.json'
$atlasStationPath = Join-Path $SourceRoot 'station.json'
$atlasSecretPath = Join-Path $SourceRoot 'secrets\secret.atlas-registry-v1.bin'
$atlasSqlitePath = Join-Path $SourceRoot 'routing\1-1\inbox.sqlite'
$atlasLockPath = Join-Path $SourceRoot 'service.lock'
foreach ($atlasRequired in @($atlasIdentityPath, $atlasStationPath, $atlasSecretPath, $atlasSqlitePath, $atlasLockPath)) {
    if (-not (Test-Path -LiteralPath $atlasRequired -PathType Leaf)) { throw "Required local state is missing: $atlasRequired" }
}
$atlasIdentity = Get-Content -LiteralPath $atlasIdentityPath -Raw | ConvertFrom-Json
if ($atlasIdentity.agentId -ne $ExpectedUuid.ToString()) { throw 'Source UUID mismatch.' }
# The stopped manual agent must release this lock before a coherent copy can begin.
$atlasLock = [IO.FileStream]::new($atlasLockPath, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
    $atlasFiles = [Collections.Generic.List[IO.FileInfo]]::new()
    function Add-AtlasSourceFiles([string]$Path) {
        $atlasDirectory = Get-Item -LiteralPath $Path -Force
        if ($atlasDirectory.Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) { throw 'Source link denied.' }
        foreach ($atlasItem in Get-ChildItem -LiteralPath $Path -Force) {
            if ($atlasItem.Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) { throw 'Source link denied.' }
            if ($atlasItem.PSIsContainer) { Add-AtlasSourceFiles $atlasItem.FullName }
            elseif (-not $atlasItem.Name.EndsWith('.lock', [StringComparison]::OrdinalIgnoreCase)) { $atlasFiles.Add($atlasItem) }
        }
    }
    Add-AtlasSourceFiles $SourceRoot
    $atlasParent = Split-Path -Parent $BackupRoot
    New-Item -ItemType Directory -Path $atlasParent -Force | Out-Null
    New-Item -ItemType Directory -Path $BackupRoot | Out-Null
    $atlasAcl = [Security.AccessControl.DirectorySecurity]::new()
    $atlasAcl.SetAccessRuleProtection($true, $false)
    $atlasAcl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    foreach ($atlasSid in @('S-1-5-32-544', 'S-1-5-18')) {
        $atlasAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($atlasSid), 'FullControl',
            'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    }
    Set-Acl -LiteralPath $BackupRoot -AclObject $atlasAcl
    $atlasTarget = Join-Path $BackupRoot 'protected-original'
    New-Item -ItemType Directory -Path $atlasTarget | Out-Null
    $atlasEvidence = @(
        foreach ($atlasFile in $atlasFiles) {
            # Windows PowerShell 5.1 uses .NET Framework, which has no Path.GetRelativePath.
            $atlasRelative = $atlasFile.FullName.Substring($SourceRoot.Length).TrimStart('\')
            $atlasDestination = Join-Path $atlasTarget $atlasRelative
            New-Item -ItemType Directory -Path (Split-Path -Parent $atlasDestination) -Force | Out-Null
            Copy-Item -LiteralPath $atlasFile.FullName -Destination $atlasDestination
            $atlasSourceHash = (Get-FileHash -LiteralPath $atlasFile.FullName -Algorithm SHA256).Hash
            $atlasDestHash = (Get-FileHash -LiteralPath $atlasDestination -Algorithm SHA256).Hash
            if ($atlasSourceHash -ne $atlasDestHash) { throw "Backup verification failed: $atlasRelative" }
            [pscustomobject]@{ RelativePath = $atlasRelative; Bytes = $atlasFile.Length; Sha256 = $atlasSourceHash }
        }
    )
    $atlasManifest = [ordered]@{
        AgentUuid = $ExpectedUuid.ToString(); SourceRoot = $SourceRoot; SourceUserSid = $atlasOwner.User.Value
        CreatedUtc = [DateTime]::UtcNow.ToString('o'); Files = $atlasEvidence
        IdentitySha256 = (Get-FileHash -LiteralPath $atlasIdentityPath -Algorithm SHA256).Hash
        StationSha256 = (Get-FileHash -LiteralPath $atlasStationPath -Algorithm SHA256).Hash
    }
    $atlasManifestPath = Join-Path $BackupRoot 'protected-original-hashes.json'
    [IO.File]::WriteAllText($atlasManifestPath, ($atlasManifest | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
    [pscustomobject]@{ AgentUuid = $ExpectedUuid; BackupRoot = $BackupRoot; FilesVerified = $atlasEvidence.Count
        ManifestSha256 = (Get-FileHash -LiteralPath $atlasManifestPath -Algorithm SHA256).Hash
        SqliteBytes = (Get-Item -LiteralPath $atlasSqlitePath).Length; ManualLockExclusive = $true } | ConvertTo-Json
}
finally { $atlasLock.Dispose() }
