# Smoke-test the exact bundled sing-box engine with synthetic credentials.
# Never use real subscription profiles in CI logs or temporary test files.
$ErrorActionPreference = 'Stop'
$release = Join-Path (Get-Location) 'build/windows/x64/runner/Release'
$engine = Join-Path $release 'engines/sing-box/sing-box.exe'
if (!(Test-Path -LiteralPath $engine)) { throw 'sing-box engine missing' }
$profiles = @(
  @{ type = 'hysteria2'; password = 'synthetic'; tls = @{ enabled = $true; server_name = 'vpn.example.org' } },
  @{ type = 'tuic'; uuid = '2DD61D93-75D8-4DA4-AC0E-6AECE7EAC365'; password = 'synthetic'; tls = @{ enabled = $true; server_name = 'vpn.example.org' } },
  @{ type = 'anytls'; password = 'synthetic'; tls = @{ enabled = $true; server_name = 'vpn.example.org' } },
  @{ type = 'naive'; username = 'synthetic'; password = 'synthetic'; tls = @{ enabled = $true; server_name = 'vpn.example.org' } },
  @{ type = 'snell'; version = 4; psk = 'synthetic' },
  @{ type = 'socks'; username = 'synthetic'; password = 'synthetic' }
)
foreach ($outbound in $profiles) {
  $protocol = $outbound.type
  $outbound.tag = 'proxy'
  $outbound.server = 'vpn.example.org'
  $outbound.server_port = 443
  $sample = @{
    log = @{ level = 'error'; timestamp = $true }
    dns = @{
      servers = @(@{ type = 'udp'; tag = 'dns-remote'; server = '1.1.1.1'; server_port = 53; detour = 'proxy' })
      final = 'dns-remote'
      cache_capacity = 4096
      optimistic = $true
    }
    inbounds = @(@{
      type = 'tun'; tag = 'twinconnect-tun'; interface_name = 'TwinConnectSB'
      address = @('172.19.0.1/30','fdfe:dcba:9876::1/126')
      mtu = 1400; auto_route = $true; strict_route = $true; dns_mode = 'hijack'
    })
    outbounds = @($outbound)
    route = @{ auto_detect_interface = $true; final = 'proxy'; rules = @(@{ action = 'sniff' }) }
  }
  $json = $sample | ConvertTo-Json -Depth 30
  $json | & $engine check -c stdin
  if ($LASTEXITCODE -ne 0) { throw "sing-box stdin config check failed: $protocol" }
  Write-Host "Synthetic sing-box config valid: $protocol"
}
