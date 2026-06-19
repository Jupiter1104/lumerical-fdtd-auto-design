"""
fdtd-mcp-server — FastMCP entry point.

Mac 端 MCP Server，暴露 FDTD 持久 job 状态机为结构化 MCP 工具供 Claude/Hermes 调用。
所有操作通过 RPC Client 转发到 Windows RPC Server 执行。

Windows 端: RPC API v1，默认端口 5000
  - Lumerical FDTD v242 (hide=True, batch mode)
  - 原生 4-phase metasurface sweep 引擎
  - 持久 job/task 状态机、quality report、SVG evidence

启动:
    FDTD_RPC_URL=http://localhost:5000 python -m src.server

配置 (Claude Code .mcp.json):
    {
      "mcpServers": {
        "fdtd": {
          "command": "python",
          "args": ["-m", "src.server"],
          "cwd": "/path/to/project",
          "env": {
            "FDTD_RPC_URL": "http://localhost:5000"
          }
        }
      }
    }
"""

import logging
import os

from mcp.server.fastmcp import FastMCP

from .rpc_client.client import RpcClient
from .tools.analysis import register_analysis_tools
from .tools.export_ import register_export_tools
from .tools.geometry import register_geometry_tools
from .tools.model import register_model_tools
from .tools.session import register_session_tools
from .tools.simulation import register_simulation_tools
from .tools.jobs import register_job_tools
from .knowledge.embedded import register_knowledge_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fdtd-mcp")

RPC_URL = os.environ.get("FDTD_RPC_URL", "http://localhost:5000")

mcp = FastMCP("FDTD MCP")
rpc = RpcClient(RPC_URL)


def register_all_tools() -> None:
    """Register all MCP tool modules."""
    register_session_tools(mcp, rpc)
    register_model_tools(mcp, rpc)
    register_geometry_tools(mcp, rpc)
    register_simulation_tools(mcp, rpc)
    register_job_tools(mcp, rpc)
    register_analysis_tools(mcp, rpc)
    register_export_tools(mcp, rpc)
    register_knowledge_tools(mcp)
    logger.info(f"FDTD MCP tools registered (RPC: {RPC_URL})")


def main() -> None:
    """Run the MCP server."""
    logger.info(f"Starting FDTD MCP Server → {RPC_URL}")
    register_all_tools()
    mcp.run()


if __name__ == "__main__":
    main()
