# Offline, unprivileged smoke test of the bundled independent Mieru client.
# No TUN, VPN routes, remote authentication or customer credentials.
$ErrorActionPreference = 'Stop'
$exe = Join-Path (Get-Location) 'build/windows/x64/runner/Release/engines/mieru/mieru.exe'
if (!(Test-Path -LiteralPath $exe)) { throw 'Bundled Mieru client missing' }
if ((Get-Item -LiteralPath $exe).Length -lt 1000000) {
  throw 'Bundled Mieru executable unexpectedly small'
}
function Get-LoopbackPort {
  $s = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
  $s.Start()
  $p = ([System.Net.IPEndPoint]$s.LocalEndpoint).Port
  $s.Stop()
  return $p
}
$ports = @()
for ($i = 0; $i -lt 16 -and $ports.Count -lt 3; $i++) {
  $p = Get-LoopbackPort
  if ($ports -notcontains $p) { $ports += $p }
}
if ($ports.Count -ne 3) { throw 'Unable to reserve synthetic Mieru loopback ports' }
$config = @{
  profiles = @(@{
    profileName = 'synthetic-test'
    user = @{name = 'synthetic-test'; password = 'not-a-customer-password'}
    servers = @(@{
      ipAddress = '203.0.113.45'
      portBindings = @(@{port=23456;protocol='TCP'})
    })
    mtu = 1400
    multiplexing = @{level='MULTIPLEXING_LOW'}
    handshakeMode = 'HANDSHAKE_STANDARD'
  })
  activeProfile = 'synthetic-test'
  rpcPort = $ports[0]
  socks5Port = $ports[1]
  socks5ListenLAN = $false
  httpProxyPort = $ports[2]
  httpProxyListenLAN = $false
  loggingLevel = 'ERROR'
}
$file = Join-Path $env:RUNNER_TEMP 'twinconnect-mieru-synthetic.json'
$stdout = Join-Path $env:RUNNER_TEMP 'twinconnect-mieru-smoke.out'
$stderr = Join-Path $env:RUNNER_TEMP 'twinconnect-mieru-smoke.err'
$child = $null
try {
  $config | ConvertTo-Json -Depth 12 -Compress |
      Set-Content -LiteralPath $file -NoNewline -Encoding utf8
  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $exe
  $psi.Arguments = 'run'
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.Environment['MIERU_CONFIG_JSON_FILE'] = $file
  $child = [System.Diagnostics.Process]::Start($psi)
  if ($null -eq $child) { throw 'Mieru native process did not start' }
  $ready = $false
  for ($i = 0; $i -lt 35; $i++) {
    if ($child.HasExited) { throw 'Mieru core exited before SOCKS readiness' }
    $socket = [System.Net.Sockets.TcpClient]::new()
    try {
      $connect = $socket.BeginConnect('127.0.0.1', $ports[1], $null, $null)
      if (!$connect.AsyncWaitHandle.WaitOne(250)) { continue }
      $socket.EndConnect($connect)
      $stream = $socket.GetStream()
      $stream.ReadTimeout = 800
      $stream.WriteTimeout = 800
      $stream.Write([byte[]]@(5, 1, 0), 0, 3)
      $response = [byte[]]@(0, 0)
      if ($stream.Read($response, 0, 2) -eq 2 -and
          $response[0] -eq 5 -and $response[1] -eq 0) {
        $ready = $true
        break
      }
    } catch {} finally { $socket.Dispose() }
    Start-Sleep -Milliseconds 150
  }
  if (!$ready) { throw 'Mieru SOCKS5 listener did not become ready' }
  Start-Sleep -Seconds 1
  if ($child.HasExited) { throw 'Mieru core exited after readiness' }
  Write-Host 'Official Mieru Windows core remained alive with isolated synthetic SOCKS5'
} finally {
  if ($null -ne $child) {
    try { if (!$child.HasExited) { $child.Kill() } } catch {}
    try { $child.WaitForExit(5000) | Out-Null } catch {}
    $child.Dispose()
  }
  Remove-Item -LiteralPath $file,$stdout,$stderr -ErrorAction SilentlyContinue
}
