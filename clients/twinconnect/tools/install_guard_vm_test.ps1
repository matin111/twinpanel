#Requires -RunAsAdministrator
# Isolated Windows virtual-machine acceptance build. Firewall starts OFF.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('Install','Uninstall')]
  [string]$Action,
  [Parameter(Mandatory=$true)][string]$BinaryPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$name = 'TwinConnectGlobalGuard'
$exe = [IO.Path]::GetFullPath($BinaryPath)
$root = [IO.Path]::GetFullPath($env:ProgramFiles).TrimEnd('\') + '\'
if (!$exe.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetFileName($exe) -ine 'TwinConnectGlobalGuard.exe') {
  throw 'VM guard executable must be installed under Program Files.'
}
# Never install this unsigned acceptance build on real hardware.
$computer = Get-CimInstance Win32_ComputerSystem
$identity = ($computer.Manufacturer + ' ' + $computer.Model)
if ($env:TWINCONNECT_DISPOSABLE_VM -ne '1' -or
    $identity -notmatch '(virtual|vmware|virtualbox|kvm|qemu|hyper-v|xen|parallels)') {
  throw 'VM_ONLY: set TWINCONNECT_DISPOSABLE_VM=1 inside a disposable Windows VM.'
}
if (!(Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Guard executable missing.' }
function GuardService { Get-CimInstance Win32_Service -Filter "Name='TwinConnectGlobalGuard'" }
$svc = GuardService
$expected = '"' + $exe + '" service'
if ($Action -eq 'Install') {
  if ($svc) {
    if ($svc.PathName -ine $expected -or
        $svc.StartName -notin @('LocalSystem', 'NT AUTHORITY\SYSTEM')) {
      throw 'Another service owns the guard name. Refusing replacement.'
    }
  } else {
    & $exe install-vm 'I_ACCEPT_OFFLINE_RECOVERY'
    if ($LASTEXITCODE -ne 0) { throw 'VM guard registration failed.' }
  }
  Start-Service -Name $name -ErrorAction Stop
  $status = & $exe status
  if ($LASTEXITCODE -ne 0 -or $status -notmatch '^OK 0 0 0') {
    throw 'Guard service unavailable or WFP rules unexpectedly armed.'
  }
  Write-Output 'VM_TEST_SERVICE_READY_WFP_OFF'
} else {
  & $exe recover 'I_ACCEPT_OFFLINE_RECOVERY' | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Independent WFP recovery failed.' }
  $audit = & $exe offline-status
  if ($LASTEXITCODE -ne 0 -or $audit -notmatch '^OWNED_RULES_PRESENT 0 0 0') {
    throw 'Owned WFP filters remain; refusing uninstall.'
  }
  if ($svc) {
    if ($svc.PathName -ine $expected) { throw 'Service identity mismatch.' }
    if ((Get-Service $name).Status -ne 'Stopped') { Stop-Service $name -ErrorAction Stop }
    & sc.exe delete $name | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to remove VM guard service.' }
  }
  Write-Output 'VM_TEST_GUARD_RECOVERED_UNINSTALLED'
}
