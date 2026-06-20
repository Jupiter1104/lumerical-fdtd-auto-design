"""Raw Lumerical debug tools."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_raw_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register raw Lumerical debug/eval tools."""

    @mcp.tool()
    def fdtd_eval(cmd: str) -> dict:
        """
        Execute a raw Lumerical script command.

        Use for debugging or for operations not yet covered by typed tools.

        Args:
            cmd: Lumerical script command to execute.

        Returns:
            Command output.
        """
        return rpc.eval(cmd)

    @mcp.tool()
    def fdtd_getv(name: str) -> dict:
        """
        Get the value of a Lumerical variable.

        Args:
            name: Variable name.

        Returns:
            Variable value.
        """
        return rpc.getv(name)

    @mcp.tool()
    def fdtd_setv(name: str, value: Any) -> dict:
        """
        Set the value of a Lumerical variable.

        Args:
            name: Variable name.
            value: Value to set.

        Returns:
            Set confirmation.
        """
        return rpc.setv(name, value)
