"""Persistent job tools for FDTD MCP Server."""

from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient

DEFAULT_RATIO_LIST = [0.2, 0.8]
DEFAULT_PERIOD_LIST = [390e-9, 540e-9]
DEFAULT_PHASES = [1, 2, 3, 4]
DEFAULT_TEMPLATE = "templates/metasurface/base_model.fsp"


def _approval_required_error() -> dict:
    return {
        "ok": False,
        "error": {
            "type": "approval_required",
            "message": "Real metasurface sweeps require approved=True.",
            "details": {"approved_for": "real_run"},
        },
    }


def build_metasurface_sweep_request(
    *,
    mode: str = "mock",
    ratio_list: Optional[List[float]] = None,
    period_list: Optional[List[float]] = None,
    base_height: float = 700e-9,
    base_period: float = 470e-9,
    phases: Optional[List[int]] = None,
    template: str = DEFAULT_TEMPLATE,
    include_models: bool = False,
    approved: bool = False,
) -> dict:
    """Build the RPC API v1 request for a metasurface sweep job."""
    if mode not in {"mock", "real", "plan"}:
        return {
            "ok": False,
            "error": {
                "type": "validation_error",
                "message": "mode must be one of plan, mock, or real.",
                "details": {"mode": mode},
            },
        }
    if mode == "real" and approved is not True:
        return _approval_required_error()

    request = {
        "mode": mode,
        "job_type": "metasurface-sweep",
        "sweep": {
            "template": template,
            "phases": phases or DEFAULT_PHASES,
            "hide": True,
            "include_models": include_models,
            "config": {
                "SWEEP_Y_AXIS": "period",
                "RATIO_LIST": ratio_list or DEFAULT_RATIO_LIST,
                "PERIOD_LIST": period_list or DEFAULT_PERIOD_LIST,
                "BASE_HEIGHT": base_height,
                "BASE_PERIOD": base_period,
                "FDTD_PROCESSES": 1,
                "FDTD_CAPACITY": 1,
                "EXPRESS_MODE": 0,
            },
        },
    }
    if mode == "real":
        request["approval"] = {"approved": True, "approved_for": "real_run"}
    return request


def register_job_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register RPC API v1 persistent job tools."""

    @mcp.tool()
    def fdtd_job_plan(request: dict) -> dict:
        """
        Create a persistent planned job without running FDTD.

        Use this before real runs to preview task count, job paths, and request
        shape. For natural-language workflows this is the safe first step.
        """
        return rpc.jobs_plan(request)

    @mcp.tool()
    def fdtd_job_start(request: dict) -> dict:
        """
        Start a mock or real persistent job through RPC API v1 `/jobs/start`.

        Real jobs require explicit human approval in the request:
        {"approval": {"approved": true, "approved_for": "real_run"}}.
        Long real jobs may return immediately with a job_id; poll with
        fdtd_job_status() and fdtd_job_tasks().
        """
        return rpc.jobs_start(request)

    @mcp.tool()
    def fdtd_job_status(job_id: str) -> dict:
        """Read manifest, status, and summary for a persistent job."""
        return rpc.jobs_get(job_id)

    @mcp.tool()
    def fdtd_job_tasks(job_id: str) -> dict:
        """Read per-task state for a persistent job."""
        return rpc.jobs_tasks(job_id)

    @mcp.tool()
    def fdtd_job_resume(job_id: str, request: Optional[dict] = None) -> dict:
        """
        Resume pending or failed tasks for a persistent job.

        Use only when the user explicitly asks to resume. Resume must not
        change physical settings, mesh, boundary conditions, template, or
        sweep ranges.
        """
        return rpc.jobs_resume(job_id, request)

    @mcp.tool()
    def fdtd_metasurface_sweep_plan(
        ratio_list: Optional[List[float]] = None,
        period_list: Optional[List[float]] = None,
        base_height: float = 700e-9,
        base_period: float = 470e-9,
        phases: Optional[List[int]] = None,
        template: str = DEFAULT_TEMPLATE,
        include_models: bool = False,
    ) -> dict:
        """
        Plan a metasurface sweep job without running FDTD.

        Defaults to a safe 2x2 CPU grid. Use this to preview task count,
        template path, output directories, and request shape before mock or
        real execution.
        """
        request = build_metasurface_sweep_request(
            mode="plan",
            ratio_list=ratio_list,
            period_list=period_list,
            base_height=base_height,
            base_period=base_period,
            phases=phases,
            template=template,
            include_models=include_models,
            approved=False,
        )
        return rpc.jobs_plan(request)

    @mcp.tool()
    def fdtd_metasurface_sweep_start(
        mode: str = "mock",
        ratio_list: Optional[List[float]] = None,
        period_list: Optional[List[float]] = None,
        base_height: float = 700e-9,
        base_period: float = 470e-9,
        phases: Optional[List[int]] = None,
        template: str = DEFAULT_TEMPLATE,
        include_models: bool = False,
        approved: bool = False,
    ) -> dict:
        """
        Start a mock or real metasurface sweep job through `/jobs/start`.

        The default mode is mock. For real FDTD execution, first present a
        run summary to the user and only call with mode="real" and
        approved=True after explicit approval. This tool uses CPU defaults:
        EXPRESS_MODE=0, FDTD_PROCESSES=1, FDTD_CAPACITY=1.
        """
        request = build_metasurface_sweep_request(
            mode=mode,
            ratio_list=ratio_list,
            period_list=period_list,
            base_height=base_height,
            base_period=base_period,
            phases=phases,
            template=template,
            include_models=include_models,
            approved=approved,
        )
        if request.get("ok") is False:
            return request
        return rpc.jobs_start(request)
