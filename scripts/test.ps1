# Unique project-owned test directory avoids global Windows temp ACL conflicts.
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
New-Item -ItemType Directory -Path (Join-Path $projectRoot 'runtime') -Force | Out-Null
$testDirectory = Join-Path $projectRoot ('runtime\tests-' + [guid]::NewGuid().ToString('N'))
Push-Location $projectRoot
try {
    uv run --locked pytest -q --tb=short --basetemp $testDirectory @args
    if ($LASTEXITCODE -ne 0) { throw 'Bridge tests failed' }
} finally {
    Pop-Location
}
