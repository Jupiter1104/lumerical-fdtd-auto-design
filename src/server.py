"""
fdtd-mcp-server — FastMCP entry point.

Mac 端 MCP Server，暴露 FDTD 扫参流水线为结构化 MCP 工具供 Claude/Hermes 调用。
所有操作通过 RPC Client 转发到 Windows RPC Server 执行。

Windows 端: metasurface autosweep pipeline
  - Lumerical FDTD v242 (hide=True, batch mode)
  - MATLAB Engine (phase post-processing, heatmaps)
  - 4-phase pipeline: .fsp generation → parallel solve → S-param extract → MATLAB plots

启动:
    FDTD_RPC_URL=http://localhost:5001 python -m src.server

配置 (Claude Code .mcp.json):
    {
      "mcpServers": {
        "fdtd": {
          "command": "python",
          "args": ["-m", "src.server"],
          "cwd": "/path/to/project",
          "env": {
            "FDTD_RPC_URL": "http://localhost:5001"
          }
        }
      }
    }
"""

import logging
import os

from mcp.server.fastmcp import FastMCP

from .rpc_client.client import RpcClient
from .tools.session import register_session_tools
from .tools.simulation import register_simulation_tools
from .tools.analysis import register_analysis_tools
from .knowledge.embedded import register_knowledge_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fdtd-mcp")

RPC_URL = os.environ.get("FDTD_RPC_URL", "http://localhost:5001")

mcp = FastMCP("FDTD MCP")
rpc = RpcClient(RPC_URL)


def register_all_tools() -> None:
    """Register all MCP tool modules."""
    register_session_tools(mcp, rpc)
    register_simulation_tools(mcp, rpc)
    register_analysis_tools(mcp, rpc)
    register_knowledge_tools(mcp)
    logger.info(f"FDTD MCP tools registered (RPC: {RPC_URL})")


def main() -> None:
    """Run the MCP server."""
    logger.info(f"Starting FDTD MCP Server → {RPC_URL}")
    register_all_tools()
    mcp.run()


if __name__ == "__main__":
    main()
