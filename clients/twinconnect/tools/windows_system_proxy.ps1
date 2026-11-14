# TwinConnect WinINET proxy engine. Runs as the signed-in Windows user.
# Does not alter WinHTTP or VPN routes. Restores only settings it owns.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('Status','Enable','Disable')]
  [string]$Action,
  [ValidateRange(1025,65535)][int]$SocksPort = 1080
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$folder = Join-Path $env:LOCALAPPDATA 'TwinConnect'
$backup = Join-Path $folder 'system-proxy-original.json'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class TwinConnectWinInetNotify {
  [DllImport("wininet.dll", SetLastError=true)]
  public static extern bool InternetSetOptionW(IntPtr handle, int option, IntPtr buffer, int length);
  public static void Refresh() {
    if (!InternetSetOptionW(IntPtr.Zero, 39, IntPtr.Zero, 0)) throw new InvalidOperationException("WININET_SETTINGS_CHANGED_FAILED");
    if (!InternetSetOptionW(IntPtr.Zero, 37, IntPtr.Zero, 0)) throw new InvalidOperationException("WININET_REFRESH_FAILED");
  }
}
'@ -ErrorAction Stop

function Get-Values {
  $settings = Get-ItemProperty -LiteralPath $key -ErrorAction Stop
  $values = @{}
  foreach ($name in @('ProxyEnable','ProxyServer','ProxyOverride','AutoConfigURL')) {
    $entry = $settings.PSObject.Properties[$name]
    if ($null -eq $entry) {
      $values[$name] = @{exists=$false; value=$null}
    } else {
      $values[$name] = @{exists=$true; value=$entry.Value}
    }
  }
  return $values
}
function Restore-Values($values) {
  foreach ($name in @('ProxyEnable','ProxyServer','ProxyOverride','AutoConfigURL')) {
    $entry = $values[$name]
    if ($entry.exists -eq $true) {
      $propertyType = if ($name -eq 'ProxyEnable') {'DWord'} else {'String'}
      New-ItemProperty -LiteralPath $key -Name $name -PropertyType $propertyType -Value $entry.value -Force | Out-Null
    } else {
      Remove-ItemProperty -LiteralPath $key -Name $name -ErrorAction SilentlyContinue
    }
  }
  [TwinConnectWinInetNotify]::Refresh()
}
function Test-Socks($port) {
  $client = [Net.Sockets.TcpClient]::new()
  try {
    $task = $client.ConnectAsync('127.0.0.1', $port)
    if (!$task.Wait(1200)) { return $false }
    $stream = $client.GetStream()
    $stream.ReadTimeout = 1200
    $stream.WriteTimeout = 1200
    $stream.Write([byte[]](5,1,0), 0, 3)
    $reply = New-Object byte[] 2
    $count = $stream.Read($reply, 0, 2)
    return ($count -eq 2 -and $reply[0] -eq 5 -and $reply[1] -eq 0)
  } catch { return $false }
  finally { $client.Dispose() }
}

$values = Get-Values
$server = if ($values['ProxyServer'].exists) { [string]$values['ProxyServer'].value } else { '' }
$enabled = $values['ProxyEnable'].exists -and ([int]$values['ProxyEnable'].value -eq 1)
$owned = $enabled -and $server -match '^socks=127\.0\.0\.1:([0-9]{4,5})$' -and (Test-Path -LiteralPath $backup)
if ($Action -eq 'Status') {
  Write-Output $(if ($owned) { "TWINCONNECT_SYSTEM_PROXY_ON $($Matches[1])" } else { 'TWINCONNECT_SYSTEM_PROXY_OFF' })
  exit 0
}
if ($Action -eq 'Enable') {
  if ($owned) { throw 'TWINCONNECT_SYSTEM_PROXY_ALREADY_ACTIVE' }
  if (Test-Path -LiteralPath $backup) { throw 'PROXY_BACKUP_EXISTS_RESTORE_FIRST' }
  if (!(Test-Socks $SocksPort)) { throw 'LOCAL_SOCKS5_NOT_VERIFIED' }
  New-Item -ItemType Directory -Path $folder -Force | Out-Null
  $snapshot = @{version=1; port=$SocksPort; values=$values}
  $snapshot | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $backup -Encoding UTF8 -NoNewline
  try {
    New-ItemProperty -LiteralPath $key -Name ProxyEnable -PropertyType DWord -Value 1 -Force | Out-Null
    New-ItemProperty -LiteralPath $key -Name ProxyServer -PropertyType String -Value "socks=127.0.0.1:$SocksPort" -Force | Out-Null
    Remove-ItemProperty -LiteralPath $key -Name AutoConfigURL -ErrorAction SilentlyContinue
    [TwinConnectWinInetNotify]::Refresh()
    $applied = Get-Values
    if ([int]$applied['ProxyEnable'].value -ne 1 -or
        $applied['ProxyServer'].value -cne "socks=127.0.0.1:$SocksPort") {
      throw 'PROXY_ENABLE_NOT_VERIFIED'
    }
    Write-Output "TWINCONNECT_SYSTEM_PROXY_ON $SocksPort"
  } catch {
    try { Restore-Values $values } finally {
      Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    }
    throw
  }
  exit 0
}
if (!(Test-Path -LiteralPath $backup)) {
  if ($owned) { throw 'PROXY_BACKUP_MISSING' }
  Write-Output 'TWINCONNECT_SYSTEM_PROXY_OFF'
  exit 0
}
if (!$owned) { throw 'PROXY_SETTINGS_CHANGED_EXTERNALLY_DO_NOT_OVERWRITE' }
$snapshot = Get-Content -LiteralPath $backup -Raw | ConvertFrom-Json
if ($snapshot.version -ne 1 -or !$snapshot.values) { throw 'PROXY_BACKUP_INVALID' }
$original = @{}
foreach ($name in @('ProxyEnable','ProxyServer','ProxyOverride','AutoConfigURL')) {
  $entry = $snapshot.values.$name
  if ($null -eq $entry) { throw 'PROXY_BACKUP_INVALID' }
  $original[$name] = @{exists=[bool]$entry.exists; value=$entry.value}
}
Restore-Values $original
Remove-Item -LiteralPath $backup -Force -ErrorAction Stop
Write-Output 'TWINCONNECT_SYSTEM_PROXY_OFF'
