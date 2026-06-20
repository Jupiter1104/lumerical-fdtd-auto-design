"""Windows FDTD Adapter -- typed domain operations for FDTD automation.

Wraps a backend (real lumapi SessionManager or FakeFdtdBackend for testing).
Provides high-level methods for project, object, material, solver, source,
monitor, analysis group, simulation, and result operations.

For ``dry_run=True``, returns compiled Lumerical script without executing
it against the backend.
"""

from __future__ import annotations

from typing import Any

from src.fdtd_operations import (
    _OBJECT_ADD_COMMANDS,
    compile_object_create,
    validate_object_type,
)
from src.fdtd_schema import fingerprint_json
from src.fdtd_script import format_lsf_value

# ---------------------------------------------------------------------------
# Source / monitor / analysis-group -> lumapi add command mappings
# ---------------------------------------------------------------------------

_SOURCE_ADD_COMMANDS: dict[str, str] = {
    "plane_source": "addplane;",
    "gaussian_source": "addgaussian;",
    "dipole_source": "adddipole;",
    "mode_source": "addmode;",
    "total_field_scattered_field_source": "addtfsf;",
}

_MONITOR_ADD_COMMANDS: dict[str, str] = {
    "power_monitor": "addpower;",
    "frequency_domain_power_monitor": "addpower;",
    "dft_monitor": "adddftmonitor;",
    "index_monitor": "addindex;",
    "time_monitor": "addtime;",
    "movie_monitor": "addmovie;",
    "profile_monitor": "addprofile;",
}

_SOURCE_TYPES = frozenset(_SOURCE_ADD_COMMANDS)
_MONITOR_TYPES = frozenset(_MONITOR_ADD_COMMANDS)
_ANALYSIS_GROUP_TYPES = frozenset({"analysis_group"})


# ---------------------------------------------------------------------------
# Error class (no dependency on rpc_server to avoid circular imports)
# ---------------------------------------------------------------------------

class AdapterError(Exception):
    """Structured error raised by adapter for invalid operations."""

    def __init__(
        self,
        error_type: str,
        message: str,
        status_code: int = 400,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        self.details = details or {}


# ---------------------------------------------------------------------------
# Script compilation helpers
# ---------------------------------------------------------------------------


def _compile_create_script(
    add_command: str,
    name: str,
    properties: dict[str, object],
) -> str:
    """Build a LSF script: add command + set name + set each sorted property."""
    lines = [add_command]
    lines.append(f'set("name",{format_lsf_value(name)});')
    for key in sorted(properties):
        lines.append(f'set("{key}",{format_lsf_value(properties[key])});')
    return "\n".join(lines)


def _compile_set_properties_script(
    object_name: str,
    properties: dict[str, object],
) -> str:
    """Build a LSF script that selects an object and sets properties."""
    lines = [f'select("{object_name}");']
    for key, val in properties.items():
        lines.append(f'set("{key}",{format_lsf_value(val)});')
    return "\n".join(lines)


def _compile_fdtd_region_script(
    properties: dict[str, object],
) -> str:
    """Build a solver-region creation script.

    Lumerical's FDTD region is the solver object itself; treating it like a
    generic geometry object and setting ``name`` can fail on real v242.
    """
    lines = ["addfdtd;"]
    for key in sorted(properties):
        lines.append(f'set("{key}",{format_lsf_value(properties[key])});')
    return "\n".join(lines)


def _compile_monitor_create_script(
    add_command: str,
    name: str,
    properties: dict[str, object],
) -> str:
    """Build monitor creation script with monitor-setting dependencies ordered."""
    lines = [add_command, f'set("name",{format_lsf_value(name)});']
    if (
        "frequency points" in properties
        and "override global monitor settings" not in properties
    ):
        lines.append('set("override global monitor settings",1);')
    for key, value in properties.items():
        lines.append(f'set("{key}",{format_lsf_value(value)});')
    return "\n".join(lines)


def _adapter_error_from_validation(validation: dict) -> AdapterError:
    """Convert a validation error dict from *validate_object_type* to an AdapterError."""
    error = validation.get("error", {})
    return AdapterError(
        error_type=error.get("type", "validation_error"),
        message=error.get("message", "Validation failed."),
        status_code=400,
        details=error.get("details", {}),
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class WindowsFdtdAdapter:
    """Typed-domain FDTD operations wrapping a backend.

    Parameters
    ----------
    backend:
        A lumapi session (``SessionManager``) or a ``FakeFdtdBackend``
        for testing.  Must expose ``eval(script)``, ``run()`` and
        ``getresult(monitor, attribute)``.
    """

    def __init__(self, backend: Any) -> None:
        self._backend = backend

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_or_dry_run(
        self,
        script: str,
        dry_run: bool,
        extra: dict | None = None,
    ) -> dict:
        """Execute *script* via backend, or return it for dry_run."""
        if dry_run:
            result: dict[str, Any] = {
                "script": script,
                "script_sha256": fingerprint_json(script),
            }
            if extra:
                result.update(extra)
            return result
        self._backend.eval(script)
        result: dict[str, Any] = extra.copy() if extra else {}
        return result

    @staticmethod
    def _safe_eval(backend: Any, script: str, default: Any = "") -> Any:
        """Call *backend.eval(script)*, returning *default* on any error."""
        try:
            return backend.eval(script)
        except Exception:
            return default

    # ------------------------------------------------------------------
    # Project
    # ------------------------------------------------------------------

    def project_new(
        self,
        name: str,
        discard_unsaved: bool = True,
    ) -> dict:
        """Create a new FDTD project."""
        script = "newproject;\n"
        script += f'set("name",{format_lsf_value(name)});'
        self._backend.eval(script)
        return {"project_name": name}

    def project_status(self) -> dict:
        """Return current project information."""
        return {"project_name": "untitled", "modified": False}

    def switch_to_layout(self) -> dict:
        """Switch to layout editor mode."""
        self._backend.eval("switchtolayout;")
        return {"mode": "layout"}

    # ------------------------------------------------------------------
    # Objects
    # ------------------------------------------------------------------

    def object_create(
        self,
        object_type: str,
        name: str,
        properties: dict[str, object] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Create a simulation object.

        Sources, monitors, and analysis groups are routed to their
        respective typed-domain methods.
        """
        props = properties or {}

        # Route typed domains to their dedicated create methods
        if object_type in _SOURCE_TYPES:
            return self.source_create(object_type, name, props, dry_run)
        if object_type in _MONITOR_TYPES:
            return self.monitor_create(object_type, name, props, dry_run)
        if object_type in _ANALYSIS_GROUP_TYPES:
            return self.analysis_group_create(name, props, dry_run)

        # Validate generic object type
        validation = validate_object_type(object_type)
        if not validation["ok"]:
            raise _adapter_error_from_validation(validation)

        add_command = _OBJECT_ADD_COMMANDS.get(object_type)
        if not add_command:
            raise AdapterError(
                "unknown_object_type",
                f"Unknown object_type: {object_type!r}.",
                400,
                {"object_type": object_type},
            )

        if object_type == "fdtd_region":
            script = _compile_fdtd_region_script(props)
        else:
            script = _compile_create_script(add_command, name, props)
        return self._execute_or_dry_run(
            script, dry_run,
            extra={"object_type": object_type, "name": name},
        )

    def object_list(
        self,
        scope: str | None = None,
        object_type: str | None = None,
    ) -> dict:
        """List objects in the simulation."""
        raw = self._safe_eval(self._backend, "?ls;", default=[])
        if isinstance(raw, (list, tuple)):
            objects = list(raw)
        elif isinstance(raw, str):
            objects = [r.strip() for r in raw.split("\n") if r.strip()]
        else:
            objects = []
        return {"objects": objects}

    def object_get(
        self,
        name: str,
        properties: list[str] | None = None,
    ) -> dict:
        """Get properties of a named object."""
        props = properties or [
            "x", "y", "z", "x_span", "y_span", "z_span", "material",
        ]
        values: dict[str, Any] = {}
        for prop in props:
            values[prop] = self._safe_eval(
                self._backend,
                f'getnamed("{name}","{prop}");',
                default=None,
            )
        return {"name": name, "properties": values}

    def object_update(
        self,
        name: str,
        properties: dict[str, object],
        dry_run: bool = False,
    ) -> dict:
        """Update properties of a named object."""
        script = _compile_set_properties_script(name, properties)
        return self._execute_or_dry_run(script, dry_run, extra={"name": name})

    def object_copy(
        self,
        name: str,
        new_name: str,
        transform: dict[str, object] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Copy an object, optionally applying a spatial transform."""
        script = f'copy("{name}","{new_name}");'
        if transform:
            for key, val in transform.items():
                script += f'\nset("{key}",{format_lsf_value(val)});'
        return self._execute_or_dry_run(
            script, dry_run,
            extra={"name": name, "new_name": new_name},
        )

    def object_rename(
        self,
        name: str,
        new_name: str,
        dry_run: bool = False,
    ) -> dict:
        """Rename an object."""
        script = (
            f'select("{name}");\n'
            f'set("name",{format_lsf_value(new_name)});'
        )
        return self._execute_or_dry_run(
            script, dry_run,
            extra={"name": name, "new_name": new_name},
        )

    def object_delete(
        self,
        name: str,
        dry_run: bool = False,
    ) -> dict:
        """Delete an object."""
        script = f'delete("{name}");'
        return self._execute_or_dry_run(script, dry_run, extra={"name": name})

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def group_update(
        self,
        group_name: str,
        add: list[str] | None = None,
        remove: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Add or remove objects from a group."""
        lines: list[str] = []
        for obj in (add or []):
            lines.append(f'groupadd("{group_name}","{obj}");')
        for obj in (remove or []):
            lines.append(f'groupremove("{group_name}","{obj}");')
        script = "\n".join(lines) if lines else ";"
        return self._execute_or_dry_run(
            script, dry_run, extra={"group_name": group_name},
        )

    # ------------------------------------------------------------------
    # Materials
    # ------------------------------------------------------------------

    def material_create(
        self,
        name: str,
        properties: dict[str, object] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Create a new material in the database."""
        props = properties or {}
        lines = ["addmaterial;"]
        lines.append(f'set("name",{format_lsf_value(name)});')
        for key, val in props.items():
            lines.append(f'set("{key}",{format_lsf_value(val)});')
        script = "\n".join(lines)
        return self._execute_or_dry_run(
            script, dry_run, extra={"material_name": name},
        )

    def material_list(self) -> dict:
        """List materials in the project."""
        raw = self._safe_eval(self._backend, "?lsmaterials;", default=[])
        if isinstance(raw, (list, tuple)):
            materials = list(raw)
        elif isinstance(raw, str):
            materials = [r.strip() for r in raw.split("\n") if r.strip()]
        else:
            materials = []
        return {"materials": materials}

    def material_get(self, name: str) -> dict:
        """Get material properties."""
        props: dict[str, Any] = {}
        for prop in ["index", "epsilon", "conductivity"]:
            props[prop] = self._safe_eval(
                self._backend,
                f'getnamed("{name}","{prop}");',
                default=None,
            )
        return {"name": name, "properties": props}

    def material_update(
        self,
        name: str,
        properties: dict[str, object],
        dry_run: bool = False,
    ) -> dict:
        """Update material properties."""
        script = _compile_set_properties_script(name, properties)
        return self._execute_or_dry_run(
            script, dry_run, extra={"material_name": name},
        )

    def material_assign(
        self,
        object_name: str,
        material_name: str,
        dry_run: bool = False,
    ) -> dict:
        """Assign a material to an object."""
        script = f'setmaterial("{object_name}","{material_name}");'
        return self._execute_or_dry_run(
            script, dry_run,
            extra={"object": object_name, "material": material_name},
        )

    def material_fit_diagnose(self, data: dict | None = None) -> dict:
        """Diagnose material fit quality (placeholder)."""
        return {"fit_quality": "nominal", "warnings": []}

    # ------------------------------------------------------------------
    # Solver
    # ------------------------------------------------------------------

    def solver_get(self) -> dict:
        """Get solver configuration."""
        config: dict[str, Any] = {}
        for prop in [
            "dimension", "simulation_time", "mesh_accuracy",
            "x", "x_span", "y", "y_span", "z", "z_span",
        ]:
            config[prop] = self._safe_eval(
                self._backend,
                f'getnamed("FDTD","{prop}");',
                default=None,
            )
        return {"solver_config": config}

    def solver_update(
        self,
        config: dict[str, object],
        dry_run: bool = False,
    ) -> dict:
        """Update solver configuration."""
        script = _compile_set_properties_script("FDTD", config)
        return self._execute_or_dry_run(
            script, dry_run, extra={"updated": list(config.keys())},
        )

    def solver_mesh_diagnose(self) -> dict:
        """Return mesh diagnostic information (placeholder)."""
        return {"mesh_cells": 0, "min_dx": 1e-9, "max_dx": 100e-9}

    def solver_resource_estimate(self) -> dict:
        """Estimate computational resources (placeholder)."""
        return {"estimated_ram_gb": 0.5, "estimated_time_s": 10.0}

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def source_create(
        self,
        source_type: str,
        name: str,
        properties: dict[str, object] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Create a source."""
        props = properties or {}
        add_command = _SOURCE_ADD_COMMANDS.get(source_type)
        if not add_command:
            raise AdapterError(
                "unknown_source_type",
                f"Unknown source_type: {source_type!r}.",
                400,
                {"source_type": source_type},
            )
        script = _compile_create_script(add_command, name, props)
        return self._execute_or_dry_run(
            script, dry_run,
            extra={"source_type": source_type, "name": name},
        )

    def source_get(self, name: str) -> dict:
        """Get source properties."""
        props: dict[str, Any] = {}
        for prop in [
            "wavelength_start", "wavelength_stop",
            "angle_theta", "angle_phi",
        ]:
            props[prop] = self._safe_eval(
                self._backend,
                f'getnamed("{name}","{prop}");',
                default=None,
            )
        return {"name": name, "source_type": "plane_source", "properties": props}

    def source_update(
        self,
        name: str,
        properties: dict[str, object],
        dry_run: bool = False,
    ) -> dict:
        """Update source properties."""
        script = _compile_set_properties_script(name, properties)
        return self._execute_or_dry_run(script, dry_run, extra={"name": name})

    # ------------------------------------------------------------------
    # Monitors
    # ------------------------------------------------------------------

    def monitor_create(
        self,
        monitor_type: str,
        name: str,
        properties: dict[str, object] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Create a monitor."""
        props = properties or {}
        add_command = _MONITOR_ADD_COMMANDS.get(monitor_type)
        if not add_command:
            raise AdapterError(
                "unknown_monitor_type",
                f"Unknown monitor_type: {monitor_type!r}.",
                400,
                {"monitor_type": monitor_type},
            )
        script = _compile_monitor_create_script(add_command, name, props)
        return self._execute_or_dry_run(
            script, dry_run,
            extra={"monitor_type": monitor_type, "name": name},
        )

    def monitor_get(self, name: str) -> dict:
        """Get monitor properties."""
        props: dict[str, Any] = {}
        for prop in ["monitor_type_name", "frequency_points"]:
            props[prop] = self._safe_eval(
                self._backend,
                f'getnamed("{name}","{prop}");',
                default=None,
            )
        return {
            "name": name,
            "monitor_type": "power_monitor",
            "properties": props,
        }

    def monitor_update(
        self,
        name: str,
        properties: dict[str, object],
        dry_run: bool = False,
    ) -> dict:
        """Update monitor properties."""
        script = _compile_set_properties_script(name, properties)
        return self._execute_or_dry_run(script, dry_run, extra={"name": name})

    # ------------------------------------------------------------------
    # Analysis Groups
    # ------------------------------------------------------------------

    def analysis_group_create(
        self,
        name: str,
        properties: dict[str, object] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Create an analysis group."""
        script = _compile_create_script(
            "addanalysisgroup;", name, properties or {},
        )
        return self._execute_or_dry_run(
            script, dry_run, extra={"name": name},
        )

    def analysis_group_get(self, name: str) -> dict:
        """Get analysis group properties."""
        return {"name": name, "properties": {}}

    def analysis_group_update(
        self,
        name: str,
        properties: dict[str, object],
        dry_run: bool = False,
    ) -> dict:
        """Update analysis group properties."""
        script = _compile_set_properties_script(name, properties)
        return self._execute_or_dry_run(script, dry_run, extra={"name": name})

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def simulation_run(self) -> dict:
        """Run the FDTD simulation."""
        self._backend.run()
        return {"message": "Simulation completed."}

    def simulation_status(self) -> dict:
        """Return current simulation status."""
        return {"running": False, "progress": 1.0}

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def result_list(self) -> dict:
        """List available results across all monitors."""
        try:
            raw = self._backend.eval("?ls;")
            if isinstance(raw, (list, tuple)):
                monitor_list = list(raw)
            elif isinstance(raw, str):
                monitor_list = [
                    m.strip() for m in raw.split("\n") if m.strip()
                ]
            else:
                monitor_list = []
        except Exception:
            monitor_list = []

        results: dict[str, list[str]] = {}
        for monitor in monitor_list:
            try:
                attrs = self._backend.eval(f'listresult("{monitor}");')
                if isinstance(attrs, (list, tuple)):
                    results[monitor] = list(attrs)
                elif isinstance(attrs, str):
                    results[monitor] = [
                        a.strip() for a in attrs.split("\n") if a.strip()
                    ]
            except Exception:
                results[monitor] = []
        return {"results": results}

    def result_describe(self, monitor: str, attribute: str) -> dict:
        """Describe a result (type, units, metadata)."""
        return {
            "monitor": monitor,
            "attribute": attribute,
            "type": "scalar",
            "units": "normalized",
        }

    def result_read(self, monitor: str, attribute: str) -> dict:
        """Read a result value."""
        data = self._backend.getresult(monitor, attribute)
        return {"monitor": monitor, "attribute": attribute, "value": data}

    def result_download(self, monitor: str, attribute: str) -> dict:
        """Download full result data."""
        data = self._backend.getresult(monitor, attribute)
        return {"monitor": monitor, "attribute": attribute, "data": data}
