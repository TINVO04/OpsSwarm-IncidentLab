# OpsSwarm IncidentLab v1.2 Control Center

This project is an independent, stateful incident simulation environment for demonstrating the workflow of `OpsSwarm-Enterprise`. It does not merge or vendor the Enterprise codebase.

## Architecture boundary

IncidentLab owns only the simulated environment and evidence sources: simulated services/deployment state, metrics/log/evidence snapshots, dependencies, stateful fault injection and recovery APIs, monitoring event generation, and timeline/evidence persistence.

OpsSwarm owns workflow authority. The Control Center visualizes the Enterprise lifecycle as telemetry:

`S8 Orchestration Hub -> S1 IntentGuard -> S2 read-only DAG -> S4 specialist dispatch -> S5 evidence/collaboration -> RCA -> S3 HorizonPlan -> Policy -> Recovery -> S6 ResilienceGuard when required -> S7 independent verification -> RESOLVED`

OpenClaw is agent runtime, not policy authority. Investigation agents are read-only. Risky writes are represented as `HUMAN_REQUIRED`; the UI displays the GitHub command and does not grant execution authority itself.

## Start

```powershell
.\scripts\demo-start.ps1
```

Open `http://localhost:8080/api/ui`.

Reset:

```powershell
.\scripts\demo-reset.ps1
```

Run a scenario:

```powershell
.\scripts\demo-run.ps1 -Scenario booking-api-high-5xx
```

Stop:

```powershell
.\scripts\demo-stop.ps1
```

## Automatic GitHub incident flow

A stateful IncidentLab run sends its monitoring payload to `POST /hooks/monitoring`. OpsSwarm creates the GitHub Issue **before** label synchronization, persists the deduplication mapping, and then attempts to apply labels. A label failure is logged as `ISSUE_LABEL_WARNING` and does not delete the Issue or stop orchestration.

```text
IncidentLab fault/test
  -> POST /hooks/monitoring
  -> GitHub Issue created + deduplication key persisted
  -> issues.opened webhook OR GitHub polling fallback
  -> S8 -> S1 -> S2 -> S4 -> S5 -> RCA -> S3 -> Policy
  -> explicit /opsswarm command when human authority is required
  -> recovery-responder -> S6 when reconciliation is required
  -> independent S7 verification
  -> final report + postmortem -> close Issue only after S7 passes
```

One monitoring identity maps to one GitHub Issue. Re-sending the same `deduplication_key` returns the existing `issue_number` and logs `ISSUE_DEDUPLICATED`. If an unresolved/failed monitoring Issue is closed outside the governed workflow, the poller treats that as state drift and reopens it; manual Issue closure is not an approval/abort command.

### GitHub webhook and polling

Configure GitHub for `issues` and `issue_comment` events and point it at `<public-base>/webhooks/github`. When `GITHUB_WEBHOOK_SECRET` is set, webhook HMAC verification is mandatory; invalid signatures return HTTP 401.

`OPSSWARM_GITHUB_POLL_SECONDS` is the fallback for environments where GitHub cannot reach the local container. The poller discovers monitoring Issues by the trusted marker embedded in the Issue body, queues orchestration without blocking the watcher, and also consumes explicit `/opsswarm ...` comments.

### OpenClaw Gateway on Windows

OpsSwarm in Docker does **not** execute a local `openclaw` binary. It calls the real OpenClaw Gateway running on Windows over HTTP. Default Docker configuration is:

```text
OPSWARM_OPENCLAW_GATEWAY_URL=http://host.docker.internal:18789
```

The integration uses the Gateway OpenResponses endpoint and Bearer authentication from `OPENCLAW_GATEWAY_TOKEN`. Multi-agent sessions are explicitly agent-scoped. Keep the token in `.env`/backend configuration only. Useful host checks are `cmd /c openclaw --version`, `cmd /c openclaw gateway status`, and `cmd /c openclaw agents list`.

Required environment keys are documented in `.env.example`. For the reference repository set `GITHUB_REPO=ZINNODNTU/OpsSwarm-IncidentLab`.

## Stateful simulator API

`GET /api/health`, `/api/services`, `/api/services/{name}`, `/api/metrics`, `/api/logs`, `/api/events`, `/api/dependencies`, `/api/state`, `/api/scenarios`, `/api/evidence`

`POST /api/faults/inject`, `/api/faults/reset`, `/api/recovery/restart`, `/api/recovery/rollback`, `/api/recovery/scale`, `/api/demo/start`, `/api/demo/reset`

`GET /api/incidents/{id}`, `/api/incidents/{id}/timeline`

## Canonical Enterprise-aligned demo

The recommended demo follows the Enterprise control model:

```text
IncidentLab fault
  -> monitoring ingress
  -> one GitHub Issue
  -> S8 -> S1 -> S2 -> S4 specialist fan-out
  -> S5 evidence aggregation -> RCA
  -> S3 recovery plan -> Policy
  -> GitHub /opsswarm command when human authority is required
  -> bounded recovery -> S6/S7
  -> close Issue only after independent verification
```

Run:

```powershell
.\scripts\demo-start.ps1
.\scripts\demo-e2e.ps1 -Scenario booking-api-high-5xx
```

For a controlled end-to-end run that posts the explicit GitHub approval command:

```powershell
.\scripts\demo-e2e.ps1 -Scenario booking-api-high-5xx -Approve
```

The -Approve switch only posts the exact /opsswarm approve <option-id> command to the GitHub Issue. It does not call a hidden approval or recovery API.

## Primary demo: booking-api-high-5xx

Initial state is approximately `booking-api=HEALTHY`, `error_rate=0.2%`, `latency=180ms`, `database=HEALTHY`.

Injection changes the simulator state to degraded conditions around `42%` errors and `2.8s` latency, with database/dependency evidence showing the injected fault. Recovery changes the simulated state through service admin APIs; it is not a text-only success response.

The default risky rollback path stops at `WAITING FOR GITHUB APPROVAL` and displays:

```text
/opsswarm approve option-001
```

After approval, the simulator executes recovery, records recovery/S6 evidence, and S7 independently reads service state. Only a passing verification changes the incident to `RESOLVED` and produces a final report/postmortem.

## Scenarios

- `booking-api-high-5xx`
- `latency-spike`
- `database-pool-exhaustion`
- `dependency-timeout`
- `failed-deployment`
- `partial-network-failure`

## UI

The Control Center provides Dashboard, Incidents, Fault Lab, Workflow, Agents, Evidence, Recovery, Verification and Settings navigation areas. Workflow is the primary focus, with `PENDING/RUNNING/WAITING/COMPLETED/FAILED/BLOCKED`, read-only specialist agents, metrics, dependencies, timeline and evidence.

## Integration status

The simulator, Docker services, Prometheus and Alertmanager are real local components. Existing OpsSwarm/OpenClaw/GitHub integration remains intact and is not replaced by the simulator. The local demo path is explicitly simulated and does not claim a GitHub/OpenClaw action occurred unless the Enterprise integration path actually did so.

Secrets remain backend/environment configuration and are not embedded in the frontend.


## Approval authority

IncidentLab has no execution-authority approval API. Legacy `/api/demo/approve` and `/lab/approve/{incident_id}` routes return HTTP 410 and exist only to fail closed for older clients. Use the exact `/opsswarm approve <option-id>` command shown by OpsSwarm on the GitHub Issue.
