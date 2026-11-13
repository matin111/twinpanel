$ErrorActionPreference = 'Stop'
# Exact stable upstream version. Verify the official GitHub release SHA256
# digest as well as the expected archive name before copying any executable.
$version = 'v1.1.11'
$assetName = "trusttunnel_client-$version-windows-x86_64.zip"
$headers = @{
  'Accept' = 'application/vnd.github+json'
  'User-Agent' = 'TwinConnect-Windows-Build'
  'X-GitHub-Api-Version' = '2022-11-28'
}
# Authenticated GitHub Actions requests use a higher API quota. Fail closed
# without weakening the release tag or SHA256 verification.
if (![string]::IsNullOrWhiteSpace($env:GH_TOKEN)) {
  $headers['Authorization'] = "Bearer $env:GH_TOKEN"
}
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/TrustTunnel/TrustTunnelClient/releases/tags/$version" -Headers $headers -TimeoutSec 90
if ($release.tag_name -ne $version -or $release.draft -eq $true) {
  throw 'Official TrustTunnel version verification failed'
}
$matches = @($release.assets | Where-Object { $_.name -ceq $assetName })
if ($matches.Count -ne 1) { throw 'Official TrustTunnel x86_64 asset is missing or ambiguous' }
$asset = $matches[0]
if ($asset.digest -notmatch '^sha256:([a-fA-F0-9]{64})$') {
  throw 'Official TrustTunnel release asset lacks a SHA256 digest'
}
$expected = $Matches[1].ToLowerInvariant()
if ($asset.size -lt 1000000 -or $asset.size -gt 300000000) {
  throw 'Official TrustTunnel archive size is unexpected'
}
$work = Join-Path $env:RUNNER_TEMP 'twinconnect-trusttunnel-v1.1.11'
New-Item -ItemType Directory -Force $work | Out-Null
$archive = Join-Path $work $assetName
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $archive -TimeoutSec 120
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Official TrustTunnel archive checksum mismatch' }
$unpacked = Join-Path $work 'unpacked'
Expand-Archive -LiteralPath $archive -DestinationPath $unpacked -Force
$exe = @(Get-ChildItem -LiteralPath $unpacked -Recurse -File |
  Where-Object { $_.Name -ieq 'trusttunnel_client.exe' })
if ($exe.Count -ne 1) { throw 'Official TrustTunnel client executable missing or ambiguous' }
$dest = Join-Path (Get-Location) 'build/windows/x64/runner/Release/engines/trusttunnel'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -LiteralPath $exe[0].FullName -Destination (Join-Path $dest 'trusttunnel_client.exe') -Force
$license = Join-Path (Get-Location) 'licenses/TRUSTTUNNEL-LICENSE.txt'
if (!(Test-Path $license)) { throw 'TrustTunnel Apache-2.0 license missing' }
Copy-Item $license -Destination (Join-Path $dest 'LICENSE.txt')
$source = @(
  'Official TrustTunnel/TrustTunnelClient Apache-2.0 Windows client',
  "Release tag: $version",
  "Release archive: $assetName",
  "Archive SHA256: $expected",
  'Bundled as independent SOCKS5-only client; never install a second TUN.'
)
Set-Content -LiteralPath (Join-Path $dest 'SOURCE.txt') -Value $source -Encoding UTF8
Write-Host 'Official TrustTunnel CLI packaged with GitHub release SHA256 verified'
