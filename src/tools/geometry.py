"""Geometry tools for FDTD MCP Server.

Thin wrappers around lumapi geometry creation. Pass parameters as keyword
arguments matching the Lumerical script command names.
"""

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_geometry_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register FDTD geometry creation tools."""

    @mcp.tool()
    def fdtd_add_fdtd_region(
        dimension: str = "3D",
        x: float = 0.0,
        x_span: float = 8e-6,
        y: float = 0.0,
        y_span: float = 8e-6,
        z: float = 0.0,
        z_span: float = 2e-6,
        mesh_accuracy: int = 2,
    ) -> dict:
        """
        Add the FDTD simulation region (the simulation bounding box).

        This must be called before running any simulation.

        Args:
            dimension: "2D" or "3D" (default: "3D")
            x, y, z: Center position (meters)
            x_span, y_span, z_span: Span in each direction (meters)
            mesh_accuracy: Mesh refinement 1-8 (2=default, higher=finer)

        Returns:
            Success confirmation or error.
        """
        return rpc.addfdtd(
            dimension=dimension,
            x=x, x_span=x_span,
            y=y, y_span=y_span,
            z=z, z_span=z_span,
            mesh_accuracy=mesh_accuracy,
        )

    @mcp.tool()
    def fdtd_add_rect(
        name: str = "rect",
        x: float = 0.0,
        x_span: float = 1e-6,
        y: float = 0.0,
        y_span: float = 1e-6,
        z: float = 0.0,
        z_span: float = 1e-6,
        material: str = "Si (Silicon) - Palik",
    ) -> dict:
        """
        Add a rectangular structure to the simulation.

        Typical use: waveguides, MMI regions, substrates.

        Args:
            name: Unique name for this rectangle.
            x, y, z: Center position (meters).
            x_span, y_span, z_span: Dimensions (meters).
            material: Material name from the Lumerical material database.

        Returns:
            Success confirmation or error.
        """
        return rpc.addrect(
            name=name,
            x=x, x_span=x_span,
            y=y, y_span=y_span,
            z=z, z_span=z_span,
            material=material,
        )

    @mcp.tool()
    def fdtd_add_circle(
        name: str = "circle",
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        z_span: float = 220e-9,
        radius: float = 1e-6,
        material: str = "Si (Silicon) - Palik",
    ) -> dict:
        """
        Add a cylindrical/disk structure to the simulation.

        Typical use: micro-ring resonators, pillars, vias.

        Args:
            name: Unique name for this circle.
            x, y, z: Center position (meters).
            z_span: Height/thickness (meters).
            radius: Radius in the XY plane (meters).
            material: Material name from the Lumerical material database.

        Returns:
            Success confirmation or error.
        """
        return rpc.addcircle(
            name=name,
            x=x, y=y, z=z,
            z_span=z_span,
            radius=radius,
            material=material,
        )
