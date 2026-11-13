#Requires -RunAsAdministrator
# EXPERIMENTAL: only on disposable Windows VM with offline console access.
# Never invoked by normal Windows preview / production app startup.
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$GuardExe,
  [Parameter(Mandatory)][ValidateSet("TwinConnectSB","TwinConnect")][string]$TunnelAlias,
  [Parameter(Mandatory)][string]$VpnEndpointIpv4,
  [Parameter(Mandatory)][string]$TransportExe,
  [Parameter(Mandatory)][string]$PhysicalIpv4,
  [Parameter(Mandatory)][string]$PhysicalIpv6,
  [switch]$DisposableVmOnly,
  [switch]$IHaveOfflineConsoleRecovery
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ack = "I_ACCEPT_OFFLINE_RECOVERY"
$task = "TwinConnectWfpEmergencyRestore"
$recovered = $false

if (!$DisposableVmOnly -or !$IHaveOfflineConsoleRecovery -or
    $env:TWINCONNECT_DISPOSABLE_VM -ne "1") {
  throw "WFP packet test prohibited outside a disposable VM."
}
if (!(Test-Path -LiteralPath $GuardExe -PathType Leaf) -or
    !(Test-Path -LiteralPath $TransportExe -PathType Leaf)) {
  throw "Service or VPN executable missing."
}
$service = Get-Service -Name "TwinConnectGlobalGuard" -ErrorAction Stop
if ($service.Status -ne "Running") { throw "Guard service is not running." }
if (!(Get-NetAdapter -InterfaceAlias $TunnelAlias -ErrorAction SilentlyContinue)) {
  throw "TwinConnect tunnel adapter not present."
}
foreach ($source in @($PhysicalIpv4, $PhysicalIpv6)) {
  $binding = Get-NetIPAddress -IPAddress $source -ErrorAction SilentlyContinue
  if (!$binding -or $binding.InterfaceAlias -eq $TunnelAlias) {
    throw "Physical source missing or belongs to tunnel: $source"
  }
}
$endpoint = [System.Net.IPAddress]::None
if (![System.Net.IPAddress]::TryParse($VpnEndpointIpv4, [ref]$endpoint) -or
    $endpoint.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
  throw "Numeric IPv4 endpoint required."
}

function Test-Physical-Egress {
  param([string]$SourceAddress,[string]$RemoteAddress="1.1.1.1",
        [int]$Port=443,[int]$TimeoutMs=3500)
  $sourceIp = [System.Net.IPAddress]::Parse($SourceAddress)
  $remoteIp = [System.Net.IPAddress]::Parse($RemoteAddress)
  if ($sourceIp.AddressFamily -ne $remoteIp.AddressFamily) {
    throw "Source and destination have different IP families."
  }
  $socket = [System.Net.Sockets.Socket]::new(
    $sourceIp.AddressFamily,
    [System.Net.Sockets.SocketType]::Stream,
    [System.Net.Sockets.ProtocolType]::Tcp)
  try {
    $socket.Bind([System.Net.IPEndPoint]::new($sourceIp, 0))
    $async = $socket.BeginConnect($RemoteAddress, $Port, $null, $null)
    if (!$async.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
    try { $socket.EndConnect($async); return $true }
    catch { return $false }
  } finally {
    $socket.Dispose()
  }
}

if (!(Test-Physical-Egress -SourceAddress $PhysicalIpv4)) {
  throw "Physical IPv4 baseline already blocked; test would be inconclusive."
}
if (!(Test-Physical-Egress -SourceAddress $PhysicalIpv6 -RemoteAddress "2606:4700:4700::1111")) {
  throw "Physical IPv6 baseline already blocked; test would be inconclusive."
}
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2)
$action = New-ScheduledTaskAction -Execute $GuardExe -Argument ("recover " + $ack)
Register-ScheduledTask -TaskName $task -Trigger $trigger -Action $action -User "SYSTEM" -RunLevel Highest -Force | Out-Null
try {
  $check = Get-ScheduledTask -TaskName $task -ErrorAction Stop
  if ($check.State -eq "Disabled") { throw "Emergency task disabled." }
  & $GuardExe arm $TunnelAlias $VpnEndpointIpv4 $TransportExe $ack
  if ($LASTEXITCODE -ne 0) { throw "Guard arm failed." }
  $status = & $GuardExe status
  if ($LASTEXITCODE -ne 0 -or $status -notmatch "OK 1 1 1") {
    throw "Dual-stack WFP filters were not reported installed."
  }
  if (Test-Physical-Egress -SourceAddress $PhysicalIpv4) {
    throw "PRIVACY FAILURE: direct physical IPv4 TCP egress still works."
  }
  if (Test-Physical-Egress -SourceAddress $PhysicalIpv6 -RemoteAddress "2606:4700:4700::1111") {
    throw "PRIVACY FAILURE: direct physical IPv6 TCP egress still works."
  }
  Write-Host "PASS: direct physical IPv4 and IPv6 TCP blocked inside VM."
} finally {
  & $GuardExe recover $ack
  $recovered = $LASTEXITCODE -eq 0
  if ($recovered) {
    Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
  } else {
    Write-Warning "Recovery failed. Independent scheduled restore remains registered."
  }
}
if (!$recovered) { throw "Emergency recovery failed." }
Write-Host "TwinConnect-owned WFP rules were removed."
# Partial test only: DNS, UDP/QUIC, crash/reboot, route transitions and
# every protocol must pass separate tests before release.
