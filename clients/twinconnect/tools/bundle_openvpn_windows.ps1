# Vendor-signed OpenVPN Community MSI is included inside TwinConnect Setup.
# Customers never need a separate download or installation step.
$ErrorActionPreference = 'Stop'
$url = 'https://build.openvpn.net/downloads/releases/OpenVPN-2.7.9-I001-amd64.msi'
$release = Join-Path (Get-Location) 'build/windows/x64/runner/Release'
$destination = Join-Path $release 'prerequisites'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$msi = Join-Path $destination 'OpenVPN-2.7.9-I001-amd64.msi'
Invoke-WebRequest -Uri $url -OutFile $msi -MaximumRedirection 3 -TimeoutSec 120
$size = (Get-Item -LiteralPath $msi).Length
if ($size -lt 5MB -or $size -gt 12MB) { throw 'Unexpected OpenVPN vendor MSI size' }
$signature = Get-AuthenticodeSignature -LiteralPath $msi
if ($signature.Status -ne 'Valid' -or !$signature.SignerCertificate -or
    $signature.SignerCertificate.Subject -notmatch 'OpenVPN') {
  throw "OpenVPN vendor Authenticode signature invalid ($($signature.Status))"
}
$hash = (Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash.ToLowerInvariant()
if ($env:TWINCONNECT_OPENVPN_SHA256) {
  if ($hash -ne $env:TWINCONNECT_OPENVPN_SHA256.ToLowerInvariant()) {
    throw 'OpenVPN official vendor MSI SHA256 mismatch'
  }
}
Set-Content -LiteralPath (Join-Path $destination 'OPENVPN-SOURCE.txt') -Encoding UTF8 -Value @(
  'OpenVPN Community 2.7.9 x64 vendor-signed MSI'
  "Upstream: $url"
  "SHA256: $hash"
  "Authenticode: $($signature.SignerCertificate.Subject)"
  'MSI is installed during TwinConnect Setup with administrator privileges.'
  'No network fetch occurs during customer installation.'
)
Write-Host "OpenVPN Community signed MSI verified: $hash"
