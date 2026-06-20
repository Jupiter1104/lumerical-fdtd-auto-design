"""Project management tools for FDTD MCP Server."""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_project_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD project lifecycle tools."""

    @mcp.tool()
    def fdtd_project_new(body: Optional[dict] = None) -> dict:
        """
        Create a new FDTD project.

        Args:
            body: Optional project configuration.

        Returns:
            Project creation confirmation.
        """
        return rpc.project_new(body)

    @mcp.tool()
    def fdtd_project_load(file_path: str) -> dict:
        """
        Load an existing .fsp project file.

        Args:
            file_path: Path to the .fsp file on the Windows machine.

        Returns:
            Load confirmation.
        """
        return rpc.project_load(file_path)

    @mcp.tool()
    def fdtd_project_save(file_path: Optional[str] = None) -> dict:
        """
        Save the current FDTD project.

        Args:
            file_path: Optional save path on Windows.

        Returns:
            Save confirmation.
        """
        return rpc.project_save(file_path)

    @mcp.tool()
    def fdtd_project_status(dry_run: bool = False) -> dict:
        """
        Get the current project status.

        Args:
            dry_run: If True, return a mock status without calling RPC.

        Returns:
            Project metadata and state.
        """
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "project": None,
                "status": "mock_no_rpc",
                "message": "Dry-run: no RPC call made.",
            }
        return rpc.project_status()

    @mcp.tool()
    def fdtd_switch_to_layout() -> dict:
        """
        Switch the FDTD GUI to layout mode.

        Returns:
            Switch confirmation.
        """
        return rpc.switch_to_layout()
