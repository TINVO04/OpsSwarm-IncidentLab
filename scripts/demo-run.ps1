param([string]$Scenario='booking-api-high-5xx')
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$body=@{scenario_id=$Scenario}|ConvertTo-Json
$result=Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/demo/start' -ContentType 'application/json' -Body $body
$result | ConvertTo-Json -Depth 20
Write-Host "`nIf policy is HUMAN_REQUIRED, use the Enterprise GitHub control surface with:"
Write-Host '/opsswarm approve option-001'
