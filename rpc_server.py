"""
FDTD RPC Server — Windows Flask 服务。

运行在 Windows 端，持有持久 PyLumerical 会话，通过 HTTP 暴露 lumapi 操作接口。
Mac 端的 MCP Server 通过此 RPC 服务间接控制 FDTD GUI。

启动方式:
    python rpc_server.py --port 5000

依赖:
    pip install ansys-lumerical-core flask
"""

import argparse
import logging
import os
import sys
import threading
import time
import traceback
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fdtd-rpc")


# ---------------------------------------------------------------------------
# PyLumerical import (auto-discovery via LUMERICAL_HOME / registry / fs)
# ---------------------------------------------------------------------------
def _import_lumapi():
    """Try to import PyLumerical, falling back to raw lumapi."""
    try:
        import ansys.lumerical.core as lumapi
        logger.info("Using ansys-lumerical-core (official PyLumerical)")
        return lumapi
    except ImportError:
        logger.warning(
            "ansys-lumerical-core not found, trying raw lumapi import. "
            "Install with: pip install ansys-lumerical-core"
        )
        try:
            import lumapi
            logger.info("Using raw lumapi (fallback)")
            return lumapi
        except ImportError:
            logger.error(
                "Cannot import lumapi. Install PyLumerical: "
                "pip install ansys-lumerical-core"
            )
            raise


lumapi = _import_lumapi()

# ---------------------------------------------------------------------------
# Session Manager (Singleton — like COMSOL MCP)
# ---------------------------------------------------------------------------


class SolverStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionManager:
    """Singleton manager for the FDTD lumapi session."""

    _instance: Optional["SessionManager"] = None
    _fdtd = None
    _model_file: Optional[str] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._fdtd is not None

    @property
    def fdtd(self):
        """Return the raw FDTD session object."""
        return self._fdtd

    def start(self, hide: bool = False) -> dict:
        """Start an FDTD session. Only one session at a time (license limit)."""
        with self._lock:
            if self._fdtd is not None:
                try:
                    self._fdtd.close()
                except Exception:
                    pass
                self._fdtd = None
                self._model_file = None

            try:
                self._fdtd = lumapi.FDTD(hide=hide)
                version = self._fdtd.getversion()
                logger.info(f"FDTD session started (version={version}, hide={hide})")
                return {
                    "success": True,
                    "version": version,
                    "hide": hide,
                    "message": f"FDTD {version} session started.",
                }
            except Exception as e:
                self._fdtd = None
                logger.error(f"Failed to start FDTD: {e}")
                return {"success": False, "error": str(e)}

    def stop(self) -> dict:
        """Close the FDTD session."""
        with self._lock:
            if self._fdtd is None:
                return {"success": True, "message": "No active session."}
            try:
                self._fdtd.close()
            except Exception as e:
                logger.warning(f"Error closing FDTD: {e}")
            finally:
                self._fdtd = None
                self._model_file = None
            logger.info("FDTD session closed.")
            return {"success": True, "message": "FDTD session closed."}

    def status(self) -> dict:
        """Get current session status."""
        if self._fdtd is None:
            return {"connected": False, "message": "No active FDTD session."}
        try:
            version = self._fdtd.getversion()
        except Exception:
            version = "unknown"
        return {
            "connected": True,
            "version": version,
            "model_file": self._model_file,
        }

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def save(self, file_path: Optional[str] = None) -> dict:
        """Save current FDTD project. Overwrites without prompt."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        try:
            if file_path:
                save_path = str(Path(file_path).absolute())
            elif self._model_file:
                save_path = self._model_file
            else:
                save_path = str(Path.cwd() / "fdtd_project.fsp")

            # Ensure directory exists
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            self._fdtd.save(save_path)
            self._model_file = save_path
            logger.info(f"Project saved to {save_path}")
            return {"success": True, "saved_to": save_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load(self, file_path: str) -> dict:
        """Load an .fsp project file."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        try:
            self._fdtd.load(str(path.absolute()))
            self._model_file = str(path.absolute())
            logger.info(f"Project loaded from {path}")
            return {"success": True, "loaded": str(path.absolute())}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def eval(self, cmd: str) -> dict:
        """Execute an arbitrary lumapi command string."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        try:
            result = self._fdtd.eval(cmd)
            return {"success": True, "result": str(result)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def getv(self, name: str) -> dict:
        """Get the value of a named object property."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        try:
            value = self._fdtd.getv(name)
            return {"success": True, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def setv(self, name: str, value) -> dict:
        """Set the value of a named object property."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        try:
            self._fdtd.setv(name, value)
            return {"success": True, "message": f"Set {name} = {value}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Run the FDTD simulation (synchronous)."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        try:
            self._fdtd.run()
            logger.info("Simulation completed.")
            return {"success": True, "message": "Simulation completed."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def getresult(self, monitor: str, attribute: str) -> dict:
        """Get a result from a monitor."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        try:
            data = self._fdtd.getresult(monitor, attribute)
            # Convert numpy arrays to lists for JSON serialization
            import numpy as np

            if isinstance(data, np.ndarray):
                data = data.tolist()
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def getelectric(self, monitor: str) -> dict:
        """Get electric field from a monitor."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        try:
            E = self._fdtd.getelectric(monitor)
            import numpy as np

            if isinstance(E, np.ndarray):
                E = E.tolist()
            return {"success": True, "data": E}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Named object convenience methods
    # ------------------------------------------------------------------

    def addfdtd(self, **kwargs) -> dict:
        """Add an FDTD simulation region."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        try:
            self._fdtd.addfdtd(**kwargs)
            return {"success": True, "message": "FDTD region added."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def addrect(self, **kwargs) -> dict:
        """Add a rectangle structure."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        try:
            self._fdtd.addrect(**kwargs)
            return {"success": True, "message": "Rectangle added."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def addcircle(self, **kwargs) -> dict:
        """Add a circle structure."""
        if self._fdtd is None:
            return {"success": False, "error": "No active FDTD session."}
        try:
            self._fdtd.addcircle(**kwargs)
            return {"success": True, "message": "Circle added."}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
session = SessionManager()


# ---------------------------------------------------------------------------
# Flask Application
# ---------------------------------------------------------------------------
app = Flask(__name__)


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "server": "fdtd-rpc-server"})


@app.route("/status", methods=["GET"])
def status():
    return jsonify(session.status())


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
@app.route("/session/start", methods=["POST"])
def session_start():
    data = request.get_json(silent=True) or {}
    hide = data.get("hide", False)
    return jsonify(session.start(hide=hide))


@app.route("/session/stop", methods=["POST"])
def session_stop():
    return jsonify(session.stop())


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------
@app.route("/file/save", methods=["POST"])
def file_save():
    data = request.get_json(silent=True) or {}
    file_path = data.get("file_path")
    return jsonify(session.save(file_path))


@app.route("/file/load", methods=["POST"])
def file_load():
    data = request.get_json(silent=True) or {}
    file_path = data.get("file_path")
    if not file_path:
        return jsonify({"success": False, "error": "file_path is required."})
    return jsonify(session.load(file_path))


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------
@app.route("/eval", methods=["POST"])
def eval_cmd():
    """
    Execute an arbitrary lumapi eval string.

    Body: {"cmd": "fdtd.getversion()"}
    """
    data = request.get_json(silent=True) or {}
    cmd = data.get("cmd")
    if not cmd:
        return jsonify({"success": False, "error": "cmd is required."})
    return jsonify(session.eval(cmd))


@app.route("/getv", methods=["POST"])
def getv():
    """Get named object property. Body: {"name": "::model"}"""
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        return jsonify({"success": False, "error": "name is required."})
    return jsonify(session.getv(name))


@app.route("/setv", methods=["POST"])
def setv():
    """Set named object property. Body: {"name": "...", "value": ...}"""
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    value = data.get("value")
    if not name:
        return jsonify({"success": False, "error": "name is required."})
    return jsonify(session.setv(name, value))


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
@app.route("/sim/run", methods=["POST"])
def sim_run():
    return jsonify(session.run())


@app.route("/sim/getresult", methods=["POST"])
def sim_getresult():
    data = request.get_json(silent=True) or {}
    monitor = data.get("monitor")
    attribute = data.get("attribute")
    if not monitor or not attribute:
        return jsonify(
            {"success": False, "error": "monitor and attribute are required."}
        )
    return jsonify(session.getresult(monitor, attribute))


@app.route("/sim/getelectric", methods=["POST"])
def sim_getelectric():
    data = request.get_json(silent=True) or {}
    monitor = data.get("monitor", "monitor")
    return jsonify(session.getelectric(monitor))


# ---------------------------------------------------------------------------
# Geometry convenience
# ---------------------------------------------------------------------------
@app.route("/geom/addfdtd", methods=["POST"])
def geom_addfdtd():
    kwargs = request.get_json(silent=True) or {}
    return jsonify(session.addfdtd(**kwargs))


@app.route("/geom/addrect", methods=["POST"])
def geom_addrect():
    kwargs = request.get_json(silent=True) or {}
    return jsonify(session.addrect(**kwargs))


@app.route("/geom/addcircle", methods=["POST"])
def geom_addcircle():
    kwargs = request.get_json(silent=True) or {}
    return jsonify(session.addcircle(**kwargs))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FDTD RPC Server")
    parser.add_argument("--port", type=int, default=5000, help="Server port (default: 5000)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    args = parser.parse_args()

    logger.info(f"Starting FDTD RPC Server on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
