# Windows CI smoke test for the actual process lifecycle.
# Synthetic proxy-only config: no real credentials, DNS or Windows routes.
$ErrorActionPreference = 'Stop'
$engine = Join-Path (Get-Location) 'build/windows/x64/runner/Release/engines/sing-box/sing-box.exe'
if (!(Test-Path -LiteralPath $engine)) { throw 'sing-box engine not bundled' }

$lease = [System.Net.Sockets.TcpListener]::new(
  [System.Net.IPAddress]::Loopback, 0)
$lease.Start()
$port = ([System.Net.IPEndPoint]$lease.LocalEndpoint).Port
$lease.Stop()
$config = @{
  log = @{ level = 'error' }
  inbounds = @(@{
    type = 'mixed'; tag = 'twinconnect-ci-probe'
    listen = '127.0.0.1'; listen_port = $port
  })
  outbounds = @(@{ type = 'direct'; tag = 'direct' })
  route = @{ final = 'direct' }
} | ConvertTo-Json -Depth 12

$info = [System.Diagnostics.ProcessStartInfo]::new()
$info.FileName = $engine
$info.ArgumentList.Add('run')
$info.ArgumentList.Add('-c')
$info.ArgumentList.Add('stdin')
$info.UseShellExecute = $false
$info.CreateNoWindow = $true
$info.RedirectStandardInput = $true
$info.RedirectStandardOutput = $true
$info.RedirectStandardError = $true
$proc = [System.Diagnostics.Process]::new()
$proc.StartInfo = $info
$ready = $false
try {
  if (!$proc.Start()) { throw 'Could not launch sing-box' }
  $proc.StandardInput.Write($config)
  $proc.StandardInput.Close()
  for ($i = 0; $i -lt 30; $i++) {
    if ($proc.HasExited) { throw 'sing-box exited before proxy became ready' }
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
      $task = $client.ConnectAsync('127.0.0.1', [int]$port)
      if ($task.Wait(300) -and $client.Connected) { $ready = $true; break }
    } catch {} finally { $client.Dispose() }
    Start-Sleep -Milliseconds 200
  }
  if (!$ready) { throw 'sing-box local listener did not start' }
  Write-Host 'sing-box process accepted stdin config and opened loopback listener'
} finally {
  if (!$proc.HasExited) {
    $proc.Kill()
    if (!$proc.WaitForExit(5000)) {
      throw 'Synthetic sing-box process failed to stop'
    }
  }
  $proc.Dispose()
}
