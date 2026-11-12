# Bundle the independent, upstream mieru Windows client binary.
# Binaries are not silently substituted with sing-box or third-party DLLs.
$ErrorActionPreference = 'Stop'
$version = '3.39.0'
$archiveName = "mieru_${version}_windows_amd64.zip"
# The official v3.39.0 release publishes a SHA256 manifest beside its
# immutable versioned archive. Do not hard-code an unverified guess.
$url = "https://github.com/enfein/mieru/releases/download/v$version/$archiveName"
$manifestUrl = "$url.sha256.txt"
$dest = Join-Path (Get-Location) 'build/windows/x64/runner/Release/engines/mieru'
$work = Join-Path $env:RUNNER_TEMP "twinconnect-mieru-$version"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$archive = Join-Path $work $archiveName
$manifest = Join-Path $work "$archiveName.sha256.txt"
Invoke-WebRequest -Uri $manifestUrl -OutFile $manifest -TimeoutSec 90
$manifestText = (Get-Content -LiteralPath $manifest -Raw).Trim()
$expectedPattern = '^([a-fA-F0-9]{64})\s+\*?' + [regex]::Escape($archiveName) + '$'
if ($manifestText -notmatch $expectedPattern) {
  throw 'Official Mieru release checksum manifest is missing or malformed'
}
$expected = $Matches[1].ToLowerInvariant()
Invoke-WebRequest -Uri $url -OutFile $archive -TimeoutSec 90
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Mieru archive SHA256 differs from upstream release checksum' }
$unpacked = Join-Path $work 'unpacked'
Expand-Archive -LiteralPath $archive -DestinationPath $unpacked -Force
$executables = @(Get-ChildItem -LiteralPath $unpacked -Recurse -File |
    Where-Object { $_.Name -ieq 'mieru.exe' })
if ($executables.Count -ne 1) { throw 'Mieru archive must contain exactly one client executable' }
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -LiteralPath $executables[0].FullName -Destination (Join-Path $dest 'mieru.exe') -Force
# Source is the official GPLv3 file already tracked for other native cores.
$license = Join-Path (Get-Location) 'licenses/GPL-3.0.txt'
if (!(Test-Path $license)) { throw 'GPLv3 license missing from checkout' }
Copy-Item -LiteralPath $license -Destination (Join-Path $dest 'GPL-3.0.txt') -Force
Set-Content -LiteralPath (Join-Path $dest 'SOURCE.txt') -Encoding UTF8 -Value @(
    'Official enfein/mieru independent Windows client, GPL-3.0',
    "Release: $url",
    "Archive SHA256 (upstream manifest): $expected",
    'Client mode only. A verified SOCKS5-to-TUN bridge is required for VPN.'
)
Write-Host 'Version-fixed official Mieru Windows core and upstream SHA256 verified'

if ($manifestText -notmatch $expectedPattern) {
  throw 'Official Mieru release checksum manifest is missing or malformed'
}
$expected = $Matches[1].ToLowerInvariant()
Invoke-WebRequest -Uri $url -OutFile $archive -TimeoutSec 90
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Mieru archive SHA256 differs from upstream release checksum' }
$unpacked = Join-Path $work 'unpacked'
Expand-Archive -LiteralPath $archive -DestinationPath $unpacked -Force
$executables = @(Get-ChildItem -LiteralPath $unpacked -Recurse -File |
    Where-Object { $_.Name -ieq 'mieru.exe' })
if ($executables.Count -ne 1) { throw 'Mieru archive must contain exactly one client executable' }
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -LiteralPath $executables[0].FullName -Destination (Join-Path $dest 'mieru.exe') -Force
# Source is the official GPLv3 file already tracked for other native cores.
$license = Join-Path (Get-Location) 'licenses/GPL-3.0.txt'
if (!(Test-Path $license)) { throw 'GPLv3 license missing from checkout' }
Copy-Item -LiteralPath $license -Destination (Join-Path $dest 'GPL-3.0.txt') -Force
Set-Content -LiteralPath (Join-Path $dest 'SOURCE.txt') -Encoding UTF8 -Value @(
    'Official enfein/mieru independent Windows client, GPL-3.0',
    "Release: $url",
    "Archive SHA256: $expected",
    'Client mode only. A verified SOCKS5-to-TUN bridge is required for VPN.'
)
Write-Host 'Pinned independent mieru Windows core packaged successfully'
