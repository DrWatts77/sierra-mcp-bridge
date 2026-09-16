[CmdletBinding()]
param([ValidateSet('plan','install','status','enable','restart','stop','uninstall')][string]$Action='plan',
      [string]$NssmPath, [string]$NgrokConfig)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$python=Join-Path $root '.venv\Scripts\python.exe'
$arguments=@('-m','sierra_mcp_bridge.windows_service',$Action,'--root',$root)
if ($Action -in @('plan','install')) {
    if (-not $NssmPath) {
        $command=Get-Command nssm.exe -ErrorAction SilentlyContinue
        $bundled=Join-Path $root 'bin\nssm.exe'
        $NssmPath=if (Test-Path -LiteralPath $bundled) { $bundled } elseif ($command) { $command.Source } else { $bundled }
    }
    $ngrok=(Get-Command ngrok.exe -ErrorAction Stop).Source
    if (-not $NgrokConfig) { $NgrokConfig=Join-Path $env:LOCALAPPDATA 'ngrok\ngrok.yml' }
    $arguments+=@('--nssm',$NssmPath,'--ngrok',$ngrok,'--ngrok-config',$NgrokConfig)
}
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Service operation failed. See the preceding setup message.' }
if ($Action -eq 'status') {
    . (Join-Path $PSScriptRoot 'Exposure-Common.ps1')
    $settings=Get-Content -LiteralPath (Join-Path $root 'service.local.json') -Raw | ConvertFrom-Json
    foreach ($base in @(('http://127.0.0.1:' + $settings.port),$settings.public_url)) {
        $ready=Test-BridgeReady $base $settings.auth $settings.public_url
        Write-Host ($base + ': ' + $script:BridgeReadinessDetail)
    }
    $preflight = & $python -m sierra_mcp_bridge.setup --config (Join-Path $root 'config.local.json') | ConvertFrom-Json
    $preflight.checks | Where-Object { $_.stage -like 'snapshot:*' } | ConvertTo-Json
}
