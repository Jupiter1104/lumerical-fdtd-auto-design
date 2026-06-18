import json
from pathlib import Path

from src.job_store import JobStore
from src.native_sweep import NativeSweepRunner


class FakeFdtd:
    def __init__(self):
        self.calls = []

    def clearjobs(self):
        self.calls.append(("clearjobs",))

    def redrawoff(self):
        self.calls.append(("redrawoff",))

    def redrawon(self):
        self.calls.append(("redrawon",))

    def setresource(self, *args):
        self.calls.append(("setresource",) + args)

    def load(self, path):
        self.calls.append(("load", path))

    def switchtolayout(self):
        self.calls.append(("switchtolayout",))

    def setnamed(self, name, prop, value):
        self.calls.append(("setnamed", name, prop, value))

    def save(self, path):
        self.calls.append(("save", path))
        Path(path).write_bytes(b"fsp")

    def addjob(self, path):
        self.calls.append(("addjob", path))

    def runjobs(self):
        self.calls.append(("runjobs",))


class FakeSession:
    def __init__(self, fdtd):
        self.fdtd = fdtd
        self.is_connected = True

    def start(self, hide=True):
        self.is_connected = True
        return {"hide": hide}


def create_real_job(tmp_path, phases=None):
    template = tmp_path / "templates" / "base_model.fsp"
    template.parent.mkdir(parents=True)
    template.write_bytes(b"template")
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job = store.enqueue(
        {
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {
                "template": str(template),
                "phases": phases or [1, 2],
                "config": {
                    "RATIO_LIST": [0.2, 0.8],
                    "PERIOD_LIST": [390e-9],
                },
            },
            "approval": {"approved": True, "approved_for": "real_run"},
        }
    )
    return store, job


def test_native_runner_generates_models_then_runs_queue_once(tmp_path):
    store, job = create_real_job(tmp_path)
    fdtd = FakeFdtd()
    runner = NativeSweepRunner(FakeSession(fdtd), store)

    runner.run(job["job_id"])

    names = [call[0] for call in fdtd.calls]
    assert names.count("clearjobs") == 1
    assert names.count("load") == 2
    assert names.count("save") == 2
    assert names.count("addjob") == 2
    assert names.count("runjobs") == 1
    first_load = names.index("load")
    first_save = names.index("save")
    assert names.index("clearjobs") < first_load < first_save < names.index("runjobs")
    assert all(
        task["phase"] == "solving"
        for task in store.list_tasks(job["job_id"])["tasks"]
    )


def test_native_runner_sets_express_mode_after_every_template_load(tmp_path):
    store, job = create_real_job(tmp_path)
    fdtd = FakeFdtd()

    NativeSweepRunner(FakeSession(fdtd), store).run(job["job_id"])

    calls = fdtd.calls
    load_indexes = [
        index for index, call in enumerate(calls) if call[0] == "load"
    ]
    for load_index in load_indexes:
        next_save = next(
            index
            for index in range(load_index + 1, len(calls))
            if calls[index][0] == "save"
        )
        assert (
            "setnamed",
            "FDTD",
            "express mode",
            1,
        ) in calls[load_index + 1 : next_save]


def test_native_runner_reads_normalized_sweep_request(tmp_path):
    store, job = create_real_job(tmp_path)
    request_path = Path(job["job_dir"]) / "inputs" / "request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))

    assert request["sweep"]["template"].endswith("base_model.fsp")
    assert request["sweep"]["config"]["RATIO_LIST"] == [0.2, 0.8]
