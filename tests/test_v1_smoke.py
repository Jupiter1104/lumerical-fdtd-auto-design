from pathlib import Path

import pytest

from scripts.v1_smoke_test import SmokeFailure, run_smoke


class FakeClient:
    def __init__(self, saved_path: Path, fail_at: str = ""):
        self.saved_path = saved_path
        self.fail_at = fail_at
        self.closed = False

    def _result(self, step: str, data=None):
        if self.fail_at == step:
            return {
                "ok": False,
                "error": {
                    "type": "test_error",
                    "message": step,
                    "details": {},
                },
            }
        return {"ok": True, **(data or {})}

    def health(self):
        return self._result(
            "health",
            {"api_version": "v1", "connected": not self.closed},
        )

    def session_start(self, hide=False):
        return self._result("start", {"version": "v242", "hide": hide})

    def status(self):
        return self._result("status", {"connected": True})

    def addfdtd(self, **kwargs):
        return self._result("addfdtd")

    def addrect(self, **kwargs):
        return self._result("addrect")

    def file_save(self, file_path):
        self.saved_path.parent.mkdir(parents=True, exist_ok=True)
        self.saved_path.write_bytes(b"fsp")
        return self._result("save", {"saved_to": str(self.saved_path)})

    def session_close(self):
        self.closed = True
        return {"ok": True}


def test_smoke_happy_path(tmp_path):
    artifact = tmp_path / "saved.fsp"
    client = FakeClient(artifact)

    def legacy_stop():
        client.closed = True
        return {
            "ok": True,
            "meta": {
                "deprecated_route": "/session/stop",
                "use_instead": "/session/close",
            },
        }

    result = run_smoke(
        "http://127.0.0.1:5004",
        tmp_path,
        client=client,
        legacy_stop=legacy_stop,
    )

    assert result == artifact
    assert client.closed is True


def test_smoke_closes_session_after_failure(tmp_path):
    client = FakeClient(tmp_path / "saved.fsp", fail_at="addrect")

    with pytest.raises(SmokeFailure, match="add silicon rectangle failed"):
        run_smoke(
            "http://127.0.0.1:5004",
            tmp_path,
            client=client,
        )

    assert client.closed is True
