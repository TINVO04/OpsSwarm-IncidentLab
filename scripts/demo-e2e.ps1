param(
    [string]$Scenario = "booking-api-high-5xx",
    [int]$WaitSeconds = 180,
    [switch]$Approve
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Get-RunState([int]$IssueNumber) {
    try { return Invoke-RestMethod -Uri "http://localhost:8088/runs/$IssueNumber" -TimeoutSec 10 }
    catch { return $null }
}

Write-Host "=== OpsSwarm IncidentLab Enterprise Demo ==="
Write-Host "Scenario: $Scenario"
docker compose up --build -d
Start-Sleep -Seconds 8
$health = Invoke-RestMethod -Uri "http://localhost:8088/health" -TimeoutSec 15
Write-Host "Health: $($health.ok) | OpenClaw: $($health.openclaw.ok)"

$start = Invoke-RestMethod -Method Post -Uri "http://localhost:8088/api/demo/start" -ContentType "application/json" -Body (@{scenario_id=$Scenario} | ConvertTo-Json)
$issue = [int]$start.github_issue_number
Write-Host "GitHub Issue: #$issue"
if ($start.github_issue_url) { Write-Host "URL: $($start.github_issue_url)" }

$deadline = (Get-Date).AddSeconds($WaitSeconds)
$run = $null
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 5
    $run = Get-RunState $issue
    if ($run) {
        Write-Host ("[{0}] state={1} findings={2} root_cause={3} plan={4} decision={5} execution={6} verification={7}" -f (Get-Date -Format "HH:mm:ss"), $run.state, @($run.findings).Count, [bool]$run.root_cause, [bool]$run.recovery_plan, [bool]$run.decision, [bool]$run.execution, [bool]$run.verification)
        if ($run.state -in @("WAITING_APPROVAL","WAITING_DECISION","WAITING_INPUT","RESOLVED","FAILED","ABORTED")) { break }
    }
}
if (-not $run) { throw "No orchestration run was observed for Issue #$issue." }

Write-Host ""
Write-Host "=== DEMO CHECKPOINT ==="
Write-Host "Issue #$issue => $($run.state)"

if ($run.state -eq "WAITING_APPROVAL") {
    $option = $run.decision.options | Select-Object -First 1
    Write-Host "Required human command: /opsswarm approve $($option.id)"
    if ($Approve) {
        $py = "import os,httpx; token=os.environ['GITHUB_TOKEN']; repo=os.environ['GITHUB_REPO']; h={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}; r=httpx.post(f'https://api.github.com/repos/{repo}/issues/$issue/comments',headers=h,json={'body':'/opsswarm approve $($option.id)'},timeout=15); r.raise_for_status(); print('EXPLICIT_GITHUB_APPROVAL_COMMENT_POSTED')"
        $py | docker compose exec -T opsswarm python -
        $deadline = (Get-Date).AddSeconds($WaitSeconds)
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 5
            $run = Get-RunState $issue
            if ($run) {
                Write-Host ("[{0}] state={1} execution={2} verification={3}" -f (Get-Date -Format "HH:mm:ss"), $run.state, [bool]$run.execution, [bool]$run.verification)
                if ($run.state -in @("RESOLVED","FAILED","ABORTED")) { break }
            }
        }
    }
}

Write-Host ""
Write-Host "=== FINAL ==="
Write-Host "Issue #$issue => $($run.state)"
Write-Host "Authorization remains on the GitHub /opsswarm command path."
