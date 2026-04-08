param(
  [string]$StartDate = "2025-07-29",
  [string]$EndDate = "",
  [string]$Ticker = "ALL",
  [string]$PythonExe = "python",
  [switch]$SkipLoadBlueGreen,
  [switch]$StopOnError
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot "streamlit_full_chain.py"

if (-not (Test-Path $runner)) {
  throw "Missing runner script: $runner"
}

$argsList = @(
  $runner,
  "--start-date", $StartDate,
  "--ticker", $Ticker,
  "--python-exec", $PythonExe
)

if ($EndDate -ne "") {
  $argsList += @("--end-date", $EndDate)
}
if ($SkipLoadBlueGreen.IsPresent) {
  $argsList += "--skip-load-blue-green"
}
if ($StopOnError.IsPresent) {
  $argsList += "--stop-on-error"
}

Write-Host "[streamlit-full-chain.ps1] Repo: $repoRoot"
Write-Host "[streamlit-full-chain.ps1] Command: $PythonExe $($argsList -join ' ')"

Push-Location $repoRoot
try {
  & $PythonExe @argsList
  $exitCode = $LASTEXITCODE
} finally {
  Pop-Location
}

if ($exitCode -ne 0) {
  throw "streamlit_full_chain.py exited with code $exitCode"
}
