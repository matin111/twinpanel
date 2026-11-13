#Requires -RunAsAdministrator
<#
  Installer bridge for a future CERTIFIED TwinConnectGlobalGuard service.
  The regular Windows preview does not include this script or the service.
  Installer flag IncludeVerifiedGlobalGuard must remain OFF until guard
  signature, native bridge, packet leak tests and recovery are verified.
  Installation NEVER arms firewall filters.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [ValidateSet('Install','Uninstall')]
  [string]$Action,
  [Parameter(Mandatory)]
  [string]$BinaryPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$name = 'TwinConnectGlobalGuard'
$ack = 'I_ACCEPT_OFFLINE_RECOVERY'
$logDir = Join-Path $env:ProgramData 'TwinConnect'
New-Item -Path $logDir -ItemType Directory -Force | Out-Null

function Invoke-Guard {
  param([string[]]$Arguments)
  & $BinaryPath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Guard rejected command: $($Arguments[0])"
  }
}

function Service-Exists {
  return [bool](Get-Service -Name $name -ErrorAction SilentlyContinue)
}

$binary = [System.IO.Path]::GetFullPath($BinaryPath)
$programFiles = [System.IO.Path]::GetFullPath($env:ProgramFiles).TrimEnd('\') + '\'
if (!$binary.StartsWith($programFiles, [StringComparison]::OrdinalIgnoreCase)) {
  throw 'Guard must be installed under protected Program Files.'
}
if (!(Test-Path -LiteralPath $binary -PathType Leaf)) {
  throw 'Bundled global guard binary is missing.'
}
$signature = Get-AuthenticodeSignature -LiteralPath $binary
if ($signature.Status -ne 'Valid') {
  throw 'Unsigned or untrusted guard service refused.'
}
if ($Action -eq 'Install') {
  if (!(Service-Exists)) {
    # Service API stays OFF during installation; never silently enforce filters.
    & sc.exe create $name binPath= ('"' + $binary + '" service') start= auto obj= LocalSystem
    if ($LASTEXITCODE -ne 0) { throw 'Could not register guard Windows service.' }
  }
  & sc.exe config $name start= auto
  if ($LASTEXITCODE -ne 0) { throw 'Could not configure automatic service startup.' }
  Start-Service -Name $name -ErrorAction Stop
  $service = Get-Service -Name $name -ErrorAction Stop
  if ($service.Status -ne 'Running') { throw 'Global guard service did not start.' }
  Write-Output 'Verified service installed and running; blocking remains disabled.'
} else {
  # The independent recovery command must work before service removal.
  Invoke-Guard -Arguments @('recover', $ack)
  $status = & $binary status
  if ($LASTEXITCODE -ne 0 -or $status -notmatch 'OK 0 0 0') {
    throw 'Owned WFP filters still present. Refusing to uninstall.'
  }
  if (Service-Exists) {
    Stop-Service -Name $name -Force -ErrorAction Stop
    & sc.exe delete $name
    if ($LASTEXITCODE -ne 0) { throw 'SCM service deletion failed.' }
  }
  Write-Output 'Owned filters recovered and service removed.'
}
