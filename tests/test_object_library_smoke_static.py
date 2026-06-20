"""Static analysis tests for object_library_analysis_group_smoke.py.

Verifies the script contains expected patterns without requiring Windows execution.
"""

from pathlib import Path

SCRIPT = (
    Path(__file__).parent.parent
    / "scripts"
    / "windows"
    / "object_library_analysis_group_smoke.py"
)


def content():
    return SCRIPT.read_text(encoding="utf-8")


def test_smoke_is_non_solver_technical_evidence():
    text = content()
    assert '"technical_smoke": True' in text
    assert '"physical_conclusion": False' in text
    assert "/simulation/run" not in text
    assert "/jobs/start" not in text


def test_smoke_checks_catalog_probe_setup_and_restore():
    text = content()
    assert "/session/start" in text
    assert "/analysis-groups" in text
    assert '"prefer_builtin": True' in text
    assert '"require_builtin": True' in text
    assert '"catalog_enumerated"' in text
    assert '"probe_restore_verified"' in text
    assert '"setup_verified"' in text


def test_smoke_writes_fsp_and_json_report():
    text = content()
    assert "/project/save" in text
    assert "object_library_model.fsp" in text
    assert "object_library_smoke_report.json" in text
