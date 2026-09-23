param([string]$Scenario='booking-api-high-5xx')
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$body=@{scenario_id=$Scenario}|ConvertTo-Json
$result=Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/demo/start' -ContentType 'application/json' -Body $body
$result | ConvertTo-Json -Depth 20
if ($result.github_issue_url) {
  Write-Host "`nGitHub system-of-record: $($result.github_issue_url)"
}
Write-Host "Wait for the OpsSwarm policy/decision comment on that Issue."
Write-Host "If human authority is required, use the exact /opsswarm approve <option-id> command shown there; this script never approves recovery itself."
