[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$IsccPath,
    [Parameter(Mandatory = $true)][string]$PayloadDir
)
$ErrorActionPreference = 'Stop'
$agentRoot = Split-Path -Parent $PSScriptRoot
# Keep AppId below Inno's key shortening threshold so the assertion is exact.
$qaId = 'AtlasAgent.QA.' + [Guid]::NewGuid().ToString('N')
$qaRoot = Join-Path $agentRoot ('artifacts\installer-smoke-' + [Guid]::NewGuid().ToString('N'))
$installDir = Join-Path $qaRoot 'installed'
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$registryKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\${qaId}_is1"
$defaultData = Join-Path $env:LOCALAPPDATA 'Atlas\LocalAgent'
function DataFingerprint {
    if (!(Test-Path -LiteralPath $defaultData)) { return 'ABSENT' }
    return ((Get-ChildItem -LiteralPath $defaultData -Recurse -File | Sort-Object FullName | ForEach-Object {
        $_.FullName + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }) -join "`n")
}
$before = DataFingerprint
$installed = $false
try {
    & $IsccPath /Q "/DPayloadDir=$PayloadDir" "/DOutputDir=$qaRoot" "/DInstallerAppId=$qaId" '/DInstallerQa=1' '/DOutputName=installer-smoke' (Join-Path $PSScriptRoot 'atlas-local-agent.iss')
    if ($LASTEXITCODE -ne 0) { throw 'QA compile failed' }
    $setup = Join-Path $qaRoot 'installer-smoke.exe'
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', '/LANG=spanish', '/TASKS=', ('/DIR="' + $installDir + '"'))
    $result = Start-Process -FilePath $setup -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($result.ExitCode -ne 0) { throw "QA install failed: $($result.ExitCode)" }
    $installed = $true
    if (!(Test-Path -LiteralPath $registryKey)) { throw 'QA uninstall registration missing' }
    $manifest = Get-Content -LiteralPath (Join-Path $PayloadDir 'payload-sha256.json') -Raw | ConvertFrom-Json
    foreach ($entry in $manifest) {
        $file = Join-Path $installDir $entry.path
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) { throw 'Installed payload mismatch' }
    }
    # Start only the installed QA child with a new data root. No pairing or consumer.
    $qaData = Join-Path $qaRoot 'runtime-data'
    $childStart = [Diagnostics.ProcessStartInfo]::new((Join-Path $installDir 'service\Atlas.LocalAgent.Service.exe'))
    $childStart.UseShellExecute = $false
    $childStart.CreateNoWindow = $true
    $childStart.RedirectStandardInput = $true
    foreach ($arg in @('--data-dir', $qaData, '--environment', 'Production', '--stop-on-stdin-close')) { $childStart.ArgumentList.Add($arg) }
    $childStart.Environment.Remove('LOCAL_AGENT_ALLOW_LOOPBACK_HTTP') | Out-Null
    $child = [Diagnostics.Process]::Start($childStart)
    try {
        $probeStart = [Diagnostics.ProcessStartInfo]::new($childStart.FileName)
        $probeStart.UseShellExecute = $false
        $probeStart.CreateNoWindow = $true
        $probeStart.RedirectStandardOutput = $true
        foreach ($arg in @('--data-dir', $qaData, '--probe')) { $probeStart.ArgumentList.Add($arg) }
        $probe = [Diagnostics.Process]::Start($probeStart)
        try {
            $replyText = $probe.StandardOutput.ReadToEnd()
            $probe.WaitForExit()
            if ($probe.ExitCode -ne 0) { throw 'Installed runtime probe failed' }
            $reply = $replyText | ConvertFrom-Json
            if ($reply.snapshot.state -ne 'Unpaired' -or $reply.printDiagnostics.physicalPrintingEnabled -ne $false) { throw 'Installed runtime is not safe/unpaired' }
            if ($reply.snapshot.configuration.association.organizationId) { throw 'Unexpected preconfigured tenant' }
        }
        finally { $probe.Dispose() }
        $child.StandardInput.Close()
        if (!$child.WaitForExit(15000) -or $child.ExitCode -ne 0) { throw 'Installed child did not stop cleanly' }
    }
    finally {
        $child.StandardInput.Close()
        if (!$child.HasExited) { $child.Kill(); $child.WaitForExit() }
        $child.Dispose()
    }
    # Remove only the runtime fixture this test created, after verifying its location.
    $resolvedQaData = [IO.Path]::GetFullPath($qaData)
    if (!$resolvedQaData.StartsWith([IO.Path]::GetFullPath($qaRoot) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe QA cleanup target' }
    Remove-Item -LiteralPath $resolvedQaData -Recurse -Force
    if ((DataFingerprint) -cne $before) { throw 'Unexpected runtime data change on install' }
    # Reinstall/upgrade must not alter station state either.
    $result = Start-Process -FilePath $setup -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($result.ExitCode -ne 0) { throw 'QA reinstall failed' }
    if ((DataFingerprint) -cne $before) { throw 'Unexpected runtime data change on reinstall' }
    $uninstaller = Join-Path $installDir 'unins000.exe'
    $result = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -WindowStyle Hidden -Wait -PassThru
    if ($result.ExitCode -ne 0) { throw 'QA uninstall failed' }
    $installed = $false
    # Inno's final self-cleanup can complete just after its parent returns.
    for ($retry = 0; $retry -lt 30 -and (Test-Path -LiteralPath $registryKey); $retry++) { Start-Sleep -Milliseconds 200 }
    if (Test-Path -LiteralPath $registryKey) { throw 'QA uninstall registration was not removed' }
    if (Test-Path -LiteralPath (Join-Path $installDir 'tray\Atlas.LocalAgent.Tray.exe')) { throw 'QA application files remain' }
    if ((DataFingerprint) -cne $before) { throw 'Unexpected runtime data change on uninstall' }
    [PSCustomObject]@{ Result = 'PASS'; Install = 'PASS'; InstalledRuntime = 'PASS'; Reinstall = 'PASS'; Uninstall = 'PASS'; PayloadHashes = $manifest.Count; RuntimeDataUnchanged = $true; Pairing = $false; PhysicalPrintsSent = 0; QaRoot = $qaRoot }
}
finally {
    if ($installed -and (Test-Path -LiteralPath (Join-Path $installDir 'unins000.exe'))) {
        Start-Process -FilePath (Join-Path $installDir 'unins000.exe') -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -WindowStyle Hidden -Wait | Out-Null
    }
}
