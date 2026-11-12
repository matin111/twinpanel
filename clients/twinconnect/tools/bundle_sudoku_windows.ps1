# Pin the official SUDOKU-ASCII Windows CLI core; independent of sing-box.
$ErrorActionPreference = 'Stop'
$version = 'v0.5.2-1'
$archiveName = 'sudoku-windows-amd64.zip'
$expected = '52051b7b30d6af66ee151d6a978fa20434edeb5eaaecc4c9bb27063bed33efe1'
$url = "https://github.com/SUDOKU-ASCII/sudoku/releases/download/$version/$archiveName"
$root = Join-Path (Get-Location) 'build/windows/x64/runner/Release/engines/sudoku'
$work = Join-Path $env:RUNNER_TEMP "twinconnect-sudoku-$version"
$archive = Join-Path $work $archiveName
New-Item -ItemType Directory -Force -Path $work | Out-Null
Invoke-WebRequest -Uri $url -OutFile $archive -MaximumRedirection 5
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($hash -ne $expected) { throw 'Official Sudoku core archive checksum mismatch' }
$unpack = Join-Path $work 'unpacked'
Expand-Archive -LiteralPath $archive -DestinationPath $unpack -Force
$matches = @(Get-ChildItem -LiteralPath $unpack -Recurse -File |
  Where-Object { $_.Name -ieq 'sudoku.exe' })
if ($matches.Count -ne 1) { throw 'Expected exactly one sudoku.exe' }
New-Item -ItemType Directory -Force -Path $root | Out-Null
Copy-Item -LiteralPath $matches[0].FullName -Destination (Join-Path $root 'sudoku.exe') -Force
# Ship the upstream GPL-3.0 license with this independent CLI executable.
$licenseUrl = 'https://raw.githubusercontent.com/SUDOKU-ASCII/sudoku/v0.5.2-1/LICENSE'
$upstreamLicense = Join-Path $root 'LICENSE.txt'
Invoke-WebRequest -Uri $licenseUrl -OutFile $upstreamLicense
# Upstream's LICENSE is a short GPLv3 copyright/exception notice (778 bytes),
# not the full FSF license text. Never reject it based on a 1000-byte minimum.
$notice = Get-Content -LiteralPath $upstreamLicense -Raw
if (!$notice -or
    !$notice.Contains('GNU General Public License') -or
    !$notice.Contains('Copyright (C) 2026')) {
  throw 'Sudoku upstream license notice missing or invalid'
}
# Keep the exact upstream notice, including its additional naming restriction,
# and distribute the full GPLv3 text alongside the binary.
$gplFile = Join-Path $root 'GPL-3.0.txt'
Invoke-WebRequest -Uri 'https://www.gnu.org/licenses/gpl-3.0.txt' -OutFile $gplFile
$gplText = Get-Content -LiteralPath $gplFile -Raw
if ($gplText.Length -lt 30000 -or
    !$gplText.Contains('GNU GENERAL PUBLIC LICENSE') -or
    !$gplText.Contains('Version 3, 29 June 2007')) {
  throw 'Official GPLv3 license text missing or invalid'
}
$exe = Join-Path $root 'sudoku.exe'
& $exe -h 2>&1 | Out-Null
# Golang flag -h normally exits with 0. Do not assume a version flag exists.
if ($LASTEXITCODE -ne 0) { throw "Sudoku executable self-check failed: $LASTEXITCODE" }
Set-Content -LiteralPath (Join-Path $root 'SOURCE.txt') -Encoding UTF8 -Value @(
  'SUDOKU-ASCII/sudoku official CLI, GPL-3.0',
  "Release: $url",
  "Archive SHA256: $expected",
  'Native Windows mixed SOCKS5 core. Full VPN requires separate TUN verification.'
)
Write-Host 'Pinned Sudoku core bundled successfully'
