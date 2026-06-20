"""Monitor management tools for FDTD MCP Server."""

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_monitor_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD monitor management tools."""

    @mcp.tool()
    def fdtd_monitor_create(body: dict, dry_run: bool = False) -> dict:
        """
        Create a simulation monitor (frequency-domain, time-domain, movie, etc.).

        Args:
            body: Monitor specification (type, geometry, frequency points).
            dry_run: If True, return a mock success without calling RPC.

        Returns:
            Creation confirmation with monitor name.
        """
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "name": body.get("name", "dry_run_monitor"),
                "type": body.get("type", "unknown"),
                "message": "Dry-run: no RPC call made.",
            }
        return rpc.monitor_create(body)

    @mcp.tool()
    def fdtd_monitor_get(name: str) -> dict:
        """
        Get properties of a specific monitor.

        Args:
            name: Monitor name.

        Returns:
            Monitor properties.
        """
        return rpc.monitor_get(name)

    @mcp.tool()
    def fdtd_monitor_update(name: str, body: dict) -> dict:
        """
        Update properties of a monitor.

        Args:
            name: Monitor name.
            body: Properties to update.

        Returns:
            Update confirmation.
        """
        return rpc.monitor_update(name, body)
