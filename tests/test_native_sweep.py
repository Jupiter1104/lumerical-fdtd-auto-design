import json
from pathlib import Path

from src.job_store import JobStore
from src.native_sweep import NativeSweepRunner


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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

    def runanalysis(self, name):
        self.calls.append(("runanalysis", name))

    def haveresult(self, name, result):
        self.calls.append(("haveresult", name, result))
        return True

    def getresult(self, name, result):
        self.calls.append(("getresult", name, result))
        if result == "T":
            return {"T": [0.75]}
        return {"S21_Gn": [1j]}


class FakeSession:
    def __init__(self, fdtd):
        self.fdtd = fdtd
        self.is_connected = True

    def start(self, hide=True):
        self.is_connected = True
        return {"hide": hide}


class FailingSecondResultFdtd(FakeFdtd):
    def __init__(self):
        super().__init__()
        self.transmission_reads = 0

    def getresult(self, name, result):
        if result == "T":
            self.transmission_reads += 1
            if self.transmission_reads == 2:
                raise RuntimeError("sample extraction failed")
        return super().getresult(name, result)


class MissingSecondSResultFdtd(FakeFdtd):
    def __init__(self):
        super().__init__()
        self.s_result_checks = 0

    def haveresult(self, name, result):
        self.calls.append(("haveresult", name, result))
        if result == "S":
            self.s_result_checks += 1
            return self.s_result_checks != 2
        return True


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


def test_native_runner_extracts_each_sample_result(tmp_path):
    store, job = create_real_job(tmp_path, phases=[1, 2, 3])
    fdtd = FakeFdtd()

    result = NativeSweepRunner(FakeSession(fdtd), store).run(job["job_id"])

    assert result["state"] == "succeeded"
    tasks = store.list_tasks(job["job_id"])["tasks"]
    assert [task["state"] for task in tasks] == ["succeeded", "succeeded"]
    assert [task["phase"] for task in tasks] == ["complete", "complete"]
    sample = json.loads(
        Path(tasks[0]["outputs"]["result_file"]).read_text(encoding="utf-8")
    )
    assert sample["transmission"] == 0.75
    assert sample["phase_rad"] == 1.5707963267948966


def test_native_runner_keeps_successful_result_when_another_sample_fails(
    tmp_path,
):
    store, job = create_real_job(tmp_path, phases=[1, 2, 3])

    result = NativeSweepRunner(
        FakeSession(FailingSecondResultFdtd()),
        store,
    ).run(job["job_id"])

    assert result["state"] == "partial"
    first, second = store.list_tasks(job["job_id"])["tasks"]
    assert first["state"] == "succeeded"
    assert Path(first["outputs"]["result_file"]).is_file()
    assert second["state"] == "failed"
    assert second["phase"] == "extracting"
    assert second["error"]["message"] == "sample extraction failed"


def test_native_runner_extracts_from_recorded_model_file(tmp_path):
    store, job = create_real_job(tmp_path, phases=[3])
    custom_model = tmp_path / "custom_models" / "task_0001.fsp"
    custom_model.parent.mkdir()
    custom_model.write_bytes(b"fsp")
    store.update_task(
        job["job_id"],
        "task_0001",
        outputs={"model_file": str(custom_model)},
    )
    fdtd = FakeFdtd()

    NativeSweepRunner(FakeSession(fdtd), store).run(job["job_id"])

    assert ("load", str(custom_model)) in fdtd.calls


def test_native_runner_marks_sample_failed_when_s_result_is_missing(
    tmp_path,
):
    store, job = create_real_job(tmp_path, phases=[1, 2, 3])

    result = NativeSweepRunner(
        FakeSession(MissingSecondSResultFdtd()),
        store,
    ).run(job["job_id"])

    assert result["state"] == "partial"
    first, second = store.list_tasks(job["job_id"])["tasks"]
    assert first["state"] == "succeeded"
    assert second["state"] == "failed"
    assert second["error"]["message"] == "Missing S result."


def test_native_runner_phase_four_writes_evidence_artifacts(tmp_path):
    store, job = create_real_job(tmp_path, phases=[1, 2, 3, 4])

    result = NativeSweepRunner(FakeSession(FakeFdtd()), store).run(job["job_id"])

    job_dir = Path(job["job_dir"])
    assert result["state"] == "succeeded"
    assert (job_dir / "results" / "sweep_results.csv").is_file()
    assert (job_dir / "results" / "sweep_summary.json").is_file()
    assert (job_dir / "quality_report.json").is_file()
    assert (job_dir / "evidence" / "index.json").is_file()
    assert (job_dir / "evidence" / "transmission_heatmap.svg").is_file()
    assert (job_dir / "evidence" / "phase_heatmap.svg").is_file()
    summary = read_json(job_dir / "summary.json")
    assert summary["quality_report"]["conclusion"] == "pass"
    assert summary["evidence"]["download_policy"]["default_payload"] == (
        "evidence-only"
    )
