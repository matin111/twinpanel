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
$restored = $false
$taskRegistered = $false

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
$physicalBindings = @{}
foreach ($source in @($PhysicalIpv4, $PhysicalIpv6)) {
  $binding = @(Get-NetIPAddress -IPAddress $source -ErrorAction SilentlyContinue)
  if ($binding.Count -ne 1 -or $binding[0].InterfaceAlias -eq $TunnelAlias -or
      $binding[0].InterfaceIndex -le 0) {
    throw "Physical source missing, ambiguous or belongs to tunnel: $source"
  }
  $physicalBindings[$source] = [int]$binding[0].InterfaceIndex
}
$physicalV4Index = $physicalBindings[$PhysicalIpv4]
$physicalV6Index = $physicalBindings[$PhysicalIpv6]
$endpoint = [System.Net.IPAddress]::None
if (![System.Net.IPAddress]::TryParse($VpnEndpointIpv4, [ref]$endpoint) -or
    $endpoint.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
  throw "Numeric IPv4 endpoint required."
}

# Binding an IP address alone does NOT prove that packets went out of the
# physical interface. Select the outgoing NIC explicitly using the Windows
# IP_UNICAST_IF / IPV6_UNICAST_IF option. If unsupported, fail the test.
function Set-Physical-Interface {
  param([System.Net.Sockets.Socket]$Socket, [int]$InterfaceIndex)
  if ($InterfaceIndex -le 0) { throw "Invalid physical interface index." }
  $option = [System.Net.Sockets.SocketOptionName]31
  if ($Socket.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork) {
    $index = [System.Net.IPAddress]::HostToNetworkOrder($InterfaceIndex)
    $Socket.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::IP,
        $option, $index)
  } elseif ($Socket.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetworkV6) {
    $Socket.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::IPv6,
        $option, $InterfaceIndex)
  } else {
    throw "Unsupported physical interface address family."
  }
}

function Test-Physical-Egress {
  param([string]$SourceAddress,[string]$RemoteAddress="1.1.1.1",
        [int]$Port=443,[int]$TimeoutMs=3500,
        [int]$InterfaceIndex)
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
    Set-Physical-Interface -Socket $socket -InterfaceIndex $InterfaceIndex
    $socket.Bind([System.Net.IPEndPoint]::new($sourceIp, 0))
    $async = $socket.BeginConnect($RemoteAddress, $Port, $null, $null)
    if (!$async.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
    try { $socket.EndConnect($async); return $true }
    catch { return $false }
  } finally {
    $socket.Dispose()
  }
}

# Send a real uncached DNS query directly through the physical source,
# bypassing the Windows resolver/cache. UDP "send succeeded" is never counted
# as egress: a matching DNS response is required.
function Test-Physical-Dns {
  param([string]$SourceAddress, [string]$RemoteAddress,
        [int]$TimeoutMs=3500, [int]$InterfaceIndex)
  $source = [System.Net.IPAddress]::Parse($SourceAddress)
  $remote = [System.Net.IPAddress]::Parse($RemoteAddress)
  if ($source.AddressFamily -ne $remote.AddressFamily) {
    throw "DNS source/destination IP family mismatch."
  }
  $udp = [System.Net.Sockets.UdpClient]::new(
    [System.Net.IPEndPoint]::new($source, 0))
  try {
    Set-Physical-Interface -Socket $udp.Client -InterfaceIndex $InterfaceIndex
    $udp.Client.ReceiveTimeout = $TimeoutMs
    $id = [byte[]]::new(2)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($id)
    # DNS header: id, recursion desired, one question.
    $packet = [System.Collections.Generic.List[byte]]::new()
    $packet.AddRange($id)
    $packet.AddRange([byte[]]@(0x01,0x00,0x00,0x01,0x00,0x00,0x00,0x00,0x00,0x00))
    # Random query name avoids cached local resolver replies.
    $label = 'tc' + [Guid]::NewGuid().ToString('N').Substring(0,12)
    foreach ($part in @($label,'example','com')) {
      $packet.Add([byte]$part.Length)
      $packet.AddRange([System.Text.Encoding]::ASCII.GetBytes($part))
    }
    $packet.AddRange([byte[]]@(0x00,0x00,0x01,0x00,0x01))
    $query = $packet.ToArray()
    $remoteEndpoint = [System.Net.IPEndPoint]::new($remote,53)
    [void]$udp.Send($query, $query.Length, $remoteEndpoint)
    $sender = [System.Net.IPEndPoint]::new(
      [System.Net.IPAddress]::Any, 0)
    if ($source.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetworkV6) {
      $sender = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::IPv6Any,0)
    }
    $reply = $udp.Receive([ref]$sender)
    return $reply.Length -ge 12 -and
      $sender.Address.Equals($remote) -and
      $reply[0] -eq $id[0] -and $reply[1] -eq $id[1] -and
      ($reply[2] -band 0x80) -ne 0
  } catch [System.Net.Sockets.SocketException] {
    return $false
  } finally {
    $udp.Dispose()
  }
}

if (!(Test-Physical-Egress -SourceAddress $PhysicalIpv4 -InterfaceIndex $physicalV4Index)) {
  throw "Physical IPv4 baseline already blocked; test would be inconclusive."
}
if (!(Test-Physical-Egress -SourceAddress $PhysicalIpv6 -InterfaceIndex $physicalV6Index -RemoteAddress "2606:4700:4700::1111")) {
  throw "Physical IPv6 baseline already blocked; test would be inconclusive."
}
if (!(Test-Physical-Dns -SourceAddress $PhysicalIpv4 -InterfaceIndex $physicalV4Index -RemoteAddress "1.1.1.1")) {
  throw "Direct IPv4 DNS baseline unavailable; cannot prove DNS protection."
}
if (!(Test-Physical-Dns -SourceAddress $PhysicalIpv6 -InterfaceIndex $physicalV6Index -RemoteAddress "2606:4700:4700::1111")) {
  throw "Direct IPv6 DNS baseline unavailable; cannot prove DNS protection."
}
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2)
$action = New-ScheduledTaskAction -Execute $GuardExe -Argument ("recover " + $ack)
# Run missed emergency recovery as soon as Windows is booted again. A
# snapshot/reboot must not leave persistent WFP filters stranded indefinitely.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
Register-ScheduledTask -TaskName $task -Trigger $trigger -Action $action -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
$taskRegistered = $true
try {
  $check = Get-ScheduledTask -TaskName $task -ErrorAction Stop
  if ($check.State -eq "Disabled" -or !$check.Settings.StartWhenAvailable) {
    throw "Emergency task must be enabled and recover after reboot."
  }
  & $GuardExe arm $TunnelAlias $VpnEndpointIpv4 $TransportExe $ack
  if ($LASTEXITCODE -ne 0) { throw "Guard arm failed." }
  $status = & $GuardExe status
  if ($LASTEXITCODE -ne 0 -or $status -notmatch "OK 1 1 1") {
    throw "Dual-stack WFP filters were not reported installed."
  }
  if (Test-Physical-Egress -SourceAddress $PhysicalIpv4 -InterfaceIndex $physicalV4Index) {
    throw "PRIVACY FAILURE: direct physical IPv4 TCP egress still works."
  }
  if (Test-Physical-Egress -SourceAddress $PhysicalIpv6 -InterfaceIndex $physicalV6Index -RemoteAddress "2606:4700:4700::1111") {
    throw "PRIVACY FAILURE: direct physical IPv6 TCP egress still works."
  }
  if (Test-Physical-Dns -SourceAddress $PhysicalIpv4 -InterfaceIndex $physicalV4Index -RemoteAddress "1.1.1.1") {
    throw "PRIVACY FAILURE: IPv4 DNS UDP leaked outside tunnel."
  }
  if (Test-Physical-Dns -SourceAddress $PhysicalIpv6 -InterfaceIndex $physicalV6Index -RemoteAddress "2606:4700:4700::1111") {
    throw "PRIVACY FAILURE: IPv6 DNS UDP leaked outside tunnel."
  }
  Write-Host "PASS: direct IPv4/IPv6 TCP and DNS UDP blocked inside VM."
} finally {
  & $GuardExe recover $ack
  $recovered = $LASTEXITCODE -eq 0
  if ($recovered) {
    # The recovery CLI returning success is not sufficient. Query raw filter
    # ownership, then prove both original physical routes can connect again.
    $rawStatus = & $GuardExe offline-status
    $recovered = $LASTEXITCODE -eq 0 -and
        ($rawStatus -match 'OWNED_RULES_PRESENT 0 0 0')
    if ($recovered) {
      for ($attempt = 0; $attempt -lt 4 -and !$restored; $attempt++) {
        $v4Restored = Test-Physical-Egress -SourceAddress $PhysicalIpv4 -InterfaceIndex $physicalV4Index
        $v6Restored = Test-Physical-Egress -SourceAddress $PhysicalIpv6 -InterfaceIndex $physicalV6Index -RemoteAddress "2606:4700:4700::1111"
        $dns4Restored = Test-Physical-Dns -SourceAddress $PhysicalIpv4 -InterfaceIndex $physicalV4Index -RemoteAddress "1.1.1.1"
        $dns6Restored = Test-Physical-Dns -SourceAddress $PhysicalIpv6 -InterfaceIndex $physicalV6Index -RemoteAddress "2606:4700:4700::1111"
        $restored = $v4Restored -and $v6Restored -and
            $dns4Restored -and $dns6Restored
        if (!$restored) { Start-Sleep -Seconds 2 }
      }
    }
  }
  if ($recovered -and $restored) {
    Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
    $taskRegistered = $false
  } else {
    Write-Warning "Connectivity was not fully restored. Independent SYSTEM emergency task remains registered."
  }
}
if (!$recovered -or !$restored) {
  throw "Recovery was not verified: both physical IPv4 and IPv6 must work again."
}
Write-Host "PASS: TwinConnect-owned WFP rules removed and both physical networks restored."
# Partial test only: DNS, UDP/QUIC, crash/reboot, route transitions and
# every protocol must pass separate tests before release.
