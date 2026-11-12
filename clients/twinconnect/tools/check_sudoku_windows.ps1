# Synthetic Sudoku CLI validation only; no remote dial / Windows routes.
# Never publish a generated private key to CI logs or artifacts.
$ErrorActionPreference = 'Stop'
$exe = Join-Path (Get-Location) 'build/windows/x64/runner/Release/engines/sudoku/sudoku.exe'
if (!(Test-Path $exe)) { throw 'Official Sudoku core not bundled' }
$keygen = (& $exe -keygen 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0) { throw 'Sudoku keygen self-test failed' }
$match = [regex]::Match($keygen, 'Available Private Key:\s*([0-9a-fA-F]{64,128})')
if (!$match.Success) { throw 'Sudoku generated no valid test key' }
$sample = @{
  mode = 'client'
  transport = 'tcp'
  server_address = '203.0.113.44:18553'
  local_address = '127.0.0.1'
  local_port = 19388
  key = $match.Groups[1].Value
  aead = 'chacha20-poly1305'
  padding_min = 5
  padding_max = 15
  ascii = 'prefer_entropy'
  enable_pure_downlink = $true
  multiplex = 'off'
  httpmask = @{ disable = $false; mode = 'auto' }
  rule_urls = @('global')
}
$file = Join-Path $env:RUNNER_TEMP 'twinconnect-sudoku-synthetic.json'
try {
  $sample | ConvertTo-Json -Depth 6 -Compress |
    Set-Content -LiteralPath $file -NoNewline -Encoding utf8
  & $exe -test -c $file 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw 'Official Sudoku CLI rejected a synthetic TwinConnect client profile'
  }
  # Also exercise the real Windows listener. A successful -test is not proof
  # that the native Sudoku process can stay alive as a SOCKS5 server.
  # This uses only a generated test key and an unroutable RFC5737 upstream;
  # it never changes Windows routes or contacts a customer server.
  $listener = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback, 0)
  $listener.Start()
  $localPort = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
  $listener.Stop()
  $sample.local_port = $localPort
  $sample | ConvertTo-Json -Depth 6 -Compress |
    Set-Content -LiteralPath $file -NoNewline -Encoding utf8
  $stdout = Join-Path $env:RUNNER_TEMP 'sudoku-smoke-stdout.txt'
  $stderr = Join-Path $env:RUNNER_TEMP 'sudoku-smoke-stderr.txt'
  $child = $null
  try {
    $child = Start-Process -FilePath $exe -ArgumentList @('-c', ('"' + $file + '"')) `
      -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
      $child.Refresh()
      if ($child.HasExited) { throw 'Sudoku core exited before local SOCKS readiness' }
      $socket = [System.Net.Sockets.TcpClient]::new()
      try {
        $connection = $socket.BeginConnect('127.0.0.1', $localPort, $null, $null)
        if (!$connection.AsyncWaitHandle.WaitOne(200)) { continue }
        $socket.EndConnect($connection)
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
      } catch {
        # Startup race: retry while the child remains running.
      } finally {
        $socket.Dispose()
      }
      Start-Sleep -Milliseconds 150
    }
    if (!$ready) { throw 'Sudoku core did not expose a live loopback SOCKS5 listener' }
    Start-Sleep -Seconds 2
    $child.Refresh()
    if ($child.HasExited) { throw 'Sudoku core exited after SOCKS5 readiness' }
    Write-Host 'Official Sudoku core stayed alive with a synthetic local SOCKS5 listener'
  } finally {
    if ($null -ne $child) {
      try { if (!$child.HasExited) { $child.Kill() } } catch {}
      try { $child.WaitForExit(5000) | Out-Null } catch {}
      $child.Dispose()
    }
    Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
  }
} finally {
  Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue
}
Write-Host 'Official Sudoku CLI accepts synthetic client config'
