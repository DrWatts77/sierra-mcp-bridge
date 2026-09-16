[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'Exposure-Common.ps1')
$operationLock = Enter-ExposureLock
try {
    if (-not (Test-Path -LiteralPath $exposureState)) { Write-Host 'No managed exposure recorded.'; return }
    $records = Get-Content -LiteralPath $exposureState -Raw | ConvertFrom-Json
    Stop-OwnedExposure $records
    Save-ExposureState @()
    Write-Host 'Stopped the recorded bridge/tunnel processes. Existing manually started processes were not targeted.'
} finally { $operationLock.Dispose() }
