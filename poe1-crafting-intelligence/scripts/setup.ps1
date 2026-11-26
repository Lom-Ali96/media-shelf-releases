# One-time setup (safe to re-run): venv, dependencies, current game data.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python environment in .venv ..."
    python -m venv .venv
}
Write-Host "Installing dependencies ..."
.\.venv\Scripts\python -m pip install --upgrade pip --quiet
.\.venv\Scripts\python -m pip install -e "backend[dev]" --quiet
Write-Host "Downloading current game data (skipped if already present) ..."
.\.venv\Scripts\python -m poeci.knowledge.importer
Write-Host ""
Write-Host "Setup complete. Start the app with:  powershell -ExecutionPolicy Bypass -File scripts\start.ps1"
