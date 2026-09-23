from pathlib import Path
import yaml


def test_prometheus_config_has_alertmanager_and_rules():
    cfg = yaml.safe_load(Path("infrastructure/prometheus.yml").read_text())
    assert cfg["rule_files"]
    targets = cfg["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    assert "alertmanager:9093" in targets
    jobs = {x["job_name"] for x in cfg["scrape_configs"]}
    assert {"demomart", "opsswarm"}.issubset(jobs)
    demomart = next(x for x in cfg["scrape_configs"] if x["job_name"] == "demomart")
    targets = demomart["static_configs"][0]["targets"]
    assert len(targets) == 5
    assert "booking-api:8000" in targets
    opsswarm = next(x for x in cfg["scrape_configs"] if x["job_name"] == "opsswarm")
    assert "opsswarm:8080" in opsswarm["static_configs"][0]["targets"]


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
    assert webhook == "http://opsswarm:8080/api/v1/alertmanager"

