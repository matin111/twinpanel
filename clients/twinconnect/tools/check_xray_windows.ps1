# Credential-free smoke test: loopback SOCKS and blackhole only.
# No VPN route or real server is touched.
$ErrorActionPreference = 'Stop'
$exe = Join-Path (Get-Location) 'build/windows/x64/runner/Release/engines/xray/xray.exe'
if (!(Test-Path $exe)) { throw 'Xray executable not bundled' }
$config = '{"log":{"loglevel":"warning"},"inbounds":[{"listen":"127.0.0.1","port":19387,"protocol":"socks","settings":{"auth":"noauth","udp":false}}],"outbounds":[{"protocol":"blackhole","tag":"block"}]}'
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $exe
$psi.Arguments = 'run -test -config stdin:'
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi
if (!$process.Start()) { throw 'Could not start xray' }
try {
  $process.StandardInput.Write($config)
  $process.StandardInput.Close()
  if (!$process.WaitForExit(10000)) {
    $process.Kill()
    throw 'Xray syntax validation timed out'
  }
  if ($process.ExitCode -ne 0) { throw "Xray syntax check failed with code $($process.ExitCode)" }
} finally { $process.Dispose() }
Write-Host 'Xray synthetic stdin config validated'
