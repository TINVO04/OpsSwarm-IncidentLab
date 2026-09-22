$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose down
