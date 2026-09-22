import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from opsswarm import tool_adapter as tools
from opsswarm.scenarios import load
from opsswarm.skills.s1_incident_intake.logic import run as s1
from opsswarm.skills.s2_severity_assessment.logic import run as s2
from opsswarm.skills.s3_evidence_collector.logic import run as s3
from opsswarm.skills.s4_response_orchestrator.logic import run as s4
from opsswarm.skills.s5_stakeholder_communication.logic import run as s5
from opsswarm.skills.s6_recovery_verification.logic import run as s6
from opsswarm.skills.s7_post_incident_review.logic import run as s7

router = APIRouter()
SC = load()
INC = {}
SEEN = set()
SEQ = 0
LAB = {"scenario_id": None, "duplicate_alerts": False}
COUNTERS = {"alertmanager_webhooks": 0, "incidents_created": 0, "duplicates_suppressed": 0}
ED = Path(os.getenv("EVIDENCE_DIR", "/tmp/evidence"))
(ED / "incidents").mkdir(parents=True, exist_ok=True)


def now():
    return datetime.now(timezone.utc).isoformat()


def nid():
    global SEQ
    SEQ += 1
    return f"INC-{SEQ:06d}"


def persist(incident):
    (ED / "incidents" / f"{incident['id']}.json").write_text(
        json.dumps(incident, indent=2), encoding="utf-8"
    )


def alert_for(service, metrics, scenario_id):
    if "error_rate" not in metrics:
        kind = "telemetry_missing"
    elif metrics.get("healthy") is False:
        kind = "service_unhealthy"
    elif metrics.get("error_rate", 0) >= 0.03:
        kind = "error_rate"
    elif metrics.get("latency_ms", 0) >= 1000:
        kind = "latency"
    elif metrics.get("cpu_percent", 0) >= 90:
        kind = "cpu"
    elif metrics.get("memory_percent", 0) >= 90:
        kind = "memory"
    else:
        return None
    return {
        "service": service,
        "kind": kind,
        "scenario_id": scenario_id,
        "observed": metrics,
        "source": "manual-detect",
    }


def create(alert):
    intake = s1(alert, SEEN)
    if intake["duplicate"]:
        COUNTERS["duplicates_suppressed"] += 1
        return {"duplicate": True, "fingerprint": intake["fingerprint"]}

    incident_id = nid()
    normalized = intake["normalized"]
    sev = s2(normalized)
    direct_metrics = tools.all_metrics()
    evidence = s3(direct_metrics)
    service = normalized["service"]
    evidence["prometheus_snapshot"] = tools.prometheus_snapshot(service)
    evidence["prometheus_health"] = tools.prometheus_health()
    plan = s4(normalized, evidence)
    comm = s5(incident_id, sev["severity"], service)

    obj = {
        "id": incident_id,
        "scenario_id": normalized.get("scenario_id"),
        "service": service,
        "severity": sev["severity"],
        "severity_rationale": sev["rationale"],
        "status": "AWAITING_APPROVAL",
        "alert_source": alert.get("source", "unknown"),
        "intake": intake,
        "evidence": evidence,
        "orchestration": plan,
        "communications": comm,
        "timeline": [
            {"ts": now(), "event": "INCIDENT_CREATED"},
            {"ts": now(), "event": "EVIDENCE_COLLECTED"},
            {"ts": now(), "event": "RECOVERY_RECOMMENDED"},
        ],
    }
    INC[incident_id] = obj
    COUNTERS["incidents_created"] += 1
    persist(obj)
    return obj


@router.get("/", response_class=HTMLResponse)
def ui():
    return HTMLResponse(
        """<!doctype html><html><head><meta charset="utf-8"><title>OpsSwarm IncidentLab</title>
<style>body{font-family:Arial;max-width:1050px;margin:30px auto;background:#f5f6fa}.c{background:#fff;padding:18px;margin:12px;border-radius:12px}button{padding:10px;margin:4px}pre{background:#111;color:#eee;padding:14px;max-height:520px;overflow:auto}a{margin-right:16px}</style></head>
<body><h1>OpsSwarm IncidentLab v1.1</h1>
<div class="c"><b>Observability:</b> <a href="http://localhost:9090" target="_blank">Prometheus</a><a href="http://localhost:9093" target="_blank">Alertmanager</a></div>
<div class="c"><button onclick="p('/lab/reset')">Reset</button><button onclick="p('/lab/fault/C03')">C03 Bad Deployment</button><button onclick="p('/lab/fault/C02')">C02 Error Spike</button><button onclick="p('/lab/fault/C06')">C06 Latency</button><button onclick="p('/lab/fault/C09')">C09 Gateway Timeout</button><button onclick="p('/lab/fault/C11')">C11 Missing Telemetry</button><button onclick="p('/lab/fault/C12')">C12 False Recovery</button></div>
<div class="c"><p><b>Automatic path:</b> inject a fault, wait ~3-5 seconds, then click Refresh Incidents. Prometheus â†’ Alertmanager â†’ OpsSwarm will create the incident.</p><button onclick="refreshInc()">Refresh Incidents</button><button onclick="detect()">Manual Detect fallback</button><button onclick="approve()">Approve Latest + S6-S7</button></div>
<pre id="o">Ready</pre><script>let id=null;async function p(u){let r=await fetch(u,{method:'POST'}),j=await r.json();document.getElementById('o').textContent=JSON.stringify(j,null,2);return j}async function detect(){let j=await p('/lab/detect');if(j.created&&j.created[0])id=j.created[0].id}async function refreshInc(){let r=await fetch('/incidents'),j=await r.json();document.getElementById('o').textContent=JSON.stringify(j,null,2);if(j.length)id=j[j.length-1].id}async function approve(){if(!id){alert('Refresh or detect an incident first');return}await p('/lab/approve/'+id)}</script></body></html>"""
    )


@router.get("/health")
def health():
    return {"ok": True, "prometheus": tools.prometheus_health()}


@router.get("/metrics")
def metrics():
    body = "\n".join(
        [
            "# HELP opsswarm_alertmanager_webhooks_total Alertmanager webhook calls received.",
            "# TYPE opsswarm_alertmanager_webhooks_total counter",
            f'opsswarm_alertmanager_webhooks_total {COUNTERS["alertmanager_webhooks"]}',
            "# HELP opsswarm_incidents_created_total Incidents created.",
            "# TYPE opsswarm_incidents_created_total counter",
            f'opsswarm_incidents_created_total {COUNTERS["incidents_created"]}',
            "# HELP opsswarm_duplicates_suppressed_total Duplicate alerts suppressed.",
            "# TYPE opsswarm_duplicates_suppressed_total counter",
            f'opsswarm_duplicates_suppressed_total {COUNTERS["duplicates_suppressed"]}',
        ]
    ) + "\n"
    return Response(body, media_type="text/plain; version=0.0.4")


@router.get("/scenarios")
def scenarios():
    return list(SC.values())


@router.get("/incidents")
def incidents():
    return list(INC.values())


@router.get("/incidents/{incident_id}")
def incident(incident_id):
    if incident_id not in INC:
        raise HTTPException(404, "not found")
    return INC[incident_id]


@router.get("/observability")
def observability():
    return {
        "prometheus": tools.prometheus_health(),
        "payment_prometheus_snapshot": tools.prometheus_snapshot("payment"),
        "counters": COUNTERS,
    }


@router.post("/api/v1/alertmanager")
async def alertmanager_webhook(request: Request):
    payload = await request.json()
    COUNTERS["alertmanager_webhooks"] += 1
    created = []
    duplicates = []
    resolved = []

    for item in payload.get("alerts", []):
        labels = item.get("labels", {})
        service = labels.get("service")
        if service not in tools.URLS:
            continue
        if item.get("status") == "resolved":
            resolved.append({"service": service, "alertname": labels.get("alertname")})
            continue

        try:
            observed = tools.getm(service)
        except Exception as exc:
            observed = {"service": service, "healthy": False, "tool_error": str(exc)}

        alert = {
            "service": service,
            "kind": labels.get("alertname", "prometheus_alert"),
            "scenario_id": LAB.get("scenario_id"),
            "observed": observed,
            "source": "prometheus-alertmanager",
            "alertmanager": {
                "status": item.get("status"),
                "labels": labels,
                "annotations": item.get("annotations", {}),
                "startsAt": item.get("startsAt"),
                "fingerprint": item.get("fingerprint"),
            },
        }
        result = create(alert)
        if result.get("duplicate"):
            duplicates.append(result)
        else:
            created.append(result)

    return {
        "accepted": True,
        "created": created,
        "deduplicated": duplicates,
        "resolved": resolved,
    }


@router.post("/lab/reset")
def reset():
    INC.clear()
    SEEN.clear()
    LAB.update({"scenario_id": None, "duplicate_alerts": False})
    tools.reset_all()
    return {"reset": True}


@router.post("/lab/fault/{scenario_id}")
def fault(scenario_id):
    if scenario_id not in SC:
        raise HTTPException(404, "unknown scenario")
    x = SC[scenario_id]
    LAB["scenario_id"] = scenario_id
    LAB["duplicate_alerts"] = scenario_id == "C10"
    service, fault_name, value = x["service"], x["fault"], x["value"]
    if fault_name == "bad_deployment":
        tools.set_version(service, str(value))
        tools.set_fault(service, "error_rate", True, 0.43)
    elif fault_name == "duplicate_alerts":
        tools.set_fault(service, "error_rate", True, 0.43)
    elif fault_name in {"error_rate", "latency_ms", "cpu_percent", "memory_percent"}:
        tools.set_fault(service, fault_name, True, value)
    else:
        tools.set_fault(service, fault_name, bool(value))
    return {"injected": True, "scenario": x, "metrics": tools.getm(service)}


@router.post("/lab/detect")
def detect():
    metrics = tools.all_metrics()
    created, duplicates = [], []
    for service, values in metrics.items():
        alert = alert_for(service, values, LAB["scenario_id"])
        if alert:
            result = create(alert)
            (duplicates if result.get("duplicate") else created).append(result)
            if LAB["duplicate_alerts"]:
                result = create(alert)
                (duplicates if result.get("duplicate") else created).append(result)
    return {
        "scenario_id": LAB["scenario_id"],
        "created": created,
        "deduplicated": duplicates,
        "metrics": metrics,
        "prometheus": tools.prometheus_health(),
    }


@router.post("/lab/approve/{incident_id}")
def approve(incident_id):
    if incident_id not in INC:
        raise HTTPException(404, "not found")
    x = INC[incident_id]
    action = x["orchestration"]["recommended_action"]
    x["timeline"].append({"ts": now(), "event": "HUMAN_APPROVED"})
    execution = tools.recover(action)
    time.sleep(0.1)
    metrics = tools.getm(x["service"])
    verification = s6(x["service"], metrics)
    x["recovery"] = {
        "execution": execution,
        "metrics": metrics,
        "verification": verification,
    }
    x["status"] = "RESOLVED" if verification["verified"] else "RECOVERY_NOT_VERIFIED"
    x["timeline"].append(
        {
            "ts": now(),
            "event": "RECOVERY_VERIFIED" if verification["verified"] else "RECOVERY_REJECTED",
        }
    )
    x["post_incident_review"] = s7(x)
    persist(x)
    return x

