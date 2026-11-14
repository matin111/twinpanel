#Requires -RunAsAdministrator
# Application-scoped outbound internet block via Windows Defender Firewall.
# Blocks both direct and VPN traffic while enabled; not a VPN-drop-only Kill Switch.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('Pick','Status','Lock','Unlock')]
  [string]$Action,
  [string]$Executable = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($Action -eq 'Pick') {
  Add-Type -AssemblyName System.Windows.Forms
  $dialog = New-Object System.Windows.Forms.OpenFileDialog
  $dialog.Title = 'TwinConnect - Select an installed application'
  $dialog.Filter = 'Windows applications (*.exe)|*.exe'
  $dialog.CheckFileExists = $true
  $dialog.Multiselect = $false
  $dialog.InitialDirectory = $env:ProgramFiles
  try {
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
      Write-Output 'TWINCONNECT_PICK_CANCELLED'
      exit 0
    }
    $Executable = $dialog.FileName
  } finally {
    $dialog.Dispose()
  }
}
if ([string]::IsNullOrWhiteSpace($Executable)) { throw 'APP_EXECUTABLE_REQUIRED' }
$path = [IO.Path]::GetFullPath($Executable)
$roots = @([IO.Path]::GetFullPath($env:ProgramFiles).TrimEnd('\') + '\')
if (${env:ProgramFiles(x86)}) { $roots += [IO.Path]::GetFullPath(${env:ProgramFiles(x86)}).TrimEnd('\') + '\' }
$trusted = $false
foreach ($root in $roots) {
  if ($path.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) { $trusted = $true }
}
if (!$trusted -or [IO.Path]::GetExtension($path) -ine '.exe' -or
    !(Test-Path -LiteralPath $path -PathType Leaf)) { throw 'APP_MUST_BE_INSTALLED_IN_PROGRAM_FILES' }
# The native engine installs persistent IPv4/IPv6 WFP rules with BOTH:
# exact app identity AND interface != selected TwinConnect VPN interface.
# Unlike a generic Windows Firewall application block, traffic on the VPN
# interface remains allowed; direct traffic stays blocked on disconnect.
$binary = Join-Path $env:ProgramFiles 'TwinConnect\services\TwinConnectAppKillSwitch.exe'
if (!(Test-Path -LiteralPath $binary -PathType Leaf)) { throw 'APP_WFP_ENGINE_NOT_INSTALLED' }

if ($Action -eq 'Pick') {
  Write-Output ('TWINCONNECT_PICKED ' + $path)
  exit 0
}

if ($Action -eq 'Status') {
  $output = & $binary status $path 2>&1
} elseif ($Action -eq 'Unlock') {
  $output = & $binary disarm $path 2>&1
} else {
  $tunnel = @('TwinConnectSB','TwinConnect') | Where-Object {
    $adapter = Get-NetAdapter -Name $_ -ErrorAction SilentlyContinue
    $adapter -and $adapter.Status -eq 'Up' -and !$adapter.HardwareInterface
  } | Select-Object -First 1
  if (!$tunnel) { throw 'CONNECT_TO_TWINCONNECT_VPN_BEFORE_ENABLING_APP_KILL_SWITCH' }
  $output = & $binary arm $path $tunnel 2>&1
}
if ($LASTEXITCODE -ne 0) {
  throw ('APP_WFP_' + $Action.ToUpperInvariant() + '_FAILED: ' + ($output -join ' '))
}
$result = ($output -join '').Trim()
$expected = if ($Action -eq 'Unlock') { 'TWINCONNECT_APP_UNLOCKED' } else { 'TWINCONNECT_APP_LOCKED' }
if ($Action -eq 'Status') {
  if ($result -notin @('TWINCONNECT_APP_LOCKED','TWINCONNECT_APP_UNLOCKED')) {
    throw 'APP_WFP_STATUS_UNVERIFIED'
  }
} elseif ($result -cne $expected) { throw 'APP_WFP_STATUS_UNVERIFIED' }

# Migrate only our previous version's exact application block rule AFTER
# WFP protection is confirmed; otherwise it would still block tunneled traffic.
if ($Action -in @('Lock','Unlock')) {
  $sha = [Security.Cryptography.SHA256]::Create()
  try {
    $hash = ([BitConverter]::ToString($sha.ComputeHash(
      [Text.Encoding]::UTF8.GetBytes($path.ToUpperInvariant())))).Replace('-','')
  } finally { $sha.Dispose() }
  $oldRule = 'TwinConnect-AppKillSwitch-' + $hash.Substring(0,24)
  $legacy = @(Get-NetFirewallRule -Name $oldRule -PolicyStore PersistentStore -ErrorAction SilentlyContinue)
  if ($legacy.Count -eq 1 -and
      $legacy[0].Description -ceq 'Explicitly selected application; blocks outbound traffic until disabled.' -and
      $legacy[0].Action -eq 'Block' -and $legacy[0].Direction -eq 'Outbound') {
    $legacyApp = $legacy[0] | Get-NetFirewallApplicationFilter
    if ($legacyApp -and $legacyApp.Program -ieq $path) {
      Remove-NetFirewallRule -Name $oldRule -PolicyStore PersistentStore -ErrorAction Stop
    }
  }
}
Write-Output $result
