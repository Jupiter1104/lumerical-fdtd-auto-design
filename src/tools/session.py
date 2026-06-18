"""Session management tools for the FDTD RPC API v1."""

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_session_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register session management tools."""

    @mcp.tool()
    def fdtd_health() -> dict:
        """
        Check the Windows RPC Server and FDTD session status.

        Returns whether the RPC server is reachable and whether FDTD is connected.

        Returns:
            {"ok": true, "api_version": "v1", "connected": bool}
        """
        return rpc.health()

    @mcp.tool()
    def fdtd_session_start(hide: bool = False) -> dict:
        """
        Start an FDTD session on the Windows machine.

        Two modes:
        - hide=False (default): FDTD GUI visible on Windows desktop.
          Use this for debugging, inspecting models, or watching simulations.
        - hide=True: Headless batch mode for production sweeps.
          Memory-efficient for hundreds of load() calls.

        Only one session can run at a time (single-user license).

        Args:
            hide: If True, hide FDTD GUI. Default False (GUI visible).

        Returns:
            {"ok": true, "version": "...", "hide": bool, "message": "..."}
        """
        return rpc.session_start(hide=hide)

    @mcp.tool()
    def fdtd_session_pause(seconds: float = 300.0) -> dict:
        """
        Pause and keep the FDTD GUI open for manual inspection.

        Use this after modeling but before running a sweep — check the
        geometry, mesh, sources, and monitors on the Windows screen.
        Press Ctrl+C on Windows or call fdtd_session_close() to end early.

        Args:
            seconds: Pause duration in seconds (default: 300 = 5 min).
                     Use 9999 for effectively infinite pause.

        Returns:
            {"ok": true, "message": "Paused 300s"}
        """
        return rpc.session_pause(seconds)

    @mcp.tool()
    def fdtd_session_close() -> dict:
        """
        Close the FDTD session, releasing its license.

        Always call this when done to free licenses.

        Returns:
            {"ok": true, "message": "Sessions closed"}
        """
        return rpc.session_close()
