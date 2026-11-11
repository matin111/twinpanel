# Run a synthetic TUN only on the disposable GitHub Windows runner.
# auto_route=false/dns_mode=disabled: never alter machine-wide routing or DNS.
# No subscription credentials are used.
$ErrorActionPreference = 'Stop'
$exe = Join-Path (Get-Location) 'build/windows/x64/runner/Release/engines/sing-box/sing-box.exe'
if (!(Test-Path -LiteralPath $exe)) { throw 'Missing packaged sing-box engine' }
$probeName = 'TwinConnectCI'
$config = Join-Path $env:RUNNER_TEMP 'twinconnect-ci-tun.json'
@{
  log = @{ level = 'error' }
  inbounds = @(@{
    type = 'tun'
    tag = 'ci-tun'
    interface_name = $probeName
    address = @('198.18.201.1/30')
    mtu = 1400
    auto_route = $false
    strict_route = $false
    dns_mode = 'disabled'
  })
  outbounds = @(@{ type = 'direct'; tag = 'direct' })
  route = @{ final = 'direct' }
} | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $config -Encoding UTF8
$p = $null
try {
  & $exe check -c $config
  if ($LASTEXITCODE -ne 0) { throw 'Synthetic TUN config validation failed' }
  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $exe
  $psi.ArgumentList.Add('run')
  $psi.ArgumentList.Add('-c')
  $psi.ArgumentList.Add($config)
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $p = [System.Diagnostics.Process]::Start($psi)
  $present = $false
  for ($i = 0; $i -lt 20; $i++) {
    if ($p.HasExited) { throw "sing-box TUN child exited ($($p.ExitCode))" }
    $adapter = Get-NetAdapter -Name $probeName -ErrorAction SilentlyContinue
    if ($null -ne $adapter) { $present = $true; break }
    Start-Sleep -Milliseconds 500
  }
  if (!$present) { throw 'TUN adapter was not created by engine' }
  Write-Host 'Actual Windows TUN adapter created successfully (no automatic routes/DNS)'
} finally {
  if ($p -and !$p.HasExited) {
    $p.Kill()
    [void]$p.WaitForExit(5000)
  }
  Remove-Item -LiteralPath $config -Force -ErrorAction SilentlyContinue
}
