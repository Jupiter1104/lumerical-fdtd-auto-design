"""
fdtd-mcp-server — FastMCP entry point.

Mac 端 MCP Server，先把自然语言需求编译为可审批的 SimulationPlan，
再通过 FDTD 持久 job 状态机调用 Windows RPC Server。

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
from .tools.analysis_groups import register_analysis_group_tools
from .tools.export_ import register_export_tools
from .tools.generic_sweeps import register_generic_sweep_tools
from .tools.geometry import register_geometry_tools
from .tools.materials import register_material_tools
from .tools.model import register_model_tools
from .tools.monitors import register_monitor_tools
from .tools.objects import register_object_tools
from .tools.plans import register_plan_tools
from .tools.project import register_project_tools
from .tools.jobs import register_job_tools
from .tools.raw import register_raw_tools
from .tools.recipes import register_recipe_tools
from .tools.results import register_result_tools
from .tools.session import register_session_tools
from .tools.simulation import register_simulation_tools
from .tools.solver import register_solver_tools
from .tools.sources import register_source_tools
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
    register_plan_tools(mcp, rpc)
    register_job_tools(mcp, rpc)
    register_analysis_tools(mcp, rpc)
    register_export_tools(mcp, rpc)
    register_knowledge_tools(mcp)
    logger.info(f"FDTD MCP tools registered (RPC: {RPC_URL})")


def register_deliverable_tools(target_mcp, target_rpc) -> None:
    """Register the 0.1.0 deliverable tool set (exact 69-tool registry).

    Replaces legacy sweep tools with typed project/object/material/solver/
    source/monitor/analysis_group/result tools.
    """
    register_session_tools(target_mcp, target_rpc)
    register_project_tools(target_mcp, target_rpc)
    register_object_tools(target_mcp, target_rpc)
    register_material_tools(target_mcp, target_rpc)
    register_solver_tools(target_mcp, target_rpc)
    register_source_tools(target_mcp, target_rpc)
    register_monitor_tools(target_mcp, target_rpc)
    register_analysis_group_tools(target_mcp, target_rpc)
    register_result_tools(target_mcp, target_rpc)
    register_raw_tools(target_mcp, target_rpc)
    register_recipe_tools(target_mcp, target_rpc)
    register_generic_sweep_tools(target_mcp, target_rpc)
    register_plan_tools(target_mcp, target_rpc)
    register_job_tools(target_mcp, target_rpc)
    register_export_tools(target_mcp, target_rpc)
    register_knowledge_tools(target_mcp)


def collect_registered_tool_names_for_tests() -> list:
    """Collect tool names registered by register_deliverable_tools().

    Returns a sorted list for test assertions — does not start stdio.
    """
    class CollectingMcp:
        def __init__(self) -> None:
            self.names: list = []

        def tool(self):
            def decorator(fn):
                self.names.append(fn.__name__)
                return fn

            return decorator

    collector = CollectingMcp()
    test_rpc = RpcClient(RPC_URL)
    register_deliverable_tools(collector, test_rpc)
    return sorted(collector.names)


def main() -> None:
    """Run the MCP server."""
    logger.info(f"Starting FDTD MCP Server → {RPC_URL}")
    register_all_tools()
    mcp.run()


if __name__ == "__main__":
    main()
