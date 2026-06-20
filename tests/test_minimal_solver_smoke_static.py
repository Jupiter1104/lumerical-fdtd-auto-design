"""Static analysis tests for minimal_solver_smoke.py.

Verifies the script contains expected patterns without requiring Windows execution.
"""

from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "windows" / "minimal_solver_smoke.py"


def _read() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists_and_is_readable():
    assert SCRIPT.exists()
    content = _read()
    assert len(content) > 100


def test_creates_one_project():
    content = _read()
    assert "/project/new" in content


def test_creates_one_fixed_structure():
    content = _read()
    assert "object_type" in content
    assert "rectangle" in content


def test_creates_one_fdtd_region():
    content = _read()
    assert "fdtd_region" in content


def test_creates_one_source():
    content = _read()
    assert "/sources" in content
    assert "source_type" in content


def test_creates_one_monitor():
    content = _read()
    assert "/monitors" in content
    assert "monitor_type" in content


def test_creates_one_analysis_group():
    content = _read()
    assert "/analysis-groups" in content
    assert '"properties": {}' in content
    assert '"script": "T=1;"' not in content


def test_runs_once():
    content = _read()
    assert "/simulation/run" in content


def test_reads_one_result():
    content = _read()
    assert "/results/mon/T/value" in content


def test_saves_fsp():
    content = _read()
    assert "/project/save" in content
    assert "smoke_model.fsp" in content
    assert '"file_path"' in content


def test_downloads_result_file():
    content = _read()
    assert "/results/mon/T/download" in content
    assert "/results/smoke_report.json" not in content
    assert "downloaded_results.json" in content
    assert "result_download" in content


def test_writes_structured_result_file():
    content = _read()
    assert "smoke_report.json" in content
    assert "output_dir" in content


def test_marks_technical_smoke_true():
    content = _read()
    assert '"technical_smoke": True' in content


def test_marks_physical_conclusion_false():
    content = _read()
    assert '"physical_conclusion": False' in content


def test_does_not_create_sweep_jobs():
    content = _read()
    assert "/jobs/start" not in content
    assert "sweep" not in content.lower()


def test_has_argparse_help():
    content = _read()
    assert "ArgumentParser" in content
    assert "--help" in content or "help" in content.lower()
