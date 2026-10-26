param([switch]$Execute)
$ErrorActionPreference='Stop'
$atlasName='AtlasLocalAgent'
$atlasExpectedExe=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'AtlasPergamo\LocalAgent\service\Atlas.LocalAgent.Service.exe'
$atlasService=Get-CimInstance Win32_Service -Filter "Name='AtlasLocalAgent'"
if (!$atlasService) { Write-Output 'ServiceAbsent; all pairing/data retained.'; return }
if ($atlasService.StartName -ne 'NT SERVICE\AtlasLocalAgent' -or !$atlasService.PathName.StartsWith(('"'+$atlasExpectedExe+'" --windows-service '),[StringComparison]::OrdinalIgnoreCase)) {throw 'Unexpected service identity/path; refuse removal.'}
Write-Output 'Plan: stop/delete ONLY AtlasLocalAgent SCM registration. Preserve ProgramData, old root, DPAPI service profile, SQLite, pairing, binaries and backups.'
if (!$Execute) { Write-Output 'DRY_RUN_ONLY: no changes.'; return }
if ((Get-Service $atlasName).Status -ne 'Stopped') {Stop-Service $atlasName; (Get-Service $atlasName).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(30))}
& "$env:SystemRoot\System32\sc.exe" delete $atlasName
if ($LASTEXITCODE -ne 0) {throw 'Service delete failed; data retained.'}
Write-Output 'SCM registration removed; all pairing/data/profile retained. Manual mode still locked by machine binding until explicit rollback.'
