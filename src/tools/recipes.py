"""Device recipe tools for FDTD MCP Server.

Recipes compile high-level device descriptions into executable simulation
configurations. These tools validate, compile, and build device recipes
without requiring a running FDTD session.
"""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def _recipe_placeholder(action: str, recipe: Optional[dict] = None) -> dict:
    """Placeholder for recipe compiler (Task 1 stub)."""
    return {
        "ok": True,
        "action": action,
        "message": f"Recipe {action} stub — full compiler in Task 2+",
        "recipe": recipe,
    }


def register_recipe_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register device recipe compiler tools."""

    @mcp.tool()
    def fdtd_device_recipe_validate(recipe: dict) -> dict:
        """
        Validate a device recipe against the schema.

        Checks required fields, parameter ranges, and device type constraints.

        Args:
            recipe: Device recipe to validate.

        Returns:
            Validation result with errors/warnings.
        """
        return _recipe_placeholder("validate", recipe)

    @mcp.tool()
    def fdtd_device_recipe_compile(recipe: dict) -> dict:
        """
        Compile a validated device recipe into a simulation configuration.

        Args:
            recipe: Validated device recipe.

        Returns:
            Compiled simulation configuration.
        """
        return _recipe_placeholder("compile", recipe)

    @mcp.tool()
    def fdtd_device_recipe_build(recipe: dict) -> dict:
        """
        Build a device from a compiled recipe (create objects, set materials).

        Args:
            recipe: Compiled device recipe.

        Returns:
            Build confirmation with created objects.
        """
        return _recipe_placeholder("build", recipe)
