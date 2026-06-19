from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_windows_inventory_entry_uses_lumerical_python_and_read_only_mode():
    text = (
        ROOT
        / "scripts"
        / "windows"
        / "inspect_metasurface_template.bat"
    ).read_text(encoding="utf-8")

    assert r"F:\Program Files\Lumerical\v242\python\python.exe" in text
    assert "scripts\\inspect_metasurface_template.py" in text
    assert "--inventory" in text
    assert "base_model.fsp" in text
    assert "base_model.inventory.json" in text
