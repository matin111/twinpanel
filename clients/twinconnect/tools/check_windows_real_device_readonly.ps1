# Read-only preflight for testing TwinConnect on an actual Windows device.
# Safe to run on a daily-use PC: does not create firewall rules, install
# drivers/services, or activate the experimental WFP guard.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$report = [ordered]@{
  schema = 1
  preflightOnly = $true
  firewallChanged = $false
  supportedOS = $false
  isAdministrator = $false
  guardServiceInstalled = $false
  guardServiceRunning = $false
  twinConnectAdapter = $false
  twinConnectSBAdapter = $false
  physicalIPv4Present = $false
  physicalIPv6Present = $false
  activeDefaultIPv4Route = $false
  activeDefaultIPv6Route = $false
  safeToArmOnThisMachine = $false
  nextStep = 'DO_NOT_ARM_EXPERIMENTAL_GUARD_ON_DAILY_USE_WINDOWS'
}
try {
  $report.supportedOS = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT -and
      [Environment]::OSVersion.Version.Major -ge 10
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($id)
  $report.isAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  $service = Get-Service -Name 'TwinConnectGlobalGuard' -ErrorAction SilentlyContinue
  if ($null -ne $service) {
    $report.guardServiceInstalled = $true
    $report.guardServiceRunning = $service.Status -eq 'Running'
  }
  $adapters = @(Get-NetAdapter -ErrorAction Stop)
  foreach ($adapter in $adapters) {
    if ($adapter.Name -eq 'TwinConnect') { $report.twinConnectAdapter = $true }
    if ($adapter.Name -eq 'TwinConnectSB') { $report.twinConnectSBAdapter = $true }
  }
  $physical = @($adapters | Where-Object {
    $_.Status -eq 'Up' -and $_.HardwareInterface -eq $true -and
    $_.Name -notin @('TwinConnect','TwinConnectSB')
  })
  foreach ($adapter in $physical) {
    $addresses = @(Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -ErrorAction SilentlyContinue)
    if ($addresses | Where-Object { $_.AddressFamily -eq 'IPv4' -and
        $_.IPAddress -notlike '169.254.*' }) { $report.physicalIPv4Present = $true }
    if ($addresses | Where-Object { $_.AddressFamily -eq 'IPv6' -and
        $_.IPAddress -notlike 'fe80:*' }) { $report.physicalIPv6Present = $true }
  }
  $routes = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0','::/0' -ErrorAction SilentlyContinue)
  $report.activeDefaultIPv4Route = [bool]($routes | Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' })
  $report.activeDefaultIPv6Route = [bool]($routes | Where-Object { $_.DestinationPrefix -eq '::/0' })
} catch {
  $report.nextStep = 'PREFLIGHT_INCOMPLETE_READONLY_DIAGNOSTICS_FAILED'
}
# Explicitly not a certification: persistent WFP policies can lock out users
# even with a scheduled recovery task. Requires separate test hardware,
# console access, tested recovery media, and a signed production service.
$report | ConvertTo-Json -Depth 3
