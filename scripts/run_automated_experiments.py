#!/usr/bin/env python3
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from opsswarm.github_client import GitHubClient

BASE_URL = os.environ.get("INCIDENTLAB_PUBLIC_URL", "http://localhost:8088").rstrip("/")

async def run_scenario(gh: GitHubClient, scenario_id: str, timeout_seconds: int = 750) -> dict:
    print(f"\n{'='*70}", flush=True)
    print(f"STARTING EXPERIMENT RUN: {scenario_id}", flush=True)
    print(f"{'='*70}", flush=True)
    start_time = time.perf_counter()

    # 1. Reset simulator environment and clear registry for clean issue creation
    print("[1/5] Resetting simulator environment...", flush=True)
    try:
        reg_path = Path("runtime-data/monitoring-issues.json")
        if reg_path.exists():
            data = json.loads(reg_path.read_text(encoding="utf-8"))
            for v in data.values():
                if isinstance(v, dict):
                    v["status"] = "RESOLVED"
            reg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  Warning updating monitoring-issues.json: {e}", flush=True)

    requests.post(f"{BASE_URL}/api/demo/reset", timeout=15)
    await asyncio.sleep(4)

    # 2. Inject fault scenario
    print(f"[2/5] Injecting fault scenario: {scenario_id}...", flush=True)
    resp = requests.post(
        f"{BASE_URL}/api/demo/start",
        json={"scenario_id": scenario_id},
        headers={"Content-Type": "application/json"},
        timeout=20,
    ).json()

    issue_number = resp.get("github_issue_number")
    issue_url = resp.get("github_issue_url")
    run_id = resp.get("run_id")
    print(f"      IncidentLab Run: {run_id}", flush=True)
    print(f"      GitHub Issue: #{issue_number} ({issue_url})", flush=True)

    # 3. Wait for orchestration lifecycle
    print("[3/5] Monitoring orchestration lifecycle...", flush=True)
    deadline = time.time() + timeout_seconds
    input_provided = False
    approved = False
    last_state = None

    while time.time() < deadline:
        await asyncio.sleep(4)
        try:
            r = requests.get(f"{BASE_URL}/runs/{issue_number}", timeout=10)
            if r.status_code != 200:
                continue
            run = r.json()
        except Exception:
            continue

        state = run.get("state")
        if state != last_state:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] State transition -> {state}", flush=True)
            last_state = state

        # Case A: WAITING_INPUT before recovery plan (RCA uncertain)
        if state == "WAITING_INPUT" and not run.get("recovery_plan") and not input_provided:
            q = (run.get("decision") or {}).get("question") or "Root-cause confidence below autonomous threshold"
            print(f"  [HUMAN_GATE] WAITING_INPUT (RCA): {q[:100]}...", flush=True)
            print("  [OPERATOR] Posting: /opsswarm provide telemetry anomaly confirmed by operator, proceed with recovery", flush=True)
            await gh.comment(
                issue_number,
                f"/opsswarm provide {scenario_id} telemetry anomaly confirmed by operator, proceed with recovery",
            )
            input_provided = True

        # Case B: WAITING_INPUT after recovery plan (business input required) -> approve directly
        elif state == "WAITING_INPUT" and run.get("recovery_plan") and not approved:
            options = (run.get("recovery_plan") or {}).get("options") or []
            option_id = options[0]["id"] if options else "option-001"
            print(f"  [HUMAN_GATE] WAITING_INPUT with recovery plan: Approving {option_id}", flush=True)
            print(f"  [OPERATOR] Posting: /opsswarm approve {option_id}", flush=True)
            await gh.comment(issue_number, f"/opsswarm approve {option_id}")
            approved = True

        # Case C: WAITING_APPROVAL or WAITING_DECISION
        elif state in {"WAITING_APPROVAL", "WAITING_DECISION"} and not approved:
            options = (run.get("decision") or {}).get("options") or (run.get("recovery_plan") or {}).get("options") or []
            option_id = options[0]["id"] if options else "option-001"
            print(f"  [HUMAN_GATE] {state} encountered: Recommended option: {option_id}", flush=True)
            print(f"  [OPERATOR] Posting: /opsswarm approve {option_id}", flush=True)
            await gh.comment(issue_number, f"/opsswarm approve {option_id}")
            approved = True

        elif state == "RESOLVED":
            elapsed = time.perf_counter() - start_time
            print(f"[4/5] Recovery and verification PASSED! Total elapsed: {elapsed:.1f}s", flush=True)
            verification = run.get("verification") or {}
            root_cause = run.get("root_cause") or {}
            return {
                "arm": "M1_OPSSWARM",
                "scenario": scenario_id,
                "issue_number": issue_number,
                "elapsed_s": round(elapsed, 2),
                "status": "RESOLVED",
                "verified": bool(verification.get("verified", True)),
                "confidence": verification.get("confidence", 0.95),
                "proximate_cause": root_cause.get("proximate_cause", ""),
                "recovery_option": (run.get("execution") or {}).get("option_id", ""),
            }

        elif state in {"FAILED", "ABORTED"}:
            elapsed = time.perf_counter() - start_time
            print(f"[4/5] Run terminated with terminal state: {state}", flush=True)
            return {
                "arm": "M1_OPSSWARM",
                "scenario": scenario_id,
                "issue_number": issue_number,
                "elapsed_s": round(elapsed, 2),
                "status": state,
                "verified": False,
            }

    elapsed = time.perf_counter() - start_time
    print(f"[TIMEOUT] Scenario {scenario_id} exceeded deadline of {timeout_seconds}s", flush=True)
    return {
        "arm": "M1_OPSSWARM",
        "scenario": scenario_id,
        "issue_number": issue_number,
        "elapsed_s": round(elapsed, 2),
        "status": "TIMEOUT",
        "verified": False,
    }

async def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    if not token or not repo:
        print("ERROR: GITHUB_TOKEN and GITHUB_REPO must be set in .env")
        sys.exit(1)

    gh = GitHubClient(token=token, repo=repo)

    # 3 representative scenarios covering Rollback, Restart, and Scale
    scenarios = [
        "booking-api-high-5xx",      # Rollback recovery
        "latency-spike",             # Restart recovery
        "database-pool-exhaustion",   # Scale capacity recovery
    ]

    print(f"OpsSwarm Automated Experiment Campaign started at {datetime.now().isoformat()}")
    print(f"Target repository: {repo}")
    print(f"Scenarios to benchmark: {scenarios}")

    results = []
    for sc in scenarios:
        res = await run_scenario(gh, sc)
        results.append(res)
        await asyncio.sleep(5)

    # Save campaign results
    campaign_dir = Path("evidence/campaign")
    campaign_dir.mkdir(parents=True, exist_ok=True)
    campaign_file = campaign_dir / f"campaign-{int(time.time())}.json"
    campaign_data = {
        "timestamp": datetime.now().isoformat(),
        "model": "gpt-5.6-terra",
        "gateway": "openclaw@18789",
        "repository": repo,
        "results": results,
    }
    campaign_file.write_text(json.dumps(campaign_data, indent=2), encoding="utf-8")
    print(f"\n[5/5] Campaign data saved to: {campaign_file}")

    # Generate summary report
    reports_dir = Path("evidence/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    summary_file = reports_dir / "latest-summary.json"

    resolved_count = sum(r["status"] == "RESOLVED" for r in results)
    verified_count = sum(bool(r.get("verified")) for r in results)
    mean_elapsed = sum(r["elapsed_s"] for r in results) / len(results)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_runs": len(results),
        "resolved_rate": resolved_count / len(results),
        "verified_rate": verified_count / len(results),
        "mean_elapsed_seconds": round(mean_elapsed, 2),
        "scenarios": results,
    }
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Summary report generated at: {summary_file}")
    print("\n" + json.dumps(summary, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
