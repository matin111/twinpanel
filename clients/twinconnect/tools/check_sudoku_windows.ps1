# Synthetic Sudoku CLI validation only; no remote dial / Windows routes.
# Never publish a generated private key to CI logs or artifacts.
$ErrorActionPreference = 'Stop'
$exe = Join-Path (Get-Location) 'build/windows/x64/runner/Release/engines/sudoku/sudoku.exe'
if (!(Test-Path $exe)) { throw 'Official Sudoku core not bundled' }
$keygen = (& $exe -keygen 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0) { throw 'Sudoku keygen self-test failed' }
$match = [regex]::Match($keygen, 'Available Private Key:\s*([0-9a-fA-F]{64,128})')
if (!$match.Success) { throw 'Sudoku generated no valid test key' }
$sample = @{
  mode = 'client'
  transport = 'tcp'
  server_address = '203.0.113.44:18553'
  local_address = '127.0.0.1'
  local_port = 19388
  key = $match.Groups[1].Value
  aead = 'chacha20-poly1305'
  padding_min = 5
  padding_max = 15
  ascii = 'prefer_entropy'
  enable_pure_downlink = $true
  multiplex = 'off'
  httpmask = @{ disable = $false; mode = 'auto' }
  rule_urls = @('global')
}
$file = Join-Path $env:RUNNER_TEMP 'twinconnect-sudoku-synthetic.json'
try {
  $sample | ConvertTo-Json -Depth 6 -Compress |
    Set-Content -LiteralPath $file -NoNewline -Encoding utf8
  & $exe -test -c $file 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw 'Official Sudoku CLI rejected a synthetic TwinConnect client profile'
  }
} finally {
  Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue
}
Write-Host 'Official Sudoku CLI accepts synthetic client config'
