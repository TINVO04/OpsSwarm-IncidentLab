import os
import requests

URLS = {
    "auth": os.getenv("AUTH_URL", "http://localhost:8001"),
    "order": os.getenv("ORDER_URL", "http://localhost:8002"),
    "inventory": os.getenv("INVENTORY_URL", "http://localhost:8003"),
    "payment": os.getenv("PAYMENT_URL", "http://localhost:8004"),
}
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")


def getm(service):
    r = requests.get(URLS[service] + "/metrics-json", timeout=5)
    r.raise_for_status()
    return r.json()


def all_metrics():
    out = {}
    for service in URLS:
        try:
            out[service] = getm(service)
        except Exception as exc:
            out[service] = {
                "service": service,
                "healthy": False,
                "tool_error": str(exc),
            }
    return out


def prometheus_query(query):
    r = requests.get(
        PROMETHEUS_URL + "/api/v1/query",
        params={"query": query},
        timeout=5,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {body}")
    return body.get("data", {}).get("result", [])


def prometheus_health():
    try:
        r = requests.get(PROMETHEUS_URL + "/-/ready", timeout=3)
        return {"reachable": r.ok, "status_code": r.status_code}
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def prometheus_snapshot(service):
    expressions = {
        "healthy": f'demomart_service_healthy{{service="{service}"}}',
        "error_rate": f'demomart_error_rate{{service="{service}"}}',
        "success_rate": f'demomart_success_rate{{service="{service}"}}',
        "latency_ms": f'demomart_latency_ms{{service="{service}"}}',
        "cpu_percent": f'demomart_cpu_percent{{service="{service}"}}',
        "memory_percent": f'demomart_memory_percent{{service="{service}"}}',
        "telemetry_present": f'demomart_telemetry_present{{service="{service}"}}',
    }
    out = {}
    for key, expr in expressions.items():
        try:
            result = prometheus_query(expr)
            out[key] = float(result[0]["value"][1]) if result else None
        except Exception as exc:
            out[key] = None
            out.setdefault("errors", {})[key] = str(exc)
    return out


def post(service, path, payload=None):
    r = requests.post(URLS[service] + path, json=payload or {}, timeout=5)
    r.raise_for_status()
    return r.json()


def reset_all():
    return {service: post(service, "/admin/reset") for service in URLS}


def set_fault(service, fault, enabled=True, value=None):
    return post(
        service,
        "/admin/fault",
        {"fault": fault, "enabled": enabled, "value": value},
    )


def set_version(service, version):
    return post(service, "/admin/version", {"version": version})


def recover(action):
    service = action["service"]
    action_type = action["type"]
    if action_type == "rollback":
        set_version(service, action.get("target_version", "v2.0"))
        set_fault(service, "error_rate", False)
        set_fault(service, "crash", False)
    elif action_type == "partial_recovery":
        post(service, "/admin/reset")
        set_fault(service, "error_rate", True, 0.08)
    else:
        post(service, "/admin/reset")
    return {"executed": True, "action": action}
