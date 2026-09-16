Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$exposureRoot = Split-Path $PSScriptRoot -Parent
$exposureRuntime = Join-Path $exposureRoot 'runtime'
$exposureState = Join-Path $exposureRuntime 'exposure-state.json'

function Enter-ExposureLock {
    New-Item -ItemType Directory -Path $exposureRuntime -Force | Out-Null
    try {
        return [IO.File]::Open((Join-Path $exposureRuntime 'exposure.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch { throw 'Another start/stop operation is running.' }
}

function Get-OwnedProcess($Record) {
    $process = Get-Process -Id $Record.id -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    # PID alone is insufficient: never stop a process that reused an old PID.
    if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne $Record.started -or $process.Path -ne $Record.path) {
        throw 'Stored process identity does not match. No unrelated process will be stopped.'
    }
    return $process
}

function Save-ExposureState($Records) {
    ConvertTo-Json -InputObject @($Records) -Depth 4 | Set-Content -LiteralPath $exposureState -Encoding UTF8
}

function Stop-OwnedExposure($Records) {
    foreach ($record in @($Records | Sort-Object role -Descending)) {
        $process = Get-OwnedProcess $record
        if ($null -ne $process) {
            $process | Stop-Process -Force
            $process.WaitForExit(5000) | Out-Null
        }
    }
}

function New-ProcessRecord($Process, $Role) {
    return [pscustomobject]@{ role=$Role; id=$Process.Id; started=$Process.StartTime.ToUniversalTime().Ticks.ToString(); path=$Process.Path }
}

$script:BridgeReadinessDetail = 'No probe completed.'

function Get-ProbeFailure($ErrorRecord) {
    $response = $null
    if ($ErrorRecord.Exception.PSObject.Properties['Response']) { $response = $ErrorRecord.Exception.Response }
    if ($null -ne $response) { return ('HTTP ' + [int]$response.StatusCode) }
    if ($ErrorRecord.Exception -is [System.Net.WebException]) {
        return ('Network/TLS error: ' + $ErrorRecord.Exception.Status.ToString())
    }
    return ('Request failed: ' + $ErrorRecord.Exception.GetType().Name)
}

function Test-BridgeReady($BaseUrl, $AuthMode, $ExpectedIssuer) {
    $stage = 'OAuth metadata'
    # Windows PowerShell may otherwise negotiate obsolete TLS defaults.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $headers = @{Accept='application/json, text/event-stream'; 'ngrok-skip-browser-warning'='1'}
    try {
        if ($AuthMode -eq 'entra') {
            $response = Invoke-WebRequest -UseBasicParsing -Uri ($BaseUrl + '/.well-known/oauth-authorization-server') -Headers $headers -UserAgent 'SierraMCPBridge-Readiness/1' -TimeoutSec 5
            if ($response.Content -match 'ngrok-skip-browser-warning|You are about to visit') {
                $script:BridgeReadinessDetail='OAuth metadata: received ngrok browser warning HTML.'; return $false
            }
            try { $metadata = $response.Content | ConvertFrom-Json } catch {
                $script:BridgeReadinessDetail='OAuth metadata: response is not JSON.'; return $false
            }
            if (-not $metadata.PSObject.Properties['issuer'] -or [string]::IsNullOrWhiteSpace($metadata.issuer)) {
                $script:BridgeReadinessDetail='OAuth metadata: issuer missing.'; return $false
            }
            if ($metadata.issuer.TrimEnd('/') -ne $ExpectedIssuer.TrimEnd('/')) {
                $script:BridgeReadinessDetail='OAuth metadata: issuer does not match configured public URL.'; return $false
            }
            $stage='Unauthenticated MCP denial'
            try {
                Invoke-WebRequest -UseBasicParsing -Uri ($BaseUrl + '/mcp') -Method Post -ContentType 'application/json' -Headers $headers -UserAgent 'SierraMCPBridge-Readiness/1' -Body '{}' -TimeoutSec 5 | Out-Null
                $script:BridgeReadinessDetail='MCP endpoint accepted an unauthenticated request; expected HTTP 401.'
                return $false
            } catch {
                if ($_.Exception.PSObject.Properties['Response'] -and $null -ne $_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) {
                    $script:BridgeReadinessDetail='OAuth metadata and HTTP 401 verified.'; return $true
                }
                $script:BridgeReadinessDetail=$stage + ': ' + (Get-ProbeFailure $_); return $false
            }
        }
        $stage='Anonymous MCP initialization'
        $response = Invoke-WebRequest -UseBasicParsing -Uri ($BaseUrl + '/mcp') -Method Post -ContentType 'application/json' -Headers $headers -UserAgent 'SierraMCPBridge-Readiness/1' -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"bridge-launcher","version":"1"}}}' -TimeoutSec 5
        $success=($response.StatusCode -eq 200 -and $response.Content -match 'Sierra MCP Bridge')
        $script:BridgeReadinessDetail=if ($success) { 'MCP initialization verified.' } else { 'Unexpected MCP initialization response.' }
        return $success
    } catch { $script:BridgeReadinessDetail=$stage + ': ' + (Get-ProbeFailure $_); return $false }
}
