# Bundle the official, signed upstream OpenConnect-GUI installer alongside
# TwinConnect. No network downloads occur on the customer's PC.
# The included upstream installer provides openconnect.exe, its crypto DLLs,
# Windows route script, and TAP driver when selected by its vendor package.
$ErrorActionPreference = 'Stop'
$version = '1.6.2'
$source = "https://www.infradead.org/openconnect-gui/download/openconnect-gui-$version-win64.exe"
$release = Join-Path (Get-Location) 'build/windows/x64/runner/Release'
$destination = Join-Path $release 'prerequisites'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$installer = Join-Path $destination 'openconnect-gui-1.6.2-win64.exe'
Invoke-WebRequest -Uri $source -OutFile $installer -MaximumRedirection 3 -TimeoutSec 90
$size = (Get-Item -LiteralPath $installer).Length
if ($size -lt 5MB -or $size -gt 100MB) { throw 'Unexpected upstream OpenConnect installer size' }
$auth = Get-AuthenticodeSignature -LiteralPath $installer
if ($auth.Status -ne 'Valid' -or !$auth.SignerCertificate) {
  throw "OpenConnect upstream installer signature is not valid: $($auth.Status)"
}
# A pinned hash can be configured in the build environment after the vendor's
# release hash is independently confirmed. Any mismatch aborts publication.
$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
if ($env:TWINCONNECT_OPENCONNECT_SHA256) {
  if ($hash -ne $env:TWINCONNECT_OPENCONNECT_SHA256.ToLowerInvariant()) {
    throw 'Pinned OpenConnect upstream installer SHA-256 mismatch'
  }
}
Set-Content -LiteralPath (Join-Path $destination 'OPENCONNECT-SOURCE.txt') -Encoding UTF8 -Value @(
  "OpenConnect-GUI $version (upstream installer)",
  "Upstream: $source",
  "SHA256: $hash",
  "Authenticode thumbprint: $($auth.SignerCertificate.Thumbprint)",
  'License: GPL-2.0; preserve upstream source and notices',
  'User installation is performed by TwinConnect Setup, not by the customer',
  'TwinConnect must not claim Cisco is functional until the native lifecycle and route checks pass'
)
Write-Host "Verified upstream OpenConnect signed installer SHA256: $hash"
