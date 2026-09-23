"""Compatibility surface for the pre-v1.2 IncidentLab routes.

IncidentLab no longer implements S1-S8. Those stages belong to OpsSwarm.
This module only forwards legacy lab controls to the stateful simulator.
"""
from fastapi import APIRouter, HTTPException
from .incidentlab import start_demo, reset, latest, get_run, SCENARIOS, _services

router = APIRouter()

@router.get("/", include_in_schema=False)
def legacy_ui():
    from .incidentlab import UI
    from fastapi.responses import HTMLResponse
    return HTMLResponse(UI)

@router.get("/lab/health")
def legacy_health(): return {"ok": True, "component": "incidentlab", "mode": "stateful-simulator"}

@router.get("/scenarios")
def legacy_scenarios(): return [{"id":k,**v} for k,v in SCENARIOS.items()]

@router.get("/incidents")
def legacy_incidents():
    r=latest(); return [] if not r else [r]

@router.get("/incidents/{incident_id}")
def legacy_incident(incident_id): return get_run(incident_id)

@router.post("/lab/reset")
def legacy_reset(): return reset()

@router.post("/lab/fault/{scenario_id}")
def legacy_fault(scenario_id): return start_demo(scenario_id)

@router.post("/lab/detect")
def legacy_detect(): return start_demo("booking-api-high-5xx")

@router.post("/lab/approve/{incident_id}")
def legacy_approve(incident_id):
    raise HTTPException(410, "Approval authority is GitHub only. Use /opsswarm approve <option-id> on the incident Issue.")
