# Run from an x64 Visual Studio developer PowerShell. Never installs a DLL.
param([Parameter(Mandatory = $true)][string]$SierraSourceDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$headers = (Resolve-Path -LiteralPath $SierraSourceDirectory).Path
$source = Join-Path $projectRoot 'acsil/sierra_mcp_bridge.cpp'
if (-not (Test-Path -LiteralPath $source)) {
    $source = Join-Path (Split-Path $projectRoot -Parent) 'ACS_Source/sierra_mcp_bridge.cpp'
}
$source = (Resolve-Path -LiteralPath $source).Path
$compiler = (Get-Command cl.exe -ErrorAction Stop).Source
$buildDirectory = Join-Path $projectRoot ('runtime/native-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $buildDirectory -Force | Out-Null
Push-Location $buildDirectory
try {
    & $compiler /nologo /EHsc /std:c++17 /MD "/I$(Split-Path $source -Parent)" "/I$headers" `
        (Join-Path $projectRoot 'tests/export_identity_native.cpp') /Fe:identity_tests.exe /Fo:identity_tests.obj /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Native test build failed' }
    & (Join-Path $buildDirectory 'identity_tests.exe') $buildDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Native identity tests failed' }
    & $compiler /nologo /EHsc /std:c++17 /MD /LD "/I$headers" $source /Fe:SierraMCPBridge_64.dll /Fo:bridge.obj /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Isolated exporter build failed' }
} finally {
    Pop-Location
}
