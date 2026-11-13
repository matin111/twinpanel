#Requires -RunAsAdministrator
# Certified Windows guard installer contract. Not enabled in public setup until
# real leak/recovery acceptance and signed service release are complete.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('Install','Uninstall')]
  [string]$Action,
  [Parameter(Mandatory=$true)]
  [string]$BinaryPath,
  [Parameter(Mandatory=$true)]
  [ValidatePattern('^[A-Fa-f0-9]{40}$')]
  [string]$ExpectedSignerThumbprint
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$name = 'TwinConnectGlobalGuard'
$ack = 'I_ACCEPT_OFFLINE_RECOVERY'
$binary = [System.IO.Path]::GetFullPath($BinaryPath)
$prefix = [System.IO.Path]::GetFullPath($env:ProgramFiles).TrimEnd('\') + '\'

function Test-ServicePresent {
  return [bool](Get-Service -Name $name -ErrorAction SilentlyContinue)
}

function Assert-ServiceIdentity {
  if (!(Test-ServicePresent)) { throw 'Guard service is not registered.' }
  $svc = Get-CimInstance Win32_Service -Filter "Name='TwinConnectGlobalGuard'"
  $expected = '"' + $binary + '" service'
  if (!$svc -or $svc.PathName -ine $expected -or
      $svc.StartName -notin @('LocalSystem','NT AUTHORITY\SYSTEM')) {
    throw 'Installed service path or identity does not match the signed guard.'
  }
}

if (!$binary.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw 'Guard binary must be in protected Program Files.'
}
if (!(Test-Path -LiteralPath $binary -PathType Leaf)) {
  throw 'Guard executable is missing.'
}
$signature = Get-AuthenticodeSignature -LiteralPath $binary
if ($signature.Status -ne 'Valid' -or !$signature.SignerCertificate) {
  throw 'Unsigned or untrusted guard service refused.'
}
if ($signature.SignerCertificate.Thumbprint -ine $ExpectedSignerThumbprint) {
  throw 'Guard signing certificate differs from publisher pin.'
}

if ($Action -eq 'Install') {
  if (!(Test-ServicePresent)) {
    # Only start the service; never enable packet blocking during installation.
    & sc.exe create $name binPath= ('"' + $binary + '" service') start= auto obj= LocalSystem
    if ($LASTEXITCODE -ne 0) { throw 'SCM service creation failed.' }
  }
  Assert-ServiceIdentity
  & sc.exe config $name start= auto
  if ($LASTEXITCODE -ne 0) { throw 'SCM automatic-start configuration failed.' }
  $service = Get-Service -Name $name -ErrorAction Stop
  if ($service.Status -ne 'Running') {
    Start-Service -Name $name -ErrorAction Stop
  }
  $service = Get-Service -Name $name -ErrorAction Stop
  if ($service.Status -ne 'Running') { throw 'Guard service did not start.' }
  Assert-ServiceIdentity
  Write-Output 'Verified service installed and running; firewall blocking remains off.'
} else {
  # Recover directly against WFP even if the service or its named pipe crashed.
  & $binary recover $ack
  if ($LASTEXITCODE -ne 0) { throw 'WFP emergency recovery failed.' }
  $audit = & $binary offline-status
  if ($LASTEXITCODE -ne 0 -or $audit -notmatch 'OWNED_RULES_PRESENT 0 0 0') {
    throw 'Owned WFP filters still present. Refusing to uninstall.'
  }
  if (Test-ServicePresent) {
    Assert-ServiceIdentity
    $service = Get-Service -Name $name -ErrorAction Stop
    if ($service.Status -ne 'Stopped') {
      Stop-Service -Name $name -Force -ErrorAction Stop
    }
    & sc.exe delete $name
    if ($LASTEXITCODE -ne 0) { throw 'SCM service deletion failed.' }
  }
  Write-Output 'WFP rules recovered and service uninstalled.'
}
