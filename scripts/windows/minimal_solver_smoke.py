#!/usr/bin/env python3
"""Windows minimal FDTD solver smoke test.

Runs a single fixed-structure FDTD model through the RPC server to verify
the full RPC→lumapi→solve→result chain works end-to-end.

This is a TECHNICAL SMOKE test only — it does NOT produce physical conclusions.
The report MUST be marked technical_smoke=true, physical_conclusion=false.

Usage (Windows CMD):
    "F:\\Program Files\\Lumerical\\v242\\python\\python.exe" scripts\\windows\\minimal_solver_smoke.py --rpc http://127.0.0.1:5000 --output "%LOCALAPPDATA%\\fdtd-mcp\\smoke"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print(json.dumps({"ok": False, "error": "requests not installed"}))
    sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Windows minimal FDTD solver smoke (technical only, no physical conclusion)"
    )
    parser.add_argument("--rpc", required=True, help="RPC server URL, e.g. http://127.0.0.1:5000")
    parser.add_argument("--output", required=True, help="Smoke output directory")
    args = parser.parse_args()

    rpc_url: str = args.rpc.rstrip("/")
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "technical_smoke": True,
        "physical_conclusion": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
        "ok": False,
    }

    def record_step(name: str, success: bool, detail: dict = None):
        report["steps"].append({
            "step": name,
            "success": success,
            "detail": detail or {},
        })

    # Step 1: health check
    try:
        resp = requests.get(f"{rpc_url}/health", timeout=5)
        health = resp.json()
        record_step("health", health.get("ok", False), health)
    except Exception as exc:
        record_step("health", False, {"error": str(exc)})
        report["ok"] = False
        _write_report(output_dir, report)
        return 1

    # Step 2: start session
    try:
        resp = requests.post(f"{rpc_url}/session/start", json={"hide": True}, timeout=15)
        session = resp.json()
        record_step("session_start", session.get("ok", False), {"api_version": session.get("api_version")})
    except Exception as exc:
        record_step("session_start", False, {"error": str(exc)})
        report["ok"] = False
        _write_report(output_dir, report)
        return 1

    # Step 3: create new project
    try:
        resp = requests.post(f"{rpc_url}/project/new", json={"name": "smoke_test", "discard_unsaved": True}, timeout=10)
        record_step("project_new", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("project_new", False, {"error": str(exc)})

    # Step 4: create one fixed structure (silicon rectangle)
    try:
        resp = requests.post(f"{rpc_url}/objects", json={
            "object_type": "rectangle", "name": "si_block",
            "properties": {"x span": 1e-6, "y span": 1e-6, "z span": 0.5e-6, "material": "Si (Silicon) - Palik"},
            "dry_run": False,
        }, timeout=10)
        record_step("object_create", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("object_create", False, {"error": str(exc)})

    # Step 5: create one FDTD region
    try:
        resp = requests.post(f"{rpc_url}/objects", json={
            "object_type": "fdtd_region", "name": "fdtd",
            "properties": {"x span": 2e-6, "y span": 2e-6, "z span": 1.5e-6},
            "dry_run": False,
        }, timeout=10)
        record_step("fdtd_region", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("fdtd_region", False, {"error": str(exc)})

    # Step 6: create one source
    try:
        resp = requests.post(f"{rpc_url}/sources", json={
            "source_type": "plane_source", "name": "src",
            "properties": {"wavelength start": 1.5e-6, "wavelength stop": 1.6e-6},
            "dry_run": False,
        }, timeout=10)
        record_step("source_create", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("source_create", False, {"error": str(exc)})

    # Step 7: create one monitor
    try:
        resp = requests.post(f"{rpc_url}/monitors", json={
            "monitor_type": "power_monitor", "name": "mon",
            "properties": {"frequency points": 5},
            "dry_run": False,
        }, timeout=10)
        record_step("monitor_create", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("monitor_create", False, {"error": str(exc)})

    # Step 8: create one analysis group
    try:
        resp = requests.post(f"{rpc_url}/analysis-groups", json={
            "name": "analysis",
            "properties": {"script": "T=1;"},
            "dry_run": False,
        }, timeout=10)
        record_step("analysis_group_create", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("analysis_group_create", False, {"error": str(exc)})

    # Step 9: run simulation once
    try:
        resp = requests.post(f"{rpc_url}/simulation/run", json={}, timeout=120)
        record_step("simulation_run", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("simulation_run", False, {"error": str(exc)})

    time.sleep(0.5)

    # Step 10: check simulation status
    try:
        resp = requests.get(f"{rpc_url}/simulation/status", timeout=5)
        record_step("simulation_status", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("simulation_status", False, {"error": str(exc)})

    # Step 11: save project to .fsp
    smoke_fsp = output_dir / "smoke_model.fsp"
    try:
        resp = requests.post(f"{rpc_url}/project/save", json={"path": str(smoke_fsp)}, timeout=10)
        record_step("project_save", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("project_save", False, {"error": str(exc)})

    # Step 12: list results
    try:
        resp = requests.get(f"{rpc_url}/results", timeout=5)
        record_step("result_list", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("result_list", False, {"error": str(exc)})

    # Step 13: read one result value
    try:
        resp = requests.get(f"{rpc_url}/results/mon/T/value", timeout=5)
        record_step("result_read_value", resp.json().get("ok", False), resp.json())
    except Exception as exc:
        record_step("result_read_value", False, {"error": str(exc)})

    # Step 14: download result file
    try:
        resp = requests.get(f"{rpc_url}/results/smoke_report.json", timeout=5)
        if resp.status_code == 200:
            dl_path = output_dir / "downloaded_results.json"
            dl_path.write_bytes(resp.content)
            record_step("result_download", True, {"path": str(dl_path), "size": len(resp.content)})
        else:
            record_step("result_download", False, {"http_status": resp.status_code})
    except Exception as exc:
        record_step("result_download", False, {"error": str(exc)})

    # Final: determine overall status
    all_ok = all(s["success"] for s in report["steps"])
    report["ok"] = all_ok
    report["finished_at"] = datetime.now(timezone.utc).isoformat()

    # Write structured result file
    result_path = output_dir / "smoke_report.json"
    _write_report_to(report, result_path)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


def _write_report(output_dir: Path, report: dict):
    _write_report_to(report, output_dir / "smoke_report.json")


def _write_report_to(report: dict, path: Path):
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
