#Requires -RunAsAdministrator
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('Install','Uninstall')]
  [string]$Action,
  [Parameter(Mandatory=$true)]
  [string]$BinaryPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$name = 'TwinConnectGuardDiagnostic'
$path = [IO.Path]::GetFullPath($BinaryPath)
$root = [IO.Path]::GetFullPath($env:ProgramFiles).TrimEnd('\') + '\'
if (!$path.StartsWith($root,[StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetFileName($path) -ne 'TwinConnectGuardDiagnostic.exe') {
  throw 'Invalid diagnostic service executable path.'
}
function Get-GuardService { Get-CimInstance Win32_Service -Filter "Name='TwinConnectGuardDiagnostic'" }
if ($Action -eq 'Install') {
  if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Diagnostic service binary missing.' }
  $svc = Get-GuardService
  $expected = '"' + $path + '" service'
  if ($svc -and ($svc.PathName -ine $expected -or
       $svc.StartName -notin @('LocalSystem','NT AUTHORITY\SYSTEM'))) {
    throw 'Conflicting service with same name; refusing replacement.'
  }
  if (!$svc) {
    New-Service -Name $name -BinaryPathName $expected -DisplayName 'TwinConnect Guard Installation Diagnostic' -StartupType Manual | Out-Null
  }
  Start-Service -Name $name -ErrorAction Stop
  if ((Get-Service $name).Status -ne 'Running') { throw 'Diagnostic service did not start.' }
  Write-Output 'DIAGNOSTIC_SERVICE_RUNNING_NO_FIREWALL_FILTERS'
} else {
  $svc = Get-GuardService
  if (!$svc) { exit 0 }
  $expected = '"' + $path + '" service'
  if ($svc.PathName -ine $expected) { throw 'Service path mismatch; refusing to remove unrelated service.' }
  if ((Get-Service $name).Status -ne 'Stopped') { Stop-Service -Name $name -ErrorAction Stop }
  & sc.exe delete $name | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Diagnostic service deletion failed.' }
  Write-Output 'DIAGNOSTIC_SERVICE_UNINSTALLED'
}
