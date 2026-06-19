"""MCP tools for SimulationPlan validation, approval, and execution."""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..plan_compilers.metasurface import compile_metasurface_plan
from ..production_sweep_design import (
    build_production_sweep_design_packet,
)
from ..real_run_preflight import build_real_run_preflight_packet
from ..rpc_client.client import RpcClient
from ..simulation_plan import (
    approve_simulation_plan,
    validate_execution_approvals,
    validate_simulation_plan,
)


def register_plan_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register deterministic SimulationPlan tools."""

    @mcp.tool()
    def fdtd_simulation_plan_validate(plan: dict) -> dict:
        """
        Normalize and validate a SimulationPlan without creating a job.

        Returns disclosed defaults, assumptions, warnings, task count,
        approval summary, and a deterministic SHA-256 fingerprint.
        """
        return validate_simulation_plan(plan)

    @mcp.tool()
    def fdtd_simulation_plan_approve(
        plan: dict,
        plan_fingerprint: str,
    ) -> dict:
        """
        Create a stateless plan approval after the user confirms the summary.

        The supplied fingerprint must match the current normalized Plan.
        """
        return approve_simulation_plan(plan, plan_fingerprint)

    @mcp.tool()
    def fdtd_simulation_plan_start(
        plan: dict,
        plan_approval: Optional[dict],
        mode: str = "mock",
        real_run_approval: Optional[dict] = None,
        template_contract: Optional[dict] = None,
    ) -> dict:
        """
        Start an approved persistent metasurface job.

        Mock requires a matching SimulationPlan approval. Real additionally
        requires a matching real-run approval and verified template contract.
        """
        validated = validate_simulation_plan(plan)
        if not validated["ok"]:
            return validated
        approval_check = validate_execution_approvals(
            validated,
            mode=mode,
            plan_approval=plan_approval,
            real_run_approval=real_run_approval,
            template_contract=template_contract,
        )
        if not approval_check["ok"]:
            return approval_check
        request = compile_metasurface_plan(
            validated["normalized_plan"],
            validated["plan_fingerprint"],
            mode=mode,
        )
        return rpc.jobs_start(request)

    @mcp.tool()
    def fdtd_simulation_plan_real_preflight(
        plan: dict,
        plan_approval: Optional[dict],
        template_contract: dict,
    ) -> dict:
        """
        Build a local real-run approval packet without calling RPC.

        This does not start FDTD. It only verifies the Plan approval and
        Stage B1 contract, compiles the exact real request shape, and returns
        the packet that must be approved by the human before Stage C1.
        """
        return build_real_run_preflight_packet(
            plan,
            plan_approval,
            template_contract,
        )

    @mcp.tool()
    def fdtd_simulation_plan_production_preflight(
        c2_review: dict,
        template_contract: dict,
        plan: Optional[dict] = None,
        max_tasks: int = 25,
    ) -> dict:
        """
        Build a local Stage C3 production sweep packet without calling RPC.

        This uses the C2 real-result review and Stage B1 contract to
        prepare the next bounded real sweep for human approval. It does
        not start FDTD.
        """
        return build_production_sweep_design_packet(
            c2_review,
            template_contract,
            plan=plan,
            max_tasks=max_tasks,
        )
