"""Source management tools for FDTD MCP Server."""

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_source_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD source management tools."""

    @mcp.tool()
    def fdtd_source_create(body: dict, dry_run: bool = False) -> dict:
        """
        Create a simulation source (mode, gaussian, plane wave, etc.).

        Args:
            body: Source specification (type, geometry, wavelength, polarization).
            dry_run: If True, return a mock success without calling RPC.

        Returns:
            Creation confirmation with source name.
        """
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "type": body.get("type", "unknown"),
                "wavelength": body.get("wavelength"),
                "message": "Dry-run: no RPC call made.",
            }
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
