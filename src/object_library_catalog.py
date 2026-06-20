from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .fdtd_schema import fingerprint_json

CATALOG_SCHEMA_VERSION = "1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: str | None) -> str:
    if not path:
        return ""
    file = Path(path)
    if not file.is_file():
        return ""
    digest = hashlib.sha256()
    with file.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _path_version_tag(python_executable: str) -> str:
    for part in Path(python_executable).parts:
        if part.lower().startswith("v") and part[1:].isdigit():
            return part
    return ""


def resolve_object_library_root(
    environ: Mapping[str, str] | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    if env.get("STATE_ROOT"):
        return Path(env["STATE_ROOT"]) / "object-library"
    if env.get("LOCALAPPDATA"):
        return Path(env["LOCALAPPDATA"]) / "fdtd-mcp" / "object-library"
    return Path.cwd() / "runtime" / "object-library"


def build_installation_identity(
    solver_version: str,
    python_executable: str = sys.executable,
    lumapi_file: str | None = None,
) -> dict:
    return {
        "product": "FDTD",
        "solver_version": str(solver_version or "unknown"),
        "path_version_tag": _path_version_tag(python_executable),
        "lumapi_sha256": _sha256_file(lumapi_file),
    }


def identity_is_stable(identity: dict) -> bool:
    if identity.get("solver_version") not in {"", None, "unknown"}:
        return True
    return bool(identity.get("path_version_tag") and identity.get("lumapi_sha256"))


def identity_fingerprint(identity: dict) -> str:
    return fingerprint_json(identity)


class ObjectLibraryCatalog:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.Lock()
        self._catalog: dict | None = None
        self._path: Path | None = None

    def _write_atomic(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temp.replace(path)

    def ensure(
        self,
        identity: dict,
        enumerate_ids: Callable[[], list[str]],
    ) -> dict:
        with self._lock:
            stable = identity_is_stable(identity)
            fingerprint = identity_fingerprint(identity)
            path = self.root / f"catalog-{fingerprint.removeprefix('sha256:')}.json"
            if stable and path.is_file():
                self._catalog = json.loads(path.read_text(encoding="utf-8"))
                self._path = path
                return {**self._catalog, "catalog_cached": True}

            script_ids = sorted({str(item) for item in enumerate_ids() if str(item)})
            payload = {
                "schema_version": CATALOG_SCHEMA_VERSION,
                "installation_identity": identity,
                "identity": fingerprint,
                "status": "ready" if stable else "identity_unstable",
                "generated_at": _utc_now(),
                "script_ids": script_ids,
                "probes": {},
            }
            self._catalog = payload
            self._path = path if stable else None
            if stable:
                self._write_atomic(path, payload)
            return {**payload, "catalog_cached": False}

    def get_probe(self, script_id: str) -> dict | None:
        if self._catalog is None:
            return None
        return self._catalog.get("probes", {}).get(script_id)

    def put_probe(self, script_id: str, probe: dict) -> dict:
        if self._catalog is None:
            raise RuntimeError("Object Library catalog is not initialized.")
        self._catalog.setdefault("probes", {})[script_id] = {
            **probe,
            "probed_at": _utc_now(),
        }
        if self._path is not None:
            self._write_atomic(self._path, self._catalog)
        return self._catalog["probes"][script_id]

    def data(self) -> dict:
        return dict(self._catalog or {})

    def summary(self) -> dict:
        catalog = self._catalog or {}
        verified = sum(
            probe.get("status") == "verified_analysis_group"
            for probe in catalog.get("probes", {}).values()
        )
        return {
            "status": catalog.get("status", "unavailable"),
            "identity": catalog.get("identity", ""),
            "script_id_count": len(catalog.get("script_ids", [])),
            "verified_analysis_group_count": verified,
            "generated_at": catalog.get("generated_at"),
            "catalog_path": str(self._path) if self._path else None,
        }
