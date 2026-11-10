# Smoke-test the exact bundled sing-box engine with synthetic credentials.
# Never use real subscription profiles in CI logs or temporary test files.
$ErrorActionPreference = 'Stop'
$release = Join-Path (Get-Location) 'build/windows/x64/runner/Release'
$engine = Join-Path $release 'engines/sing-box/sing-box.exe'
if (!(Test-Path -LiteralPath $engine)) { throw 'sing-box engine missing' }
$config = Join-Path $env:RUNNER_TEMP 'twinconnect-singbox-synthetic-check.json'
$sample = @{
  log = @{ level = 'error'; timestamp = $true }
  dns = @{
    servers = @(@{ type = 'udp'; tag = 'dns-remote'; server = '1.1.1.1'; server_port = 53; detour = 'proxy' })
    final = 'dns-remote'
  }
  inbounds = @(@{
    type = 'tun'; tag = 'twinconnect-tun'; interface_name = 'TwinConnectSB'
    address = @('172.19.0.1/30','fdfe:dcba:9876::1/126')
    mtu = 1400; auto_route = $true; strict_route = $true; dns_mode = 'hijack'
  })
  outbounds = @(@{
    type = 'hysteria2'; tag = 'proxy'; server = 'vpn.example.org'; server_port = 443
    password = 'synthetic-not-real'; tls = @{ enabled = $true; server_name = 'vpn.example.org' }
  })
  route = @{ auto_detect_interface = $true; final = 'proxy'; rules = @(@{ action = 'sniff' }) }
}
$sample | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $config -Encoding utf8
try {
  & $engine check -c $config
  if ($LASTEXITCODE -ne 0) { throw "sing-box check failed: $LASTEXITCODE" }
} finally {
  Remove-Item -LiteralPath $config -Force -ErrorAction SilentlyContinue
}
Write-Host 'Synthetic Windows TUN sing-box config was accepted by bundled engine'
