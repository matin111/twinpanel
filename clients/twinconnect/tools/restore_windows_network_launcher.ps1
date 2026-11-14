# TwinConnect emergency network reset entry point.
# Available from the Start Menu even when the Flutter app cannot start.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$restore = Join-Path $PSScriptRoot 'reset_windows_network.ps1'
if (!(Test-Path -LiteralPath $restore -PathType Leaf)) {
  Write-Host 'TwinConnect network recovery script is missing.' -ForegroundColor Red
  Read-Host 'Press Enter to close'
  exit 1
}
$current = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($current)
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  try {
    $args = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
    $p = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $args -Verb RunAs -Wait -PassThru
    exit $p.ExitCode
  } catch {
    Write-Host ('Administrator permission was not granted: ' + $_.Exception.Message) -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
  }
}
Write-Host 'TwinConnect - Restore Windows network' -ForegroundColor Cyan
Write-Host 'This can disconnect your VPN and resets DNS, Winsock and TCP/IP.'
$yes = Read-Host 'Type RESET to proceed'
if ($yes -cne 'RESET') { Write-Host 'Cancelled.'; exit 0 }
& $restore
$code = $LASTEXITCODE
if ($code -eq 0) {
  Write-Host 'Network reset completed. Restart Windows to finish.' -ForegroundColor Green
} else {
  Write-Host 'Reset could not be verified. Review C:\ProgramData\TwinConnect\network-reset.log' -ForegroundColor Red
}
Read-Host 'Press Enter to close'
exit $code
