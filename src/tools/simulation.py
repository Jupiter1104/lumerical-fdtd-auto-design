"""Sweep pipeline tools for FDTD MCP Server.

Matches the Windows RPC sweep pipeline:
  Phase 1: batch .fsp generation from template
  Phase 2: parallel FDTD solving via Lumerical Job Manager
  Phase 3: S-parameter extraction → .mat file
  Phase 4: MATLAB post-process → heatmaps (Transmission.svg, Dephasing.svg)
"""

from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_simulation_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register sweep pipeline tools."""

    @mcp.tool()
    def fdtd_sweep_config_get() -> dict:
        """
        Get the current sweep configuration from the Windows RPC Server.

        Returns all sweep parameters: sweep axis, ranges, material settings,
        FDTD parallel processing settings, etc.

        Returns:
            {"ok": true, "config": {...}}
        """
        return rpc.sweep_config_get()

    @mcp.tool()
    def fdtd_sweep_config_set(
        sweep_y_axis: Optional[str] = None,
        ratio_pts: Optional[int] = None,
        height_pts: Optional[int] = None,
        period_pts: Optional[int] = None,
        base_period: Optional[float] = None,
        base_height: Optional[float] = None,
        wavelength: Optional[float] = None,
        fdtd_processes: Optional[int] = None,
        fdtd_capacity: Optional[int] = None,
    ) -> dict:
        """
        Update sweep configuration parameters on the Windows RPC Server.

        Only provide the parameters you want to change. Omitted parameters
        keep their current values.

        Args:
            sweep_y_axis: "height" or "period" — which variable to sweep on the Y axis
            ratio_pts: Number of duty-cycle ratio points (default 31)
            height_pts: Number of pillar height points (default 37)
            period_pts: Number of period points (default 5)
            base_period: Base period in meters (default 470e-9 for 810nm)
            base_height: Base pillar height in meters (default 700e-9)
            wavelength: Simulation wavelength in meters (default 810e-9)
            fdtd_processes: Number of FDTD processes (default 1)
            fdtd_capacity: Job manager capacity (default 6)

        Returns:
            {"ok": true, "config": {...updated config summary...}}
        """
        updates = {}
        if sweep_y_axis is not None:
            updates["SWEEP_Y_AXIS"] = sweep_y_axis
        if ratio_pts is not None:
            updates["RATIO_PTS"] = ratio_pts
        if height_pts is not None:
            updates["HEIGHT_PTS"] = height_pts
        if period_pts is not None:
            updates["PERIOD_PTS"] = period_pts
        if base_period is not None:
            updates["BASE_PERIOD"] = base_period
        if base_height is not None:
            updates["BASE_HEIGHT"] = base_height
        if wavelength is not None:
            updates["WAVELENGTH"] = wavelength
        if fdtd_processes is not None:
            updates["FDTD_PROCESSES"] = fdtd_processes
        if fdtd_capacity is not None:
            updates["FDTD_CAPACITY"] = fdtd_capacity
        return rpc.sweep_config_set(updates)

    @mcp.tool()
    def fdtd_sweep_run(phases: Optional[List[int]] = None) -> dict:
        """
        Start the sweep pipeline on the Windows machine.

        This runs in the background. Use fdtd_sweep_status() to monitor progress.

        The 4-phase pipeline:
          1. Batch .fsp generation — iterate parameters, save project files
          2. Parallel solving — Lumerical Job Manager handles scheduling
          3. Data extraction — run analysis, extract S-params, save .mat file
          4. MATLAB post-process — phase alignment, heatmap generation (.svg/.fig)

        Args:
            phases: Which phases to run, e.g. [1,2,3] or [1,2,3,4].
                    Default (empty) runs all 4 phases.
                    Use [1,2,3] to skip MATLAB post-processing.

        Returns:
            {"ok": true, "task_id": "sweep_1234567890", "message": "Sweep started"}
        """
        return rpc.sweep_run(phases)

    @mcp.tool()
    def fdtd_sweep_status(task_id: Optional[str] = None) -> dict:
        """
        Poll the status of a running sweep.

        Args:
            task_id: Task ID returned by fdtd_sweep_run(). If omitted,
                     returns the status of the most recent task.

        Returns:
            {"ok": true, "task": {"phase": "solving", "status": "running", "message": "...", "elapsed": 123.4}}
            Status values: "running", "done", "error"
        """
        return rpc.sweep_status(task_id)

    @mcp.tool()
    def fdtd_sweep_monitor(task_id: str, poll_interval: float = 15.0, max_wait: float = 3600.0) -> dict:
        """
        Monitor a sweep until completion, polling at regular intervals.

        This is a convenience wrapper around fdtd_sweep_status() that blocks
        until the sweep finishes, fails, or times out. Use for long-running
        sweeps where you want a single call rather than polling manually.

        Args:
            task_id: Task ID from fdtd_sweep_run().
            poll_interval: Seconds between status checks (default 15s).
            max_wait: Maximum total wait time in seconds (default 3600s = 1 hour).

        Returns:
            Final task status with results summary.
        """
        import time
        start = time.time()
        last_msg = ""
        while True:
            elapsed = time.time() - start
            if elapsed > max_wait:
                return {"ok": False, "error": f"Timeout after {max_wait}s. Sweep may still be running.", "task_id": task_id}

            resp = rpc.sweep_status(task_id)
            task = resp.get("task", {})
            status = task.get("status", "unknown")
            msg = task.get("message", "")

            if msg and msg != last_msg:
                # New progress message — report it
                pass
            last_msg = msg

            if status == "done":
                return {"ok": True, "task_id": task_id, "elapsed": elapsed, "message": msg}
            elif status == "error":
                return {"ok": False, "task_id": task_id, "elapsed": elapsed, "error": msg}

            time.sleep(poll_interval)
