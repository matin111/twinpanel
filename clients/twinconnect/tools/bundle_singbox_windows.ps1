# Bundles a pinned, SHA-256 verified upstream sing-box for the Windows
# preview. An engine binary alone does not enable protocols: the native
# tunnel lifecycle and secure secret handling must be implemented separately.
$ErrorActionPreference = 'Stop'
$version = '1.14.4'
$archiveName = "sing-box-$version-windows-amd64.zip"
$source = "https://github.com/SagerNet/sing-box/releases/download/v$version/$archiveName"
$sha256 = '99185d75d314a07dbba4a130c8ad986cbeb629a07927975636b341ca61f991df'
$release = Join-Path (Get-Location) 'build/windows/x64/runner/Release'
$destination = Join-Path $release 'engines/sing-box'
$work = Join-Path $env:RUNNER_TEMP "twinconnect-singbox-$version"
$archive = Join-Path $work $archiveName
New-Item -ItemType Directory -Path $work -Force | Out-Null
Invoke-WebRequest -Uri $source -OutFile $archive -MaximumRedirection 5
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $sha256) { throw 'Sing-box archive SHA256 mismatch' }
$extract = Join-Path $work 'unpacked'
Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force
$matches = @(Get-ChildItem -LiteralPath $extract -Filter 'sing-box.exe' -Recurse -File)
if ($matches.Count -ne 1) { throw 'Expected exactly one official sing-box.exe' }
$binary = $matches[0]
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -LiteralPath $binary.FullName -Destination (Join-Path $destination 'sing-box.exe') -Force
$versionOutput = & (Join-Path $destination 'sing-box.exe') version
if ($LASTEXITCODE -ne 0 -or !(($versionOutput -join ' ') -match '1\.14\.4')) {
  throw 'Bundled sing-box version mismatch'
}
$license = @(Get-ChildItem -LiteralPath $extract -Recurse -File |
  Where-Object { $_.Name -match '^(LICENSE|COPYING)(\..+)?$' } |
  Select-Object -First 1)
if ($license.Count -gt 0) {
  Copy-Item -LiteralPath $license[0].FullName -Destination (Join-Path $destination 'LICENSE') -Force
}
Set-Content -LiteralPath (Join-Path $destination 'SOURCE.txt') -Encoding UTF8 -Value @(
  "sing-box $version - upstream GPL-3.0-or-later component",
  "Upstream: https://github.com/SagerNet/sing-box",
  "Release: $source",
  "Archive SHA256: $sha256",
  "Bundled for upcoming native engine integration; no tunnel support claimed"
)
Write-Host 'Pinned sing-box engine staged into Windows release directory'
