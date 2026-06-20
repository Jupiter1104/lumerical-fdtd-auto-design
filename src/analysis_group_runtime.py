from __future__ import annotations

import shutil
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .fdtd_schema import fingerprint_json


class AnalysisRuntimeError(Exception):
    def __init__(
        self,
        error_type: str,
        message: str,
        status_code: int = 409,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class SessionOperationGate:
    def __init__(self):
        self._lock = threading.RLock()
        self.active_kind: str | None = None

    @contextmanager
    def acquire(self, kind: str, timeout: float = 5.0):
        if not self._lock.acquire(timeout=timeout):
            raise AnalysisRuntimeError(
                "analysis_probe_unavailable",
                f"FDTD session is busy with {self.active_kind or 'another operation'}.",
            )
        previous_kind = self.active_kind
        self.active_kind = kind
        try:
            yield
        finally:
            self.active_kind = previous_kind
            self._lock.release()


class LumapiBridge:
    def __init__(self, session_or_backend: Any):
        self.owner = session_or_backend
        self.raw = getattr(session_or_backend, "fdtd", None) or session_or_backend

    def call(self, name: str, *args):
        method = getattr(self.raw, name, None)
        if not callable(method):
            raise AnalysisRuntimeError(
                "analysis_probe_failed",
                f"lumapi command {name} is unavailable.",
                500,
            )
        return method(*args)

    def runsetup(self, name: str) -> None:
        self.call("select", name)
        self.call("runsetup")

    def is_layout_mode(self) -> bool:
        return bool(self.call("layoutmode"))

    def current_model_file(self) -> str | None:
        return getattr(self.owner, "_model_file", None)

    def restore_model_reference(self, file_path: str | None) -> None:
        if hasattr(self.owner, "_model_file"):
            self.owner._model_file = file_path

    def save(self, path: Path) -> None:
        target = getattr(self.owner, "save", None) or getattr(self.raw, "save")
        target(str(path))

    def load(self, path: Path) -> None:
        target = getattr(self.owner, "load", None) or getattr(self.raw, "load")
        target(str(path))

    def list_objects(self) -> list[str]:
        get_all = getattr(self.raw, "getAllObjects", None)
        if callable(get_all):
            value = get_all()
        else:
            method = getattr(self.raw, "ls", None)
            if callable(method):
                value = method()
            else:
                self.raw.eval("__fdtd_mcp_object_names=ls;")
                value = self.raw.getv("__fdtd_mcp_object_names")
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        return [str(item) for item in (value or [])]


def _schema(query: Any) -> list[dict]:
    if not isinstance(query, dict):
        return []
    names = list(query.get("name", []))
    types = list(query.get("type", []))
    return [
        {"name": str(name), "type_code": int(types[index])}
        for index, name in enumerate(names)
        if index < len(types)
    ]


class AnalysisGroupInspector:
    def __init__(self, bridge, catalog, work_root: Path, operation_gate):
        self.bridge = bridge
        self.catalog = catalog
        self.work_root = Path(work_root)
        self.operation_gate = operation_gate
        self._failed_this_session: set[str] = set()

    def _read_inserted_group(self, name: str) -> dict:
        try:
            analysis = _schema(self.bridge.call("queryanalysisprop", name))
        except Exception as exc:
            return {
                "status": "not_analysis_group",
                "error": {
                    "type": "not_analysis_group",
                    "message": str(exc),
                },
                "setup_properties": [],
                "analysis_properties": [],
                "analysis_results": [],
                "settable_properties": [],
                "probe_evidence": {},
            }

        try:
            setup = _schema(self.bridge.call("queryuserprop", name))
            results = _schema(self.bridge.call("queryanalysisresult", name))
            settable_raw = self.bridge.call("querynamed", name)
        except Exception as exc:
            return {
                "status": "probe_failed",
                "error": {
                    "type": "analysis_probe_failed",
                    "message": str(exc),
                },
                "setup_properties": [],
                "analysis_properties": analysis,
                "analysis_results": [],
                "settable_properties": [],
                "probe_evidence": {},
            }

        settable = (
            [line.strip() for line in settable_raw.splitlines() if line.strip()]
            if isinstance(settable_raw, str)
            else [str(item) for item in (settable_raw or [])]
        )
        for item in setup + analysis:
            try:
                item["default_value"] = self.bridge.call(
                    "getnamed", name, item["name"]
                )
                item["default_readable"] = True
            except Exception:
                item["default_readable"] = False
        return {
            "status": "verified_analysis_group",
            "setup_properties": setup,
            "analysis_properties": analysis,
            "analysis_results": results,
            "settable_properties": settable,
            "probe_evidence": {},
        }

    def inspect(self, script_id: str) -> dict:
        cached = self.catalog.get_probe(script_id)
        if cached and cached.get("status") in {
            "verified_analysis_group",
            "not_analysis_group",
        }:
            return cached
        if cached and cached.get("status") == "probe_failed":
            if script_id in self._failed_this_session:
                return cached

        with self.operation_gate.acquire("analysis_probe"):
            if not self.bridge.is_layout_mode():
                raise AnalysisRuntimeError(
                    "analysis_probe_unavailable",
                    "Object Library probe is disabled while FDTD is in Analysis mode.",
                    409,
                )
            work = self.work_root / f"probe-{uuid.uuid4().hex}"
            restore = work / "restore.fsp"
            work.mkdir(parents=True, exist_ok=False)
            before = self.bridge.list_objects()
            original_model_file = self.bridge.current_model_file()
            restored = False
            probe: dict | None = None
            try:
                self.bridge.save(restore)
                self.bridge.call("newproject")
                self.bridge.call("addobject", script_id)
                name = f"__fdtd_mcp_probe_{uuid.uuid4().hex}"
                self.bridge.call("set", "name", name)
                probe = self._read_inserted_group(name)
            except AnalysisRuntimeError:
                raise
            except Exception as exc:
                probe = {
                    "status": "probe_failed",
                    "error": {
                        "type": "analysis_probe_failed",
                        "message": str(exc),
                    },
                    "setup_properties": [],
                    "analysis_properties": [],
                    "analysis_results": [],
                    "settable_properties": [],
                    "probe_evidence": {},
                }
            finally:
                try:
                    self.bridge.load(restore)
                    self.bridge.restore_model_reference(original_model_file)
                    restored = self.bridge.list_objects() == before
                except Exception as exc:
                    raise AnalysisRuntimeError(
                        "analysis_probe_restore_failed",
                        "Failed to restore the project after Object Library probe.",
                        500,
                        {"message": str(exc), "work_dir": str(work)},
                    ) from exc
                if not restored:
                    raise AnalysisRuntimeError(
                        "analysis_probe_restore_failed",
                        "Project object signature changed after Object Library probe.",
                        500,
                        {
                            "before": fingerprint_json(before),
                            "after": fingerprint_json(self.bridge.list_objects()),
                            "work_dir": str(work),
                        },
                    )
                shutil.rmtree(work, ignore_errors=True)

            probe["probe_evidence"]["restore_verified"] = True
            stored = self.catalog.put_probe(script_id, probe)
            if stored.get("status") == "probe_failed":
                self._failed_this_session.add(script_id)
            else:
                self._failed_this_session.discard(script_id)
            return stored
