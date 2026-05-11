param(
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$server = Join-Path $scriptDir "server.py"

if (-not (Test-Path -LiteralPath $server)) {
  throw "server.py not found: $server"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
  $python = Get-Command py -ErrorAction SilentlyContinue
}
if ($null -eq $python) {
  throw "Python was not found. Install Python or add it to PATH."
}

Set-Location $repoRoot
Write-Host "Starting MemoFlow config manager..."
Write-Host "Repository: $repoRoot"
Write-Host "Requested URL: http://127.0.0.1:$Port/"
Write-Host "Press Ctrl+C to stop."

if ($python.Source -like "*\py.exe") {
  & $python.Source -3 $server --port $Port
} else {
  & $python.Source $server --port $Port
}
