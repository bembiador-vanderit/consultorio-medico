param([Parameter(Mandatory=$true)][string]$HealthEndpoint)
$ErrorActionPreference = 'Stop'
$atlasCurrent = [Security.Principal.WindowsIdentity]::GetCurrent()
if (!([Security.Principal.WindowsPrincipal]::new($atlasCurrent)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Elevated administrator required for the temporary SCM lab.' }
if ($HealthEndpoint -notmatch '^https://[^/@?#:]+/api/v1/health$') { throw 'HTTPS health endpoint only.' }
$atlasRun = [Guid]::NewGuid().ToString('N').Substring(0,12)
$atlasBase = [Environment]::GetEnvironmentVariable('ATLAS_IDENTITY_LAB_BASE', 'Machine')
if (!$atlasBase) { $atlasBase = 'C:\AtlasQaLabs' }
if (![IO.Path]::IsPathFullyQualified($atlasBase) -or $atlasBase -match '(?i)\\Atlas\\LocalAgent|\\AtlasPergamo(?:\\|$)') { throw 'Synthetic lab base required; operational roots denied.' }
$atlasRoot = Join-Path $atlasBase ('service-account-lab-' + $atlasRun)
$atlasCandidate = 'AtlasDpapiCandidateQA_' + $atlasRun
$atlasObserver = 'AtlasDpapiObserverQA_' + $atlasRun
$atlasExe = Join-Path $atlasRoot 'bin\Atlas.LocalAgent.IdentityLab.exe'
$atlasCreated = @()
$atlasIdentities = @{}
$atlasSucceeded = $false

function Set-LabAcl([string]$Path, [hashtable]$Rules) {
    if (!$Path.StartsWith($atlasRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'ACL path outside lab.' }
    $atlasSecurity = [Security.AccessControl.DirectorySecurity]::new()
    $atlasSecurity.SetAccessRuleProtection($true,$false)
    $atlasSecurity.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    foreach ($atlasPair in $Rules.GetEnumerator()) {
        $atlasRule = [Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($atlasPair.Key),[Security.AccessControl.FileSystemRights]$atlasPair.Value,
            [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit',[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow)
        $atlasSecurity.AddAccessRule($atlasRule)
    }
    Set-Acl -LiteralPath $Path -AclObject $atlasSecurity
}
function Invoke-LabSc([string[]]$ScArguments) {
    $atlasScOutput = & "$env:SystemRoot\System32\sc.exe" @ScArguments
    if ($LASTEXITCODE -ne 0) { throw ('SCM lab action failed: ' + $ScArguments[0] + ' ' + $ScArguments[1]) }
    $atlasScOutput | Out-Host
}
function Write-LabConfig([int]$Phase) {
    $atlasOptions.Phase = $Phase
    [IO.File]::WriteAllText((Join-Path $atlasRoot 'config\lab.json'),($atlasOptions | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
}
function Wait-LabReport([string]$Path,[string]$Service) {
    $atlasUntil = [DateTimeOffset]::UtcNow.AddSeconds(100)
    while (!(Test-Path -LiteralPath $Path) -and [DateTimeOffset]::UtcNow -lt $atlasUntil) { Start-Sleep -Milliseconds 250 }
    if (!(Test-Path -LiteralPath $Path)) { throw 'Synthetic report timeout.' }
    (Get-Service -Name $Service).WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped,[TimeSpan]::FromSeconds(15))
    $atlasReport = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($atlasReport.Completed -ne $true) { throw ('Synthetic service report failed: ' + $atlasReport.ErrorCode) }
    $atlasReport | ConvertTo-Json -Depth 5 | Out-Host
    return $atlasReport
}

try {
    if (Test-Path -LiteralPath $atlasRoot) { throw 'Fresh lab root required.' }
    New-Item -ItemType Directory -Path $atlasRoot | Out-Null
    Set-LabAcl $atlasRoot @{'S-1-5-32-544'='FullControl';'S-1-5-18'='FullControl'}
    foreach ($atlasSub in @('bin','config','user','service','service\data','service\secrets','reports','observer-reports','exchange-a\secrets','exchange-b\secrets')) {
        New-Item -ItemType Directory -Path (Join-Path $atlasRoot $atlasSub) -Force | Out-Null
    }
    $atlasProject = Join-Path $PSScriptRoot 'Atlas.LocalAgent.IdentityLab\Atlas.LocalAgent.IdentityLab.csproj'
    & dotnet publish $atlasProject -c Release -r win-x64 --self-contained true -o (Join-Path $atlasRoot 'bin')
    if ($LASTEXITCODE -ne 0) { throw 'Lab publish failed.' }
    foreach ($atlasSpec in @(@($atlasCandidate,'--candidate'),@($atlasObserver,'--observer'))) {
        $atlasName=$atlasSpec[0]; $atlasMode=$atlasSpec[1]
        if (Get-Service -Name $atlasName -ErrorAction SilentlyContinue) { throw 'Refuse existing service.' }
        $atlasCommand = '"' + $atlasExe + '" ' + $atlasMode + ' "' + $atlasRoot + '"'
        Invoke-LabSc -ScArguments @('create',$atlasName,'binPath=',$atlasCommand,'start=','demand','obj=',('NT SERVICE\'+$atlasName))
        $atlasCreated += $atlasName
        $atlasService=Get-CimInstance Win32_Service -Filter "Name='$atlasName'"
        if ($atlasService.StartName -ne ('NT SERVICE\'+$atlasName) -or $atlasService.StartMode -ne 'Manual') { throw 'Wrong lab account/start mode.' }
        $atlasSid=([Security.Principal.NTAccount]::new('NT SERVICE',$atlasName)).Translate([Security.Principal.SecurityIdentifier]).Value
        $atlasIdentities[$atlasName]=$atlasSid
        if (Get-CimInstance Win32_UserProfile -Filter "SID='$atlasSid'") { throw 'Refuse existing profile.' }
        # Strip optional token privileges. No password, local admin group, logon policy or machine-wide ACL changes.
        Invoke-LabSc -ScArguments @('privs',$atlasName,'SeChangeNotifyPrivilege')
    }
    $atlasSidB=$atlasIdentities[$atlasCandidate]; $atlasSidC=$atlasIdentities[$atlasObserver]
    $atlasRead=@{'S-1-5-32-544'='FullControl';'S-1-5-18'='FullControl'}
    $atlasRead[$atlasSidB]='ReadAndExecute'; $atlasRead[$atlasSidC]='ReadAndExecute'
    Set-LabAcl $atlasRoot $atlasRead
    Set-LabAcl (Join-Path $atlasRoot 'bin') $atlasRead
    Set-LabAcl (Join-Path $atlasRoot 'config') $atlasRead
    Set-LabAcl (Join-Path $atlasRoot 'user') @{'S-1-5-32-544'='FullControl';'S-1-5-18'='FullControl'}
    $atlasWriteB=@{'S-1-5-32-544'='FullControl';'S-1-5-18'='FullControl'}; $atlasWriteB[$atlasSidB]='Modify'
    foreach ($atlasSub in @('service','reports')) { Set-LabAcl (Join-Path $atlasRoot $atlasSub) $atlasWriteB }
    # WindowsSecretStore sets its own owner/DACL. Grant that right only on its private synthetic keystore.
    $atlasSecretRules=@{'S-1-5-32-544'='FullControl';'S-1-5-18'='FullControl'}; $atlasSecretRules[$atlasSidB]='FullControl'
    Set-LabAcl (Join-Path $atlasRoot 'service\secrets') $atlasSecretRules
    $atlasWriteC=@{'S-1-5-32-544'='FullControl';'S-1-5-18'='FullControl'}; $atlasWriteC[$atlasSidC]='Modify'
    Set-LabAcl (Join-Path $atlasRoot 'observer-reports') $atlasWriteC
    Set-LabAcl (Join-Path $atlasRoot 'exchange-a') $atlasRead
    $atlasExchange=@{}+$atlasRead; $atlasExchange[$atlasSidB]='Modify'
    Set-LabAcl (Join-Path $atlasRoot 'exchange-b') $atlasExchange
    $atlasOptions=[ordered]@{RunId=$atlasRun;CreatorSid=$atlasCurrent.User.Value;CandidateSid=$atlasSidB;ObserverSid=$atlasSidC;
        SyntheticAgentUuid=[Guid]::NewGuid().ToString();HealthEndpoint=$HealthEndpoint;Phase=1;SyntheticOnly=$true}
    Write-LabConfig 1
    & $atlasExe --prepare $atlasRoot
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic preparation failed.' }
    Invoke-LabSc -ScArguments @('start',$atlasCandidate)
    & $atlasExe --handoff $atlasRoot
    if ($LASTEXITCODE -ne 0) { throw 'Memory-only synthetic handoff failed.' }
    $atlasFirst=Wait-LabReport (Join-Path $atlasRoot 'reports\phase-1.json') $atlasCandidate
    Write-LabConfig 2
    Invoke-LabSc -ScArguments @('start',$atlasCandidate)
    $atlasSecond=Wait-LabReport (Join-Path $atlasRoot 'reports\phase-2.json') $atlasCandidate
    Invoke-LabSc -ScArguments @('start',$atlasObserver)
    $atlasUnauthorized=Wait-LabReport (Join-Path $atlasRoot 'observer-reports\phase-2.json') $atlasObserver
    & $atlasExe --verify $atlasRoot | Tee-Object -FilePath (Join-Path $atlasRoot 'reports\creator-verify.json') | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Creator verification failed.' }
    $atlasCreator=Get-Content -LiteralPath (Join-Path $atlasRoot 'reports\creator-verify.json') -Raw | ConvertFrom-Json
    foreach ($atlasReport in @($atlasFirst,$atlasSecond)) {
        foreach ($atlasRequired in @('WrongUserBlobDenied','OtherUserSecretsAclDenied','SameServiceAccountDecrypt','ProfileDirectoryPresent','SqliteLockEnforced','SqliteReadWriteRollback','PrinterWithCapabilitiesFound','PrinterOpenReadApi','SpoolerQueryable','DnsResolved')) {
            if ($atlasReport.$atlasRequired -ne $true) { throw ('Missing lab proof: '+$atlasRequired) }
        }
        if ($atlasReport.IsAdministrator -ne $false -or $atlasReport.HttpsStatus -ne 200 -or $atlasReport.PhysicalPrintsSent -ne 0) { throw 'Unexpected candidate privileges/transport/print state.' }
    }
    if (!$atlasSecond.RestartDpapiRecovered -or !$atlasSecond.SqliteRestartRecovered -or !$atlasUnauthorized.CandidateSecretsAclDenied -or
        !$atlasUnauthorized.CopiedCandidateBlobDenied -or !$atlasCreator.CreatorOwnDecrypt -or !$atlasCreator.CreatorCannotDecryptCandidateCopy -or
        !$atlasCreator.SyntheticUuidPreserved -or !$atlasCreator.NoPlaintextRuntimeArtifacts) { throw 'Synthetic isolation/recovery verification failed.' }
    $atlasSucceeded=$true
}
finally {
    foreach ($atlasName in $atlasCreated) {
        $atlasService=Get-CimInstance Win32_Service -Filter "Name='$atlasName'"
        if ($atlasService -and $atlasName -match '^AtlasDpapi(Candidate|Observer)QA_[a-f0-9]{12}$' -and $atlasService.PathName.Contains($atlasRoot) -and $atlasService.StartName -eq ('NT SERVICE\'+$atlasName)) {
            if ((Get-Service -Name $atlasName).Status -ne 'Stopped') { Stop-Service -Name $atlasName; (Get-Service $atlasName).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(15)) }
            Invoke-LabSc -ScArguments @('delete',$atlasName)
        } elseif ($atlasService) { throw 'Unexpected service identity: refuse cleanup.' }
    }
    # No broad profile delete. These synthetic profile caches are inventoried for safe targeted cleanup.
    $atlasProfiles=@(foreach ($atlasSid in $atlasIdentities.Values) { Get-CimInstance Win32_UserProfile -Filter "SID='$atlasSid'" | Select-Object SID,LocalPath,Loaded })
    [pscustomobject]@{Succeeded=$atlasSucceeded;Root=$atlasRoot;ServicesRemoved=@($atlasCreated | Where-Object {Get-Service -Name $_ -ErrorAction SilentlyContinue}).Count -eq 0;SyntheticProfiles=$atlasProfiles;RealCredentialsTouched=$false;PhysicalPrintsSent=0} |
        ConvertTo-Json -Depth 5 | Tee-Object -FilePath (Join-Path $atlasRoot 'lab-summary.json') | Out-Host
}
