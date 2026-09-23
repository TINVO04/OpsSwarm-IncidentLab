from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MONITORING_MARKER = "<!-- opsswarm-monitoring-event -->"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(event: str, **fields: Any) -> None:
    record = {"timestamp": utc_now(), "component": "opsswarm", "event": event, **fields}
    print(json.dumps(record, ensure_ascii=False, default=str), flush=True)


def incident_correlation_key(payload: dict[str, Any]) -> str:
    """Stable identity for one active incident, independent of run/alert IDs."""
    explicit = str(payload.get("correlation_key") or "").strip()
    if explicit:
        return explicit
    environment = str(payload.get("environment") or "unknown").strip().lower()
    service = str(payload.get("service") or "unknown").strip().lower()
    scenario = str(payload.get("scenario_id") or payload.get("fault_type") or "unknown").strip().lower()
    # Source is deliberately excluded so IncidentLab, Alertmanager and retries
    # converge on the same incident identity.
    raw = f"env={environment}|service={service}|scenario={scenario}"
    return "incident:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def deduplication_key(payload: dict[str, Any]) -> str:
    """Backward-compatible alias; issue dedup now uses incident correlation, not run IDs."""
    explicit = str(payload.get("deduplication_key") or "").strip()
    return explicit or incident_correlation_key(payload)


def is_monitoring_issue(issue: dict[str, Any], required_label: str | None = None) -> bool:
    if MONITORING_MARKER in (issue.get("body") or ""):
        return True
    if required_label:
        labels = [x.get("name", "") if isinstance(x, dict) else str(x) for x in issue.get("labels", [])]
        return required_label in labels
    return False


def build_issue_body(payload: dict[str, Any], key: str) -> str:
    incident_id = payload.get("incident_id") or "unknown"
    run_id = payload.get("run_id") or "unknown"
    scenario_id = payload.get("scenario_id") or "unknown"
    correlation_key = payload.get("correlation_key") or incident_correlation_key(payload)
    base = os.getenv("INCIDENTLAB_PUBLIC_URL", "http://localhost:8080").rstrip("/")
    reference = payload.get("incidentlab_reference") or f"{base}/api/incidents/{incident_id}"
    evidence = {
        "metrics": payload.get("metrics") or {},
        "dependencies": payload.get("dependencies") or {},
        "initial_evidence": payload.get("initial_evidence") or [],
    }
    evidence_json = json.dumps(evidence, indent=2, ensure_ascii=False, default=str)
    fault_type = payload.get("fault_type") or "unknown"
    severity = payload.get("severity") or payload.get("severity_label") or "unknown"
    return f"""{MONITORING_MARKER}
<!-- opsswarm-deduplication-key: {key} -->
<!-- opsswarm-correlation-key: {correlation_key} -->

## Incident

### Service
{payload.get('service', 'unknown')}

### Symptoms
{payload.get('symptom', 'Monitoring alert')}

### Customer impact
{payload.get('customer_impact', 'unknown')}

### Environment
{payload.get('environment', 'production')}

### Observed since
{payload.get('observed_since', 'unknown')}

### Severity
{severity}

### IncidentLab Run ID
{run_id}

### Incident ID
{incident_id}

### Scenario ID
{scenario_id}

### Fault type
{fault_type}

### Correlation key
{correlation_key}

### Deduplication key
{key}

### Initial evidence
```json
{evidence_json}
```

### IncidentLab reference
{reference}

### OpsSwarm orchestration status
WAITING_FOR_GITHUB_WEBHOOK_OR_POLL

### Control policy
- GitHub Issue: system of record for this incident
- Investigation: read-only by default
- Agent recommendations: never execution authority
- Risky writes: require explicit /opsswarm approve <option-id> from an authorized maintainer
- Free-text comments: information only; they never authorize side effects
- Successful recovery: closes this Issue only after independent S7 verification

### Operator commands
/opsswarm investigate <read-only request>
/opsswarm provide <operational context>
/opsswarm approve <option-id>
/opsswarm reject
/opsswarm resume
/opsswarm abort

This Issue was created automatically from a stateful IncidentLab monitoring event. Repeated alerts for the same correlation identity must update this Issue rather than create another incident Issue.
"""


class MonitoringIssueRegistry:
    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "monitoring-issues.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            log_event("ISSUE_REGISTRY_WARNING", error_type=type(exc).__name__, error=str(exc))
            return {}

    def find_active(self, correlation_key: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._load()
            for value in data.values():
                if not isinstance(value, dict):
                    continue
                if value.get("correlation_key") != correlation_key:
                    continue
                if str(value.get("status") or "ACTIVE").upper() == "ACTIVE":
                    return dict(value)
            return None

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._load().get(key)
            return dict(value) if isinstance(value, dict) else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            data = self._load()
            data[key] = value
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            tmp.replace(self.path)

    def mark_status(self, issue_number: int, status: str) -> bool:
        with self._lock:
            data = self._load()
            changed = False
            for key, value in data.items():
                if isinstance(value, dict) and int(value.get("issue_number") or 0) == int(issue_number):
                    value["status"] = status.upper()
                    data[key] = value
                    changed = True
            if changed:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
                tmp.replace(self.path)
            return changed


class ProcessedCommentRegistry:
    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "processed-github-comments.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _load(self) -> set[int]:
        if not self.path.exists():
            return set()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {int(x) for x in data} if isinstance(data, list) else set()
        except Exception as exc:
            log_event("COMMENT_REGISTRY_WARNING", error_type=type(exc).__name__, error=str(exc))
            return set()

    def contains(self, comment_id: int) -> bool:
        with self._lock:
            return int(comment_id) in self._load()

    def add(self, comment_id: int) -> None:
        with self._lock:
            values = self._load()
            values.add(int(comment_id))
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(sorted(values), indent=2), encoding="utf-8")
            tmp.replace(self.path)
