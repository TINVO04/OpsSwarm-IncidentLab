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

## Stateful simulator API

`GET /api/health`, `/api/services`, `/api/services/{name}`, `/api/metrics`, `/api/logs`, `/api/events`, `/api/dependencies`, `/api/state`, `/api/scenarios`, `/api/evidence`

`POST /api/faults/inject`, `/api/faults/reset`, `/api/recovery/restart`, `/api/recovery/rollback`, `/api/recovery/scale`, `/api/demo/start`, `/api/demo/approve`, `/api/demo/reset`

`GET /api/incidents/{id}`, `/api/incidents/{id}/timeline`

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

