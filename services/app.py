import os
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import Response

SERVICE = os.getenv("SERVICE_NAME", "service")
DEFAULT_VERSION = os.getenv("DEFAULT_VERSION", "v1.0")
app = FastAPI(title=f"DemoMart {SERVICE}")

state = {
    "version": DEFAULT_VERSION,
    "crash": False,
    "error_rate": 0.0,
    "latency_ms": 0,
    "cpu_percent": 15,
    "memory_percent": 25,
    "db_down": False,
    "db_pool_exhausted": False,
    "external_timeout": False,
    "telemetry_missing": False,
}

class Fault(BaseModel):
    fault: str
    enabled: bool = True
    value: float | int | str | None = None

class Version(BaseModel):
    version: str


def healthy():
    return not any(
        [
            state["crash"],
            state["db_down"],
            state["db_pool_exhausted"],
            state["external_timeout"],
        ]
    )


@app.get("/health")
def health():
    return {
        "service": SERVICE,
        "healthy": healthy(),
        "version": state["version"],
        "status": "UP" if healthy() else "DEGRADED",
    }


@app.get("/metrics-json")
def metrics_json():
    d = {
        "service": SERVICE,
        "version": state["version"],
        "healthy": healthy(),
        "error_rate": float(state["error_rate"]),
        "success_rate": max(0.0, 1.0 - float(state["error_rate"])),
        "latency_ms": int(state["latency_ms"]),
        "cpu_percent": int(state["cpu_percent"]),
        "memory_percent": int(state["memory_percent"]),
        "db_down": state["db_down"],
        "db_pool_exhausted": state["db_pool_exhausted"],
        "external_timeout": state["external_timeout"],
        "telemetry_present": not state["telemetry_missing"],
    }
    if state["telemetry_missing"]:
        d.pop("error_rate", None)
        d.pop("success_rate", None)
    return d


@app.get("/metrics")
def metrics():
    h = 1 if healthy() else 0
    telemetry = 0 if state["telemetry_missing"] else 1
    version = str(state["version"]).replace('"', '')
    lines = [
        "# HELP demomart_service_healthy Whether the service is healthy (1/0).",
        "# TYPE demomart_service_healthy gauge",
        f'demomart_service_healthy{{service="{SERVICE}"}} {h}',
        "# HELP demomart_telemetry_present Whether required telemetry is present (1/0).",
        "# TYPE demomart_telemetry_present gauge",
        f'demomart_telemetry_present{{service="{SERVICE}"}} {telemetry}',
        "# HELP demomart_service_info Service version information.",
        "# TYPE demomart_service_info gauge",
        f'demomart_service_info{{service="{SERVICE}",version="{version}"}} 1',
        "# HELP demomart_cpu_percent Simulated CPU saturation percentage.",
        "# TYPE demomart_cpu_percent gauge",
        f'demomart_cpu_percent{{service="{SERVICE}"}} {state["cpu_percent"]}',
        "# HELP demomart_memory_percent Simulated memory pressure percentage.",
        "# TYPE demomart_memory_percent gauge",
        f'demomart_memory_percent{{service="{SERVICE}"}} {state["memory_percent"]}',
        "# HELP demomart_latency_ms Simulated application latency in milliseconds.",
        "# TYPE demomart_latency_ms gauge",
        f'demomart_latency_ms{{service="{SERVICE}"}} {state["latency_ms"]}',
    ]
    if not state["telemetry_missing"]:
        e = float(state["error_rate"])
        s = max(0.0, 1.0 - e)
        lines += [
            "# HELP demomart_error_rate Simulated request error ratio.",
            "# TYPE demomart_error_rate gauge",
            f'demomart_error_rate{{service="{SERVICE}"}} {e}',
            "# HELP demomart_success_rate Simulated request success ratio.",
            "# TYPE demomart_success_rate gauge",
            f'demomart_success_rate{{service="{SERVICE}"}} {s}',
        ]
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.post("/admin/fault")
def fault(req: Fault):
    if req.fault not in state:
        raise HTTPException(400, "unknown fault")
    if req.fault in {"error_rate", "latency_ms", "cpu_percent", "memory_percent"}:
        defaults = {
            "error_rate": 0.0,
            "latency_ms": 0,
            "cpu_percent": 15,
            "memory_percent": 25,
        }
        if req.enabled and req.value is None:
            raise HTTPException(400, "value is required")
        state[req.fault] = req.value if req.enabled else defaults[req.fault]
    else:
        state[req.fault] = bool(req.enabled)
    return {"service": SERVICE, "state": state}


@app.post("/admin/version")
def version(req: Version):
    state["version"] = req.version
    return {"service": SERVICE, "version": state["version"]}


@app.post("/admin/reset")
def reset():
    state.update(
        {
            "version": DEFAULT_VERSION,
            "crash": False,
            "error_rate": 0.0,
            "latency_ms": 0,
            "cpu_percent": 15,
            "memory_percent": 25,
            "db_down": False,
            "db_pool_exhausted": False,
            "external_timeout": False,
            "telemetry_missing": False,
        }
    )
    return {"service": SERVICE, "state": state}
