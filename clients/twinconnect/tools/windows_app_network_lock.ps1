#Requires -RunAsAdministrator
# Selective Windows Firewall app lock; NOT a system-wide VPN Kill Switch.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('Status','Lock','Unlock')][string]$Action,
  [ValidateSet('Edge','Chrome','Firefox')][string]$Browser = 'Edge'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$program = @{}
$program['Edge'] = @(
  (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
  (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe')
)
$program['Chrome'] = @(
  (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
  (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe')
)
$program['Firefox'] = @(
  (Join-Path $env:ProgramFiles 'Mozilla Firefox\firefox.exe'),
  (Join-Path ${env:ProgramFiles(x86)} 'Mozilla Firefox\firefox.exe')
)
$found = @($program[$Browser] | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
if ($found.Count -eq 0) { throw 'BROWSER_NOT_INSTALLED_IN_TRUSTED_LOCATION' }
$path = [IO.Path]::GetFullPath([string]$found[0])
$rule = 'TwinConnect-AppLock-' + $Browser
$existing = Get-NetFirewallRule -Name $rule -PolicyStore PersistentStore -ErrorAction SilentlyContinue
if ($existing) {
  if (@($existing).Count -ne 1 -or $existing.Direction -ne 'Outbound' -or
      $existing.Action -ne 'Block' -or $existing.Enabled -ne 'True') {
    throw 'RULE_NAME_CONFLICT'
  }
  $filter = $existing | Get-NetFirewallApplicationFilter
  if (!$filter -or $filter.Program -ine $path) { throw 'RULE_OWNER_MISMATCH' }
}
if ($Action -eq 'Status') {
  if ($existing) { Write-Output "TWINCONNECT_APP_LOCKED $Browser" }
  else { Write-Output "TWINCONNECT_APP_UNLOCKED $Browser" }
  exit 0
}
if ($Action -eq 'Lock' -and !$existing) {
  New-NetFirewallRule -Name $rule -DisplayName "TwinConnect Browser Lock: $Browser" -Description 'Blocks all outbound browser connections until explicitly released in TwinConnect.' -Direction Outbound -Action Block -Profile Any -Enabled True -Program $path -PolicyStore PersistentStore | Out-Null
}
if ($Action -eq 'Unlock' -and $existing) {
  Remove-NetFirewallRule -Name $rule -PolicyStore PersistentStore -ErrorAction Stop
}
$result = Get-NetFirewallRule -Name $rule -PolicyStore PersistentStore -ErrorAction SilentlyContinue
if ($Action -eq 'Lock' -and !$result) { throw 'FIREWALL_BLOCK_NOT_VERIFIED' }
if ($Action -eq 'Unlock' -and $result) { throw 'FIREWALL_RESTORE_NOT_VERIFIED' }
Write-Output $(if ($Action -eq 'Lock') { "TWINCONNECT_APP_LOCKED $Browser" } else { "TWINCONNECT_APP_UNLOCKED $Browser" })
