# Bundle pinned official Xray-core for Windows. Does not enable full VPN routing.
$ErrorActionPreference = 'Stop'
$version = '26.11.9'
$filename = 'Xray-windows-64.zip'
$expected = '1262522266337b824f07beb8e1375786b437683b3890105469088f8e17e0a69d'
$url = "https://github.com/XTLS/Xray-core/releases/download/v$version/$filename"
$release = Join-Path (Get-Location) 'build/windows/x64/runner/Release'
$destination = Join-Path $release 'engines/xray'
$work = Join-Path $env:RUNNER_TEMP "twinconnect-xray-$version"
$archive = Join-Path $work $filename
New-Item -ItemType Directory -Path $work -Force | Out-Null
Invoke-WebRequest -Uri $url -OutFile $archive -MaximumRedirection 5
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Xray-core archive checksum mismatch' }
$extract = Join-Path $work 'unpacked'
Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force
$matches = @(Get-ChildItem -LiteralPath $extract -Filter 'xray.exe' -Recurse -File)
if ($matches.Count -ne 1) { throw 'Expected exactly one official xray.exe' }
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -LiteralPath $matches[0].FullName -Destination (Join-Path $destination 'xray.exe') -Force
foreach ($name in @('geoip.dat', 'geosite.dat')) {
  $files = @(Get-ChildItem -LiteralPath $extract -Filter $name -Recurse -File)
  if ($files.Count -ne 1) { throw "Xray asset missing: $name" }
  Copy-Item -LiteralPath $files[0].FullName -Destination (Join-Path $destination $name) -Force
}
$exe = Join-Path $destination 'xray.exe'
$versionText = (& $exe version) -join ' '
if ($LASTEXITCODE -ne 0 -or $versionText -notmatch '26\.11\.9') { throw 'Xray version mismatch' }
Set-Content -LiteralPath (Join-Path $destination 'SOURCE.txt') -Encoding UTF8 -Value @(
  "XTLS Xray-core v$version",
  "Source: $url",
  "SHA256: $expected",
  'No system-wide VPN connectivity claimed by this binary bundle'
)
Write-Host 'Verified Xray-core staged'
