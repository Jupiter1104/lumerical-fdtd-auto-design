"""FDTD RPC Server — Windows Flask service.

The process owns one persistent lumapi session. Mac-side clients call the v1
HTTP contract defined in docs/superpowers/specs/.

Run on Windows:
    python rpc_server.py --port 5000
"""

import argparse
import importlib
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from src.device_recipe import compile_recipe
from src.job_store import JobError, JobStore
from src.object_library_catalog import (
    ObjectLibraryCatalog,
    build_installation_identity,
    resolve_object_library_root,
)
from src.native_sweep import NativeSweepRunner
from src.sweep_job import write_job_artifacts
from src.windows_fdtd_adapter import AdapterError, WindowsFdtdAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fdtd-rpc")

FDTD_CLOSE_TIMEOUT_SECONDS = 5.0


class RpcError(Exception):
    """An expected API error with a stable machine-readable type."""

    def __init__(
        self,
        error_type: str,
        message: str,
        status_code: int,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _import_lumapi():
    """Import lumapi only when a real FDTD session is started."""
    try:
        module = importlib.import_module("ansys.lumerical.core")
        logger.info("Using ansys-lumerical-core")
        return module
    except ImportError:
        logger.info("ansys-lumerical-core unavailable; trying raw lumapi")

    candidate_paths = []
    if os.environ.get("LUMAPI_PATH"):
        candidate_paths.append(Path(os.environ["LUMAPI_PATH"]))
    candidate_paths.append(Path(sys.executable).resolve().parent.parent / "api" / "python")
    for candidate in candidate_paths:
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.append(str(candidate))

    try:
        module = importlib.import_module("lumapi")
        logger.info("Using raw lumapi")
        return module
    except ImportError as exc:
        raise RpcError(
            "backend_unavailable",
            "Cannot import lumapi. Run with Lumerical's Python or install the supported API package.",
            500,
        ) from exc


def _to_jsonable(value: Any) -> Any:
    """Convert common lumapi/numpy return values to JSON-compatible values."""
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return _to_jsonable(value.tolist())
    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}
    return value


class SessionManager:
    """Singleton owner of the FDTD lumapi session."""

    _instance: Optional["SessionManager"] = None
    _fdtd = None
    _model_file: Optional[str] = None
    _lock = threading.Lock()
    _object_library_catalog = None
    _object_library_status = {"status": "unavailable"}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def is_connected(self) -> bool:
        return self._fdtd is not None

    @property
    def fdtd(self):
        return self._fdtd

    def _require_session(self):
        if self._fdtd is None:
            raise RpcError(
                "session_not_active",
                "No active FDTD session.",
                409,
            )
        return self._fdtd

    @staticmethod
    def _get_version(fdtd) -> str:
        """Read the solver version across Pythonic and raw v242 lumapi."""
        getversion = getattr(fdtd, "getversion", None)
        if callable(getversion):
            return str(getversion())

        try:
            fdtd.eval("__rpc_version=getversion;")
            return str(fdtd.getv("__rpc_version"))
        except Exception:
            logger.warning("Could not read the FDTD version.", exc_info=True)
            return "unknown"

    def configure_object_library(self, catalog: ObjectLibraryCatalog) -> None:
        self._object_library_catalog = catalog
        self._object_library_status = self._public_catalog_summary(
            catalog.summary()
        )

    @staticmethod
    def _public_catalog_summary(summary: dict) -> dict:
        public = dict(summary)
        raw_path = public.get("catalog_path")
        local_app_data = os.environ.get("LOCALAPPDATA")
        public["catalog_path"] = None
        if raw_path and local_app_data:
            try:
                relative = Path(raw_path).resolve().relative_to(
                    Path(local_app_data).resolve()
                )
                public["catalog_path"] = str(
                    Path("%LOCALAPPDATA%") / relative
                )
            except ValueError:
                pass
        return public

    @staticmethod
    def _enumerate_object_library_ids(fdtd) -> list[str]:
        addobject = getattr(fdtd, "addobject", None)
        if callable(addobject):
            raw = addobject()
        else:
            fdtd.eval("__fdtd_mcp_object_library=addobject;")
            raw = fdtd.getv("__fdtd_mcp_object_library")
        converted = _to_jsonable(raw)
        if isinstance(converted, str):
            return [line.strip() for line in converted.splitlines() if line.strip()]
        if isinstance(converted, list):
            return [str(item) for item in converted]
        return []

    def _initialize_object_library(self, lumapi, version: str) -> dict:
        catalog = self._object_library_catalog
        if catalog is None:
            catalog = ObjectLibraryCatalog(resolve_object_library_root())
            self.configure_object_library(catalog)
        identity = build_installation_identity(
            solver_version=version,
            python_executable=sys.executable,
            lumapi_file=getattr(lumapi, "__file__", None),
        )
        try:
            catalog.ensure(
                identity,
                lambda: self._enumerate_object_library_ids(self._fdtd),
            )
            self._object_library_status = self._public_catalog_summary(
                catalog.summary()
            )
        except Exception as exc:
            self._object_library_status = {
                "status": "unavailable",
                "identity": "",
                "script_id_count": 0,
                "verified_analysis_group_count": 0,
                "generated_at": None,
                "catalog_path": None,
                "enumeration_error": {
                    "type": "object_library_enumeration_failed",
                    "message": str(exc),
                },
            }
        return self._object_library_status

    def start(self, hide: bool = False) -> dict:
        """Start the only allowed FDTD session."""
        with self._lock:
            if self._fdtd is not None:
                raise RpcError(
                    "session_already_active",
                    "An FDTD session is already active.",
                    409,
                )

            lumapi = _import_lumapi()
            try:
                self._fdtd = lumapi.FDTD(hide=hide)
                version = self._get_version(self._fdtd)
            except Exception:
                if self._fdtd is not None:
                    try:
                        self._fdtd.close()
                    except Exception:
                        logger.warning(
                            "Failed to close FDTD after session start error.",
                            exc_info=True,
                        )
                self._fdtd = None
                raise

            logger.info("FDTD session started (version=%s, hide=%s)", version, hide)
            object_library_status = self._initialize_object_library(lumapi, version)
            return {
                "version": version,
                "hide": hide,
                "message": f"FDTD {version} session started.",
                "object_library": object_library_status,
            }

    @staticmethod
    def _close_backend(fdtd) -> str:
        """Close FDTD without letting raw lumapi hang the RPC service."""
        close_error = []

        def worker():
            try:
                fdtd.close()
            except Exception as exc:
                close_error.append(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(FDTD_CLOSE_TIMEOUT_SECONDS)

        if thread.is_alive():
            logger.warning(
                "FDTD close did not return within %.1fs; RPC session was detached.",
                FDTD_CLOSE_TIMEOUT_SECONDS,
            )
            return "timed_out"
        if close_error:
            error = close_error[0]
            logger.warning(
                "FDTD close raised an error.",
                exc_info=(type(error), error, error.__traceback__),
            )
            return "error"
        return "closed"

    def close(self) -> dict:
        """Detach the active session and ask FDTD to release the license."""
        with self._lock:
            if self._fdtd is None:
                return {"message": "No active FDTD session."}
            fdtd = self._fdtd
            self._fdtd = None
            self._model_file = None
            self._object_library_status = {"status": "unavailable"}

        close_state = self._close_backend(fdtd)
        if close_state == "closed":
            logger.info("FDTD session closed.")
            message = "FDTD session closed."
        else:
            logger.info("FDTD session detached (close_state=%s).", close_state)
            message = "FDTD session detached; backend close did not confirm."
        return {"message": message, "close_state": close_state}

    def status(self) -> dict:
        if self._fdtd is None:
            return {
                "connected": False,
                "version": None,
                "model_file": None,
                "object_library": self._object_library_status,
            }
        try:
            version = self._get_version(self._fdtd)
        except Exception:
            version = "unknown"
        return {
            "connected": True,
            "version": version,
            "model_file": self._model_file,
            "object_library": self._object_library_status,
        }

    def save(self, file_path: Optional[str] = None) -> dict:
        fdtd = self._require_session()
        if file_path:
            save_path = str(Path(file_path).absolute())
        elif self._model_file:
            save_path = self._model_file
        else:
            save_path = str(Path.cwd() / "fdtd_project.fsp")

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fdtd.save(save_path)
        self._model_file = save_path
        logger.info("Project saved to %s", save_path)
        return {"saved_to": save_path}

    def load(self, file_path: str) -> dict:
        fdtd = self._require_session()
        path = Path(file_path)
        if not path.exists():
            raise RpcError(
                "file_not_found",
                f"File not found: {file_path}",
                404,
                {"file_path": file_path},
            )
        absolute_path = str(path.absolute())
        fdtd.load(absolute_path)
        self._model_file = absolute_path
        logger.info("Project loaded from %s", absolute_path)
        return {"loaded": absolute_path}

    def eval(self, cmd: str) -> dict:
        result = self._require_session().eval(cmd)
        return {"result": _to_jsonable(result)}

    def getv(self, name: str) -> dict:
        value = self._require_session().getv(name)
        return {"value": _to_jsonable(value)}

    def setv(self, name: str, value: Any) -> dict:
        self._require_session().setv(name, value)
        return {"message": f"Set {name}."}

    def run(self) -> dict:
        self._require_session().run()
        logger.info("Simulation completed.")
        return {"message": "Simulation completed."}

    def getresult(self, monitor: str, attribute: str) -> dict:
        data = self._require_session().getresult(monitor, attribute)
        return {"data": _to_jsonable(data)}

    def getelectric(self, monitor: str) -> dict:
        data = self._require_session().getelectric(monitor)
        return {"data": _to_jsonable(data)}

    def addfdtd(self, **kwargs) -> dict:
        self._require_session().addfdtd(**kwargs)
        return {"message": "FDTD region added."}

    def addrect(self, **kwargs) -> dict:
        self._require_session().addrect(**kwargs)
        return {"message": "Rectangle added."}

    def addcircle(self, **kwargs) -> dict:
        self._require_session().addcircle(**kwargs)
        return {"message": "Circle added."}


LEGACY_ROUTES = {
    "/session/stop": "/session/close",
    "/file/save": "/model/save",
    "/file/load": "/model/load",
    "/eval": "/debug/eval",
    "/getv": "/debug/getv",
    "/setv": "/debug/setv",
    "/sim/run": "/simulation/run",
    "/sim/getresult": "/simulation/result",
    "/sim/getelectric": "/simulation/electric",
    "/geom/addfdtd": "/geometry/fdtd-region",
    "/geom/addrect": "/geometry/rectangle",
    "/geom/addcircle": "/geometry/circle",
}


def _success(data: Optional[dict] = None, status_code: int = 200):
    payload = {"ok": True}
    if data:
        payload.update(data)
    replacement = LEGACY_ROUTES.get(request.path)
    if replacement:
        payload["meta"] = {
            "deprecated_route": request.path,
            "use_instead": replacement,
        }
    return jsonify(payload), status_code


def _error_payload(
    error_type: str,
    message: str,
    details: Optional[dict] = None,
) -> dict:
    return {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
            "details": details or {},
        },
    }


def _json_body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RpcError(
            "validation_error",
            "JSON body must be an object.",
            400,
        )
    return data


def _required(data: dict, key: str):
    value = data.get(key)
    if value is None or value == "":
        raise RpcError(
            "validation_error",
            f"{key} is required.",
            400,
        )
    return value


def _geometry_smoke_executor(session: SessionManager):
    def run(task: dict, job_dir: Path) -> dict:
        hide = bool(task.get("input", {}).get("hide", False))
        started_here = False
        if not session.is_connected:
            session.start(hide=hide)
            started_here = True

        try:
            session.addfdtd(
                dimension="3D",
                x=0.0,
                x_span=2e-6,
                y=0.0,
                y_span=2e-6,
                z=0.0,
                z_span=1e-6,
                mesh_accuracy=2,
            )
            session.addrect(
                name=f"{task['task_id']}_waveguide",
                x=0.0,
                x_span=1e-6,
                y=0.0,
                y_span=500e-9,
                z=0.0,
                z_span=220e-9,
                material="Si (Silicon) - Palik",
            )
            model_path = job_dir / "models" / f"{task['task_id']}.fsp"
            saved = session.save(str(model_path))
            return {
                "model_file": saved.get("saved_to", str(model_path)),
                "hide": hide,
            }
        finally:
            if started_here:
                session.close()

    return run


def _job_executor(data: dict, session: SessionManager):
    if data.get("mode") != "real":
        return None
    if data.get("job_type") == "geometry-smoke":
        return _geometry_smoke_executor(session)
    return None


class SweepCoordinator:
    def __init__(self, runner, job_store=None):
        self.runner = runner
        self.job_store = job_store
        self._lock = threading.Lock()
        self._active_job_id = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._active_job_id is not None

    def start(self, job_id: str) -> None:
        with self._lock:
            if self._active_job_id is not None:
                raise RpcError(
                    "sweep_already_running",
                    f"Sweep {self._active_job_id} is already running.",
                    409,
                    {"active_job_id": self._active_job_id},
                )
            self._active_job_id = job_id

        def worker():
            try:
                self.runner.run(job_id)
            except Exception as exc:
                logger.exception(
                    "Native sweep job failed: %s", job_id
                )
                if self.job_store is not None:
                    self.job_store.fail(job_id, exc)
            finally:
                with self._lock:
                    self._active_job_id = None

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()


def _is_real_metasurface_sweep(data: dict) -> bool:
    return data.get("mode") == "real" and data.get("job_type") == "metasurface-sweep"


def _validate_real_sweep_request(data: dict) -> None:
    approval = data.get("approval") or {}
    if (
        approval.get("approved") is not True
        or approval.get("approved_for") != "real_run"
    ):
        raise JobError(
            "approval_required",
            "Real jobs require explicit approval.",
            403,
        )
    sweep = data.get("sweep") or {}
    template = Path(
        sweep.get("template")
        or "templates/metasurface/base_model.fsp"
    )
    if not template.exists():
        raise RpcError(
            "template_not_found",
            f"Sweep template not found: {template}",
            400,
            {"template": str(template)},
        )


def _write_mock_metasurface_artifacts(jobs: JobStore, job: dict) -> dict:
    write_job_artifacts(
        Path(job["job_dir"]),
        job_id=job["job_id"],
        expected_count=job["task_count"],
        include_models=False,
    )
    return jobs.finalize(job["job_id"])


def create_app(
    session_manager: Optional[SessionManager] = None,
    job_store: Optional[JobStore] = None,
    sweep_runner=None,
    backend=None,
) -> Flask:
    """Create a testable Flask app with an injectable session backend.

    Parameters
    ----------
    backend:
        Optional fake backend for tests.  When provided, the adapter wraps
        *backend* instead of the session manager, allowing typed routes to
        be exercised without a real Lumerical session.
    """
    app = Flask(__name__)
    session = session_manager or SessionManager()
    if isinstance(session, SessionManager) and session._object_library_catalog is None:
        session.configure_object_library(
            ObjectLibraryCatalog(resolve_object_library_root())
        )
    jobs = job_store or JobStore()
    jobs.recover_interrupted_jobs()
    runner = sweep_runner or NativeSweepRunner(session, jobs)
    sweeps = SweepCoordinator(runner, jobs)

    # Adapter wraps the test backend if given; otherwise wraps the session
    adapter = WindowsFdtdAdapter(backend if backend is not None else session)

    def reject_during_sweep() -> None:
        if sweeps.is_running:
            raise RpcError(
                "sweep_running",
                "Operation is unavailable while a real sweep is running.",
                409,
            )

    @app.errorhandler(RpcError)
    def handle_rpc_error(error):
        return (
            jsonify(
                _error_payload(
                    error.error_type,
                    error.message,
                    error.details,
                )
            ),
            error.status_code,
        )

    @app.errorhandler(JobError)
    def handle_job_error(error):
        return (
            jsonify(
                _error_payload(
                    error.error_type,
                    error.message,
                    error.details,
                )
            ),
            error.status_code,
        )

    @app.errorhandler(AdapterError)
    def handle_adapter_error(error):
        return (
            jsonify(
                _error_payload(
                    error.error_type,
                    error.message,
                    error.details,
                )
            ),
            error.status_code,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        if isinstance(error, HTTPException):
            return (
                jsonify(
                    _error_payload(
                        "http_error",
                        error.description,
                        {"status_code": error.code},
                    )
                ),
                error.code,
            )
        logger.exception("Unhandled RPC error")
        return (
            jsonify(
                _error_payload(
                    "internal_error",
                    str(error) or "Unexpected server error.",
                )
            ),
            500,
        )

    @app.get("/health")
    def health():
        return _success(
            {
                "api_version": "v1",
                "server": "fdtd-rpc-server",
                "connected": session.is_connected,
            }
        )

    @app.get("/status")
    def status():
        return _success(session.status())

    @app.post("/session/start")
    def session_start():
        reject_during_sweep()
        data = _json_body()
        return _success(session.start(hide=bool(data.get("hide", False))))

    @app.post("/session/close")
    @app.post("/session/stop")
    def session_close():
        reject_during_sweep()
        return _success(session.close())

    @app.post("/model/save")
    @app.post("/project/save")
    @app.post("/file/save")
    def model_save():
        reject_during_sweep()
        data = _json_body()
        return _success(session.save(data.get("file_path")))

    @app.post("/model/load")
    @app.post("/project/load")
    @app.post("/file/load")
    def model_load():
        reject_during_sweep()
        data = _json_body()
        return _success(session.load(_required(data, "file_path")))

    @app.post("/debug/eval")
    @app.post("/eval")
    def debug_eval():
        reject_during_sweep()
        data = _json_body()
        return _success(session.eval(_required(data, "cmd")))

    @app.post("/debug/getv")
    @app.post("/getv")
    def debug_getv():
        data = _json_body()
        return _success(session.getv(_required(data, "name")))

    @app.post("/debug/setv")
    @app.post("/setv")
    def debug_setv():
        reject_during_sweep()
        data = _json_body()
        name = _required(data, "name")
        return _success(session.setv(name, data.get("value")))

    @app.post("/simulation/run")
    @app.post("/sim/run")
    def simulation_run():
        reject_during_sweep()
        return _success(adapter.simulation_run())

    @app.post("/simulation/result")
    @app.post("/sim/getresult")
    def simulation_result():
        data = _json_body()
        monitor = _required(data, "monitor")
        attribute = _required(data, "attribute")
        return _success(session.getresult(monitor, attribute))

    @app.post("/simulation/electric")
    @app.post("/sim/getelectric")
    def simulation_electric():
        data = _json_body()
        monitor = data.get("monitor", "monitor")
        return _success(session.getelectric(monitor))

    @app.post("/geometry/fdtd-region")
    @app.post("/geom/addfdtd")
    def geometry_fdtd_region():
        reject_during_sweep()
        return _success(session.addfdtd(**_json_body()))

    @app.post("/geometry/rectangle")
    @app.post("/geom/addrect")
    def geometry_rectangle():
        reject_during_sweep()
        return _success(session.addrect(**_json_body()))

    @app.post("/geometry/circle")
    @app.post("/geom/addcircle")
    def geometry_circle():
        reject_during_sweep()
        return _success(session.addcircle(**_json_body()))

    # ------------------------------------------------------------------
    # Typed project routes
    # ------------------------------------------------------------------

    @app.post("/project/new")
    def project_new():
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.project_new(
                name=_required(data, "name"),
                discard_unsaved=data.get("discard_unsaved", True),
            )
        )

    @app.get("/project/status")
    def project_status():
        return _success(adapter.project_status())

    @app.post("/project/switch-layout")
    def project_switch_layout():
        reject_during_sweep()
        return _success(adapter.switch_to_layout())

    # ------------------------------------------------------------------
    # Typed object routes
    # ------------------------------------------------------------------

    @app.post("/objects")
    def objects_create():
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.object_create(
                object_type=_required(data, "object_type"),
                name=_required(data, "name"),
                properties=data.get("properties", {}),
                dry_run=data.get("dry_run", False),
            )
        )

    @app.get("/objects")
    def objects_list():
        scope = request.args.get("scope")
        object_type = request.args.get("object_type")
        return _success(adapter.object_list(scope=scope, object_type=object_type))

    @app.get("/objects/<name>")
    def objects_get(name):
        return _success(adapter.object_get(name))

    @app.put("/objects/<name>")
    def objects_update(name):
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.object_update(
                name=name,
                properties=_required(data, "properties"),
                dry_run=data.get("dry_run", False),
            )
        )

    @app.delete("/objects/<name>")
    def objects_delete(name):
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.object_delete(
                name=name,
                dry_run=data.get("dry_run", False),
            )
        )

    @app.post("/objects/<name>/copy")
    def objects_copy(name):
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.object_copy(
                name=name,
                new_name=_required(data, "new_name"),
                transform=data.get("transform"),
                dry_run=data.get("dry_run", False),
            )
        )

    @app.post("/objects/<name>/rename")
    def objects_rename(name):
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.object_rename(
                name=name,
                new_name=_required(data, "new_name"),
                dry_run=data.get("dry_run", False),
            )
        )

    @app.post("/groups")
    def groups_update():
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.group_update(
                group_name=_required(data, "group_name"),
                add=data.get("add"),
                remove=data.get("remove"),
                dry_run=data.get("dry_run", False),
            )
        )

    # ------------------------------------------------------------------
    # Typed material routes
    # ------------------------------------------------------------------

    @app.post("/materials")
    def materials_create():
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.material_create(
                name=_required(data, "name"),
                properties=data.get("properties", {}),
                dry_run=data.get("dry_run", False),
            )
        )

    @app.get("/materials")
    def materials_list():
        return _success(adapter.material_list())

    @app.get("/materials/<name>")
    def materials_get(name):
        return _success(adapter.material_get(name))

    @app.put("/materials/<name>")
    def materials_update(name):
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.material_update(
                name=name,
                properties=_required(data, "properties"),
                dry_run=data.get("dry_run", False),
            )
        )

    @app.post("/materials/assign")
    def materials_assign():
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.material_assign(
                object_name=_required(data, "object"),
                material_name=_required(data, "material"),
                dry_run=data.get("dry_run", False),
            )
        )

    @app.post("/materials/fit-diagnose")
    def materials_fit_diagnose():
        data = _json_body()
        return _success(adapter.material_fit_diagnose(data.get("data")))

    # ------------------------------------------------------------------
    # Typed solver routes
    # ------------------------------------------------------------------

    @app.get("/solver")
    def solver_get():
        return _success(adapter.solver_get())

    @app.put("/solver")
    def solver_update():
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.solver_update(
                config=_required(data, "config"),
                dry_run=data.get("dry_run", False),
            )
        )

    @app.post("/solver/mesh-diagnose")
    def solver_mesh_diagnose():
        return _success(adapter.solver_mesh_diagnose())

    @app.get("/solver/resource-estimate")
    def solver_resource_estimate():
        return _success(adapter.solver_resource_estimate())

    # ------------------------------------------------------------------
    # Typed source routes
    # ------------------------------------------------------------------

    @app.post("/sources")
    def sources_create():
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.source_create(
                source_type=_required(data, "source_type"),
                name=_required(data, "name"),
                properties=data.get("properties", {}),
                dry_run=data.get("dry_run", False),
            )
        )

    @app.get("/sources/<name>")
    def sources_get(name):
        return _success(adapter.source_get(name))

    @app.put("/sources/<name>")
    def sources_update(name):
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.source_update(
                name=name,
                properties=_required(data, "properties"),
                dry_run=data.get("dry_run", False),
            )
        )

    # ------------------------------------------------------------------
    # Typed monitor routes
    # ------------------------------------------------------------------

    @app.post("/monitors")
    def monitors_create():
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.monitor_create(
                monitor_type=_required(data, "monitor_type"),
                name=_required(data, "name"),
                properties=data.get("properties", {}),
                dry_run=data.get("dry_run", False),
            )
        )

    @app.get("/monitors/<name>")
    def monitors_get(name):
        return _success(adapter.monitor_get(name))

    @app.put("/monitors/<name>")
    def monitors_update(name):
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.monitor_update(
                name=name,
                properties=_required(data, "properties"),
                dry_run=data.get("dry_run", False),
            )
        )

    # ------------------------------------------------------------------
    # Typed analysis-group routes
    # ------------------------------------------------------------------

    @app.post("/analysis-groups")
    def analysis_groups_create():
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.analysis_group_create(
                name=_required(data, "name"),
                properties=data.get("properties", {}),
                dry_run=data.get("dry_run", False),
                prefer_builtin=data.get("prefer_builtin", False),
                require_builtin=data.get("require_builtin", False),
                script_id=data.get("script_id", ""),
            )
        )

    @app.get("/analysis-groups/<name>")
    def analysis_groups_get(name):
        return _success(adapter.analysis_group_get(name))

    @app.put("/analysis-groups/<name>")
    def analysis_groups_update(name):
        reject_during_sweep()
        data = _json_body()
        return _success(
            adapter.analysis_group_update(
                name=name,
                properties=_required(data, "properties"),
                dry_run=data.get("dry_run", False),
            )
        )

    # ------------------------------------------------------------------
    # Typed simulation status route
    # ------------------------------------------------------------------

    @app.get("/simulation/status")
    def simulation_status():
        return _success(adapter.simulation_status())

    # ------------------------------------------------------------------
    # Typed result routes
    # ------------------------------------------------------------------

    @app.get("/results")
    def results_list():
        return _success(adapter.result_list())

    @app.get("/results/<monitor>/<attribute>")
    def results_describe(monitor, attribute):
        return _success(adapter.result_describe(monitor, attribute))

    @app.get("/results/<monitor>/<attribute>/value")
    def results_read(monitor, attribute):
        return _success(adapter.result_read(monitor, attribute))

    @app.get("/results/<monitor>/<attribute>/download")
    def results_download(monitor, attribute):
        return _success(adapter.result_download(monitor, attribute))

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    @app.post("/jobs/plan")
    def jobs_plan():
        return _success(jobs.plan(_json_body()))

    @app.post("/jobs/start")
    def jobs_start():
        data = _json_body()
        if _is_real_metasurface_sweep(data):
            _validate_real_sweep_request(data)
            job = jobs.enqueue(data)
            sweeps.start(job["job_id"])
            return _success(job, status_code=202)

        # Recipe-sweep real: enqueue and return 202 (no polling)
        if data.get("mode") == "real" and data.get("job_type") == "recipe-sweep":
            job = jobs.enqueue(data)
            return _success(job, status_code=202)

        # Recipe-sweep mock: JobStore.start() handles mock results internally
        if data.get("mode") == "mock" and data.get("job_type") == "recipe-sweep":
            job = jobs.start(data)
            return _success(job)

        executor = _job_executor(data, session)
        job = jobs.start(data, executor=executor)
        if data.get("mode") == "mock" and data.get("job_type") == "metasurface-sweep":
            job = _write_mock_metasurface_artifacts(jobs, job)
        return _success(job)

    @app.get("/jobs/<job_id>")
    def jobs_get(job_id):
        return _success(jobs.get(job_id))

    @app.get("/jobs/<job_id>/tasks")
    def jobs_tasks(job_id):
        return _success(jobs.list_tasks(job_id))

    @app.post("/jobs/<job_id>/resume")
    def jobs_resume(job_id):
        data = _json_body()
        executor = _job_executor(data, session)
        return _success(jobs.resume(job_id, executor=executor))

    # ------------------------------------------------------------------
    # Recipe build (Task 6)
    # ------------------------------------------------------------------

    @app.post("/recipes/build")
    def recipes_build():
        reject_during_sweep()
        data = _json_body()
        recipe = _required(data, "recipe")
        compile_fingerprint = _required(data, "compile_fingerprint")
        output_fsp = _required(data, "output_fsp")
        approved = data.get("approved", False)

        # 1. Must be approved
        if not approved:
            raise RpcError(
                "approval_required",
                "Recipe build requires explicit approval.",
                403,
            )

        # 2. Recompile and compare fingerprint
        compiled = compile_recipe(recipe)
        if not compiled["ok"]:
            raise RpcError(
                "recipe_compile_error",
                "Recipe failed to compile on server side.",
                400,
                {"errors": compiled.get("errors", [])},
            )

        if compiled["compile_fingerprint"] != compile_fingerprint:
            raise RpcError(
                "compile_fingerprint_mismatch",
                "The compile fingerprint does not match. The recipe may have been "
                "tampered with or the caller used a different compiler version.",
                409,
                {
                    "expected": compile_fingerprint,
                    "actual": compiled["compile_fingerprint"],
                },
            )

        # 3. Create clean project
        adapter.project_new(
            name=f"recipe_build_{output_fsp}",
            discard_unsaved=True,
        )

        # 4. Execute build-only script
        log_lines: list = []
        script = compiled["script"]
        eval_result = session.eval(script)
        log_lines.append(f"Script executed ({len(script)} chars).")

        # 5. Save to output path
        save_result = session.save(str(output_fsp))
        log_lines.append(f"Project saved to {save_result.get('saved_to', output_fsp)}.")

        # 6. Gather object list
        object_list = adapter.object_list()
        log_lines.append(
            f"Object list: {len(object_list.get('objects', []))} objects."
        )

        return _success(
            {
                "model_path": str(output_fsp),
                "objects": object_list.get("objects", []),
                "log": log_lines,
                "compile_fingerprint": compiled["compile_fingerprint"],
            }
        )

    return app


app = create_app()


def main():
    parser = argparse.ArgumentParser(description="FDTD RPC Server")
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Server port (default: 5000)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    args = parser.parse_args()

    logger.info("Starting FDTD RPC Server on %s:%s", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
