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
  $wingetPath = if ($winget) { $winget.Source } else { $null }
  if (-not $wingetPath) {
    # Elevated installer sessions may not inherit the normal user's winget alias.
    $candidates = @(Get-ChildItem -Path (Join-Path $env:ProgramFiles 'WindowsApps') -Directory -Filter 'Microsoft.DesktopAppInstaller_*' -ErrorAction SilentlyContinue |
      Sort-Object Name -Descending |
      ForEach-Object { Join-Path $_.FullName 'winget.exe' })
    $wingetPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  }
  if (-not $wingetPath) {
    Write-Log 'Windows Package Manager could not be located in the elevated setup context.'
    exit 2
  }
  Write-Log 'Installing official WireGuard.WireGuard via winget.'
  & $wingetPath install --id WireGuard.WireGuard --exact --source winget --silent --disable-interactivity --accept-package-agreements --accept-source-agreements 2>&1 | ForEach-Object { Write-Log "$_" }
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
