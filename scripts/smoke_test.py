"""
Smoke test — verify the Mac → Windows FDTD RPC control chain.

Tests the actual Windows RPC API (metasurface sweep pipeline):
  1. Health check
  2. Session start (FDTD + MATLAB)
  3. Sweep config (quick test params)
  4. Sweep run (phases 1+2+3, skip MATLAB postprocess)
  5. Poll status until done
  6. List & download results
  7. Session close

Usage:
    # Direct (same LAN):
    python scripts/smoke_test.py --rpc http://192.168.31.26:5001

    # Via SSH tunnel:
    ssh -L 5001:localhost:5001 32482@192.168.31.26
    python scripts/smoke_test.py --rpc http://localhost:5001
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rpc_client.client import RpcClient


def log(step: str, result: dict) -> bool:
    # Handle both formats: {"ok": true} and {"status": "ok"}
    ok = result.get("ok") or result.get("status") == "ok"
    status = "PASS" if ok else "FAIL"
    msg = result.get("message", result.get("error", ""))
    if not msg and result.get("fdtd_connected") is not None:
        msg = f"FDTD={result.get('fdtd_connected')}, MATLAB={result.get('matlab_connected')}"
    print(f"  [{status}] {step}: {msg}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="FDTD Smoke Test")
    parser.add_argument("--rpc", default="http://localhost:5002", help="RPC server URL")
    parser.add_argument("--full", action="store_true", help="Run full sweep (slow)")
    parser.add_argument("--headless", action="store_true", help="Start FDTD in headless mode (hide=True)")
    parser.add_argument("--pause", type=float, default=0, help="Pause N seconds for GUI inspection before sweep")
    args = parser.parse_args()

    client = RpcClient(args.rpc, timeout=120.0)
    print(f"FDTD Smoke Test → {args.rpc}")
    print("=" * 55)

    # ---- 1. Health ----
    print("\n[1/7] Health check...")
    h = client.health()
    if not log("Health", h):
        print("  RPC Server unreachable. Start it on Windows first.")
        sys.exit(1)
    print(f"       FDTD connected: {h.get('fdtd_connected')}")
    print(f"       MATLAB connected: {h.get('matlab_connected')}")

    # ---- 2. Start session (skip if already running) ----
    print("\n[2/7] Starting FDTD + MATLAB...")
    if h.get("fdtd_connected") and h.get("matlab_connected"):
        print("  [SKIP] Session already running.")
    else:
        r = client.session_start()
        if not log("Session start", r):
            sys.exit(1)

    # ---- 3. Configure quick sweep ----
    print("\n[3/7] Configuring quick test sweep...")
    if args.full:
        cfg = {"SWEEP_Y_AXIS": "period", "RATIO_PTS": 5, "PERIOD_PTS": 3, "FDTD_PROCESSES": 1, "FDTD_CAPACITY": 3}
    else:
        cfg = {"SWEEP_Y_AXIS": "period", "RATIO_PTS": 2, "PERIOD_PTS": 2, "FDTD_PROCESSES": 1, "FDTD_CAPACITY": 1}
    r = client.sweep_config_set(cfg)
    log("Config", r)

    # ---- 3b. Pause for GUI inspection (optional) ----
    if args.pause > 0:
        print(f"\n[3b/7] Pausing {args.pause}s for GUI inspection...")
        r = client.session_pause(args.pause)
        log("Pause", r)

    # ---- 4. Run sweep ----
    phases = [1, 2, 3] if not args.full else None  # skip MATLAB phase for quick test
    print(f"\n[4/7] Running sweep (phases={phases or 'all'})...")
    r = client.sweep_run(phases=phases)
    if not log("Sweep start", r):
        sys.exit(1)
    task_id = r.get("task_id", "")
    print(f"       task_id: {task_id}")

    # ---- 5. Poll ----
    print("\n[5/7] Waiting for sweep to complete...")
    last_msg = ""
    done = False
    while not done:
        time.sleep(10)
        s = client.sweep_status(task_id)
        task = s.get("task", {})
        status = task.get("status", "unknown")
        msg = task.get("message", "")
        if msg and msg != last_msg:
            print(f"       [{status}] {msg}")
            last_msg = msg
        if status in ("done", "error"):
            done = True
            log("Sweep final", {"ok": status == "done", "message": msg})

    # ---- 6. Results ----
    print("\n[6/7] Results...")
    r = client.results_list()
    log("List", r)
    for dirname, files in r.get("files", {}).items():
        for f in files:
            print(f"       {dirname}/{f}")

    # Download a result if available
    figures = r.get("files", {}).get("figures", [])
    if figures:
        for f in figures[:2]:  # download first 2
            dr = client.results_download(f"figures/{f}")
            log(f"Download figures/{f}", dr)

    # ---- 7. Close ----
    print("\n[7/7] Closing session...")
    r = client.session_close()
    log("Session close", r)

    print("\n" + "=" * 55)
    print("Smoke test complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
