"""Solver, mesh, and simulation execution tools for FDTD MCP Server."""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_solver_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD solver, mesh, and simulation tools."""

    @mcp.tool()
    def fdtd_solver_get() -> dict:
        """
        Get current solver configuration.

        Returns:
            Solver settings (boundary conditions, simulation time, etc.).
        """
        return rpc.solver_get()

    @mcp.tool()
    def fdtd_solver_update(body: dict) -> dict:
        """
        Update solver configuration.

        Args:
            body: Solver settings to update.

        Returns:
            Update confirmation.
        """
        return rpc.solver_update(body)

    @mcp.tool()
    def fdtd_mesh_diagnose() -> dict:
        """
        Diagnose mesh quality for the current simulation.

        Returns:
            Mesh quality report (cell count, smallest cell, staircasing warnings).
        """
        return rpc.mesh_diagnose()

    @mcp.tool()
    def fdtd_resource_estimate() -> dict:
        """
        Estimate computational resources needed for the current simulation.

        Returns:
            Estimated memory, time, and CPU requirements.
        """
        return rpc.resource_estimate()

    @mcp.tool()
    def fdtd_simulation_run() -> dict:
        """
        Run the FDTD simulation.

        The simulation must be fully configured (region, sources, monitors)
        before calling this tool.

        Returns:
            Simulation completion status and run statistics.
        """
        return rpc.run()

    @mcp.tool()
    def fdtd_simulation_status() -> dict:
        """
        Get the current simulation status.

        Returns:
            Status (idle, running, done, error) and progress information.
        """
        return rpc.status()
