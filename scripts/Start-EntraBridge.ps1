[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ClientId,
    [Parameter(Mandatory=$true)][string]$TenantId,
    [Parameter(Mandatory=$true)][string]$PublicUrl,
    [string]$ClientRedirect = 'https://chatgpt.com/connector_platform_oauth_redirect',
    [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectDirectory '.venv\Scripts\python.exe'
$configPath = Join-Path $projectDirectory 'config.local.json'
$secretPath = Join-Path $env:LOCALAPPDATA 'SierraMCPBridge\secrets\entra-client-secret.xml'
$secureSecret = Import-Clixml -LiteralPath $secretPath
if ($secureSecret -isnot [System.Security.SecureString]) { throw 'Invalid secret storage format.' }
$variableNames = @('SIERRA_ENTRA_CLIENT_ID', 'SIERRA_ENTRA_TENANT_ID', 'SIERRA_MCP_PUBLIC_URL', 'SIERRA_ENTRA_CLIENT_SECRET', 'SIERRA_MCP_CLIENT_REDIRECTS')
$previousValues = @{}
foreach ($name in $variableNames) { $previousValues[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:SIERRA_ENTRA_CLIENT_ID = $ClientId
    $env:SIERRA_ENTRA_TENANT_ID = $TenantId
    $env:SIERRA_MCP_PUBLIC_URL = $PublicUrl
    $env:SIERRA_MCP_CLIENT_REDIRECTS = ConvertTo-Json -InputObject @($ClientRedirect) -Compress
    $credential = New-Object System.Management.Automation.PSCredential('entra', $secureSecret)
    $env:SIERRA_ENTRA_CLIENT_SECRET = $credential.GetNetworkCredential().Password
    & $pythonPath -m sierra_mcp_bridge.server --config $configPath --auth entra --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Bridge stopped with an error.' }
}
finally {
    foreach ($name in $variableNames) { [Environment]::SetEnvironmentVariable($name, $previousValues[$name], 'Process') }
    $secureSecret.Dispose()
    $credential = $null
}
