# Run interactively as the Windows user who will run Sierra MCP Bridge.
# Export-Clixml uses Windows DPAPI for SecureString: same user and computer only.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    throw 'This secret store requires Windows DPAPI.'
}
if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw 'LOCALAPPDATA is unavailable.'
}
$secretDirectory = Join-Path $env:LOCALAPPDATA 'SierraMCPBridge\secrets'
$secretPath = Join-Path $secretDirectory 'entra-client-secret.xml'
$temporaryPath = Join-Path $secretDirectory ([guid]::NewGuid().ToString() + '.tmp')
$clientSecret = Read-Host 'Paste the Entra client secret VALUE (input is hidden)' -AsSecureString
try {
    if ($clientSecret.Length -eq 0) { throw 'No secret entered; existing storage was not changed.' }
    New-Item -ItemType Directory -Path $secretDirectory -Force | Out-Null
    $clientSecret | Export-Clixml -LiteralPath $temporaryPath
    Move-Item -LiteralPath $temporaryPath -Destination $secretPath -Force
    Write-Host 'Saved the encrypted Entra secret for this Windows user and computer.'
    Write-Host 'The bridge and tunnel have not been started.'
}
finally {
    $clientSecret.Dispose()
    if (Test-Path -LiteralPath $temporaryPath) {
        Remove-Item -LiteralPath $temporaryPath -Force
    }
}
