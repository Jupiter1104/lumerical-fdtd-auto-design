"""Export tools for FDTD MCP Server."""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_export_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register export and output tools."""

    @mcp.tool()
    def fdtd_export_gds(
        file_path: Optional[str] = None,
        layer: int = 1,
    ) -> dict:
        """
        Export the current layout to a GDS file.

        Useful for sending designs to fabrication (e-beam lithography, foundry).

        Args:
            file_path: Absolute path for the GDS file on Windows.
            layer: GDS layer number (default: 1).

        Returns:
            Export confirmation or error.
        """
        # Lumerical GDS export uses the export functionality
        gds_path = file_path or "fdtd_layout.gds"
        cmd = f'exportgds("{gds_path}", {layer});'
        return rpc.eval(cmd)

    @mcp.tool()
    def fdtd_export_data(
        monitor: str = "monitor",
        attribute: str = "T",
        file_path: Optional[str] = None,
    ) -> dict:
        """
        Export monitor data to a CSV file on the Windows machine.

        After export, use scp or shared folder to transfer to Mac.

        Args:
            monitor: Monitor name.
            attribute: Attribute to export.
            file_path: Output CSV path on Windows.

        Returns:
            Export confirmation with file path, or error.
        """
        out_path = file_path or f"fdtd_{monitor}_{attribute}.csv"
        cmd = f'exportcsv("{monitor}", "{attribute}", "{out_path}");'
        resp = rpc.eval(cmd)
        if resp.get("success"):
            resp["exported_to"] = out_path
        return resp
