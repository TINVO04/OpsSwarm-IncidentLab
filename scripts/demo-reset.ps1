$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
Invoke-RestMethod -Method Post -Uri 'http://localhost:8088/api/demo/reset' | ConvertTo-Json -Depth 10
