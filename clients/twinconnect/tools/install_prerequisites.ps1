# TwinConnect Windows prerequisite installer.
# Installs the verified official WireGuard client using the Windows package manager.
# Does not touch customer profiles, panel settings or VPN services.
$ErrorActionPreference = 'Stop'
$logPath = Join-Path $env:ProgramData 'TwinConnect\install-prerequisites.log'
New-Item -ItemType Directory -Force -Path (Split-Path $logPath) | Out-Null
function Write-Log([string]$message) {
  Add-Content -Path $logPath -Value ("$(Get-Date -Format o) $message")
}
try {
  $wireguard = Join-Path $env:ProgramFiles 'WireGuard\wireguard.exe'
  if (Test-Path $wireguard) {
    Write-Log 'Official WireGuard already installed. No changes.'
    exit 0
  }
  $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
  if (-not $winget) {
    Write-Log 'Windows Package Manager is unavailable; prerequisite could not be installed.'
    exit 2
  }
  Write-Log 'Installing official WireGuard.WireGuard via winget.'
  & $winget.Source install --id WireGuard.WireGuard --exact --source winget --silent --disable-interactivity --accept-package-agreements --accept-source-agreements 2>&1 | ForEach-Object { Write-Log "$_" }
  $code = $LASTEXITCODE
  if ($code -ne 0) {
    Write-Log "winget install failed: $code"
    exit 3
  }
  if (-not (Test-Path $wireguard)) {
    Write-Log 'Expected WireGuard executable was not found after install.'
    exit 4
  }
  Write-Log 'WireGuard prerequisite installed successfully.'
  exit 0
} catch {
  Write-Log "Prerequisite failed: $($_.Exception.GetType().Name)"
  exit 5
}
