"""Object management tools for FDTD MCP Server."""

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_object_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD simulation object CRUD tools."""

    @mcp.tool()
    def fdtd_object_create(body: dict, dry_run: bool = False) -> dict:
        """
        Create a simulation object (rectangle, circle, polygon, etc.).

        Args:
            body: Object specification with type, geometry, and material.
            dry_run: If True, return a mock success without calling RPC.

        Returns:
            Creation confirmation with object name.
        """
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "name": body.get("name", "dry_run_object"),
                "type": body.get("type", "unknown"),
                "message": "Dry-run: no RPC call made.",
            }
        return rpc.object_create(body)

    @mcp.tool()
    def fdtd_object_list() -> dict:
        """
        List all objects in the current simulation.

        Returns:
            List of object names and types.
        """
        return rpc.object_list()

    @mcp.tool()
    def fdtd_object_get(name: str) -> dict:
        """
        Get properties of a specific simulation object.

        Args:
            name: Object name.

        Returns:
            Object properties.
        """
        return rpc.object_get(name)

    @mcp.tool()
    def fdtd_object_update(name: str, body: dict) -> dict:
        """
        Update properties of a simulation object.

        Args:
            name: Object name.
            body: Properties to update.

        Returns:
            Update confirmation.
        """
        return rpc.object_update(name, body)

    @mcp.tool()
    def fdtd_object_copy(name: str, new_name: str) -> dict:
        """
        Copy a simulation object.

        Args:
            name: Source object name.
            new_name: Name for the copy.

        Returns:
            Copy confirmation.
        """
        return rpc.object_copy(name, new_name)

    @mcp.tool()
    def fdtd_object_rename(name: str, new_name: str) -> dict:
        """
        Rename a simulation object.

        Args:
            name: Current object name.
            new_name: New object name.

        Returns:
            Rename confirmation.
        """
        return rpc.object_rename(name, new_name)

    @mcp.tool()
    def fdtd_object_delete(name: str) -> dict:
        """
        Delete a simulation object.

        Args:
            name: Object name to delete.

        Returns:
            Deletion confirmation.
        """
        return rpc.object_delete(name)

    @mcp.tool()
    def fdtd_group_update(body: dict) -> dict:
        """
        Update a group of objects (selection, transformation, etc.).

        Args:
            body: Group operation specification.

        Returns:
            Group update confirmation.
        """
        return rpc.group_update(body)
