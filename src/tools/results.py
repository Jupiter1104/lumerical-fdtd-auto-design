"""Result inspection and download tools for FDTD MCP Server."""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_result_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD result inspection and download tools."""

    @mcp.tool()
    def fdtd_result_list() -> dict:
        """
        List all available results from completed simulations.

        Returns:
            List of result names, types, and metadata.
        """
        return rpc.results_list()

    @mcp.tool()
    def fdtd_result_describe(name: str) -> dict:
        """
        Describe a specific result (dimensions, units, data shape).

        Args:
            name: Result name.

        Returns:
            Result metadata and structure description.
        """
        return rpc.result_describe(name)

    @mcp.tool()
    def fdtd_result_read(name: str, body: Optional[dict] = None) -> dict:
        """
        Read data from a specific result.

        Args:
            name: Result name.
            body: Optional read parameters (slice, ROI, etc.).

        Returns:
            Result data.
        """
        return rpc.result_read(name, body)

    @mcp.tool()
    def fdtd_results_download(filepath: str, save_to: Optional[str] = None) -> dict:
        """
        Download a result file from the Windows machine.

        Args:
            filepath: Path relative to the Windows workspace.
            save_to: Local path to save. Defaults to the file's basename.

        Returns:
            Download confirmation with local path.
        """
        return rpc.results_download(filepath, save_to)
