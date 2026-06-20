"""Source management tools for FDTD MCP Server."""

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_source_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD source management tools."""

    @mcp.tool()
    def fdtd_source_create(body: dict) -> dict:
        """
        Create a simulation source (mode, gaussian, plane wave, etc.).

        Args:
            body: Source specification (type, geometry, wavelength, polarization).

        Returns:
            Creation confirmation with source name.
        """
        return rpc.source_create(body)

    @mcp.tool()
    def fdtd_source_get(name: str) -> dict:
        """
        Get properties of a specific source.

        Args:
            name: Source name.

        Returns:
            Source properties.
        """
        return rpc.source_get(name)

    @mcp.tool()
    def fdtd_source_update(name: str, body: dict) -> dict:
        """
        Update properties of a source.

        Args:
            name: Source name.
            body: Properties to update.

        Returns:
            Update confirmation.
        """
        return rpc.source_update(name, body)
