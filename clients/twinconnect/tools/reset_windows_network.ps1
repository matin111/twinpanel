#Requires -RunAsAdministrator
# User-initiated Windows network recovery. Never called automatically by Setup.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$logDirectory = Join-Path $env:ProgramData 'TwinConnect'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$log = Join-Path $logDirectory 'network-reset.log'
function Log([string]$message) { Add-Content -LiteralPath $log -Value ("$(Get-Date -Format o) " + $message) }
try {
  Log 'User confirmed Windows network reset.'
  # These are Windows OS supported recovery operations. They do not remove
  # non-TwinConnect firewall rules, VPN profiles or saved account credentials.
  & "$env:SystemRoot\System32\ipconfig.exe" /flushdns | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'DNS_FLUSH_FAILED' }
  Log 'DNS resolver cache cleared.'
  & "$env:SystemRoot\System32\netsh.exe" winsock reset | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'WINSOCK_RESET_FAILED' }
  Log 'Winsock catalog reset.'
  & "$env:SystemRoot\System32\netsh.exe" int ip reset | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'TCPIP_RESET_FAILED' }
  Log 'TCP/IP reset requested. Windows restart required.'
  Write-Output 'NETWORK_RESET_OK_RESTART_REQUIRED'
  exit 0
} catch {
  Log ('NETWORK_RESET_FAILED ' + $_.Exception.Message)
  Write-Error $_.Exception.Message
  exit 1
}
