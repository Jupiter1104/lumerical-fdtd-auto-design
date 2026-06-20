"""Generic sweep tools for FDTD MCP Server.

Generic sweeps handle parameter sweeps that are not hard-coded to the
4-phase metasurface pipeline. These tools validate, plan, and start
generic parameter sweep jobs.
"""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def _sweep_placeholder(action: str, body: Optional[dict] = None) -> dict:
    """Placeholder for generic sweep engine (Task 1 stub)."""
    return {
        "ok": True,
        "action": action,
        "message": f"Generic sweep {action} stub — full engine in Task 2+",
        "body": body,
    }


def register_generic_sweep_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register generic parameter sweep tools."""

    @mcp.tool()
    def fdtd_generic_sweep_validate(body: dict) -> dict:
        """
        Validate a generic sweep specification.

        Checks sweep parameter ranges, step counts, and resource estimates.

        Args:
            body: Sweep specification.

        Returns:
            Validation result with warnings/errors.
        """
        return _sweep_placeholder("validate", body)

    @mcp.tool()
    def fdtd_generic_sweep_plan(body: dict) -> dict:
        """
        Plan a generic sweep job without running FDTD.

        Returns task count, estimated runtime, and job structure.

        Args:
            body: Sweep specification.

        Returns:
            Sweep plan with task breakdown.
        """
        return _sweep_placeholder("plan", body)

    @mcp.tool()
    def fdtd_generic_sweep_start(body: dict) -> dict:
        """
        Start a generic sweep job.

        Args:
            body: Sweep specification with optional approval.

        Returns:
            Job start confirmation with job_id.
        """
        return _sweep_placeholder("start", body)
