"""Cross-platform helpers for FDTD template probe (Stage B0)."""

import hashlib
import json
import os
from pathlib import Path


PROBE_VERSION = "0.1"


def stable_json(value: dict) -> str:
    """Deterministic JSON with sorted keys, no whitespace, no NaN."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path, value: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(target))


def probe_fingerprint(probe: dict) -> str:
    """Stable fingerprint that excludes its own field."""
    payload = dict(probe)
    payload.pop("probe_fingerprint", None)
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def probe_installation_identity(lumapi_module) -> dict:
    """Build installation identity from lumapi module introspection.

    Returns dict with sys_executable, lumapi_file, lumapi_sha256,
    install_root, path_version_tag, api_python_path, bin_path,
    recorded_version, confirmable, and errors.
    """
    import sys

    identity = {
        "sys_executable": sys.executable,
        "lumapi_file": None,
        "lumapi_sha256": None,
        "install_root": None,
        "path_version_tag": None,
        "api_python_path": None,
        "bin_path": None,
        "recorded_version": "unknown",
        "version_warning": True,
        "confirmable": True,
        "errors": [],
    }

    # 1. lumapi file location
    lumapi_path = Path(getattr(lumapi_module, "__file__", ""))
    try:
        if lumapi_path.is_file():
            identity["lumapi_file"] = str(lumapi_path.resolve())
            identity["lumapi_sha256"] = file_sha256(lumapi_path)
    except Exception as exc:
        identity["errors"].append(
            {"type": "lumapi_path_unreadable", "message": str(exc)}
        )

    # 2. Derive install root and version tag from path hierarchy
    #    Expected: .../v242/api/python/lumapi.py
    try:
        api_python_dir = lumapi_path.parent  # python/
        if api_python_dir.name == "python":
            api_dir = api_python_dir.parent  # api/
            if api_dir.name == "api":
                version_dir = api_dir.parent  # v242/
                identity["install_root"] = str(version_dir.parent.resolve())
                identity["path_version_tag"] = version_dir.name
                identity["api_python_path"] = str(api_python_dir.resolve())
                bin_candidate = version_dir / "bin"
                if bin_candidate.is_dir():
                    identity["bin_path"] = str(bin_candidate.resolve())
    except Exception:
        pass

    # 3. Confirmability: need at least one identity signal
    has_lumapi = identity["lumapi_file"] is not None
    has_install_root = identity["install_root"] is not None
    has_version_tag = identity["path_version_tag"] is not None
    if not has_lumapi and not has_install_root and not has_version_tag:
        identity["confirmable"] = False
        identity["errors"].append(
            {
                "type": "install_identity_unconfirmable",
                "message": (
                    "No lumapi file, install root, or version tag "
                    "could be determined."
                ),
            }
        )

    return identity


def validate_probe_installation(identity: dict):
    """Return (fail: bool, warnings: list).

    Fail only when identity is completely unconfirmable.
    Warn when version is unknown but identity is otherwise confirmable.
    """
    warnings = []
    if not identity["confirmable"]:
        return True, [
            {
                "type": "install_identity_unconfirmable",
                "message": "Installation identity cannot be confirmed.",
            }
        ]
    if identity["version_warning"]:
        warnings.append(
            {
                "type": "version_unknown_warning",
                "message": (
                    "Lumerical version could not be read via API. "
                    "Installation identity (path, lumapi hash, version tag) "
                    "provides alternative audit evidence."
                ),
            }
        )
    return False, warnings


# ============================================================
# Lumapi environment preparation
# ============================================================

_DLL_DIRECTORY_HANDLES = {}


def derive_version_root(python_executable) -> Path:
    executable = Path(python_executable).resolve()
    if executable.parent.name.lower() == "python":
        return executable.parent.parent
    return executable.parent


def prepare_lumapi_environment(
    *,
    version_root=None,
    python_executable=None,
    sys_path=None,
    environ=None,
    platform_name=None,
    add_dll_directory=None,
) -> dict:
    import sys

    sys_path = sys.path if sys_path is None else sys_path
    environ = os.environ if environ is None else environ
    platform_name = sys.platform if platform_name is None else platform_name
    python_executable = (
        sys.executable if python_executable is None else python_executable
    )
    root = (
        derive_version_root(python_executable)
        if version_root is None
        else Path(version_root).resolve()
    )
    api_python = root / "api" / "python"
    bin_path = root / "bin"
    diagnostics = {
        "version_root": str(root),
        "api_python_path": str(api_python),
        "bin_path": str(bin_path),
        "api_python_exists": api_python.is_dir(),
        "bin_exists": bin_path.is_dir(),
        "sys_path_added": False,
        "path_added": False,
        "dll_directory_added": False,
        "errors": [],
    }

    if api_python.is_dir():
        api_text = str(api_python)
        if api_text not in sys_path:
            sys_path.append(api_text)
            diagnostics["sys_path_added"] = True
    else:
        diagnostics["errors"].append({
            "type": "api_python_missing",
            "path": str(api_python),
        })

    if bin_path.is_dir():
        bin_text = str(bin_path)
        path_parts = [
            item for item in environ.get("PATH", "").split(os.pathsep)
            if item
        ]
        if bin_text not in path_parts:
            environ["PATH"] = os.pathsep.join([bin_text, *path_parts])
            diagnostics["path_added"] = True
        if platform_name.startswith("win"):
            dll_adder = (
                getattr(os, "add_dll_directory", None)
                if add_dll_directory is None
                else add_dll_directory
            )
            if dll_adder is not None and bin_text not in _DLL_DIRECTORY_HANDLES:
                _DLL_DIRECTORY_HANDLES[bin_text] = dll_adder(bin_text)
                diagnostics["dll_directory_added"] = True
    else:
        diagnostics["errors"].append({
            "type": "bin_missing",
            "path": str(bin_path),
        })

    return diagnostics


# ============================================================
# Stage B1 readiness
# ============================================================

EXPECTED_TEMPLATE_SHA256 = (
    "03ba1f3ea9db6e86caa9c5458bcf84b6"
    "adb92db6c0664e60f262e2f5edde0176"
)


def _is_readable(properties, key):
    return properties.get(key, {}).get("status") == "readable"


def evaluate_stage_b1_readiness(
    *,
    template_sha_matches,
    installation_confirmable,
    fdtd_configuration,
    resolved_roles,
    model_parameters,
    errors,
) -> dict:
    blockers = []
    if not template_sha_matches:
        blockers.append("template_sha_mismatch")
    if not installation_confirmable:
        blockers.append("installation_unconfirmable")
    if fdtd_configuration.get("canonical_path") != "::model::FDTD":
        blockers.append("canonical_fdtd_unconfirmed")

    properties = fdtd_configuration.get("properties", {})
    required_properties = (
        "dimension",
        "express_mode",
        "mesh_accuracy",
        "x_min_bc",
        "x_max_bc",
        "y_min_bc",
        "y_max_bc",
        "z_min_bc",
        "z_max_bc",
    )
    for key in required_properties:
        if not _is_readable(properties, key):
            blockers.append(f"fdtd_property_unreadable:{key}")

    if not fdtd_configuration.get(
        "cpu_express_mode_evidence", {}
    ).get("cpu_confirmed"):
        blockers.append("cpu_express_mode_unconfirmed")

    for role in (
        "pillar", "substrate", "source",
        "monitors", "analysis_group",
    ):
        if not resolved_roles.get(role):
            blockers.append(f"role_unresolved:{role}")

    for name in ("ratio", "height", "period"):
        parameter = model_parameters.get(name, {})
        if "value" not in parameter:
            blockers.append(f"model_parameter_unreadable:{name}")

    if errors:
        blockers.append("probe_has_errors")
    return {"ready": not blockers, "blockers": blockers}
