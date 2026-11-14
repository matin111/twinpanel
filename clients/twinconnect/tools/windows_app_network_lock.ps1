# Picker and status run without UAC. Changing persistent WFP rules requires Administrator.
# Application-scoped WFP VPN bypass guard. Blocks connections outside
# TwinConnect's verified tunnel while retaining tunneled connectivity.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('Pick','Status','Lock','Unlock')]
  [string]$Action,
  [string]$Executable = '',
  [string]$ElevationReceipt = ''
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
# Chromium and other per-user Windows applications frequently install
# under LocalAppData. Permit these executable paths too.
if ($env:LOCALAPPDATA) {
  $roots += [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\') + '\'
}
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
if ($Action -eq 'Pick') {
  Write-Output ('TWINCONNECT_PICKED ' + $path)
  exit 0
}
$binary = Join-Path $PSScriptRoot '..\services\TwinConnectAppKillSwitch.exe'
$binary = [IO.Path]::GetFullPath($binary)
if (!(Test-Path -LiteralPath $binary -PathType Leaf)) { throw 'APP_WFP_ENGINE_NOT_INSTALLED' }

# A selected-app WFP filter needs an active, recognizable TwinConnect TUN.
# Check this BEFORE displaying UAC; proxy-only connections have no such
# interface and cannot safely be guarded by interface-based filters.
$tunnel = $null
if ($Action -eq 'Lock') {
  $tunnel = @('TwinConnectSB','TwinConnect') | Where-Object {
    $adapter = Get-NetAdapter -Name $_ -ErrorAction SilentlyContinue
    $adapter -and $adapter.Status -eq 'Up' -and !$adapter.HardwareInterface
  } | Select-Object -First 1
  if (!$tunnel) {
    throw 'APP_WFP_NO_TUN_INTERFACE_CONNECT_VPN_FIRST'
  }
}

# Windows desktop app is not normally elevated. Ask Windows for consent
# ONLY for the requested Lock/Unlock; never elevate file selection or status.
if ($Action -in @('Lock','Unlock')) {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ($ElevationReceipt) { throw 'APP_WFP_ELEVATION_LOOP' }
    $receipt = Join-Path ([IO.Path]::GetTempPath()) ('twinconnect-wfp-' + [guid]::NewGuid().ToString('N') + '.txt')
    try {
      # Windows file names cannot contain quotation marks. Pass quoted paths
      # as separate arguments to the signed-in Windows PowerShell process.
      $elevationArguments = @(
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', ('"' + $PSCommandPath + '"'),
        '-Action', $Action,
        '-Executable', ('"' + $path + '"'),
        '-ElevationReceipt', ('"' + $receipt + '"')
      )
      $child = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $elevationArguments -Verb RunAs -Wait -PassThru -ErrorAction Stop
      if ($child.ExitCode -ne 0) { throw 'APP_WFP_ELEVATED_COMMAND_FAILED' }
      if (!(Test-Path -LiteralPath $receipt -PathType Leaf)) { throw 'APP_WFP_ELEVATED_RECEIPT_MISSING' }
      $answer = (Get-Content -LiteralPath $receipt -Raw -ErrorAction Stop).Trim()
      $expected = if ($Action -eq 'Lock') { 'TWINCONNECT_APP_LOCKED' } else { 'TWINCONNECT_APP_UNLOCKED' }
      if ($answer -cne $expected) { throw 'APP_WFP_ELEVATED_RECEIPT_INVALID' }
      # Independent read-only WFP recheck prevents a stale/spoofed receipt
      # from being treated as success, including when UAC was cancelled.
      $verified = (& $binary status $path 2>$null | Out-String).Trim()
      if ($LASTEXITCODE -ne 0 -or $verified -cne $expected) {
        throw 'APP_WFP_ELEVATED_STATUS_UNVERIFIED'
      }
      Write-Output $expected
      exit 0
    } finally {
      Remove-Item -LiteralPath $receipt -Force -ErrorAction SilentlyContinue
    }
  }
}

if ($Action -eq 'Status') {
  $output = & $binary status $path 2>&1
} elseif ($Action -eq 'Unlock') {
  $output = & $binary disarm $path 2>&1
} else {
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
if ($ElevationReceipt) {
  # The unelevated parent validates this receipt against native WFP status.
  [IO.File]::WriteAllText($ElevationReceipt, $result, [Text.Encoding]::UTF8)
}
Write-Output $result
