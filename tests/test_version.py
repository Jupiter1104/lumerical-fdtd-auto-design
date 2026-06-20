"""Version tests for fdtd-mcp 0.1.0."""


def test_version_is_single_source_for_0_1_0():
    from src.version import __version__

    assert __version__ == "0.1.0"


def test_version_can_be_imported_from_src():
    import src

    assert hasattr(src, "__version__")
