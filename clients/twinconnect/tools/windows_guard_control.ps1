#Requires -RunAsAdministrator
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('Arm','Disarm')][string]$Action,
  [ValidateSet('TwinConnectSB','TwinConnect')][string]$TunnelAlias = 'TwinConnect',
  [string]$EndpointIpv4 = '',
  [string]$TransportExe = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$guard = Join-Path $env:ProgramFiles 'TwinConnect\services\TwinConnectGlobalGuard.exe'
$ack = 'I_ACCEPT_OFFLINE_RECOVERY'
$task = 'TwinConnectWfpEmergencyRestore'
if (!(Test-Path -LiteralPath $guard -PathType Leaf)) { throw 'GUARD_NOT_INSTALLED' }
$signature = Get-AuthenticodeSignature -LiteralPath $guard
if ($signature.Status -ne 'Valid' -or !$signature.SignerCertificate) { throw 'SIGNED_GUARD_REQUIRED' }
if ($Action -eq 'Disarm') {
  & $guard recover $ack | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'GUARD_RECOVERY_FAILED' }
  $audit = & $guard offline-status
  if ($LASTEXITCODE -ne 0 -or $audit -notmatch 'OWNED_RULES_PRESENT 0 0 0') { throw 'GUARD_FILTERS_STILL_PRESENT' }
  Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
  Write-Output 'GUARD_DISARMED_VERIFIED'
  exit 0
}
if ((Get-Service TwinConnectGlobalGuard -ErrorAction Stop).Status -ne 'Running') { throw 'GUARD_SERVICE_NOT_RUNNING' }
$adapter = Get-NetAdapter -InterfaceAlias $TunnelAlias -ErrorAction Stop
if ($adapter.Status -ne 'Up' -or $adapter.HardwareInterface) { throw 'VPN_TUNNEL_NOT_ACTIVE' }
$parsed = [System.Net.IPAddress]::None
if (![System.Net.IPAddress]::TryParse($EndpointIpv4, [ref]$parsed) -or
    $parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { throw 'NUMERIC_IPV4_ENDPOINT_REQUIRED' }
$transport = [IO.Path]::GetFullPath($TransportExe)
$roots = @([IO.Path]::GetFullPath($env:ProgramFiles).TrimEnd('\') + '\')
if (\${env:ProgramFiles(x86)}) { $roots += [IO.Path]::GetFullPath(\${env:ProgramFiles(x86)}).TrimEnd('\') + '\' }
$trusted = $false
foreach ($root in $roots) { if ($transport.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { $trusted = $true } }
if (!$trusted -or !(Test-Path -LiteralPath $transport -PathType Leaf)) { throw 'TRUSTED_TRANSPORT_PATH_REQUIRED' }
# SYSTEM restores internet after two minutes even if the app crashes.
# Time-bounded test mode is not a permanent production Kill Switch.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2)
$recovery = New-ScheduledTaskAction -Execute $guard -Argument "recover $ack"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
Register-ScheduledTask -TaskName $task -Trigger $trigger -Action $recovery -Settings $settings -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
try {
  $status = & $guard arm $TunnelAlias $EndpointIpv4 $transport $ack
  if ($LASTEXITCODE -ne 0 -or $status -notmatch 'OK ARMED') { throw ('GUARD_ARM_REJECTED ' + $status) }
  $status = & $guard status
  if ($LASTEXITCODE -ne 0 -or $status -notmatch 'OK 1 1 1') { throw 'GUARD_FILTER_STATUS_UNVERIFIED' }
  Write-Output 'GUARD_ARMED_TWO_MINUTE_TEST'
} catch {
  & $guard recover $ack | Out-Null
  Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
  throw
}
