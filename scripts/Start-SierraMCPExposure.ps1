[CmdletBinding()]
param([string]$ProfilePath)
. (Join-Path $PSScriptRoot 'Exposure-Common.ps1')
if ([string]::IsNullOrWhiteSpace($ProfilePath)) {
    $ProfilePath = Join-Path $exposureRoot 'connection.local.json'
}
$operationLock = Enter-ExposureLock
$records = @()
$previousSecret = [Environment]::GetEnvironmentVariable('SIERRA_ENTRA_CLIENT_SECRET', 'Process')
$names = @('SIERRA_ENTRA_CLIENT_ID','SIERRA_ENTRA_TENANT_ID','SIERRA_MCP_PUBLIC_URL','SIERRA_MCP_CLIENT_REDIRECTS')
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    if (Test-Path -LiteralPath $exposureState) {
        $existing = Get-Content -LiteralPath $exposureState -Raw | ConvertFrom-Json
        foreach ($record in $existing) {
            if ($null -ne (Get-OwnedProcess $record)) { throw 'Managed processes already exist. Run Stop-SierraMCPExposure.ps1 before restarting.' }
        }
    }
    $profile = Get-Content -LiteralPath $ProfilePath -Raw | ConvertFrom-Json
    if ($profile.auth -notin @('entra','none')) { throw 'Profile auth must be entra or none.' }
    $public = [Uri]$profile.public_url
    if ($public.Scheme -ne 'https' -or $public.AbsolutePath -ne '/' -or $public.Query -or $public.Fragment -or $public.UserInfo) { throw 'public_url must be an HTTPS origin.' }
    $publicUrl = $public.GetLeftPart([UriPartial]::Authority)
    $port = [int]$profile.port
    if ($port -lt 1 -or $port -gt 65535) { throw 'Invalid port.' }
    $python = (Resolve-Path -LiteralPath (Join-Path $exposureRoot '.venv\Scripts\python.exe')).Path
    $ngrok = (Get-Command ngrok.exe -ErrorAction Stop).Source
    $config = (Resolve-Path -LiteralPath (Join-Path $exposureRoot 'config.local.json')).Path
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw 'Bridge port is occupied. Stop the old bridge window first; existing services were not changed.' }
    if ($profile.auth -eq 'entra') {
        $env:SIERRA_ENTRA_CLIENT_ID = ([guid]$profile.client_id).ToString()
        $env:SIERRA_ENTRA_TENANT_ID = ([guid]$profile.tenant_id).ToString()
        $env:SIERRA_MCP_PUBLIC_URL = $publicUrl
        $env:SIERRA_MCP_CLIENT_REDIRECTS = ConvertTo-Json -InputObject @($profile.client_redirect) -Compress
        $secret = Import-Clixml -LiteralPath (Join-Path $env:LOCALAPPDATA 'SierraMCPBridge\secrets\entra-client-secret.xml')
        if ($secret -isnot [Security.SecureString]) { throw 'Invalid encrypted secret format.' }
        try { $env:SIERRA_ENTRA_CLIENT_SECRET = ([pscredential]::new('entra',$secret)).GetNetworkCredential().Password }
        finally { $secret.Dispose() }
    } else {
        Write-Host 'Anonymous mode: anyone reaching the public endpoint can read configured chart data.'
        [Environment]::SetEnvironmentVariable('SIERRA_ENTRA_CLIENT_SECRET', $null, 'Process')
    }
    # Arguments are data, never evaluated as a generated shell command. Only config is a path with spaces.
    $bridge = Start-Process -FilePath $python -ArgumentList @('-m','sierra_mcp_bridge.server','--config',('"' + $config + '"'),'--auth',$profile.auth,'--port',$port) -WorkingDirectory $exposureRoot -WindowStyle Hidden -PassThru
    $records += New-ProcessRecord $bridge 'bridge'
    Save-ExposureState $records
    # Do not pass the Entra secret on to ngrok.
    [Environment]::SetEnvironmentVariable('SIERRA_ENTRA_CLIENT_SECRET', $null, 'Process')
    $ready = $false
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        if ($bridge.HasExited) { throw 'Bridge exited during startup; run Start-EntraBridge.ps1 in a console to diagnose.' }
        if (Test-BridgeReady ('http://127.0.0.1:' + $port) $profile.auth $publicUrl) { $ready=$true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw ('Local readiness failed: ' + $script:BridgeReadinessDetail + ' Tunnel was not started.') }
    Write-Host 'Local bridge ready. Starting ngrok and checking public HTTPS...'
    $tunnel = Start-Process -FilePath $ngrok -ArgumentList @('http',('http://127.0.0.1:' + $port),('--url=' + $publicUrl),'--inspect=false','--log=false') -WorkingDirectory $exposureRoot -WindowStyle Hidden -PassThru
    $records += New-ProcessRecord $tunnel 'tunnel'
    Save-ExposureState $records
    $ready = $false
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        if ($bridge.HasExited -or $tunnel.HasExited) { throw 'Bridge or ngrok exited. Check ngrok account/domain setup and existing tunnels.' }
        if (Test-BridgeReady $publicUrl $profile.auth $publicUrl) { $ready=$true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw ('Public readiness failed: ' + $script:BridgeReadinessDetail + ' Newly started processes will be stopped.') }
    Write-Host ('Ready: ' + $publicUrl + '/mcp')
    Write-Host ('Authentication: ' + $profile.auth)
    Write-Host 'Stop both with scripts\Stop-SierraMCPExposure.ps1. No persistent logs are collected.'
} catch {
    if ($records.Count -gt 0) { Stop-OwnedExposure $records; Save-ExposureState @() }
    throw
} finally {
    [Environment]::SetEnvironmentVariable('SIERRA_ENTRA_CLIENT_SECRET', $previousSecret, 'Process')
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
    $operationLock.Dispose()
}
