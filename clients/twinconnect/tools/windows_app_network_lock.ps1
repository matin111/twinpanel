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
# Never replace or delete a rule owned by another program or app.
$sha = [Security.Cryptography.SHA256]::Create()
try {
  $hash = ([BitConverter]::ToString($sha.ComputeHash(
    [Text.Encoding]::UTF8.GetBytes($path.ToUpperInvariant())))).Replace('-','')
} finally { $sha.Dispose() }
$ruleName = 'TwinConnect-AppKillSwitch-' + $hash.Substring(0,24)
if ($Action -eq 'Pick') {
  Write-Output ('TWINCONNECT_PICKED ' + $path)
  exit 0
}
$rules = @(Get-NetFirewallRule -Name $ruleName -PolicyStore PersistentStore -ErrorAction SilentlyContinue)
if ($rules.Count -gt 1) { throw 'DUPLICATE_RULE_CONFLICT' }
$existing = if ($rules.Count -eq 1) { $rules[0] } else { $null }
if ($existing) {
  $appFilter = $existing | Get-NetFirewallApplicationFilter
  if (!$appFilter -or $appFilter.Program -ine $path -or
      $existing.Direction -ne 'Outbound' -or $existing.Action -ne 'Block' -or
      $existing.Enabled -ne 'True') { throw 'RULE_OWNER_MISMATCH' }
}
if ($Action -eq 'Lock' -and !$existing) {
  New-NetFirewallRule -Name $ruleName -DisplayName ('TwinConnect Kill Switch: ' + [IO.Path]::GetFileNameWithoutExtension($path)) -Description 'Explicitly selected application; blocks outbound traffic until disabled.' -Direction Outbound -Action Block -Profile Any -Enabled True -Program $path -PolicyStore PersistentStore | Out-Null
}
if ($Action -eq 'Unlock' -and $existing) {
  Remove-NetFirewallRule -Name $ruleName -PolicyStore PersistentStore -ErrorAction Stop
}
$after = @(Get-NetFirewallRule -Name $ruleName -PolicyStore PersistentStore -ErrorAction SilentlyContinue)
if ($Action -eq 'Lock' -and $after.Count -ne 1) { throw 'APP_LOCK_NOT_VERIFIED' }
if ($Action -eq 'Unlock' -and $after.Count -ne 0) { throw 'APP_UNLOCK_NOT_VERIFIED' }
if ($Action -eq 'Status' -and $after.Count -gt 1) { throw 'APP_STATUS_CONFLICT' }
if ($after.Count -gt 0) {
  Write-Output 'TWINCONNECT_APP_LOCKED'
} else {
  Write-Output 'TWINCONNECT_APP_UNLOCKED'
}
