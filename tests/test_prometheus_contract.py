from pathlib import Path
import yaml


def test_prometheus_config_has_alertmanager_and_rules():
    cfg = yaml.safe_load(Path("infrastructure/prometheus.yml").read_text())
    assert cfg["rule_files"]
    targets = cfg["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    assert "alertmanager:9093" in targets
    jobs = {x["job_name"] for x in cfg["scrape_configs"]}
    assert {"demomart", "opsswarm"}.issubset(jobs)


def test_alert_rules_cover_core_faults():
    cfg = yaml.safe_load(Path("infrastructure/alerts.yml").read_text())
    names = {r["alert"] for g in cfg["groups"] for r in g["rules"]}
    assert {
        "DemoMartServiceUnhealthy",
        "DemoMartHighErrorRate",
        "DemoMartHighLatency",
        "DemoMartHighCPU",
        "DemoMartHighMemory",
        "DemoMartTelemetryMissing",
    }.issubset(names)


def test_alertmanager_routes_to_opsswarm():
    cfg = yaml.safe_load(Path("infrastructure/alertmanager.yml").read_text())
    webhook = cfg["receivers"][0]["webhook_configs"][0]["url"]
    assert webhook == "http://host.docker.internal:8088/api/v1/alertmanager"

