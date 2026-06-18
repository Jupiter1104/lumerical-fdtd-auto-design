"""FDTD RPC Server — Windows Flask service.

The process owns one persistent lumapi session. Mac-side clients call the v1
HTTP contract defined in docs/superpowers/specs/.

Run on Windows:
    python rpc_server.py --port 5004
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

from src.job_store import JobError, JobStore

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
            return {
                "version": version,
                "hide": hide,
                "message": f"FDTD {version} session started.",
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
            }
        try:
            version = self._get_version(self._fdtd)
        except Exception:
            version = "unknown"
        return {
            "connected": True,
            "version": version,
            "model_file": self._model_file,
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


def create_app(
    session_manager: Optional[SessionManager] = None,
    job_store: Optional[JobStore] = None,
) -> Flask:
    """Create a testable Flask app with an injectable session backend."""
    app = Flask(__name__)
    session = session_manager or SessionManager()
    jobs = job_store or JobStore()

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
        data = _json_body()
        return _success(session.start(hide=bool(data.get("hide", False))))

    @app.post("/session/close")
    @app.post("/session/stop")
    def session_close():
        return _success(session.close())

    @app.post("/model/save")
    @app.post("/file/save")
    def model_save():
        data = _json_body()
        return _success(session.save(data.get("file_path")))

    @app.post("/model/load")
    @app.post("/file/load")
    def model_load():
        data = _json_body()
        return _success(session.load(_required(data, "file_path")))

    @app.post("/debug/eval")
    @app.post("/eval")
    def debug_eval():
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
        data = _json_body()
        name = _required(data, "name")
        return _success(session.setv(name, data.get("value")))

    @app.post("/simulation/run")
    @app.post("/sim/run")
    def simulation_run():
        return _success(session.run())

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
        return _success(session.addfdtd(**_json_body()))

    @app.post("/geometry/rectangle")
    @app.post("/geom/addrect")
    def geometry_rectangle():
        return _success(session.addrect(**_json_body()))

    @app.post("/geometry/circle")
    @app.post("/geom/addcircle")
    def geometry_circle():
        return _success(session.addcircle(**_json_body()))

    @app.post("/jobs/plan")
    def jobs_plan():
        return _success(jobs.plan(_json_body()))

    @app.post("/jobs/start")
    def jobs_start():
        data = _json_body()
        executor = (
            _geometry_smoke_executor(session)
            if data.get("mode") == "real"
            else None
        )
        return _success(jobs.start(data, executor=executor))

    @app.get("/jobs/<job_id>")
    def jobs_get(job_id):
        return _success(jobs.get(job_id))

    @app.get("/jobs/<job_id>/tasks")
    def jobs_tasks(job_id):
        return _success(jobs.list_tasks(job_id))

    @app.post("/jobs/<job_id>/resume")
    def jobs_resume(job_id):
        data = _json_body()
        executor = (
            _geometry_smoke_executor(session)
            if data.get("mode") == "real"
            else None
        )
        return _success(jobs.resume(job_id, executor=executor))

    return app


app = create_app()


def main():
    parser = argparse.ArgumentParser(description="FDTD RPC Server")
    parser.add_argument(
        "--port",
        type=int,
        default=5003,
        help="Server port (default: 5003)",
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
