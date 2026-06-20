from pathlib import Path

from src.object_library_catalog import (
    ObjectLibraryCatalog,
    build_installation_identity,
    identity_fingerprint,
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
