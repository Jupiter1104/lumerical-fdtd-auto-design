"""Persistent job tools for FDTD MCP Server."""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


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
