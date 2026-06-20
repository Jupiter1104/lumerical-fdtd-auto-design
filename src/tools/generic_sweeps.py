"""Generic sweep tools for FDTD MCP Server.

Generic sweeps handle parameter sweeps that are not hard-coded to the
4-phase metasurface pipeline. These tools validate, plan, and start
generic parameter sweep jobs.
"""

import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..generic_sweep import plan_generic_sweep, validate_sweep_plan
from ..rpc_client.client import RpcClient

logger = logging.getLogger(__name__)


def _ok_report(data: dict) -> dict:
    """Wrap a data dict as a successful response."""
    return {"ok": True, **data}


def _error_report(message: str, code: str = "generic_sweep_error") -> dict:
    """Build a structured error response."""
    return {
        "ok": False,
        "errors": [{"code": code, "message": message}],
    }


def register_generic_sweep_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register generic parameter sweep tools."""

    @mcp.tool()
    def fdtd_generic_sweep_validate(body: dict) -> dict:
        """
        Validate a generic sweep specification.

        Performs local validation only — does not compile any task scripts.
        Checks the sweep plan structure, parameter ranges, step counts,
        and resource estimates.

        Args:
            body: Sweep specification with schema_version, parameters list,
                  optional max_tasks, and optional recipe_fingerprint for
                  consistency tracking.

        Returns:
            Validation result with ok, errors, warnings, sweep_fingerprint,
            and task_count_estimate.
        """
        try:
            sweep_plan = body.get("sweep_plan", body)
            recipe_fingerprint = body.get("recipe_fingerprint", "")
            result = validate_sweep_plan(sweep_plan, recipe_fingerprint)
            return result
        except Exception as exc:
            logger.exception("fdtd_generic_sweep_validate failed")
            return _error_report(str(exc))

    @mcp.tool()
    def fdtd_generic_sweep_plan(body: dict) -> dict:
        """
        Plan a generic sweep job without running FDTD.

        Full expansion and compilation: validates the recipe and sweep plan,
        generates the Cartesian product task grid, compiles every task
        script, and returns a deterministic plan packet with fingerprints.

        Args:
            body: Dict with ``recipe`` and ``sweep_plan`` keys.
                  recipe: Device recipe dict.
                  sweep_plan: Sweep specification with parameters list.

        Returns:
            Sweep plan packet with task_count, tasks (each with task_id,
            index, parameters, script_sha256, script), and fingerprints.
        """
        try:
            recipe = body.get("recipe", {})
            sweep_plan = body.get("sweep_plan", body)
            max_tasks = body.get("max_tasks", sweep_plan.get("max_tasks", 1000))
            result = plan_generic_sweep(recipe, sweep_plan, max_tasks=max_tasks)
            return result
        except Exception as exc:
            logger.exception("fdtd_generic_sweep_plan failed")
            return _error_report(str(exc))

    @mcp.tool()
    def fdtd_generic_sweep_start(body: dict) -> dict:
        """
        Start a generic sweep job.

        Re-plans the sweep locally, checks the plan_approval fingerprint
        against the freshly computed packet_fingerprint, and when
        approved calls the RPC backend for execution.

        Args:
            body: Dict with ``recipe``, ``sweep_plan``,
                  ``plan_approval`` (optional dict with packet_fingerprint
                  and approved flag), and ``mode`` ("mock" or "real").

        Returns:
            Job start confirmation with job_id when approved, or error
            when approval is missing/mismatched.
        """
        try:
            recipe = body.get("recipe", {})
            sweep_plan = body.get("sweep_plan", body)
            plan_approval = body.get("plan_approval")
            mode = body.get("mode", "mock")
            max_tasks = body.get("max_tasks", sweep_plan.get("max_tasks", 1000))

            # ── Re-plan to get fresh fingerprint ───────────────────────
            plan_result = plan_generic_sweep(recipe, sweep_plan, max_tasks=max_tasks)
            if not plan_result["ok"]:
                return plan_result

            packet_fingerprint = plan_result["plan"]["packet_fingerprint"]

            # ── Check approval ─────────────────────────────────────────
            if plan_approval is None:
                return {
                    "ok": False,
                    "error": {
                        "type": "plan_approval_required",
                        "message": (
                            "Plan approval is required. Run fdtd_generic_sweep_plan "
                            "first, review the plan, and provide plan_approval with "
                            "approved=true and the packet_fingerprint."
                        ),
                    },
                }

            approved = plan_approval.get("approved", False)
            approval_fingerprint = plan_approval.get("packet_fingerprint", "")

            if not approved:
                return {
                    "ok": False,
                    "error": {
                        "type": "plan_not_approved",
                        "message": "Plan approval has approved=false.",
                    },
                }

            if approval_fingerprint != packet_fingerprint:
                return {
                    "ok": False,
                    "error": {
                        "type": "plan_fingerprint_mismatch",
                        "message": (
                            f"Approval fingerprint {approval_fingerprint} does not "
                            f"match fresh plan fingerprint {packet_fingerprint}. "
                            f"The sweep plan may have changed since approval."
                        ),
                    },
                }

            # ── Mode-specific checks ───────────────────────────────────
            if mode == "real":
                # Real mode requires additional real_run_approval
                real_run_approval = body.get("real_run_approval")
                if real_run_approval is None or not real_run_approval.get("approved", False):
                    return {
                        "ok": False,
                        "error": {
                            "type": "real_run_approval_required",
                            "message": (
                                "Real mode requires real_run_approval with "
                                "approved=true."
                            ),
                        },
                    }

            # ── Build request for RPC ──────────────────────────────────
            request = {
                "mode": mode,
                "job_type": "generic-sweep",
                "idempotency_key": f"generic-sweep:{packet_fingerprint}:{mode}",
                "sweep": {
                    "recipe_fingerprint": plan_result["plan"]["recipe_fingerprint"],
                    "sweep_fingerprint": plan_result["plan"]["sweep_fingerprint"],
                    "task_count": plan_result["plan"]["task_count"],
                    "tasks": [
                        {
                            "task_id": t["task_id"],
                            "index": t["index"],
                            "parameters": t["parameters"],
                            "script": t["script"],
                            "script_sha256": t["script_sha256"],
                        }
                        for t in plan_result["plan"]["tasks"]
                    ],
                },
            }

            if mode == "real":
                request["approval"] = {
                    "approved": True,
                    "approved_for": "real_run",
                }

            return rpc.jobs_start(request)

        except Exception as exc:
            logger.exception("fdtd_generic_sweep_start failed")
            return _error_report(str(exc))
