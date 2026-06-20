"""Analysis group management tools for FDTD MCP Server."""

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_analysis_group_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD analysis group management tools."""

    @mcp.tool()
    def fdtd_analysis_group_create(body: dict) -> dict:
        """
        Create an analysis group (scripted post-processing).

        Args:
            body: Analysis group specification.

        Returns:
            Creation confirmation with group name.
        """
        return rpc.analysis_group_create(body)

    @mcp.tool()
    def fdtd_analysis_group_get(name: str) -> dict:
        """
        Get properties of a specific analysis group.

        Args:
            name: Analysis group name.

        Returns:
            Analysis group properties.
        """
        return rpc.analysis_group_get(name)

    @mcp.tool()
    def fdtd_analysis_group_update(name: str, body: dict) -> dict:
        """
        Update properties of an analysis group.

        Args:
            name: Analysis group name.
            body: Properties to update.

        Returns:
            Update confirmation.
        """
        return rpc.analysis_group_update(name, body)
