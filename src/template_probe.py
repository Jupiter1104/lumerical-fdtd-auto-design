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
