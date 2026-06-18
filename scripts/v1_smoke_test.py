"""Real Windows smoke test for RPC API v1.

This opens a visible FDTD session, creates minimal geometry, saves an .fsp
artifact, verifies one deprecated route, and closes the session. It does not
run the solver.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rpc_client.client import RpcClient


class SmokeFailure(RuntimeError):
    pass


def _describe_error(result: dict) -> str:
    error = result.get("error", {})
    if isinstance(error, dict):
        return f"{error.get('type', 'error')}: {error.get('message', '')}"
    return str(error)


def _require(step: str, result: dict) -> dict:
    if result.get("ok") is not True:
        raise SmokeFailure(f"{step} failed: {_describe_error(result)}")
    print(f"[PASS] {step}")
    return result


def _legacy_stop(
    base_url: str,
    timeout: float,
    post: Callable = requests.post,
) -> dict:
    try:
        response = post(
            f"{base_url}/session/stop",
            json={},
            timeout=timeout,
        )
        return response.json()
    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": {
                "type": "request_error",
                "message": str(exc),
                "details": {},
            },
        }
    except ValueError:
        return {
            "ok": False,
            "error": {
                "type": "invalid_response",
                "message": "Legacy stop returned non-JSON content.",
                "details": {},
            },
        }


def run_smoke(
    base_url: str,
    output_dir: Path,
    *,
    timeout: float = 60.0,
    client: Optional[RpcClient] = None,
    legacy_stop: Optional[Callable[[], dict]] = None,
) -> Path:
    rpc = client or RpcClient(base_url, timeout=timeout)
    session_open = False

    try:
        health = _require("health", rpc.health())
        if health.get("api_version") != "v1":
            raise SmokeFailure(
                f"health returned api_version={health.get('api_version')!r}, expected 'v1'"
            )

        start = _require("session start (GUI)", rpc.session_start(hide=False))
        session_open = True
        print(f"       FDTD version: {start.get('version', 'unknown')}")

        status = _require("session status", rpc.status())
        if status.get("connected") is not True:
            raise SmokeFailure("status did not report connected=true")

        _require(
            "add FDTD region",
            rpc.addfdtd(
                dimension="3D",
                x=0.0,
                x_span=2e-6,
                y=0.0,
                y_span=2e-6,
                z=0.0,
                z_span=1e-6,
                mesh_accuracy=2,
            ),
        )
        _require(
            "add silicon rectangle",
            rpc.addrect(
                name="smoke_waveguide",
                x=0.0,
                x_span=1e-6,
                y=0.0,
                y_span=500e-9,
                z=0.0,
                z_span=220e-9,
                material="Si (Silicon) - Palik",
            ),
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        artifact = (
            output_dir
            / f"rpc_v1_smoke_{datetime.now().strftime('%Y%m%d_%H%M%S')}.fsp"
        ).resolve()
        saved = _require("save model", rpc.file_save(str(artifact)))
        saved_path = Path(saved.get("saved_to", artifact))
        if not saved_path.exists():
            raise SmokeFailure(f"Server reported save success but file is missing: {saved_path}")

        stop_result = (
            legacy_stop()
            if legacy_stop is not None
            else _legacy_stop(base_url, timeout)
        )
        _require("legacy /session/stop alias", stop_result)
        expected_meta = {
            "deprecated_route": "/session/stop",
            "use_instead": "/session/close",
        }
        if stop_result.get("meta") != expected_meta:
            raise SmokeFailure(
                f"legacy route metadata mismatch: {stop_result.get('meta')!r}"
            )
        session_open = False

        final_health = _require("final health", rpc.health())
        if final_health.get("connected") is not False:
            raise SmokeFailure("final health did not report connected=false")

        return saved_path
    finally:
        if session_open:
            close_result = rpc.session_close()
            if close_result.get("ok") is not True:
                print(
                    f"[WARN] cleanup close failed: {_describe_error(close_result)}",
                    file=sys.stderr,
                )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the real Windows RPC API v1 smoke test without solving."
    )
    parser.add_argument(
        "--rpc",
        default="http://127.0.0.1:5004",
        help="RPC Server URL (default: http://127.0.0.1:5004)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "smoke-output",
        help="Directory for the generated .fsp artifact.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-request timeout in seconds.",
    )
    args = parser.parse_args()

    print(f"RPC v1 smoke → {args.rpc}")
    try:
        artifact = run_smoke(
            args.rpc.rstrip("/"),
            args.output_dir,
            timeout=args.timeout,
        )
    except SmokeFailure as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(f"[PASS] Smoke complete: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
