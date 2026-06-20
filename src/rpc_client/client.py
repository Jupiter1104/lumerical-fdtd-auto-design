"""Mac-side HTTP client for the Windows FDTD RPC API v1."""

from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import quote

import requests


def _client_error(error_type: str, message: str, details: Optional[dict] = None):
    return {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
            "details": details or {},
        },
    }


class RpcClient:
    """Thin client for the single RPC API v1 contract."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        request_timeout = self.timeout if timeout is None else timeout
        try:
            response = self._session.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                json=body if method != "GET" else None,
                timeout=request_timeout,
            )
        except requests.ConnectionError:
            return _client_error(
                "connection_error",
                f"Cannot connect to {self.base_url}.",
                {"path": path},
            )
        except requests.Timeout:
            return _client_error(
                "timeout",
                f"Request to {path} timed out after {request_timeout}s.",
                {
                    "path": path,
                    "timeout_seconds": request_timeout,
                    "remote_state": "unknown",
                },
            )
        except requests.RequestException as exc:
            return _client_error(
                "request_error",
                str(exc),
                {"path": path},
            )

        try:
            payload = response.json()
        except ValueError:
            return _client_error(
                "invalid_response",
                f"RPC Server returned non-JSON content for {path}.",
                {
                    "path": path,
                    "status_code": response.status_code,
                },
            )

        if not isinstance(payload, dict) or "ok" not in payload:
            return _client_error(
                "invalid_response",
                f"RPC Server returned an invalid v1 envelope for {path}.",
                {
                    "path": path,
                    "status_code": response.status_code,
                },
            )

        if response.status_code >= 400 and payload.get("ok") is not False:
            return _client_error(
                "http_error",
                f"RPC Server returned HTTP {response.status_code}.",
                {
                    "path": path,
                    "status_code": response.status_code,
                },
            )
        return payload

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        return self._request("GET", path, params=params)

    def _post(self, path: str, body: Optional[dict] = None) -> dict:
        return self._request("POST", path, body=body or {})

    # Health and session

    def health(self) -> dict:
        return self._get("/health")

    def status(self) -> dict:
        return self._get("/status")

    def session_start(self, hide: bool = False) -> dict:
        return self._post("/session/start", {"hide": hide})

    def session_close(self) -> dict:
        return self._post("/session/close")

    def session_pause(self, seconds: float = 300.0) -> dict:
        """Compatibility with the deployed sweep server extension."""
        return self._post("/session/pause", {"seconds": seconds})

    # Model and debug

    def file_save(self, file_path: Optional[str] = None) -> dict:
        body = {}
        if file_path is not None:
            body["file_path"] = file_path
        return self._post("/model/save", body)

    def file_load(self, file_path: str) -> dict:
        return self._post("/model/load", {"file_path": file_path})

    def eval(self, cmd: str) -> dict:
        return self._post("/debug/eval", {"cmd": cmd})

    def getv(self, name: str) -> dict:
        return self._post("/debug/getv", {"name": name})

    def setv(self, name: str, value: Any) -> dict:
        return self._post("/debug/setv", {"name": name, "value": value})

    # Simulation

    def run(self) -> dict:
        return self._post("/simulation/run")

    def getresult(self, monitor: str, attribute: str) -> dict:
        return self._post(
            "/simulation/result",
            {"monitor": monitor, "attribute": attribute},
        )

    def getelectric(self, monitor: str = "monitor") -> dict:
        return self._post("/simulation/electric", {"monitor": monitor})

    # Geometry

    @staticmethod
    def _properties(properties: Optional[dict], kwargs: dict) -> dict:
        body = dict(properties or {})
        body.update(kwargs)
        return body

    def addfdtd(self, properties: Optional[dict] = None, **kwargs) -> dict:
        return self._post(
            "/geometry/fdtd-region",
            self._properties(properties, kwargs),
        )

    def addrect(self, properties: Optional[dict] = None, **kwargs) -> dict:
        return self._post(
            "/geometry/rectangle",
            self._properties(properties, kwargs),
        )

    def addcircle(self, properties: Optional[dict] = None, **kwargs) -> dict:
        return self._post(
            "/geometry/circle",
            self._properties(properties, kwargs),
        )

    # Persistent jobs

    def jobs_plan(self, request: dict) -> dict:
        return self._post("/jobs/plan", request)

    def jobs_start(self, request: dict) -> dict:
        return self._post("/jobs/start", request)

    def jobs_get(self, job_id: str) -> dict:
        return self._get(f"/jobs/{quote(job_id, safe='')}")

    def jobs_tasks(self, job_id: str) -> dict:
        return self._get(f"/jobs/{quote(job_id, safe='')}/tasks")

    def jobs_resume(self, job_id: str, request: Optional[dict] = None) -> dict:
        return self._post(
            f"/jobs/{quote(job_id, safe='')}/resume",
            request or {},
        )

    # Project management (Task 1 stubs — routed to _get/_post)

    def project_new(self, name: str = "untitled", discard_unsaved: bool = False) -> dict:
        return self._post("/project/new", {"name": name, "discard_unsaved": discard_unsaved})

    def project_load(self, file_path: str) -> dict:
        return self._post("/project/load", {"file_path": file_path})

    def project_save(self, file_path: Optional[str] = None) -> dict:
        body = {}
        if file_path is not None:
            body["file_path"] = file_path
        return self._post("/project/save", body)

    def project_status(self) -> dict:
        return self._get("/project/status")

    def switch_to_layout(self) -> dict:
        return self._post("/model/layout")

    # Object management (Task 1 stubs)

    def object_create(
        self, object_type: str, name: str, properties: dict, dry_run: bool = False
    ) -> dict:
        return self._post(
            "/objects",
            {
                "object_type": object_type,
                "name": name,
                "properties": properties,
                "dry_run": dry_run,
            },
        )

    def object_list(self) -> dict:
        return self._get("/objects")

    def object_get(self, name: str, scope: Optional[str] = None) -> dict:
        return self._get(f"/objects/{quote(name, safe='')}")

    def object_update(self, name: str, body: dict) -> dict:
        return self._post(f"/objects/{quote(name, safe='')}/update", body)

    def object_copy(self, name: str, new_name: str) -> dict:
        return self._post(
            f"/objects/{quote(name, safe='')}/copy",
            {"new_name": new_name},
        )

    def object_rename(self, name: str, new_name: str) -> dict:
        return self._post(
            f"/objects/{quote(name, safe='')}/rename",
            {"new_name": new_name},
        )

    def object_delete(self, name: str) -> dict:
        return self._post(f"/objects/{quote(name, safe='')}/delete")

    def group_update(self, body: dict) -> dict:
        return self._post("/objects/group-update", body)

    # Material management (Task 1 stubs)

    def material_create(self, body: dict) -> dict:
        return self._post("/materials/create", body)

    def material_list(self) -> dict:
        return self._get("/materials")

    def material_get(self, name: str) -> dict:
        return self._get(f"/materials/{quote(name, safe='')}")

    def material_update(self, name: str, body: dict) -> dict:
        return self._post(f"/materials/{quote(name, safe='')}/update", body)

    def material_assign(self, body: dict) -> dict:
        return self._post("/materials/assign", body)

    def material_fit_diagnose(self, body: dict) -> dict:
        return self._post("/materials/fit-diagnose", body)

    # Solver & mesh management (Task 1 stubs)

    def solver_get(self) -> dict:
        return self._get("/solver")

    def solver_update(self, body: dict) -> dict:
        return self._post("/solver/update", body)

    def mesh_diagnose(self) -> dict:
        return self._get("/solver/mesh-diagnose")

    def resource_estimate(self) -> dict:
        return self._get("/solver/resource-estimate")

    # Source management (Task 1 stubs)

    def source_create(
        self, source_type: str, name: str, properties: dict, dry_run: bool = False
    ) -> dict:
        return self._post(
            "/sources",
            {
                "source_type": source_type,
                "name": name,
                "properties": properties,
                "dry_run": dry_run,
            },
        )

    def source_get(self, name: str) -> dict:
        return self._get(f"/sources/{quote(name, safe='')}")

    def source_update(self, name: str, body: dict) -> dict:
        return self._post(f"/sources/{quote(name, safe='')}/update", body)

    # Monitor management (Task 1 stubs)

    def monitor_create(
        self, monitor_type: str, name: str, properties: dict, dry_run: bool = False
    ) -> dict:
        return self._post(
            "/monitors",
            {
                "monitor_type": monitor_type,
                "name": name,
                "properties": properties,
                "dry_run": dry_run,
            },
        )

    def monitor_get(self, name: str) -> dict:
        return self._get(f"/monitors/{quote(name, safe='')}")

    def monitor_update(self, name: str, body: dict) -> dict:
        return self._post(f"/monitors/{quote(name, safe='')}/update", body)

    # Analysis group management (Task 1 stubs)

    def analysis_group_create(
        self, name: str, properties: dict, dry_run: bool = False
    ) -> dict:
        return self._post(
            "/analysis-groups",
            {
                "name": name,
                "properties": properties,
                "dry_run": dry_run,
            },
        )

    def analysis_group_get(self, name: str) -> dict:
        return self._get(f"/analysis-groups/{quote(name, safe='')}")

    def analysis_group_update(self, name: str, body: dict) -> dict:
        return self._post(f"/analysis-groups/{quote(name, safe='')}/update", body)

    # Result inspection (Task 1 stubs)

    def result_list(self) -> dict:
        return self._get("/results")

    def result_describe(self, name: str) -> dict:
        return self._get(f"/results/{quote(name, safe='')}/describe")

    def result_read(self, name: str, attribute: str) -> dict:
        return self._get(
            f"/results/{quote(name, safe='')}/{quote(attribute, safe='')}"
        )

    # Recipe build (Task 6)

    def recipe_build(
        self,
        recipe: dict,
        compile_fingerprint: str,
        output_fsp: str,
        approved: bool = False,
    ) -> dict:
        return self._post(
            "/recipes/build",
            {
                "recipe": recipe,
                "compile_fingerprint": compile_fingerprint,
                "output_fsp": output_fsp,
                "approved": approved,
            },
        )

    # Deployed sweep server extensions

    def sweep_config_get(self) -> dict:
        return self._get("/sweep/config")

    def sweep_config_set(self, config: dict) -> dict:
        return self._post("/sweep/config", config)

    def sweep_run(self, phases: Optional[List[int]] = None) -> dict:
        body = {}
        if phases is not None:
            body["phases"] = phases
        return self._post("/sweep/run", body)

    def sweep_status(self, task_id: Optional[str] = None) -> dict:
        params = {}
        if task_id:
            params["task_id"] = task_id
        return self._get("/sweep/status", params=params)

    def results_list(self) -> dict:
        return self._get("/results")

    def results_download(
        self,
        filepath: str,
        save_to: Optional[str] = None,
    ) -> dict:
        remote_path = quote(filepath.lstrip("/"), safe="/")
        path = f"/results/{remote_path}"
        try:
            response = self._session.get(
                f"{self.base_url}{path}",
                timeout=max(self.timeout, 60.0),
                stream=True,
            )
        except requests.ConnectionError:
            return _client_error(
                "connection_error",
                f"Cannot connect to {self.base_url}.",
                {"path": path},
            )
        except requests.Timeout:
            return _client_error(
                "timeout",
                f"Download from {path} timed out.",
                {"path": path, "remote_state": "unknown"},
            )
        except requests.RequestException as exc:
            return _client_error("request_error", str(exc), {"path": path})

        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict) and payload.get("ok") is False:
                return payload
            return _client_error(
                "http_error",
                f"RPC Server returned HTTP {response.status_code}.",
                {"path": path, "status_code": response.status_code},
            )

        local_path = Path(save_to or Path(filepath).name)
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with local_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        output.write(chunk)
        except OSError as exc:
            return _client_error(
                "local_io_error",
                str(exc),
                {"save_to": str(local_path)},
            )

        return {
            "ok": True,
            "saved_to": str(local_path.resolve()),
        }
