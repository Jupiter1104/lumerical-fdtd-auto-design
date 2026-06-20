from pathlib import Path

import pytest

from src.object_library_catalog import (
    ObjectLibraryCatalog,
    build_installation_identity,
    identity_fingerprint,
    resolve_object_library_root,
)


def identity(version="2024 R2.4", lumapi_sha="sha256:aaa"):
    return {
        "product": "FDTD",
        "solver_version": version,
        "path_version_tag": "v242",
        "lumapi_sha256": lumapi_sha,
    }


def test_same_identity_reuses_catalog_without_enumerating(tmp_path):
    calls = []
    store = ObjectLibraryCatalog(tmp_path)
    first = store.ensure(identity(), lambda: calls.append("enumerate") or ["box", "farfield"])
    second = store.ensure(identity(), lambda: calls.append("again") or ["wrong"])

    assert calls == ["enumerate"]
    assert first["script_ids"] == ["box", "farfield"]
    assert second["script_ids"] == ["box", "farfield"]
    assert second["catalog_cached"] is True


def test_version_or_lumapi_hash_change_creates_new_catalog(tmp_path):
    store = ObjectLibraryCatalog(tmp_path)
    store.ensure(identity(), lambda: ["v1"])
    changed = store.ensure(
        identity(version="2024 R2.5", lumapi_sha="sha256:bbb"),
        lambda: ["v2"],
    )

    assert changed["script_ids"] == ["v2"]
    assert len(list(tmp_path.glob("catalog-*.json"))) == 2


def test_unknown_version_requires_path_tag_and_lumapi_hash_for_disk_cache(tmp_path):
    unstable = {
        "product": "FDTD",
        "solver_version": "unknown",
        "path_version_tag": "",
        "lumapi_sha256": "",
    }
    calls = []
    store = ObjectLibraryCatalog(tmp_path)
    first = store.ensure(unstable, lambda: calls.append(1) or ["a"])
    second_store = ObjectLibraryCatalog(tmp_path)
    second = second_store.ensure(unstable, lambda: calls.append(2) or ["b"])

    assert calls == [1, 2]
    assert first["status"] == "identity_unstable"
    assert second["script_ids"] == ["b"]
    assert list(tmp_path.glob("catalog-*.json")) == []


def test_probe_records_are_atomic_and_version_scoped(tmp_path):
    store = ObjectLibraryCatalog(tmp_path)
    store.ensure(identity(), lambda: ["power_box"])
    store.put_probe("power_box", {
        "status": "verified_analysis_group",
        "setup_properties": [],
        "analysis_properties": [],
        "analysis_results": [{"name": "T", "type_code": 0}],
        "settable_properties": [],
        "probe_evidence": {},
    })

    assert store.get_probe("power_box")["analysis_results"][0]["name"] == "T"
    assert not list(tmp_path.glob("*.tmp"))


def test_put_probe_without_ensure_raises_error(tmp_path):
    store = ObjectLibraryCatalog(tmp_path)
    with pytest.raises(RuntimeError, match="not initialized"):
        store.put_probe("anything", {"status": "nope"})


def test_get_probe_without_ensure_returns_none(tmp_path):
    store = ObjectLibraryCatalog(tmp_path)
    assert store.get_probe("anything") is None


def test_build_installation_identity_defaults():
    ident = build_installation_identity(solver_version="2024 R2.4")
    assert ident["product"] == "FDTD"
    assert ident["solver_version"] == "2024 R2.4"
    assert isinstance(ident["path_version_tag"], str)
    assert ident["lumapi_sha256"] == ""


def test_build_installation_identity_with_lumapi(tmp_path):
    lumapi = tmp_path / "lumapi.py"
    lumapi.write_text("mock content")
    ident = build_installation_identity(
        solver_version="2024 R2.6", python_executable="/usr/bin/python3",
        lumapi_file=str(lumapi),
    )
    assert ident["solver_version"] == "2024 R2.6"
    assert ident["lumapi_sha256"].startswith("sha256:")


def test_build_installation_identity_path_version_tag():
    ident = build_installation_identity(
        solver_version="2024 R2.5",
        python_executable="/opt/lumerical/v242/bin/python",
    )
    assert ident["path_version_tag"] == "v242"


def test_build_installation_identity_path_no_version_tag():
    ident = build_installation_identity(
        solver_version="2024 R2.5",
        python_executable="/usr/bin/python3",
    )
    assert ident["path_version_tag"] == ""


def test_identity_fingerprint_is_deterministic():
    fp1 = identity_fingerprint(identity())
    fp2 = identity_fingerprint(identity())
    assert fp1 == fp2


def test_identity_fingerprint_differs_on_different_identity():
    fp_a = identity_fingerprint(identity(version="2024 R2.4"))
    fp_b = identity_fingerprint(identity(version="2024 R2.6"))
    assert fp_a != fp_b


def test_resolve_object_library_root_default():
    root = resolve_object_library_root(environ={})
    assert str(root).endswith("runtime/object-library") or str(root).endswith(
        "runtime\\object-library"
    )


def test_resolve_object_library_root_state_root():
    root = resolve_object_library_root(environ={"STATE_ROOT": "/opt/data"})
    assert root == Path("/opt/data/object-library")


def test_resolve_object_library_root_localappdata():
    root = resolve_object_library_root(
        environ={"LOCALAPPDATA": "/home/user/appdata"}
    )
    assert root == Path("/home/user/appdata/fdtd-mcp/object-library")
