"""Model management tools for FDTD MCP Server."""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_model_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD model/project file management tools."""

    @mcp.tool()
    def fdtd_save(file_path: Optional[str] = None) -> dict:
        """
        Save the current FDTD project to an .fsp file.

        Uses a fixed file path to avoid Lumerical popup dialogs.
        If no path given, saves to the default location (fdtd_project.fsp in working dir).

        Args:
            file_path: Path to save the .fsp file on Windows.

        Returns:
            Save confirmation with file path, or error.
        """
        return rpc.file_save(file_path)

    @mcp.tool()
    def fdtd_load(file_path: str) -> dict:
        """
        Load an existing .fsp project file.

        Args:
            file_path: Path to the .fsp file on the Windows machine.

        Returns:
            Load confirmation or error.
        """
        return rpc.file_load(file_path)
