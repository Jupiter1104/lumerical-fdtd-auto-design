"""Generic FDTD object creation compiler and typed-domain validation.

Pure-Python compiler that produces deterministic Lumerical script
strings.  Paired with ``fdtd_schema.py`` for fingerprinting so every
operation can be hashed and deduplicated.
"""

from __future__ import annotations

from src.fdtd_schema import fingerprint_json
from src.fdtd_script import format_lsf_value

# ---------------------------------------------------------------------------
# Object-type → lumapi ``add*`` command mapping
# ---------------------------------------------------------------------------

_OBJECT_ADD_COMMANDS: dict[str, str] = {
    "rectangle": "addrect;",
    "circle": "addcircle;",
    "ring": "addring;",
    "polygon": "addpoly;",
    "fdtd_region": "addfdtd;",
    "structure_group": "addstructuregroup;",
    "mesh_override": "addmesh;",
}

# ---------------------------------------------------------------------------
# Typed-domain tool routing
# ---------------------------------------------------------------------------

_SOURCE_TYPES = frozenset({
    "plane_source",
    "gaussian_source",
    "dipole_source",
    "mode_source",
    "total_field_scattered_field_source",
})

_MONITOR_TYPES = frozenset({
    "power_monitor",
    "frequency_domain_power_monitor",
    "dft_monitor",
    "index_monitor",
    "time_monitor",
    "movie_monitor",
    "profile_monitor",
})

_ANALYSIS_GROUP_TYPES = frozenset({"analysis_group"})

_GENERIC_TYPES = frozenset(_OBJECT_ADD_COMMANDS)


def _typed_domain_error(object_type: str, tool: str) -> dict:
    return {
        "ok": False,
        "error": {
            "type": "use_typed_domain_tool",
            "message": f"Use {tool} for object_type={object_type}.",
            "details": {"tool": tool},
        },
    }


def validate_object_type(object_type: str) -> dict:
    """Return ``{"ok": True}`` if *object_type* is valid for generic create.

    Returns a structured error pointing to the correct typed-domain tool
    for sources, monitors, and analysis groups.
    """
    if object_type in _SOURCE_TYPES:
        return _typed_domain_error(object_type, "fdtd_source_create")
    if object_type in _MONITOR_TYPES:
        return _typed_domain_error(object_type, "fdtd_monitor_create")
    if object_type in _ANALYSIS_GROUP_TYPES:
        return _typed_domain_error(object_type, "fdtd_analysis_group_create")
    if object_type in _GENERIC_TYPES:
        return {"ok": True}
    return {
        "ok": False,
        "error": {
            "type": "unknown_object_type",
            "message": f"Unknown object_type: {object_type!r}.",
            "details": {"object_type": object_type},
        },
    }


# ---------------------------------------------------------------------------
# Dry-run script compilation
# ---------------------------------------------------------------------------


def compile_object_create(
    object_type: str,
    name: str,
    properties: dict[str, object],
) -> dict:
    """Produce a deterministic Lumerical script that creates *object_type*.

    Returns ``{"ok": True, "script": <str>, "script_sha256": <str>}`` on
    success, or a structured error dict when *object_type* is not valid.
    """
    validation = validate_object_type(object_type)
    if not validation["ok"]:
        return validation

    add_command = _OBJECT_ADD_COMMANDS[object_type]
    lines = [add_command]
    lines.append(f"set(\"name\",{format_lsf_value(name)});")
    for prop_key in sorted(properties):
        lines.append(
            f"set(\"{prop_key}\",{format_lsf_value(properties[prop_key])});"
        )

    script = "\n".join(lines)
    return {
        "ok": True,
        "script": script,
        "script_sha256": fingerprint_json(script),
    }
