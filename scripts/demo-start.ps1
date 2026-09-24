param([int]$WaitSeconds=8)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose up --build -d
Start-Sleep -Seconds $WaitSeconds
Write-Host 'IncidentLab Control Center: http://localhost:8088/api/ui'

