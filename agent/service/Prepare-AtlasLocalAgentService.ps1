param(
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$MachineName,
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][Guid]$StationId,
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$SourceRoot,
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$BackupRoot,
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$HealthEndpoint,
    [Parameter(Mandatory=$true)][ValidateRange(1,2147483647)][int]$AgentId
)
$ErrorActionPreference='Stop'
if ([Environment]::MachineName -ne $MachineName) {throw 'Machine identity mismatch.'}
if ($StationId -eq [Guid]::Empty) {throw 'Station UUID required.'}
if (![IO.Path]::IsPathFullyQualified($SourceRoot) -or ![IO.Path]::IsPathFullyQualified($BackupRoot)) {throw 'Absolute source and backup roots required.'}
$atlasHealthUri=$null
if (![Uri]::TryCreate($HealthEndpoint,[UriKind]::Absolute,[ref]$atlasHealthUri) -or
    $atlasHealthUri.Scheme -ne 'https' -or $atlasHealthUri.AbsolutePath -ne '/api/v1/health' -or
    $atlasHealthUri.UserInfo -or $atlasHealthUri.Query -or $atlasHealthUri.Fragment) {throw 'Explicit HTTPS health endpoint required.'}
$atlasEndpoint=$atlasHealthUri.GetLeftPart([UriPartial]::Authority) + '/'
$atlasIdentity=[Security.Principal.WindowsIdentity]::GetCurrent()
if (!([Security.Principal.WindowsPrincipal]::new($atlasIdentity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {throw 'Administrator required to provision SCM/ACL.'}
if (Get-Service AtlasLocalAgent -ErrorAction SilentlyContinue) {throw 'Refuse existing service; no silent upgrade/replacement.'}
if (!(Test-Path -LiteralPath (Join-Path $BackupRoot 'protected-original-hashes.json'))) {throw 'Protected backup required first.'}
if ((Get-Content -LiteralPath (Join-Path $SourceRoot 'identity.json') -Raw | ConvertFrom-Json).agentId -ne $StationId.ToString()) {throw 'Source UUID mismatch.'}
$atlasBase=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'AtlasPergamo\LocalAgent'
$atlasBin=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'AtlasPergamo\LocalAgent\service'
if ((Test-Path -LiteralPath $atlasBase) -or (Test-Path -LiteralPath $atlasBin)) {throw 'Fresh service runtime and binaries required.'}
$atlasPublish=Join-Path $BackupRoot 'service-release'
& dotnet publish (Join-Path $PSScriptRoot '..\Atlas.LocalAgent.Service\Atlas.LocalAgent.Service.csproj') -c Release -r win-x64 --self-contained true -o $atlasPublish
if ($LASTEXITCODE -ne 0) {throw 'Self-contained publish failed.'}
$atlasExe=Join-Path $atlasBin 'Atlas.LocalAgent.Service.exe'
function Invoke-AtlasSc([string[]]$ScArguments) {
    & "$env:SystemRoot\System32\sc.exe" @ScArguments | Out-Host
    if ($LASTEXITCODE -ne 0) {throw ('SCM operation failed: '+$ScArguments[0])}
}
function Set-AtlasDirectoryAcl([string]$Path,[hashtable]$Rules) {
    $atlasSecurity=[Security.AccessControl.DirectorySecurity]::new()
    $atlasSecurity.SetAccessRuleProtection($true,$false)
    $atlasSecurity.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    foreach($atlasPair in $Rules.GetEnumerator()) {
        $atlasSecurity.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($atlasPair.Key),$atlasPair.Value,'ContainerInherit,ObjectInherit','None','Allow'))
    }
    Set-Acl -LiteralPath $Path -AclObject $atlasSecurity
}
$atlasAdmin=@{'S-1-5-32-544'='FullControl';'S-1-5-18'='FullControl'}
New-Item -ItemType Directory -Path $atlasBase,$atlasBin -Force | Out-Null
Set-AtlasDirectoryAcl $atlasBase $atlasAdmin
Set-AtlasDirectoryAcl $atlasBin $atlasAdmin
Copy-Item -Path (Join-Path $atlasPublish '*') -Destination $atlasBin -Recurse
$atlasConfig=Join-Path $atlasBase 'config\service.json'
$atlasCommand='"'+$atlasExe+'" --windows-service "'+$atlasConfig+'"'
# Demand start until all staged checks have passed; delayed-auto is enabled only after cutover.
Invoke-AtlasSc -ScArguments @('create','AtlasLocalAgent','binPath=',$atlasCommand,'start=','demand','obj=','NT SERVICE\AtlasLocalAgent','DisplayName=','Atlas Pérgamo Local Agent')
Invoke-AtlasSc -ScArguments @('description','AtlasLocalAgent','Atlas Local Agent: HTTPS heartbeat and SafeValidation only. No physical grant.')
Invoke-AtlasSc -ScArguments @('sidtype','AtlasLocalAgent','unrestricted')
Invoke-AtlasSc -ScArguments @('privs','AtlasLocalAgent','SeChangeNotifyPrivilege')
$atlasSid=([Security.Principal.NTAccount]::new('NT SERVICE','AtlasLocalAgent')).Translate([Security.Principal.SecurityIdentifier]).Value
$atlasRead=@{}+$atlasAdmin; $atlasRead[$atlasSid]='ReadAndExecute'
Set-AtlasDirectoryAcl $atlasBase $atlasRead
Set-AtlasDirectoryAcl $atlasBin $atlasRead
foreach($atlasPart in @('config','data','logs','secrets')) {New-Item -ItemType Directory -Path (Join-Path $atlasBase $atlasPart) | Out-Null}
Set-AtlasDirectoryAcl (Join-Path $atlasBase 'config') $atlasRead
foreach($atlasPart in @('data','logs')) {$atlasWrite=@{}+$atlasAdmin; $atlasWrite[$atlasSid]='Modify'; Set-AtlasDirectoryAcl (Join-Path $atlasBase $atlasPart) $atlasWrite}
$atlasSecret=@{}+$atlasAdmin; $atlasSecret[$atlasSid]='FullControl'
Set-AtlasDirectoryAcl (Join-Path $atlasBase 'secrets') $atlasSecret
# Old credential directory keeps its protected original ACL. Only traversal/read on the old root
# and write on the ZERO-BYTE lock are granted; no old secret access is granted to the service.
$atlasSourceAcl=Get-Acl -LiteralPath $SourceRoot
$atlasSourceAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($atlasSid),'ReadAndExecute','None','None','Allow'))
Set-Acl -LiteralPath $SourceRoot -AclObject $atlasSourceAcl
$atlasLock=Join-Path $SourceRoot 'service.lock'
$atlasLockAcl=Get-Acl -LiteralPath $atlasLock
$atlasLockAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($atlasSid),'Modify','Allow'))
Set-Acl -LiteralPath $atlasLock -AclObject $atlasLockAcl
$atlasRegistry=Get-Content -LiteralPath (Join-Path $BackupRoot 'registry-pre.jsonl')
$atlasPrinters=@(($atlasRegistry[1] | ConvertFrom-Json) | Where-Object {$_.agent_id -eq $AgentId} | ForEach-Object {$_.local_id})
$atlasSettings=[ordered]@{BasePath=$atlasBase;SourceRoot=$SourceRoot;AgentUuid=$StationId.ToString();SourceUserSid=$atlasIdentity.User.Value;ServiceSid=$atlasSid;
    Endpoint=$atlasEndpoint;Phase='Synthetic';IdentitySha256=(Get-FileHash -LiteralPath (Join-Path $SourceRoot 'identity.json')).Hash;
    StationSha256=(Get-FileHash -LiteralPath (Join-Path $SourceRoot 'station.json')).Hash;PrinterIds=$atlasPrinters;ReplayJobId=$null;SafeValidation=$true;PhysicalGlobal=$false;AllowedJobId=$null}
[IO.File]::WriteAllText($atlasConfig,($atlasSettings | ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))
[pscustomobject]@{Service='AtlasLocalAgent';Account='NT SERVICE\AtlasLocalAgent';Sid=$atlasSid;State=(Get-Service AtlasLocalAgent).Status.ToString();Config=$atlasConfig;Executable=$atlasExe;RealCredentialMigrated=$false;PhysicalPrintsSent=0} | ConvertTo-Json
Write-Output 'Prepared but NOT started. Next: copy state, synthetic profile check, then separately initiate memory-only handoff.'
