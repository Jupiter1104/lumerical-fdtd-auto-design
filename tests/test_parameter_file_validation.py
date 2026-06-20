"""Tests for validate_parameter_file.py — offline parameter validation."""

import json
import subprocess
import sys
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_parameters.json"
SCRIPT = Path(__file__).parent.parent / "scripts" / "validate_parameter_file.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    """Run the validation script without any env manipulation."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True,
    )


def test_help_exits_zero():
    result = _run("--help")
    assert result.returncode == 0
    assert "--parameter-file" in result.stdout


def test_validates_synthetic_parameters():
    result = _run("--parameter-file", str(FIXTURE))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert output["parameter_count"] == 3
    assert output["task_count"] == 1
    assert output["recipe_fingerprint"].startswith("sha256:")
    assert output["sweep_fingerprint"].startswith("sha256:")
    assert output["packet_fingerprint"].startswith("sha256:")
    assert output["technical_validation"] is True
    assert output["physical_conclusion"] is False


def test_rejects_missing_file():
    result = _run("--parameter-file", "/nonexistent/file.json")
    assert result.returncode != 0
    output = json.loads(result.stdout)
    assert output["ok"] is False


def test_rejects_invalid_json():
    bad_file = Path(__file__).parent / "fixtures" / "_tmp_bad.json"
    bad_file.write_text("not json{{{")
    try:
        result = _run("--parameter-file", str(bad_file))
        assert result.returncode != 0
        output = json.loads(result.stdout)
        assert output["ok"] is False
    finally:
        bad_file.unlink(missing_ok=True)


def test_no_call_to_jobs_start():
    """Verify the script does not import or reference jobs/start."""
    content = SCRIPT.read_text()
    assert "/jobs/start" not in content
    assert "recipe_build" not in content
    assert "RpcClient" not in content


def test_task_count_equals_cartesian_product():
    result = _run("--parameter-file", str(FIXTURE))
    output = json.loads(result.stdout)
    assert output["task_count"] == 1


def test_physical_conclusion_is_always_false():
    result = _run("--parameter-file", str(FIXTURE))
    output = json.loads(result.stdout)
    assert output["physical_conclusion"] is False
