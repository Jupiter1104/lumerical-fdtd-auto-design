"""Analysis group management tools for FDTD MCP Server."""

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_analysis_group_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD analysis group management tools."""

    @mcp.tool()
    def fdtd_analysis_group_create(body: dict) -> dict:
        """
        Create an analysis group (scripted post-processing) with
        deterministic runtime matching against the Object Library.
        The server probes and verifies candidate analysis groups using
        lumapi setup/readback; it never guesses numeric parameters.

        Args:
            body: Analysis group specification.
                analysis_intent: high-level intent (e.g. kind, outputs)
                    that drives candidate selection.
                recipe_context: solver geometry, monitor configuration,
                    and figure-of-merit hints from the device recipe.
                parameter_overrides: explicit numeric overrides for
                    analysis group parameters.
                Optional official Object Library fields:
                prefer_builtin: if true, use addobject(script_id) when
                    script_id is provided; otherwise fall back to custom.
                require_builtin: if true, fail unless script_id is provided.
                script_id: verified Object Library script ID from docs or
                    target-version addobject enumeration.

        Returns:
            Creation confirmation with group name, source, match score,
            parameter resolution, and verification status.
        """
        return rpc.analysis_group_create(
            name=body["name"],
            properties=body.get("properties", {}),
            dry_run=body.get("dry_run", False),
            prefer_builtin=body.get("prefer_builtin", False),
            require_builtin=body.get("require_builtin", False),
            script_id=body.get("script_id", ""),
            analysis_intent=body.get("analysis_intent"),
            recipe_context=body.get("recipe_context", {}),
            parameter_overrides=body.get("parameter_overrides", {}),
        )

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
