# Extract the optional CLI component from a signature- and hash-verified
# upstream OpenConnect-GUI installer, not the default silent install layout.
$ErrorActionPreference = 'Stop'
$release = Join-Path (Get-Location) 'build/windows/x64/runner/Release'
$vendor = Join-Path $release 'prerequisites/openconnect-gui-1.6.2-win64.exe'
$destination = Join-Path $release 'engines/openconnect'
$sevenZip = @(
  (Join-Path $env:ProgramFiles '7-Zip/7z.exe'),
  'C:/Program Files (x86)/7-Zip/7z.exe'
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (!$sevenZip) { throw '7-Zip missing from Windows runner' }
if (!(Test-Path -LiteralPath $vendor)) { throw 'Verified vendor installer missing' }
if (Test-Path -LiteralPath $destination) {
  Remove-Item -LiteralPath $destination -Recurse -Force
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
& $sevenZip x '-y' "-o$destination" $vendor | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Vendor archive extraction failed: $LASTEXITCODE" }
$files = @(Get-ChildItem -LiteralPath $destination -Recurse -File)
$cli = @($files | Where-Object { $_.Name -ieq 'openconnect.exe' })
if ($cli.Count -ne 1) {
  $relevant = @($files | Where-Object { $_.Name -match 'openconnect|vpnc-script' } |
      Select-Object -ExpandProperty Name -Unique)
  Write-Host "Upstream archive entries: $($relevant -join ', ')"
  throw "Expected exactly one upstream openconnect.exe, found $($cli.Count)"
}
$scripts = @($files | Where-Object {
  $_.Name -ieq 'vpnc-script-win.js' -or $_.Name -ieq 'vpnc-script.js'
})
if (!$scripts) { throw 'OpenConnect Windows routing/DNS script missing' }
$relativeCli = [IO.Path]::GetRelativePath($destination, $cli[0].FullName)
$relativeScript = [IO.Path]::GetRelativePath($destination, $scripts[0].FullName)
if ($relativeCli.StartsWith('..') -or $relativeScript.StartsWith('..')) {
  throw 'Unexpected archive path traversal'
}
$check = & $cli[0].FullName --version 2>&1 | Select-Object -First 4
if ($LASTEXITCODE -ne 0) { throw "Bundled CLI cannot run: $check" }
@(
  'Vendor: signed and checksum-verified OpenConnect-GUI 1.6.2',
  "CLI: $relativeCli",
  "Windows route script: $relativeScript",
  "Files: $($files.Count)",
  'Native Cisco routing, connection and safe teardown remain disabled pending tests.'
) | Set-Content -LiteralPath (Join-Path $destination 'OPENCONNECT-ENGINE-MANIFEST.txt') -Encoding UTF8
Write-Host "OpenConnect engine verified: $relativeCli"
Write-Host "OpenConnect script present: $relativeScript"
