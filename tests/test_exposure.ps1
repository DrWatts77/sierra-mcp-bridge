$ErrorActionPreference='Stop'
$sandbox=Join-Path $PSScriptRoot ('exposure-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $sandbox 'scripts'),(Join-Path $sandbox '.venv\Scripts') -Force | Out-Null
foreach ($name in @('Exposure-Common.ps1','Start-SierraMCPExposure.ps1','Stop-SierraMCPExposure.ps1')) {
 Copy-Item -LiteralPath (Join-Path (Split-Path $PSScriptRoot -Parent) ('scripts\'+$name)) -Destination (Join-Path $sandbox 'scripts')
}
# Exercise a fresh powershell.exe -File invocation, not an inherited script scope.
# No profile exists yet, so it must resolve the correct path and fail before launch.
$freshStart=New-Object System.Diagnostics.ProcessStartInfo
$freshStart.FileName='powershell.exe'
$freshStart.Arguments='-NoProfile -File "' + (Join-Path $sandbox 'scripts\Start-SierraMCPExposure.ps1') + '"'
$freshStart.WorkingDirectory=$env:TEMP
$freshStart.UseShellExecute=$false
$freshStart.CreateNoWindow=$true
$freshStart.RedirectStandardError=$true
$freshStart.RedirectStandardOutput=$true
$freshProcess=[System.Diagnostics.Process]::Start($freshStart)
$freshErrors=$freshProcess.StandardError.ReadToEnd()
$freshProcess.StandardOutput.ReadToEnd() | Out-Null
$freshProcess.WaitForExit()
if ($freshProcess.ExitCode -eq 0 -or $freshErrors -notmatch 'connection.local.json' -or $freshErrors -match 'empty string') {
 throw 'Fresh -File default-profile resolution regression failed.'
}
$freshProcess.Dispose()
Set-Content -LiteralPath (Join-Path $sandbox '.venv\Scripts\python.exe') -Value ''
Set-Content -LiteralPath (Join-Path $sandbox 'config.local.json') -Value '{}'
Set-Content -LiteralPath (Join-Path $sandbox 'connection.local.json') -Value '{"auth":"none","port":18765,"public_url":"https://example.com"}'
$global:fakeProcesses=@{}
$global:fakeStarts=0
$global:fakeStops=0
$global:fakeOccupied=$false
function global:Get-NetTCPConnection { if ($global:fakeOccupied) { return 'occupied' } }
function global:Get-Command { return [pscustomobject]@{Source='C:\fake\ngrok.exe'} }
function global:Start-Process {
 $global:fakeStarts++
 $p=[pscustomobject]@{Id=$global:fakeStarts;StartTime=[datetime]::Now;Path='C:\fake\process.exe';HasExited=$false}
 $p | Add-Member ScriptMethod WaitForExit { param($timeout) return $true }
 $global:fakeProcesses[$p.Id]=$p
 return $p
}
function global:Get-Process { param($Id) return $global:fakeProcesses[[int]$Id] }
function global:Stop-Process { param([Parameter(ValueFromPipeline=$true)]$InputObject,[switch]$Force) process { $global:fakeStops++; $global:fakeProcesses.Remove([int]$InputObject.Id) } }
function global:Invoke-WebRequest { return [pscustomobject]@{StatusCode=200;Content='{"result":{"serverInfo":{"name":"Sierra MCP Bridge"}}}'} }
& (Join-Path $sandbox 'scripts\Start-SierraMCPExposure.ps1')
if ($global:fakeStarts -ne 2) { throw 'Expected bridge and tunnel' }
try { & (Join-Path $sandbox 'scripts\Start-SierraMCPExposure.ps1'); throw 'Duplicate was allowed' } catch { if ($_.Exception.Message -notmatch 'Managed processes already exist') { throw } }
if ($global:fakeStarts -ne 2 -or $global:fakeStops -ne 0) { throw 'Duplicate altered processes' }
& (Join-Path $sandbox 'scripts\Stop-SierraMCPExposure.ps1')
& (Join-Path $sandbox 'scripts\Stop-SierraMCPExposure.ps1')
if ($global:fakeStops -ne 2) { throw 'Stop did not handle exactly two processes' }
$global:fakeProcesses[900]=[pscustomobject]@{Id=900;StartTime=[datetime]::Now;Path='C:\fake\reused.exe'}
. (Join-Path $sandbox 'scripts\Exposure-Common.ps1')
try { Get-OwnedProcess ([pscustomobject]@{id=900;started='0';path='C:\fake\old.exe'}); throw 'Reused PID accepted' } catch { if ($_.Exception.Message -notmatch 'identity does not match') { throw } }
$global:fakeOccupied=$true
try { & (Join-Path $sandbox 'scripts\Start-SierraMCPExposure.ps1'); throw 'Occupied port allowed' } catch { if ($_.Exception.Message -notmatch 'port is occupied') { throw } }
Write-Output 'PASS: mocked start, duplicate rejection, owned stop, repeated stop and occupied-port rejection. No real services or secrets used.'

$global:probeCase='good'
function global:Invoke-WebRequest {
 param($Uri,$Headers,$UserAgent)
 if ($Headers['ngrok-skip-browser-warning'] -ne '1' -or $UserAgent -ne 'SierraMCPBridge-Readiness/1') { throw 'Missing programmatic probe headers' }
 if ($global:probeCase -eq 'network') { throw [Net.WebException]::new('synthetic', [Net.WebExceptionStatus]::NameResolutionFailure) }
 if ($Uri -match 'well-known') {
   $content=switch ($global:probeCase) {
     'html' { '<html>You are about to visit ngrok-skip-browser-warning</html>' }
     'wrong' { '{"issuer":"https://wrong.example.com"}' }
     'missing' { '{}' }
     'invalid' { 'not-json' }
     default { '{"issuer":"https://example.com/"}' }
   }
   return [pscustomobject]@{StatusCode=200;Content=$content}
 }
 $e=New-Object System.Exception('synthetic HTTP error')
 $status=if ($global:probeCase -eq 'upstream') { 502 } else { 401 }
 $e | Add-Member NoteProperty Response ([pscustomobject]@{StatusCode=$status})
 throw $e
}
foreach ($case in @('good','html','wrong','missing','invalid','network','upstream')) {
 $global:probeCase=$case
 $result=Test-BridgeReady 'https://example.com' 'entra' 'https://example.com'
 if ($result -ne ($case -eq 'good')) { throw ('Probe case failed: '+$case) }
 if (-not $result -and [string]::IsNullOrWhiteSpace($script:BridgeReadinessDetail)) { throw 'Missing diagnostic' }
 if ($case -eq 'upstream' -and $script:BridgeReadinessDetail -notmatch '502') { throw 'Missing HTTP status' }
}
Write-Output 'PASS: Entra metadata/401, ngrok HTML, invalid/missing/mismatched metadata, network failure and HTTP 502 diagnostics.'
