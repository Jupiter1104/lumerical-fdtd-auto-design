"""Device recipe tools for FDTD MCP Server.

Recipes compile high-level device descriptions into executable simulation
configurations. These tools validate, compile, and build device recipes
without requiring a running FDTD session (validation and compilation are
pure Python; build requires the RPC backend when approved).
"""

import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..device_recipe import compile_recipe, validate_recipe
from ..rpc_client.client import RpcClient

logger = logging.getLogger(__name__)


def _ok_report(data: dict) -> dict:
    """Wrap a data dict as a successful response."""
    return {"ok": True, **data}


def _error_report(message: str, code: str = "recipe_tool_error") -> dict:
    """Build a structured error response."""
    return {
        "ok": False,
        "errors": [{"code": code, "message": message}],
    }


def register_recipe_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register device recipe compiler tools."""

    @mcp.tool()
    def fdtd_device_recipe_validate(recipe: dict) -> dict:
        """
        Validate a device recipe against the schema.

        Checks required fields, parameter ranges, expression validity,
        assumption documentation, and material/geometry completeness.

        Args:
            recipe: Device recipe dict with schema_version, parameters,
                    assumptions, materials, geometry, and optional sources,
                    monitors, analysis_groups, pre_run, post_run.

        Returns:
            Validation result with ok, errors, warnings, and
            normalized_recipe (when ok=True).
        """
        try:
            result = validate_recipe(recipe)
            return result
        except Exception as exc:
            logger.exception("fdtd_device_recipe_validate failed")
            return _error_report(str(exc))

    @mcp.tool()
    def fdtd_device_recipe_compile(recipe: dict) -> dict:
        """
        Compile a device recipe into an executable Lumerical script.

        Validates the recipe first; if validation fails, returns the
        validation errors.  On success returns the full compile report
        including the compiled LSF script, fingerprints, object lifecycle,
        and assumptions report.

        Args:
            recipe: Device recipe dict (see validate for structure).

        Returns:
            Compile report with ok, recipe_fingerprint, compile_fingerprint,
            script_sha256, script, object_lifecycle, assumptions_report,
            raw_hook_hashes, and warnings.
        """
        try:
            result = compile_recipe(recipe)
            return result
        except Exception as exc:
            logger.exception("fdtd_device_recipe_compile failed")
            return _error_report(str(exc))

    @mcp.tool()
    def fdtd_device_recipe_build(
        recipe: dict,
        compile_fingerprint: str = "",
        output_fsp: str = "device_model.fsp",
        approved: bool = False,
    ) -> dict:
        """
        Build a device from a compiled recipe.

        Recompiles the recipe locally and checks the compile_fingerprint
        against the one provided.  If they mismatch the build is rejected.
        When *approved* is True the tool calls the RPC backend to execute
        the build; otherwise it returns the compile report for review.

        Args:
            recipe: Device recipe dict.
            compile_fingerprint: Fingerprint string from a prior compile
                call.  Must match the local recompile or the build is
                rejected.
            output_fsp: Path for the saved .fsp file on the remote host.
            approved: Whether the user has approved the build.  When False
                only dry-run compilation is performed.

        Returns:
            Build result.  When approved=False the compile report is
            included for review.  When approved=True the remote build
            response is forwarded.
        """
        try:
            # Always recompile locally first
            compile_result = compile_recipe(recipe)

            if not compile_result["ok"]:
                return {
                    "ok": False,
                    "errors": compile_result.get("errors", []),
                    "message": "Recipe validation failed — cannot build",
                }

            # Check compile fingerprint match
            if compile_fingerprint and compile_result["compile_fingerprint"] != compile_fingerprint:
                return _error_report(
                    "Compile fingerprint mismatch: "
                    f"expected {compile_fingerprint}, "
                    f"got {compile_result['compile_fingerprint']}. "
                    "The recipe may have changed since the last compile.",
                    code="fingerprint_mismatch",
                )

            if not approved:
                # Dry-run: return the compile report for review
                return {
                    "ok": True,
                    "approved": False,
                    "message": (
                        "Recipe compiled successfully.  Review the compile "
                        "report and call again with approved=True to build."
                    ),
                    "compile_report": compile_result,
                }

            # Approved: attempt RPC build via typed client method
            try:
                rpc_result = rpc.recipe_build(
                    recipe=recipe,
                    compile_fingerprint=compile_result["compile_fingerprint"],
                    output_fsp=output_fsp,
                    approved=True,
                )
                return {
                    "ok": rpc_result.get("ok", False),
                    "approved": True,
                    "rpc_result": rpc_result,
                    "compile_report": compile_result,
                }
            except Exception as rpc_exc:
                logger.error("RPC build call failed: %s", rpc_exc)
                return _error_report(
                    f"RPC build failed: {rpc_exc}",
                    code="rpc_build_failed",
                )

        except Exception as exc:
            logger.exception("fdtd_device_recipe_build failed")
            return _error_report(str(exc))
