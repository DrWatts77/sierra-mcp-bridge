[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$SettingsPath,
      [Parameter(Mandatory=$true)][ValidateSet('bridge','tunnel')][string]$Role)
$ErrorActionPreference='Stop'
try {
    $settings=Get-Content -LiteralPath $SettingsPath -Raw | ConvertFrom-Json
    if ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne $settings.owner_sid) {
        throw 'Service Windows account does not match the credential owner.'
    }
    Set-Location -LiteralPath $settings.root
    if ($Role -eq 'tunnel') {
        # Own ngrok process stays attached to NSSM through this foreground runner.
        & $settings.ngrok http ('http://127.0.0.1:' + $settings.port) ('--url=' + $settings.public_url) ('--config=' + $settings.ngrok_config) --inspect=false --log=false
        exit $LASTEXITCODE
    }
    $env:FASTMCP_HOME=$settings.oauth_home
    if ($settings.auth -eq 'entra') {
        $secret=Import-Clixml -LiteralPath $settings.secret
        try { $env:SIERRA_ENTRA_CLIENT_SECRET=([pscredential]::new('entra',$secret)).GetNetworkCredential().Password }
        finally { $secret.Dispose() }
        $env:SIERRA_ENTRA_CLIENT_ID=$settings.client_id
        $env:SIERRA_ENTRA_TENANT_ID=$settings.tenant_id
        $env:SIERRA_MCP_PUBLIC_URL=$settings.public_url
        $env:SIERRA_MCP_CLIENT_REDIRECTS=ConvertTo-Json -InputObject @($settings.client_redirect) -Compress
    } elseif ($settings.auth -ne 'none') { throw 'Unsupported service auth mode.' }
    & $settings.python -m sierra_mcp_bridge.server --config $settings.config --auth $settings.auth --port $settings.port
    exit $LASTEXITCODE
} catch {
    Write-Error 'Service runner failed. Check service identity, file permissions and local configuration using the foreground launcher.'
    exit 1
} finally { Remove-Item Env:\SIERRA_ENTRA_CLIENT_SECRET -ErrorAction SilentlyContinue }
