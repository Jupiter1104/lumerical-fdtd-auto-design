from __future__ import annotations

import shutil
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .analysis_group_selection import (
    AnalysisSelectionError,
    choose_high_confidence,
    rank_probed_candidates,
    resolve_analysis_intent,
    resolve_analysis_parameters,
    shortlist_candidates,
)
from .fdtd_schema import fingerprint_json

_SENTINEL = object()


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

    @property
    def raw(self):
        """Dynamically resolve the backend so that a SessionManager that
        acquires ``.fdtd`` after bridge construction is visible."""
        return getattr(self.owner, "fdtd", None) or self.owner

    def call(self, name: str, *args):
        raw = self.raw
        method = getattr(raw, name, None)
        if not callable(method):
            # When the owner carries an explicit ``.fdtd`` that is falsy
            # (None / not-yet-started) the session is inactive.  When the
            # owner has no ``.fdtd`` attribute at all we treat the owner
            # itself as the backend — the backend just lacks this command.
            fdtd = getattr(self.owner, "fdtd", _SENTINEL)
            if fdtd is _SENTINEL:
                # owner IS the backend; missing method is a probe failure
                raise AnalysisRuntimeError(
                    "analysis_probe_failed",
                    f"lumapi command {name} is unavailable.",
                    500,
                )
            if not fdtd:
                raise AnalysisRuntimeError(
                    "session_not_active",
                    "FDTD session is not active — no lumapi backend available.",
                    409,
                )
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


class AnalysisGroupService:
    """Orchestrates the full selection flow: intent -> catalog -> shortlist ->
    probe -> parameter resolution -> builtin creation -> setup -> readback
    verification -> fallback.
    """

    def __init__(self, adapter, bridge, catalog, inspector):
        self.adapter = adapter
        self.bridge = bridge
        self.catalog = catalog
        self.inspector = inspector

    def _fallback(
        self,
        body: dict,
        reason: str | None,
        candidates: list[dict],
        fallback_used: bool = True,
    ) -> dict:
        if body.get("require_builtin"):
            raise AnalysisRuntimeError(
                "builtin_analysis_group_no_high_confidence_match",
                "No verified Object Library analysis group passed the selection gate.",
                400,
                {"candidates": candidates[:5], "reason": reason},
            )
        custom = self.adapter.analysis_group_create(
            name=body["name"],
            properties=body.get("properties", {}),
            dry_run=body.get("dry_run", False),
        )
        return {
            **custom,
            "source": "custom",
            "script_id": "",
            "match_confidence": 0.0,
            "match_reasons": [],
            "candidates": candidates[:5],
            "parameters": {
                "applied": body.get("properties", {}),
                "defaults_preserved": {},
                "unresolved": [],
                "verification": {},
            },
            "setup_verified": False,
            "fallback_used": fallback_used,
            "fallback_reason": reason,
            "physical_conclusion": False,
        }

    def create(self, body: dict) -> dict:
        requested_builtin = bool(
            body.get("prefer_builtin")
            or body.get("require_builtin")
            or body.get("script_id")
        )
        if not requested_builtin:
            return self._fallback(
                body,
                None,
                [],
                fallback_used=False,
            )

        catalog = self.catalog.data()
        intent = resolve_analysis_intent(
            body.get("analysis_intent"),
            body.get("recipe_context"),
        )
        script_id = str(body.get("script_id", ""))
        if script_id:
            if script_id not in catalog.get("script_ids", []):
                if body.get("require_builtin"):
                    raise AnalysisRuntimeError(
                        "object_library_script_id_not_found",
                        f"{script_id!r} is not present in the current Object Library.",
                        400,
                    )
                return self._fallback(body, "script_id_not_found", [])
            shortlist = [{
                "script_id": script_id,
                "score": 1.0,
                "match_reasons": ["explicit_script_id"],
                "probe": self.catalog.get_probe(script_id),
            }]
        else:
            shortlist = shortlist_candidates(
                catalog,
                intent,
                body.get("recipe_context") or {},
            )

        if body.get("dry_run"):
            ranked = rank_probed_candidates(
                shortlist,
                intent,
                body.get("recipe_context") or {},
            )
            chosen = choose_high_confidence(ranked)
            return {
                "name": body["name"],
                "source": "builtin" if chosen else "custom",
                "script_id": chosen["script_id"] if chosen else "",
                "intent": intent,
                "candidates": ranked or shortlist,
                "probe_required": any(not item.get("probe") for item in shortlist),
                "fallback_used": chosen is None,
                "fallback_reason": None if chosen else "probe_required_or_low_confidence",
                "physical_conclusion": False,
            }

        inspected = []
        for candidate in shortlist:
            probe = candidate.get("probe") or self.inspector.inspect(
                candidate["script_id"]
            )
            inspected.append({**candidate, "probe": probe})
        ranked = rank_probed_candidates(
            inspected,
            intent,
            body.get("recipe_context") or {},
        )
        chosen = choose_high_confidence(ranked)
        if script_id and ranked:
            chosen = ranked[0]
        if chosen is None:
            return self._fallback(body, "no_high_confidence_match", ranked)

        probe = chosen["probe"]
        try:
            parameter_context = {
                **(body.get("recipe_context") or {}),
                "explicit_properties": body.get("properties", {}),
            }
            parameters = resolve_analysis_parameters(
                probe,
                body.get("parameter_overrides", {}),
                parameter_context,
            )
        except AnalysisSelectionError as exc:
            raise AnalysisRuntimeError(
                exc.error_type, exc.message, 400, exc.details
            ) from exc

        self.adapter.create_verified_builtin_analysis_group(
            chosen["script_id"], body["name"]
        )
        try:
            for name, value in parameters["applied"].items():
                self.bridge.call("setnamed", body["name"], name, value)
            self.bridge.runsetup(body["name"])
            verification = {}
            for name, expected in parameters["applied"].items():
                actual = self.bridge.call("getnamed", body["name"], name)
                matched = (
                    abs(actual - expected) <= max(abs(expected), 1.0) * 1e-12
                    if isinstance(expected, (int, float))
                    else actual == expected
                )
                verification[name] = {
                    "expected": expected,
                    "actual": actual,
                    "matched": matched,
                }
            if not all(item["matched"] for item in verification.values()):
                raise AnalysisRuntimeError(
                    "analysis_parameter_verification_failed",
                    "One or more analysis parameters failed readback verification.",
                    409,
                    {"verification": verification},
                )
        except Exception as exc:
            self.adapter.delete_named_object(body["name"])
            if isinstance(exc, AnalysisRuntimeError) and body.get("require_builtin"):
                raise
            if body.get("require_builtin"):
                raise AnalysisRuntimeError(
                    "analysis_setup_failed", str(exc), 409
                ) from exc
            return self._fallback(body, "builtin_setup_or_verification_failed", ranked)

        parameters["verification"] = verification
        return {
            "name": body["name"],
            "source": "builtin",
            "script_id": chosen["script_id"],
            "catalog_identity": catalog.get("identity", ""),
            "catalog_status": catalog.get("status", "unavailable"),
            "intent": intent,
            "match_confidence": chosen["score"],
            "match_reasons": chosen["match_reasons"],
            "candidates": ranked[:5],
            "probe": {
                "status": "cached_or_executed",
                "restore_verified": probe["probe_evidence"]["restore_verified"],
            },
            "probe_schema_fingerprint": fingerprint_json({
                "setup_properties": probe.get("setup_properties", []),
                "analysis_properties": probe.get("analysis_properties", []),
                "analysis_results": probe.get("analysis_results", []),
                "settable_properties": probe.get("settable_properties", []),
            }),
            "parameters": parameters,
            "setup_verified": True,
            "fallback_used": False,
            "fallback_reason": None,
            "physical_conclusion": False,
        }
