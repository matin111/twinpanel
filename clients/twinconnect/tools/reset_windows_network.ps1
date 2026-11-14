#Requires -RunAsAdministrator
# User-initiated Windows network recovery. Never called automatically by Setup.
[CmdletBinding()]
param([switch]$GuardOnly)
$ErrorActionPreference = 'Stop'
$logDirectory = Join-Path $env:ProgramData 'TwinConnect'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$log = Join-Path $logDirectory 'network-reset.log'
function Log([string]$message) { Add-Content -LiteralPath $log -Value ("$(Get-Date -Format o) " + $message) }
try {
  Log 'User confirmed Windows network reset.'
  # Attempt recovery of ONLY TwinConnect-owned persistent WFP filters first.
  # Resetting Winsock does not remove WFP filters. Never reset the whole
  # Windows Firewall or delete rules belonging to unrelated applications.
  $guard = Join-Path $env:ProgramFiles 'TwinConnect\services\TwinConnectGlobalGuard.exe'
  $service = Get-Service -Name 'TwinConnectGlobalGuard' -ErrorAction SilentlyContinue
  if ((Test-Path -LiteralPath $guard -PathType Leaf) -or $service) {
    if (!(Test-Path -LiteralPath $guard -PathType Leaf)) {
      throw 'GUARD_SERVICE_PRESENT_BUT_RECOVERY_BINARY_MISSING'
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $guard
    if ($signature.Status -ne 'Valid') {
      throw 'GUARD_RECOVERY_BINARY_NOT_SIGNED_OR_TRUSTED'
    }
    # Independent CLI works even if the service/pipe is stopped.
    & $guard recover 'I_ACCEPT_OFFLINE_RECOVERY' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'GUARD_WFP_RECOVERY_FAILED' }
    $audit = & $guard offline-status
    if ($LASTEXITCODE -ne 0 -or
        $audit -notmatch '^OWNED_RULES_PRESENT 0 0 0') {
      throw 'GUARD_OWNED_FILTERS_STILL_PRESENT'
    }
    Log 'Verified no TwinConnect-owned WFP filters remain.'
  } else {
    if ($GuardOnly) { throw 'GUARD_SERVICE_NOT_INSTALLED' }
    Log 'No installed TwinConnect guard; WFP recovery not applicable.'
  }
  if ($GuardOnly) {
    Log 'User requested Kill Switch emergency recovery only.'
    Write-Output 'TWINCONNECT_GUARD_RECOVERY_OK'
    exit 0
  }
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
