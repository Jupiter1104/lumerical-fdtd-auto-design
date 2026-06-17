"""
RPC Client — Mac 端 HTTP 客户端，封装对 Windows FDTD RPC Server 的调用。

对齐实际 Windows RPC API（v242 metasurface sweep pipeline）：
  - 返回格式: {"ok": true/false, ...}
  - 端点: /health, /session/start, /session/close, /sweep/*, /results/*

Usage:
    from src.rpc_client.client import RpcClient
    client = RpcClient("http://localhost:5001")
    h = client.health()
    r = client.session_start()
    r = client.sweep_run(phases=[1,2,3])
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


class RpcClient:
    """HTTP client for the Windows FDTD RPC Server (Autosweep pipeline)."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        try:
            resp = self._session.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.ConnectionError:
            return {"ok": False, "error": f"Cannot connect to {self.base_url}. Is RPC Server running?"}
        except requests.Timeout:
            return {"ok": False, "error": f"Request to {path} timed out ({self.timeout}s)."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _post(self, path: str, body: Optional[dict] = None) -> dict:
        try:
            resp = self._session.post(
                f"{self.base_url}{path}",
                json=body or {},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.ConnectionError:
            return {"ok": False, "error": f"Cannot connect to {self.base_url}. Is RPC Server running?"}
        except requests.Timeout:
            return {"ok": False, "error": f"Request to {path} timed out ({self.timeout}s)."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict:
        """GET /health — check server and session status."""
        return self._get("/health")

    # ------------------------------------------------------------------
    # Session (FDTD + MATLAB)
    # ------------------------------------------------------------------

    def session_start(self, hide: bool = False) -> dict:
        """POST /session/start — start FDTD + MATLAB Engine.

        Args:
            hide: If True, headless mode (for batch sweeps).
                  If False (default), GUI visible on Windows desktop (for debug/inspection).
        """
        return self._post("/session/start", {"hide": hide})

    def session_close(self) -> dict:
        """POST /session/close — close FDTD + MATLAB sessions."""
        return self._post("/session/close")

    def session_pause(self, seconds: float = 300.0) -> dict:
        """POST /session/pause — pause, keeping GUI open for manual inspection.

        Args:
            seconds: How long to pause (default: 300s).
                     Use a large value to keep the GUI open indefinitely.
        """
        return self._post("/session/pause", {"seconds": seconds})

    # ------------------------------------------------------------------
    # Sweep configuration
    # ------------------------------------------------------------------

    def sweep_config_get(self) -> dict:
        """GET /sweep/config — get current sweep configuration."""
        return self._get("/sweep/config")

    def sweep_config_set(self, config: dict) -> dict:
        """POST /sweep/config — update sweep parameters.

        Common keys:
          SWEEP_Y_AXIS: "height" | "period"
          RATIO_PTS, HEIGHT_PTS, PERIOD_PTS: number of sweep points
          BASE_HEIGHT, BASE_PERIOD, WAVELENGTH: physical defaults
          FDTD_PROCESSES, FDTD_CAPACITY: parallel solving settings
        """
        return self._post("/sweep/config", config)

    # ------------------------------------------------------------------
    # Sweep execution
    # ------------------------------------------------------------------

    def sweep_run(self, phases: Optional[List[int]] = None) -> dict:
        """POST /sweep/run — start sweep pipeline in background thread.

        Args:
            phases: Which phases to run, e.g. [1,2,3] or [1,2,3,4].
                    Phase 1: batch .fsp generation
                    Phase 2: parallel FDTD solving
                    Phase 3: S-parameter extraction → .mat
                    Phase 4: MATLAB post-process → heatmaps
                    Default (omitted): all 4 phases.

        Returns:
            {"ok": true, "task_id": "sweep_1234567890", "message": "Sweep started"}
        """
        body = {}
        if phases is not None:
            body["phases"] = phases
        return self._post("/sweep/run", body)

    def sweep_status(self, task_id: Optional[str] = None) -> dict:
        """GET /sweep/status?task_id=... — poll sweep progress.

        Returns:
            {"ok": true, "task": {"phase": "...", "status": "running"|"done"|"error", "message": "...", "elapsed": 0}}
        """
        params = {}
        if task_id:
            params["task_id"] = task_id
        return self._get("/sweep/status", params=params)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def results_list(self) -> dict:
        """GET /results — list files in results/ and figures/ directories."""
        return self._get("/results")

    def results_download(self, filepath: str, save_to: Optional[str] = None) -> dict:
        """GET /results/<path> — download a result file.

        Args:
            filepath: Path relative to server cwd, e.g. "figures/Transmission.svg"
            save_to: Local path to save. Defaults to basename of filepath.

        Returns:
            {"ok": true, "saved_to": "/local/path"} or error.
        """
        try:
            resp = self._session.get(
                f"{self.base_url}/results/{filepath}",
                timeout=max(self.timeout, 60.0),
                stream=True,
            )
            resp.raise_for_status()
            local_path = save_to or Path(filepath).name
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return {"ok": True, "saved_to": str(Path(local_path).resolve())}
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return {"ok": False, "error": f"File not found: {filepath}"}
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
