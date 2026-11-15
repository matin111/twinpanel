$ErrorActionPreference = 'Stop'
# Include official AmneziaWG as an integrated Windows prerequisite.
# The version and asset name are pinned, checksum comes from GitHub's
# release asset digest and is checked before packaging the driver installer.
$tag = '3.1.0'
$name = 'amneziawg-amd64-3.1.0.msi'
$headers = @{
  Accept = 'application/vnd.github+json'
  'User-Agent' = 'TwinConnect-Windows-Builder'
}
$release = Invoke-RestMethod -Uri (
  'https://api.github.com/repos/amnezia-vpn/amneziawg-windows-client/releases/tags/' + $tag
) -Headers $headers -TimeoutSec 90
if ($release.tag_name -ne $tag -or $release.draft) {
  throw 'Official AmneziaWG release version mismatch'
}
$assets = @($release.assets | Where-Object { $_.name -ceq $name })
if ($assets.Count -ne 1) { throw 'Official AmneziaWG x64 MSI not found' }
$asset = $assets[0]
if ($asset.digest -notmatch '^sha256:([0-9a-fA-F]{64})$') {
  throw 'AmneziaWG release MSI is missing upstream SHA256 digest'
}
$expected = $Matches[1].ToLowerInvariant()
if ($asset.size -lt 1000000 -or $asset.size -gt 80000000) {
  throw 'Official AmneziaWG MSI size out of supported range'
}
$dir = Join-Path (Get-Location) 'build/windows/x64/runner/Release/prerequisites'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$path = Join-Path $dir $name
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $path -TimeoutSec 120
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'AmneziaWG installer SHA256 mismatch' }
$signature = Get-AuthenticodeSignature -LiteralPath $path
if ($signature.Status -eq 'Valid') {
  Write-Host 'Official AmneziaWG MSI Authenticode signature verified'
} else {
  Write-Host 'Installer has no valid Authenticode signature; GitHub release SHA256 was verified'
}
$source = @(
  'Official amnezia-vpn/amneziawg-windows-client 3.1.0',
  'License: GNU GPLv3; upstream: https://github.com/amnezia-vpn/amneziawg-windows-client',
  "SHA256 verified via GitHub release asset digest: $expected",
  'MSI installed only through the elevated TwinConnect setup process.'
)
Set-Content -LiteralPath (Join-Path $dir 'AMNEZIAWG-SOURCE.txt') -Encoding UTF8 -Value $source
Write-Host 'Verified official AmneziaWG MSI bundled with TwinConnect'
