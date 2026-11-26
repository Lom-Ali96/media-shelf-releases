# Copies the local database to backups\poeci-<timestamp>.sqlite3
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
New-Item -ItemType Directory -Force backups | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item "data\poeci.sqlite3" "backups\poeci-$stamp.sqlite3"
Write-Host "Backup written to backups\poeci-$stamp.sqlite3"
