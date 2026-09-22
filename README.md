# OpsSwarm IncidentLab v1.1

Corrected observability build of the enterprise incident-response demo/testbed.

## What v1.1 fixes

v1.0 started Prometheus, but OpsSwarm bypassed it and read `/metrics-json` directly. There were also no alert rules and no Alertmanager. Therefore Prometheus was not part of the actual incident trigger path.

v1.1 adds the complete path:

```text
DemoMart /metrics
      ↓ scrape every 2s
Prometheus
      ↓ alert rules
Alertmanager
      ↓ webhook
OpsSwarm /api/v1/alertmanager
      ↓
S1 → S2 → S3 → S4 → S5
      ↓
Human Approval
      ↓
Recovery Tool
      ↓
S6 → S7
```

It also fixes C11 so that `telemetry_missing` is visible consistently to Prometheus via `demomart_telemetry_present=0` and removal of error/success series.

## Start

```bash
docker compose up --build -d
```

Wait until the containers are healthy, then open:

- OpsSwarm: http://localhost:8080
- Prometheus: http://localhost:9090
- Prometheus targets: http://localhost:9090/targets
- Prometheus alerts: http://localhost:9090/alerts
- Alertmanager: http://localhost:9093

## Verify Prometheus before demo

All DemoMart targets should be `UP` at `/targets`.

Queries to try in Prometheus:

```promql
demomart_service_healthy

demomart_error_rate

demomart_latency_ms

demomart_telemetry_present

opsswarm_alertmanager_webhooks_total
```

## Automatic C03 demo

1. Reset the lab.
2. Inject `C03 Bad Deployment`.
3. Wait about 3–5 seconds.
4. Open Prometheus `/alerts`: `DemoMartHighErrorRate` should be FIRING.
5. Open Alertmanager: the alert should be visible.
6. In OpsSwarm click `Refresh Incidents`.
7. The incident's `alert_source` should equal `prometheus-alertmanager`.
8. Approve recovery.
9. The payment error rate returns to normal and Prometheus resolves the alert.

### CLI smoke check

```bash
bash scripts/verify_observability.sh
```

## Manual detect

`POST /lab/detect` is retained only as a deterministic fallback and test helper. It is no longer the only path.

## Important experimental limitation

B0 remains a scripted software baseline, not a human-operator baseline. Do not report its timings as human MTTA/MTTR.
