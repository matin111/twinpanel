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
Write-Host 'TwinConnect - Restore Internet' -ForegroundColor Cyan
Write-Host '1 - Remove ONLY TwinConnect-owned WFP Kill Switch rules (no restart)'
Write-Host '2 - Remove Kill Switch rules and reset DNS/Winsock/TCP-IP (restart required)'
$choice = Read-Host 'Choose 1 or 2'
if ($choice -notin @('1','2')) { Write-Host 'Cancelled.'; exit 0 }
$yes = Read-Host 'Type RESET to confirm'
if ($yes -cne 'RESET') { Write-Host 'Cancelled.'; exit 0 }
if ($choice -eq '1') { & $restore -GuardOnly }
else { & $restore }
$code = $LASTEXITCODE
if ($code -eq 0) {
  if ($choice -eq '1') {
    Write-Host 'TwinConnect-owned WFP rules removed and independently verified.' -ForegroundColor Green
  } else {
    Write-Host 'Network reset completed. Restart Windows to finish.' -ForegroundColor Green
  }
} else {
  Write-Host 'Recovery could not be verified. Review C:\ProgramData\TwinConnect\network-reset.log' -ForegroundColor Red
}
Read-Host 'Press Enter to close'
exit $code
