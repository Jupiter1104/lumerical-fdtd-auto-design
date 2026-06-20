#!/usr/bin/env python3
"""Windows Object Library analysis group smoke test.

Performs a no-solve technical smoke that:
- Enumerates the live v242 Object Library catalog via /session/start.
- Submits a transmission analysis intent with require_builtin.
- Verifies probe → restore → setup → readback for the selected group.
- Saves the model and writes a structured report.

This script does NOT invoke any solver run or async job start endpoint.
The report MUST carry technical_smoke=true, physical_conclusion=false.

Usage (Windows CMD):
    "F:\\Program Files\\Lumerical\\v242\\python\\python.exe" ^
      scripts\\windows\\object_library_analysis_group_smoke.py ^
      --rpc http://127.0.0.1:5000 ^
      --output "%LOCALAPPDATA%\\fdtd-mcp\\object-library-smoke"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print(json.dumps({"ok": False, "error": "requests not installed"}))
    sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Windows Object Library analysis group smoke (no solve, technical only)"
    )
    parser.add_argument("--rpc", required=True, help="RPC server URL, e.g. http://127.0.0.1:5000")
    parser.add_argument("--output", required=True, help="Smoke output directory")
    parser.add_argument(
        "--intent-kind",
        default="transmission",
        help="Analysis intent kind (default: transmission)",
    )
    parser.add_argument(
        "--output-name",
        default="T",
        help="Expected output name in analysis results (default: T)",
    )
    parser.add_argument(
        "--script-id",
        default="",
        help="Explicit script_id to probe; must be verified by the RPC server against the live catalog",
    )
    args = parser.parse_args()

    rpc_url: str = args.rpc.rstrip("/")
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    intent_kind: str = args.intent_kind
    output_name: str = args.output_name
    explicit_script_id: str = args.script_id

    report = {
        "technical_smoke": True,
        "physical_conclusion": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "catalog_enumerated": False,
        "probe_restore_verified": False,
        "setup_verified": False,
        "ok": False,
    }

    # ---- Step 1: health ----------------------------------------------------
    try:
        resp = requests.get(f"{rpc_url}/health", timeout=5)
        health = resp.json()
        if not health.get("ok"):
            _fail(output_dir, report, f"health: {health}")
            return 1
    except Exception as exc:
        _fail(output_dir, report, f"health exception: {exc}")
        return 1

    # ---- Step 2: session/start (hide=true) ---------------------------------
    try:
        resp = requests.post(f"{rpc_url}/session/start", json={"hide": True}, timeout=30)
        session_payload = resp.json()
        if not session_payload.get("ok"):
            _fail(output_dir, report, f"session_start: {session_payload}")
            return 1
    except Exception as exc:
        _fail(output_dir, report, f"session_start exception: {exc}")
        return 1

    # ---- Step 3: catalog enumeration ---------------------------------------
    obj_lib = session_payload.get("object_library", {})
    script_id_count = obj_lib.get("script_id_count", 0)
    report["catalog_enumerated"] = script_id_count > 0
    catalog_identity = obj_lib.get("identity", "unknown")
    catalog_status = obj_lib.get("status", "unavailable")
    if not report["catalog_enumerated"]:
        _fail(
            output_dir,
            report,
            f"Object Library catalog empty: identity={catalog_identity!r}, "
            f"status={catalog_status!r}",
        )
        return 1

    # ---- Step 4: project/new -----------------------------------------------
    try:
        resp = requests.post(f"{rpc_url}/project/new", json={"name": "object_library_smoke", "discard_unsaved": True}, timeout=10)
        proj = resp.json()
        if not proj.get("ok"):
            _fail(output_dir, report, f"project_new: {proj}")
            return 1
    except Exception as exc:
        _fail(output_dir, report, f"project_new exception: {exc}")
        return 1

    # ---- Step 5: minimal FDTD region / source / monitor --------------------
    for step_label, route, body in _minimal_setup(intent_kind):
        try:
            resp = requests.post(f"{rpc_url}{route}", json=body, timeout=10)
            payload = resp.json()
            if not payload.get("ok"):
                _fail(output_dir, report, f"{step_label}: {payload}")
                return 1
        except Exception as exc:
            _fail(output_dir, report, f"{step_label} exception: {exc}")
            return 1

    # ---- Step 6: analysis-groups -------------------------------------------
    analysis_body = {
        "name": "object_library_smoke_analysis",
        "analysis_intent": {
            "kind": intent_kind,
            "outputs": [output_name],
        },
        "recipe_context": {
            "solver": {
                "x span": 1.2e-6,
                "y span": 1.2e-6,
                "z span": 1.0e-6,
            },
            "monitors": [{"type": "power_monitor", "name": "mon"}],
            "outputs": [output_name],
            "fom": {"result": output_name},
        },
        "parameter_overrides": {},
        "prefer_builtin": True,
        "require_builtin": True,
        "script_id": explicit_script_id,
        "properties": {},
        "dry_run": False,
    }
    try:
        resp = requests.post(f"{rpc_url}/analysis-groups", json=analysis_body, timeout=30)
        analysis_payload = resp.json()
        if not analysis_payload.get("ok"):
            _fail(
                output_dir,
                report,
                f"analysis-groups: {analysis_payload}",
            )
            return 1
    except Exception as exc:
        _fail(output_dir, report, f"analysis-groups exception: {exc}")
        return 1

    # ---- Step 7: derive report fields --------------------------------------
    report["probe_restore_verified"] = bool(
        analysis_payload.get("probe", {}).get("restore_verified")
    )
    report["setup_verified"] = bool(analysis_payload.get("setup_verified"))
    report["ok"] = all((
        report["catalog_enumerated"],
        report["probe_restore_verified"],
        report["setup_verified"],
        analysis_payload.get("source") == "builtin",
    ))

    report["finished_at"] = datetime.now(timezone.utc).isoformat()

    # ---- Step 8: project/save ----------------------------------------------
    model_path = output_dir / "object_library_model.fsp"
    try:
        resp = requests.post(f"{rpc_url}/project/save", json={"file_path": str(model_path)}, timeout=10)
        save_payload = resp.json()
        if not save_payload.get("ok"):
            report["error"] = f"project_save: {save_payload}"
            report["ok"] = False
    except Exception as exc:
        report["error"] = f"project_save exception: {exc}"
        report["ok"] = False

    # ---- Step 9: write report ----------------------------------------------
    report_path = output_dir / "object_library_smoke_report.json"
    _write_report_to(report, report_path)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _minimal_setup(intent_kind: str):
    """Return the minimal FDTD region, source and monitor steps.

    Only needed when the analysis intent requires a populated simulation
    context.  For a transmission intent we add an FDTD region, a plane
    source and a power monitor so the analysis script has something to
    configure against.
    """
    if intent_kind in ("transmission",):
        return [
            (
                "fdtd_region",
                "/geometry/fdtd-region",
                {
                    "dimension": "3D",
                    "x": 0.0,
                    "x span": 1.2e-6,
                    "y": 0.0,
                    "y span": 1.2e-6,
                    "z": 0.0,
                    "z span": 1.0e-6,
                    "mesh accuracy": 1,
                    "simulation time": 50e-15,
                    "auto shutoff min": 1e-3,
                },
            ),
            (
                "source_create",
                "/sources",
                {
                    "source_type": "plane_source",
                    "name": "source",
                    "properties": {
                        "injection axis": "z",
                        "direction": "backward",
                        "x span": 1.0e-6,
                        "y span": 1.0e-6,
                        "z": 0.45e-6,
                        "wavelength start": 1.5e-6,
                        "wavelength stop": 1.6e-6,
                    },
                    "dry_run": False,
                },
            ),
            (
                "monitor_create",
                "/monitors",
                {
                    "monitor_type": "power_monitor",
                    "name": "mon",
                    "properties": {
                        "x span": 1.0e-6,
                        "y span": 1.0e-6,
                        "z": -0.45e-6,
                        "frequency points": 5,
                    },
                    "dry_run": False,
                },
            ),
        ]
    return []


def _fail(output_dir: Path, report: dict, message: str):
    report["error"] = message
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_report_to(report, output_dir / "object_library_smoke_report.json")
    print(json.dumps(report, indent=2, ensure_ascii=False))


def _write_report_to(report: dict, path: Path):
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
