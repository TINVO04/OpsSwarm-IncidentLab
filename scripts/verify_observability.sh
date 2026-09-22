#!/usr/bin/env bash
set -euo pipefail

PROM="${PROMETHEUS_URL:-http://localhost:9090}"
AM="${ALERTMANAGER_URL:-http://localhost:9093}"
OPS="${OPSSWARM_URL:-http://localhost:8080}"

printf '1/6 OpsSwarm health...\n'
curl -fsS "$OPS/health" | python3 -m json.tool

printf '\n2/6 Prometheus ready...\n'
curl -fsS "$PROM/-/ready"

printf '\n3/6 Prometheus targets...\n'
curl -fsS "$PROM/api/v1/targets" > /tmp/opsswarm-targets.json
python3 - <<'PY'
import json
p=json.load(open('/tmp/opsswarm-targets.json'))
active=p['data']['activeTargets']
for t in active:
    print(t['labels'].get('job'), t.get('scrapeUrl'), t.get('health'), t.get('lastError',''))
required=[t for t in active if t['labels'].get('job')=='demomart']
assert len(required)==4, f'expected 4 demomart targets, got {len(required)}'
assert all(t.get('health')=='up' for t in required), 'one or more DemoMart targets are not UP'
PY

printf '\n4/6 Query metric...\n'
curl -fsS --get "$PROM/api/v1/query" --data-urlencode 'query=demomart_service_healthy' > /tmp/opsswarm-query.json
python3 - <<'PY'
import json
p=json.load(open('/tmp/opsswarm-query.json'))
assert p['status']=='success'
print('series=',len(p['data']['result']))
assert len(p['data']['result'])==4
PY

printf '\n5/6 Alertmanager status...\n'
curl -fsS "$AM/-/ready"

printf '\n6/6 OpsSwarm observability endpoint...\n'
curl -fsS "$OPS/observability" | python3 -m json.tool

printf '\nOBSERVABILITY_SMOKE_TEST = PASS\n'
