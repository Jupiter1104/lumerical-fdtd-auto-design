"""Tests for Stage B0 template probe helpers and output contract."""

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


# --- Probe output contract tests ---


def test_probe_fingerprint_excludes_own_field():
    from src.template_probe import probe_fingerprint

    probe = {
        "probe_version": "0.1",
        "probe_fingerprint": "old",
        "template": {"sha256": "abc"},
        "objects": [],
    }
    first = probe_fingerprint(probe)
    probe["probe_fingerprint"] = "different"
    assert probe_fingerprint(probe) == first


def test_probe_json_is_git_ignored():
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "templates/metasurface/base_model.probe.json" in ignore_text


def test_stable_json_rejects_nan():
    from src.template_probe import stable_json

    assert stable_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    with pytest.raises(ValueError):
        stable_json({"value": float("nan")})


def test_probe_module_no_forbidden_imports():
    """Probe module must not import or expose forbidden operations."""
    # This test verifies the probe module can be imported on Mac (no lumapi)
    import src.template_probe as tp
    for forbidden in (
        "run", "runjobs", "runanalysis", "save", "set", "setnamed",
        "delete", "addrect", "addcircle",
    ):
        assert not hasattr(tp, forbidden), f"module exposes forbidden: {forbidden}"


# --- Installation identity tests ---


class MockLumapiModule:
    """Simulates a lumapi module for install identity tests."""

    def __init__(self, file_path, with_file=True):
        if with_file:
            self.__file__ = file_path


def test_version_unknown_with_complete_install_identity_produces_warning_not_fail():
    from src.template_probe import (
        probe_installation_identity,
        validate_probe_installation,
    )

    # Simulate v242: lumapi.__file__ exists, but getversion is not a Python method
    mock = MockLumapiModule(
        "/install/Lumerical/v242/api/python/lumapi.py", with_file=True
    )
    # Make the file actually exist for sha256
    import tempfile
    import os as _os
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(b"# mock lumapi\n")
        tmp_path = f.name
    try:
        mock.__file__ = tmp_path
        identity = probe_installation_identity(mock)
        fail, warnings = validate_probe_installation(identity)

        assert fail is False
        assert any(w["type"] == "version_unknown_warning" for w in warnings)
        assert identity["confirmable"] is True
        assert identity["lumapi_sha256"] is not None
    finally:
        _os.unlink(tmp_path)


def test_completely_unconfirmable_install_identity_fails():
    from src.template_probe import (
        probe_installation_identity,
        validate_probe_installation,
    )

    # Simulate lumapi where __file__ doesn't exist and no path info
    mock = MockLumapiModule("", with_file=False)
    identity = probe_installation_identity(mock)
    fail, warnings = validate_probe_installation(identity)

    assert fail is True
    assert any(
        "unconfirmable" in w.get("type", "").lower() for w in [{"type": e.get("type", "")} for e in identity.get("errors", [])]
    ) or identity["confirmable"] is False


def test_path_version_tag_derived_from_lumapi_file(tmp_path):
    from src.template_probe import probe_installation_identity

    # Build a fake directory structure: .../v242/api/python/lumapi.py
    version_dir = tmp_path / "v242"
    api_dir = version_dir / "api"
    python_dir = api_dir / "python"
    python_dir.mkdir(parents=True)
    lumapi_file = python_dir / "lumapi.py"
    lumapi_file.write_text("# mock lumapi\n")

    mock = MockLumapiModule(str(lumapi_file), with_file=True)
    identity = probe_installation_identity(mock)

    assert identity["path_version_tag"] == "v242"
    assert identity["install_root"] == str(tmp_path)
    assert identity["api_python_path"] == str(python_dir)
    assert identity["confirmable"] is True
