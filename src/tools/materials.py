"""Material management tools for FDTD MCP Server."""

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_material_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD material management tools."""

    @mcp.tool()
    def fdtd_material_create(body: dict) -> dict:
        """
        Create a new material definition.

        Args:
            body: Material specification (name, type, optical properties).

        Returns:
            Creation confirmation.
        """
        return rpc.material_create(body)

    @mcp.tool()
    def fdtd_material_list() -> dict:
        """
        List all materials in the current project.

        Returns:
            List of material names and types.
        """
        return rpc.material_list()

    @mcp.tool()
    def fdtd_material_get(name: str) -> dict:
        """
        Get properties of a specific material.

        Args:
            name: Material name.

        Returns:
            Material properties.
        """
        return rpc.material_get(name)

    @mcp.tool()
    def fdtd_material_update(name: str, body: dict) -> dict:
        """
        Update properties of a material.

        Args:
            name: Material name.
            body: Properties to update.

        Returns:
            Update confirmation.
        """
        return rpc.material_update(name, body)

    @mcp.tool()
    def fdtd_material_assign(body: dict) -> dict:
        """
        Assign a material to one or more objects.

        Args:
            body: Assignment specification (material, objects).

        Returns:
            Assignment confirmation.
        """
        return rpc.material_assign(body)

    @mcp.tool()
    def fdtd_material_fit_diagnose(body: dict) -> dict:
        """
        Diagnose material fit quality for a given wavelength range.

        Args:
            body: Fit diagnostic parameters.

        Returns:
            Fit quality report.
        """
        return rpc.material_fit_diagnose(body)
