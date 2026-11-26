# Starts the local server on http://127.0.0.1:8765 and opens the browser.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$port = if ($env:POECI_PORT) { $env:POECI_PORT } else { "8765" }
Start-Job { Start-Sleep 2; Start-Process "http://127.0.0.1:$using:port" } | Out-Null
.\.venv\Scripts\python -m poeci
