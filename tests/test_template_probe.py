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
