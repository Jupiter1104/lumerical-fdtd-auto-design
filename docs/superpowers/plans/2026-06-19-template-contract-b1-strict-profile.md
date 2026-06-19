# Template Contract Stage B1 Strict Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Stage B0.1 probe evidence into a git-tracked strict template profile and a runtime verified template contract, then stop before any real FDTD run.

**Architecture:** Keep Stage B1 offline and evidence-first: a tracked JSON profile declares the exact template assumptions, a pure Python contract builder compares that profile against the latest Windows probe JSON, and a runtime contract JSON records pass/fail checks plus fingerprints. The contract is only an authorization input for later real-run approval; it does not start jobs, mutate `.fsp`, or modify `/jobs/*` behavior in this stage.

**Tech Stack:** Python 3.10+ standard library, pytest, JSON/SHA-256, Windows batch wrapper, existing `src/template_contract.py` and Stage B0.1 `base_model.probe.json`.

## Global Constraints

- Do not run Lumerical solves: no `run`, `runjobs`, or `runanalysis`.
- Do not modify templates: no `.fsp` save, no `save`, no `set`, no `setnamed`, no `delete`, no `add*`, no `putv`, no `importdataset`.
- Do not create a real job, start a sweep, restart RPC, or modify Windows services.
- Do not modify `src/native_sweep.py`, `src/job_store.py`, `src/simulation_plan.py`, `src/plan_compilers/`, `src/tools/`, or `/jobs/*` behavior in this stage.
- `stage_b1_ready=true` means only "strict profile generation is allowed"; it is not real-run approval.
- `templates/metasurface/template-inspection-profile.json` is git-tracked.
- `templates/metasurface/base_model.contract.json` is runtime output and remains git-ignored.
- Boundary values must preserve the current B0.1 evidence: x = `Anti-Symmetric`, y = `Symmetric`, z = `PML`; record this as a physics review warning, not a B1 blocker.
- Contract validation must fail closed: missing evidence, SHA mismatch, wrong canonical path, nonzero express mode, unconfirmed CPU, missing source, missing monitor, missing boundary, or fingerprint tampering all produce an unverified contract.
- Windows must sync to current `origin/main` before generating the Stage B1 runtime contract.

---

## Current Evidence Baseline

- Latest reviewed Stage B0.1 code: `bff39a0`.
- Windows probe code commit in reported probe: `1087980`; before B1 Windows generation, sync to latest HEAD.
- Stage B0.1 probe status: `probe`, `errors=[]`, `stage_b1_ready=true`.
- Template SHA-256: `03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176`.
- Probe fingerprint: `a8e7e2ee4265f607012c54b85e29a01f55ede9220cb37b12033be6f471c017d6`.
- Canonical FDTD path: `::model::FDTD`.
- FDTD properties: `dimension=3D`, `express_mode=0.0`, `mesh_accuracy=6.0`, `simulation_time=5e-11`.
- Boundaries: `x min/max=Anti-Symmetric`, `y min/max=Symmetric`, `z min/max=PML`.
- Mesh override path: `::model::mesh`; `dx=dy=dz=5e-9`, x/y span `4.7e-7`, z span `7e-7`.
- Pillar: `::model::pillar`, type `Circle`, material `Si3N4 (Silicon Nitride) - Kischkat`, radius `1.88e-7`, z span `7e-7`.
- Substrate: `::model::substrate`, type `Rectangle`, material `SiO2 (Glass) - Palik`.
- Source: explicit object `::model::s_params::source`, type `PlaneSource`.
- Monitors: `::model::field`, `::model::s_params::T`, `::model::s_params::R`, `::model::s_params::T_index`, `::model::s_params::R_index`.
- Analysis group: `::model::s_params`, result assumptions include `T` and `S21_Gn`.
- Model parameters: `ratio=0.8`, `height=7e-7`, `period=4.7e-7`.
- Duplicate root/model objects: `unresolved_scope_alias`, not independent-object proof.

## File Structure

- Modify `src/template_contract.py`: profile schema validation, contract generation, contract validation, stable fingerprints.
- Create `templates/metasurface/template-inspection-profile.json`: strict tracked profile derived from B0.1 evidence.
- Create `scripts/generate_template_contract.py`: offline CLI that reads probe JSON + profile JSON and writes runtime contract JSON.
- Create `scripts/windows/generate_template_contract.bat`: Windows entry point for B1 contract generation.
- Modify `tests/test_template_contract.py`: focused unit and CLI tests for Stage B1.
- Modify `README.md`, `SOP.md`, `docs/WINDOWS_RUNBOOK.md`, `templates/metasurface/README.md`, `DEV_LOG.md`: document strict profile workflow, warning semantics, and stop gate.

---

### Task 1: Add strict profile schema validation

**Files:**
- Modify: `src/template_contract.py`
- Modify: `tests/test_template_contract.py`

**Interfaces:**
- Consumes: existing `stable_json(value: dict) -> str`.
- Produces:
  - `STRICT_PROFILE_VERSION: str`
  - `STRICT_PROFILE_MODE: str`
  - `EXPECTED_TEMPLATE_SHA256: str`
  - `validate_inspection_profile(profile: dict) -> dict`
  - `inspection_profile_fingerprint(profile: dict) -> str`

- [ ] **Step 1: Write failing tests for strict profile validation**

Append this to `tests/test_template_contract.py`:

```python
def valid_inspection_profile():
    return {
        "profile_version": "0.1",
        "mode": "contract",
        "template": {
            "logical_path": "templates/metasurface/base_model.fsp",
            "sha256": (
                "03ba1f3ea9db6e86caa9c5458bcf84b6"
                "adb92db6c0664e60f262e2f5edde0176"
            ),
        },
        "canonical_paths": {
            "fdtd": "::model::FDTD",
            "model": "::model",
            "pillar": "::model::pillar",
            "substrate": "::model::substrate",
            "mesh": "::model::mesh",
            "source": "::model::s_params::source",
            "analysis_group": "::model::s_params",
            "field_monitor": "::model::field",
            "transmission_monitor": "::model::s_params::T",
            "reflection_monitor": "::model::s_params::R",
            "transmission_index_monitor": "::model::s_params::T_index",
            "reflection_index_monitor": "::model::s_params::R_index",
        },
        "fdtd": {
            "dimension": "3D",
            "express_mode": 0,
            "resource_type": "CPU",
            "mesh_accuracy": 6,
            "simulation_time": 5e-11,
            "boundary_conditions": {
                "x_min_bc": "Anti-Symmetric",
                "x_max_bc": "Anti-Symmetric",
                "y_min_bc": "Symmetric",
                "y_max_bc": "Symmetric",
                "z_min_bc": "PML",
                "z_max_bc": "PML",
            },
        },
        "materials": {
            "pillar": "Si3N4 (Silicon Nitride) - Kischkat",
            "substrate": "SiO2 (Glass) - Palik",
        },
        "model_parameters": {
            "ratio": 0.8,
            "height": 7e-7,
            "period": 4.7e-7,
        },
        "results": {
            "transmission": "T",
            "s_parameter": "S21_Gn",
        },
        "warnings": [
            {
                "type": "physics_review_required",
                "message": (
                    "B0.1 evidence shows x boundaries are Anti-Symmetric "
                    "and y boundaries are Symmetric. Stage B1 preserves "
                    "template evidence and does not change physics settings."
                ),
            }
        ],
    }


def test_inspection_profile_accepts_valid_strict_profile():
    from src.template_contract import validate_inspection_profile

    profile = valid_inspection_profile()

    assert validate_inspection_profile(profile) == profile


def test_inspection_profile_fingerprint_excludes_its_own_field():
    from src.template_contract import inspection_profile_fingerprint

    profile = valid_inspection_profile()
    first = inspection_profile_fingerprint(profile)
    profile["profile_fingerprint"] = "old"

    assert inspection_profile_fingerprint(profile) == first


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda p: p.update({"mode": "inventory"}), "mode"),
        (lambda p: p["template"].update({"sha256": "bad"}), "Template"),
        (lambda p: p["canonical_paths"].update({"fdtd": "FDTD"}), "fdtd"),
        (lambda p: p["fdtd"].update({"express_mode": 1}), "express_mode"),
        (lambda p: p["fdtd"].update({"resource_type": "GPU"}), "resource_type"),
        (
            lambda p: p["fdtd"]["boundary_conditions"].pop("x_min_bc"),
            "boundary_conditions",
        ),
        (lambda p: p["warnings"].clear(), "physics_review_required"),
    ],
)
def test_inspection_profile_rejects_invalid_strict_profile(mutation, match):
    from src.template_contract import validate_inspection_profile

    profile = valid_inspection_profile()
    mutation(profile)

    with pytest.raises(ValueError, match=match):
        validate_inspection_profile(profile)
```

- [ ] **Step 2: Run the new tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_inspection_profile_accepts_valid_strict_profile \
  tests/test_template_contract.py::test_inspection_profile_fingerprint_excludes_its_own_field \
  tests/test_template_contract.py::test_inspection_profile_rejects_invalid_strict_profile \
  -q
```

Expected: FAIL because `validate_inspection_profile` and `inspection_profile_fingerprint` are not defined.

- [ ] **Step 3: Implement strict profile validation**

Add these constants and helpers to `src/template_contract.py`:

```python
STRICT_PROFILE_VERSION = "0.1"
STRICT_PROFILE_MODE = "contract"
EXPECTED_TEMPLATE_SHA256 = (
    "03ba1f3ea9db6e86caa9c5458bcf84b6"
    "adb92db6c0664e60f262e2f5edde0176"
)

STRICT_PROFILE_KEYS = {
    "profile_version",
    "mode",
    "template",
    "canonical_paths",
    "fdtd",
    "materials",
    "model_parameters",
    "results",
    "warnings",
}

REQUIRED_CANONICAL_PATHS = {
    "fdtd": "::model::FDTD",
    "model": "::model",
    "pillar": "::model::pillar",
    "substrate": "::model::substrate",
    "mesh": "::model::mesh",
    "source": "::model::s_params::source",
    "analysis_group": "::model::s_params",
    "field_monitor": "::model::field",
    "transmission_monitor": "::model::s_params::T",
    "reflection_monitor": "::model::s_params::R",
    "transmission_index_monitor": "::model::s_params::T_index",
    "reflection_index_monitor": "::model::s_params::R_index",
}

REQUIRED_BOUNDARY_CONDITIONS = {
    "x_min_bc": "Anti-Symmetric",
    "x_max_bc": "Anti-Symmetric",
    "y_min_bc": "Symmetric",
    "y_max_bc": "Symmetric",
    "z_min_bc": "PML",
    "z_max_bc": "PML",
}

REQUIRED_MODEL_PARAMETERS = {
    "ratio": 0.8,
    "height": 7e-7,
    "period": 4.7e-7,
}

REQUIRED_RESULTS = {
    "transmission": "T",
    "s_parameter": "S21_Gn",
}


def inspection_profile_fingerprint(profile: dict) -> str:
    payload = dict(profile)
    payload.pop("profile_fingerprint", None)
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def _require_mapping(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    return value


def _require_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} must be {expected!r}; got {actual!r}.")


def _require_physics_review_warning(profile: dict) -> None:
    warnings = profile.get("warnings", [])
    if not isinstance(warnings, list):
        raise ValueError("warnings must be a list.")
    if not any(
        isinstance(item, dict)
        and item.get("type") == "physics_review_required"
        for item in warnings
    ):
        raise ValueError("warnings must include physics_review_required.")


def validate_inspection_profile(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise ValueError("Inspection profile must be an object.")
    _require_exact_keys(profile, STRICT_PROFILE_KEYS, "Inspection profile")
    _require_equal(
        profile["profile_version"],
        STRICT_PROFILE_VERSION,
        "profile_version",
    )
    _require_equal(profile["mode"], STRICT_PROFILE_MODE, "mode")

    template = _require_mapping(profile["template"], "template")
    _require_exact_keys(template, {"logical_path", "sha256"}, "template")
    _require_equal(
        template["logical_path"],
        "templates/metasurface/base_model.fsp",
        "template.logical_path",
    )
    _require_equal(
        template["sha256"],
        EXPECTED_TEMPLATE_SHA256,
        "Template SHA-256",
    )

    canonical_paths = _require_mapping(
        profile["canonical_paths"],
        "canonical_paths",
    )
    _require_equal(canonical_paths, REQUIRED_CANONICAL_PATHS, "canonical_paths")

    fdtd = _require_mapping(profile["fdtd"], "fdtd")
    _require_exact_keys(
        fdtd,
        {
            "dimension",
            "express_mode",
            "resource_type",
            "mesh_accuracy",
            "simulation_time",
            "boundary_conditions",
        },
        "fdtd",
    )
    _require_equal(fdtd["dimension"], "3D", "dimension")
    _require_equal(fdtd["express_mode"], 0, "express_mode")
    _require_equal(fdtd["resource_type"], "CPU", "resource_type")
    _require_equal(fdtd["mesh_accuracy"], 6, "mesh_accuracy")
    _require_equal(fdtd["simulation_time"], 5e-11, "simulation_time")
    _require_equal(
        fdtd["boundary_conditions"],
        REQUIRED_BOUNDARY_CONDITIONS,
        "boundary_conditions",
    )

    materials = _require_mapping(profile["materials"], "materials")
    _require_equal(
        materials,
        {
            "pillar": "Si3N4 (Silicon Nitride) - Kischkat",
            "substrate": "SiO2 (Glass) - Palik",
        },
        "materials",
    )
    _require_equal(
        profile["model_parameters"],
        REQUIRED_MODEL_PARAMETERS,
        "model_parameters",
    )
    _require_equal(profile["results"], REQUIRED_RESULTS, "results")
    _require_physics_review_warning(profile)
    return profile
```

- [ ] **Step 4: Run tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_contract.py -q
```

Expected: all `tests/test_template_contract.py` tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/template_contract.py tests/test_template_contract.py
git commit -m "feat: validate strict template profile"
```

---

### Task 2: Add the tracked strict inspection profile

**Files:**
- Create: `templates/metasurface/template-inspection-profile.json`
- Modify: `tests/test_template_contract.py`

**Interfaces:**
- Consumes: `validate_inspection_profile(profile: dict) -> dict`.
- Produces: tracked strict profile for B1 contract generation.

- [ ] **Step 1: Write failing repository-profile test**

Append this to `tests/test_template_contract.py`:

```python
def test_repository_inspection_profile_matches_schema():
    from src.template_contract import validate_inspection_profile

    profile_path = (
        ROOT
        / "templates"
        / "metasurface"
        / "template-inspection-profile.json"
    )
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    assert validate_inspection_profile(profile) == profile
```

- [ ] **Step 2: Run the test and confirm RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_repository_inspection_profile_matches_schema \
  -q
```

Expected: FAIL because `templates/metasurface/template-inspection-profile.json` does not exist.

- [ ] **Step 3: Create the strict profile**

Create `templates/metasurface/template-inspection-profile.json` with exactly:

```json
{
  "canonical_paths": {
    "analysis_group": "::model::s_params",
    "fdtd": "::model::FDTD",
    "field_monitor": "::model::field",
    "mesh": "::model::mesh",
    "model": "::model",
    "pillar": "::model::pillar",
    "reflection_index_monitor": "::model::s_params::R_index",
    "reflection_monitor": "::model::s_params::R",
    "source": "::model::s_params::source",
    "substrate": "::model::substrate",
    "transmission_index_monitor": "::model::s_params::T_index",
    "transmission_monitor": "::model::s_params::T"
  },
  "fdtd": {
    "boundary_conditions": {
      "x_max_bc": "Anti-Symmetric",
      "x_min_bc": "Anti-Symmetric",
      "y_max_bc": "Symmetric",
      "y_min_bc": "Symmetric",
      "z_max_bc": "PML",
      "z_min_bc": "PML"
    },
    "dimension": "3D",
    "express_mode": 0,
    "mesh_accuracy": 6,
    "resource_type": "CPU",
    "simulation_time": 5e-11
  },
  "materials": {
    "pillar": "Si3N4 (Silicon Nitride) - Kischkat",
    "substrate": "SiO2 (Glass) - Palik"
  },
  "mode": "contract",
  "model_parameters": {
    "height": 7e-7,
    "period": 4.7e-7,
    "ratio": 0.8
  },
  "profile_version": "0.1",
  "results": {
    "s_parameter": "S21_Gn",
    "transmission": "T"
  },
  "template": {
    "logical_path": "templates/metasurface/base_model.fsp",
    "sha256": "03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176"
  },
  "warnings": [
    {
      "message": "B0.1 evidence shows x boundaries are Anti-Symmetric and y boundaries are Symmetric. Stage B1 preserves template evidence and does not change physics settings.",
      "type": "physics_review_required"
    }
  ]
}
```

- [ ] **Step 4: Run repository-profile test and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_repository_inspection_profile_matches_schema \
  -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add templates/metasurface/template-inspection-profile.json tests/test_template_contract.py
git commit -m "chore: add strict template inspection profile"
```

---

### Task 3: Generate fail-closed contracts from profile and probe evidence

**Files:**
- Modify: `src/template_contract.py`
- Modify: `tests/test_template_contract.py`

**Interfaces:**
- Consumes:
  - `validate_inspection_profile(profile: dict) -> dict`
  - `inspection_profile_fingerprint(profile: dict) -> str`
- Produces:
  - `contract_fingerprint(contract: dict) -> str`
  - `generate_template_contract(profile: dict, probe: dict) -> dict`

- [ ] **Step 1: Add fake B0.1 probe helper and verified-contract test**

Append this to `tests/test_template_contract.py`:

```python
def valid_b01_probe():
    return {
        "probe_version": "0.1",
        "probe_only": True,
        "status": "probe",
        "probe_fingerprint": (
            "a8e7e2ee4265f607012c54b85e29a01"
            "f55ede9220cb37b12033be6f471c017d6"
        ),
        "template": {
            "logical_path": "templates/metasurface/base_model.fsp",
            "sha256": (
                "03ba1f3ea9db6e86caa9c5458bcf84b6"
                "adb92db6c0664e60f262e2f5edde0176"
            ),
        },
        "installation": {
            "confirmable": True,
            "path_version_tag": "v242",
            "recorded_version": "unknown",
        },
        "inspector": {
            "code_commit": "bff39a0",
            "cleanup_state": "closed",
        },
        "fdtd_configuration": {
            "canonical_path": "::model::FDTD",
            "properties": {
                "dimension": {"status": "readable", "value": "3D"},
                "express_mode": {"status": "readable", "value": 0.0},
                "mesh_accuracy": {"status": "readable", "value": 6.0},
                "simulation_time": {"status": "readable", "value": 5e-11},
                "x_min_bc": {"status": "readable", "value": "Anti-Symmetric"},
                "x_max_bc": {"status": "readable", "value": "Anti-Symmetric"},
                "y_min_bc": {"status": "readable", "value": "Symmetric"},
                "y_max_bc": {"status": "readable", "value": "Symmetric"},
                "z_min_bc": {"status": "readable", "value": "PML"},
                "z_max_bc": {"status": "readable", "value": "PML"},
            },
            "cpu_express_mode_evidence": {
                "express_mode_value": 0.0,
                "cpu_confirmed": True,
                "evidence_source": "getnamed",
            },
        },
        "role_candidates": {
            "structure": {
                "pillar": {
                    "candidates": [
                        {
                            "path": "::model::pillar",
                            "exists": True,
                            "properties": {
                                "type": {"value": "Circle"},
                                "material": {
                                    "value": (
                                        "Si3N4 (Silicon Nitride) - Kischkat"
                                    )
                                },
                            },
                        }
                    ]
                },
                "substrate": {
                    "candidates": [
                        {
                            "path": "::model::substrate",
                            "exists": True,
                            "properties": {
                                "type": {"value": "Rectangle"},
                                "material": {
                                    "value": "SiO2 (Glass) - Palik"
                                },
                            },
                        }
                    ]
                },
            }
        },
        "mesh_configuration": {
            "global_mesh_accuracy_source": "::model::FDTD",
            "overrides": [{"path": "::model::mesh", "exists": True}],
        },
        "source_strategy": {
            "classification": "explicit_object",
            "evidence": {
                "source_objects_found": [
                    {
                        "path": "::model::s_params::source",
                        "type": "planesource",
                    }
                ]
            },
        },
        "monitors": [
            {"path": "::model::field"},
            {"path": "::model::s_params::T"},
            {"path": "::model::s_params::R"},
            {"path": "::model::s_params::T_index"},
            {"path": "::model::s_params::R_index"},
        ],
        "analysis_group": {
            "::model::s_params": {
                "exists": True,
                "result_naming_assumptions": {
                    "transmission": {"assumed_name": "T"},
                    "s_parameter": {"assumed_name": "S21_Gn"},
                },
            }
        },
        "model_parameters": {
            "ratio": {"value": 0.8},
            "height": {"value": 7e-7},
            "period": {"value": 4.7e-7},
        },
        "warnings": [
            {"type": "version_unknown_warning"},
        ],
        "errors": [],
        "stage_b1_ready": True,
        "stage_b1_blockers": [],
    }


def test_generate_template_contract_returns_verified_contract():
    from src.template_contract import (
        contract_fingerprint,
        generate_template_contract,
    )

    contract = generate_template_contract(
        valid_inspection_profile(),
        valid_b01_probe(),
    )

    assert contract["contract_version"] == "0.1"
    assert contract["status"] == "verified"
    assert contract["verified"] is True
    assert contract["contract_fingerprint"] == contract_fingerprint(contract)
    assert contract["template"]["sha256"] == valid_inspection_profile()["template"]["sha256"]
    assert contract["checks"]["express_mode"]["status"] == "pass"
    assert contract["checks"]["cpu_confirmed"]["status"] == "pass"
    assert contract["warnings"][0]["type"] == "physics_review_required"
```

- [ ] **Step 2: Add fail-closed generation tests**

Append:

```python
@pytest.mark.parametrize(
    "mutation,failed_check",
    [
        (
            lambda p: p["template"].update({"sha256": "bad"}),
            "template_sha",
        ),
        (
            lambda p: p["fdtd_configuration"].update({"canonical_path": "FDTD"}),
            "canonical_fdtd_path",
        ),
        (
            lambda p: p["fdtd_configuration"]["properties"]["express_mode"].update(
                {"value": 1}
            ),
            "express_mode",
        ),
        (
            lambda p: p["fdtd_configuration"]["cpu_express_mode_evidence"].update(
                {"cpu_confirmed": False}
            ),
            "cpu_confirmed",
        ),
        (
            lambda p: p["source_strategy"].update({"classification": "unresolved"}),
            "source",
        ),
        (
            lambda p: p["monitors"].pop(),
            "monitors",
        ),
        (
            lambda p: p["fdtd_configuration"]["properties"].pop("x_min_bc"),
            "boundary_conditions",
        ),
        (
            lambda p: p.update({"errors": [{"type": "probe_error"}]}),
            "probe_errors",
        ),
    ],
)
def test_generate_template_contract_fails_closed(mutation, failed_check):
    from src.template_contract import generate_template_contract

    probe = valid_b01_probe()
    mutation(probe)
    contract = generate_template_contract(valid_inspection_profile(), probe)

    assert contract["status"] == "unverified"
    assert contract["verified"] is False
    assert contract["checks"][failed_check]["status"] == "fail"
```

- [ ] **Step 3: Run new tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_generate_template_contract_returns_verified_contract \
  tests/test_template_contract.py::test_generate_template_contract_fails_closed \
  -q
```

Expected: FAIL because `generate_template_contract` and `contract_fingerprint` are not defined.

- [ ] **Step 4: Implement contract generation helpers**

Add to `src/template_contract.py`:

```python
CONTRACT_VERSION = "0.1"


def contract_fingerprint(contract: dict) -> str:
    payload = dict(contract)
    payload.pop("contract_fingerprint", None)
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def _read_probe_property(probe: dict, key: str):
    return (
        probe.get("fdtd_configuration", {})
        .get("properties", {})
        .get(key, {})
        .get("value")
    )


def _check(name: str, passed: bool, *, expected=None, actual=None) -> tuple:
    return name, {
        "status": "pass" if passed else "fail",
        "expected": expected,
        "actual": actual,
    }


def _values_match(actual, expected) -> bool:
    if actual == expected:
        return True
    if actual is None:
        return False
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return float(actual) == float(expected)
    return False


def _candidate_material(probe: dict, role: str, path: str):
    candidates = (
        probe.get("role_candidates", {})
        .get("structure", {})
        .get(role, {})
        .get("candidates", [])
    )
    for candidate in candidates:
        if candidate.get("path") != path or not candidate.get("exists"):
            continue
        return (
            candidate.get("properties", {})
            .get("material", {})
            .get("value")
        )
    return None


def _monitor_paths(probe: dict) -> set:
    return {
        item.get("path")
        for item in probe.get("monitors", [])
        if isinstance(item, dict)
    }


def generate_template_contract(profile: dict, probe: dict) -> dict:
    validate_inspection_profile(profile)
    paths = profile["canonical_paths"]
    checks = {}

    name, item = _check(
        "template_sha",
        probe.get("template", {}).get("sha256") == profile["template"]["sha256"],
        expected=profile["template"]["sha256"],
        actual=probe.get("template", {}).get("sha256"),
    )
    checks[name] = item

    name, item = _check(
        "probe_status",
        probe.get("status") == "probe" and probe.get("stage_b1_ready") is True,
        expected={"status": "probe", "stage_b1_ready": True},
        actual={
            "status": probe.get("status"),
            "stage_b1_ready": probe.get("stage_b1_ready"),
        },
    )
    checks[name] = item

    name, item = _check(
        "probe_errors",
        probe.get("errors") == [],
        expected=[],
        actual=probe.get("errors"),
    )
    checks[name] = item

    actual_fdtd_path = probe.get("fdtd_configuration", {}).get("canonical_path")
    name, item = _check(
        "canonical_fdtd_path",
        actual_fdtd_path == paths["fdtd"],
        expected=paths["fdtd"],
        actual=actual_fdtd_path,
    )
    checks[name] = item

    for prop_name, expected in (
        ("dimension", profile["fdtd"]["dimension"]),
        ("express_mode", profile["fdtd"]["express_mode"]),
        ("mesh_accuracy", profile["fdtd"]["mesh_accuracy"]),
        ("simulation_time", profile["fdtd"]["simulation_time"]),
    ):
        actual = _read_probe_property(probe, prop_name)
        checks[prop_name] = _check(
            prop_name,
            _values_match(actual, expected),
            expected=expected,
            actual=actual,
        )[1]

    actual_cpu = (
        probe.get("fdtd_configuration", {})
        .get("cpu_express_mode_evidence", {})
        .get("cpu_confirmed")
    )
    checks["cpu_confirmed"] = _check(
        "cpu_confirmed",
        actual_cpu is True,
        expected=True,
        actual=actual_cpu,
    )[1]

    actual_boundaries = {
        key: _read_probe_property(probe, key)
        for key in REQUIRED_BOUNDARY_CONDITIONS
    }
    checks["boundary_conditions"] = _check(
        "boundary_conditions",
        actual_boundaries == profile["fdtd"]["boundary_conditions"],
        expected=profile["fdtd"]["boundary_conditions"],
        actual=actual_boundaries,
    )[1]

    for role in ("pillar", "substrate"):
        actual = _candidate_material(probe, role, paths[role])
        checks[f"{role}_material"] = _check(
            f"{role}_material",
            actual == profile["materials"][role],
            expected=profile["materials"][role],
            actual=actual,
        )[1]

    actual_source_paths = {
        item.get("path")
        for item in (
            probe.get("source_strategy", {})
            .get("evidence", {})
            .get("source_objects_found", [])
        )
    }
    checks["source"] = _check(
        "source",
        probe.get("source_strategy", {}).get("classification") == "explicit_object"
        and paths["source"] in actual_source_paths,
        expected=paths["source"],
        actual=sorted(path for path in actual_source_paths if path),
    )[1]

    expected_monitors = {
        paths["field_monitor"],
        paths["transmission_monitor"],
        paths["reflection_monitor"],
        paths["transmission_index_monitor"],
        paths["reflection_index_monitor"],
    }
    actual_monitors = _monitor_paths(probe)
    checks["monitors"] = _check(
        "monitors",
        expected_monitors.issubset(actual_monitors),
        expected=sorted(expected_monitors),
        actual=sorted(path for path in actual_monitors if path),
    )[1]

    ag = probe.get("analysis_group", {}).get(paths["analysis_group"], {})
    result_names = ag.get("result_naming_assumptions", {})
    checks["analysis_group"] = _check(
        "analysis_group",
        ag.get("exists") is True
        and result_names.get("transmission", {}).get("assumed_name")
        == profile["results"]["transmission"]
        and result_names.get("s_parameter", {}).get("assumed_name")
        == profile["results"]["s_parameter"],
        expected={
            "path": paths["analysis_group"],
            "results": profile["results"],
        },
        actual={"exists": ag.get("exists"), "results": result_names},
    )[1]

    actual_params = {
        key: probe.get("model_parameters", {}).get(key, {}).get("value")
        for key in REQUIRED_MODEL_PARAMETERS
    }
    checks["model_parameters"] = _check(
        "model_parameters",
        actual_params == profile["model_parameters"],
        expected=profile["model_parameters"],
        actual=actual_params,
    )[1]

    verified = all(item["status"] == "pass" for item in checks.values())
    contract = {
        "contract_version": CONTRACT_VERSION,
        "status": "verified" if verified else "unverified",
        "verified": verified,
        "contract_fingerprint": "",
        "profile_fingerprint": inspection_profile_fingerprint(profile),
        "probe_fingerprint": probe.get("probe_fingerprint"),
        "template": profile["template"],
        "installation": {
            "path_version_tag": probe.get("installation", {}).get(
                "path_version_tag"
            ),
            "recorded_version": probe.get("installation", {}).get(
                "recorded_version"
            ),
            "confirmable": probe.get("installation", {}).get("confirmable"),
        },
        "code_commit": probe.get("inspector", {}).get("code_commit"),
        "checks": checks,
        "warnings": profile["warnings"]
        + [
            item
            for item in probe.get("warnings", [])
            if item.get("type") == "version_unknown_warning"
        ],
    }
    contract["contract_fingerprint"] = contract_fingerprint(contract)
    return contract
```

- [ ] **Step 5: Run contract generation tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_generate_template_contract_returns_verified_contract \
  tests/test_template_contract.py::test_generate_template_contract_fails_closed \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/template_contract.py tests/test_template_contract.py
git commit -m "feat: generate strict template contracts"
```

---

### Task 4: Add offline contract validation and tamper detection

**Files:**
- Modify: `src/template_contract.py`
- Modify: `tests/test_template_contract.py`

**Interfaces:**
- Consumes:
  - `contract_fingerprint(contract: dict) -> str`
  - `generate_template_contract(profile: dict, probe: dict) -> dict`
- Produces:
  - `validate_template_contract(contract: dict) -> dict`

- [ ] **Step 1: Write validation and tamper tests**

Append:

```python
def test_validate_template_contract_accepts_verified_contract():
    from src.template_contract import (
        generate_template_contract,
        validate_template_contract,
    )

    contract = generate_template_contract(
        valid_inspection_profile(),
        valid_b01_probe(),
    )

    assert validate_template_contract(contract) == {
        "ok": True,
        "errors": [],
    }


def test_validate_template_contract_rejects_tampered_fingerprint():
    from src.template_contract import (
        generate_template_contract,
        validate_template_contract,
    )

    contract = generate_template_contract(
        valid_inspection_profile(),
        valid_b01_probe(),
    )
    contract["checks"]["express_mode"]["actual"] = 1

    result = validate_template_contract(contract)

    assert result["ok"] is False
    assert "contract_fingerprint_mismatch" in result["errors"]


def test_validate_template_contract_rejects_unverified_status():
    from src.template_contract import validate_template_contract

    contract = {
        "contract_version": "0.1",
        "status": "unverified",
        "verified": False,
        "contract_fingerprint": "not-a-real-fingerprint",
        "checks": {"template_sha": {"status": "fail"}},
    }

    result = validate_template_contract(contract)

    assert result["ok"] is False
    assert "contract_not_verified" in result["errors"]
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_validate_template_contract_accepts_verified_contract \
  tests/test_template_contract.py::test_validate_template_contract_rejects_tampered_fingerprint \
  tests/test_template_contract.py::test_validate_template_contract_rejects_unverified_status \
  -q
```

Expected: FAIL because `validate_template_contract` is not defined.

- [ ] **Step 3: Implement validation**

Add to `src/template_contract.py`:

```python
def validate_template_contract(contract: dict) -> dict:
    errors = []
    if not isinstance(contract, dict):
        return {"ok": False, "errors": ["contract_not_object"]}
    if contract.get("contract_version") != CONTRACT_VERSION:
        errors.append("unsupported_contract_version")
    if contract.get("status") != "verified" or contract.get("verified") is not True:
        errors.append("contract_not_verified")
    expected_fingerprint = contract_fingerprint(contract)
    if contract.get("contract_fingerprint") != expected_fingerprint:
        errors.append("contract_fingerprint_mismatch")
    checks = contract.get("checks", {})
    if not isinstance(checks, dict):
        errors.append("checks_not_object")
    else:
        failed = [
            name
            for name, item in checks.items()
            if not isinstance(item, dict) or item.get("status") != "pass"
        ]
        if failed:
            errors.append("contract_checks_failed:" + ",".join(sorted(failed)))
    return {"ok": not errors, "errors": errors}
```

- [ ] **Step 4: Run validation tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_validate_template_contract_accepts_verified_contract \
  tests/test_template_contract.py::test_validate_template_contract_rejects_tampered_fingerprint \
  tests/test_template_contract.py::test_validate_template_contract_rejects_unverified_status \
  -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/template_contract.py tests/test_template_contract.py
git commit -m "feat: validate strict template contracts"
```

---

### Task 5: Add offline contract generation CLI and Windows entry point

**Files:**
- Create: `scripts/generate_template_contract.py`
- Create: `scripts/windows/generate_template_contract.bat`
- Modify: `tests/test_template_contract.py`

**Interfaces:**
- Consumes:
  - `atomic_write_json(path, value: dict) -> None`
  - `generate_template_contract(profile: dict, probe: dict) -> dict`
  - `validate_template_contract(contract: dict) -> dict`
- Produces:
  - CLI: `scripts/generate_template_contract.py --probe <probe.json> --profile <profile.json> --output <contract.json>`
  - Windows wrapper: `scripts\windows\generate_template_contract.bat`

- [ ] **Step 1: Write CLI tests**

Append:

```python
def test_generate_template_contract_cli_writes_verified_contract(tmp_path):
    import subprocess
    import sys

    profile_path = tmp_path / "profile.json"
    probe_path = tmp_path / "probe.json"
    output_path = tmp_path / "contract.json"
    atomic_write_json(profile_path, valid_inspection_profile())
    atomic_write_json(probe_path, valid_b01_probe())

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_template_contract.py"),
            "--profile",
            str(profile_path),
            "--probe",
            str(probe_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    contract = json.loads(output_path.read_text(encoding="utf-8"))
    assert contract["status"] == "verified"


def test_generate_template_contract_cli_returns_nonzero_for_unverified(tmp_path):
    import subprocess
    import sys

    profile_path = tmp_path / "profile.json"
    probe_path = tmp_path / "probe.json"
    output_path = tmp_path / "contract.json"
    probe = valid_b01_probe()
    probe["fdtd_configuration"]["properties"]["express_mode"]["value"] = 1
    atomic_write_json(profile_path, valid_inspection_profile())
    atomic_write_json(probe_path, probe)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_template_contract.py"),
            "--profile",
            str(profile_path),
            "--probe",
            str(probe_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    contract = json.loads(output_path.read_text(encoding="utf-8"))
    assert contract["status"] == "unverified"
```

- [ ] **Step 2: Run CLI tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_generate_template_contract_cli_writes_verified_contract \
  tests/test_template_contract.py::test_generate_template_contract_cli_returns_nonzero_for_unverified \
  -q
```

Expected: FAIL because `scripts/generate_template_contract.py` does not exist.

- [ ] **Step 3: Create CLI script**

Create `scripts/generate_template_contract.py`:

```python
"""Generate Stage B1 template contract from strict profile and probe JSON."""

import argparse
import json
from pathlib import Path

from src.template_contract import (
    atomic_write_json,
    generate_template_contract,
    validate_template_contract,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        default="templates/metasurface/template-inspection-profile.json",
    )
    parser.add_argument(
        "--probe",
        default="templates/metasurface/base_model.probe.json",
    )
    parser.add_argument(
        "--output",
        default="templates/metasurface/base_model.contract.json",
    )
    return parser.parse_args()


def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    profile = read_json(args.profile)
    probe = read_json(args.probe)
    contract = generate_template_contract(profile, probe)
    atomic_write_json(args.output, contract)
    validation = validate_template_contract(contract)
    if validation["ok"]:
        print(
            "template_contract status=verified "
            f"fingerprint={contract['contract_fingerprint']}"
        )
        return 0
    print(
        "template_contract status=unverified "
        f"errors={validation['errors']}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Create Windows wrapper**

Create `scripts/windows/generate_template_contract.bat`:

```bat
@echo off
setlocal
cd /d "%~dp0\..\.."

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

"%PYTHON%" scripts\generate_template_contract.py ^
  --profile templates\metasurface\template-inspection-profile.json ^
  --probe templates\metasurface\base_model.probe.json ^
  --output templates\metasurface\base_model.contract.json
exit /b %ERRORLEVEL%
```

- [ ] **Step 5: Run CLI tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_generate_template_contract_cli_writes_verified_contract \
  tests/test_template_contract.py::test_generate_template_contract_cli_returns_nonzero_for_unverified \
  -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_template_contract.py scripts/windows/generate_template_contract.bat tests/test_template_contract.py
git commit -m "feat: add template contract generation cli"
```

---

### Task 6: Documentation and stop-gate updates

**Files:**
- Modify: `README.md`
- Modify: `SOP.md`
- Modify: `docs/WINDOWS_RUNBOOK.md`
- Modify: `templates/metasurface/README.md`
- Modify: `DEV_LOG.md`

**Interfaces:**
- Consumes: Stage B1 CLI command and strict profile path from Task 5.
- Produces: operator instructions that separate B1 contract generation from later real-run approval.

- [ ] **Step 1: Update README current status**

In `README.md`, update the current-status block to state:

```markdown
- Current checkpoint: Stage B1 strict template profile is the next implementation stage.
- Stage B1 generates `templates/metasurface/base_model.contract.json` from the latest Windows `base_model.probe.json`; it does not start real FDTD.
- A verified contract is required before requesting real 2×2 SimulationPlan approval.
```

- [ ] **Step 2: Update SOP template contract workflow**

In `SOP.md`, update SOP-010 with this B1 section:

```markdown
### Stage B1 - strict profile and contract

1. Sync Windows checkout to current `origin/main`.
2. Confirm `templates/metasurface/base_model.probe.json` came from Stage B0.1 and has `stage_b1_ready=true`.
3. Run `scripts\windows\generate_template_contract.bat`.
4. Confirm `status=verified`, `verified=true`, and no failed checks.
5. Do not start a real SimulationPlan job in Stage B1.
6. Report the contract fingerprint and stop for separate real-run approval.
```

- [ ] **Step 3: Update Windows runbook**

In `docs/WINDOWS_RUNBOOK.md`, add:

```markdown
## Generate Stage B1 template contract

From `F:\lumerical-fdtd-auto-design\fdtd-auto-design`:

    git pull
    scripts\windows\generate_template_contract.bat

Expected result:

    template_contract status=verified fingerprint=<64 hex chars>

This command reads JSON evidence only. It must not open Lumerical, mutate `.fsp`, or create jobs.
```

- [ ] **Step 4: Update template README**

In `templates/metasurface/README.md`, add:

```markdown
## Stage B1 strict profile

`template-inspection-profile.json` is the git-tracked strict contract profile.
It records the exact canonical paths and solver evidence found by Stage B0.1.
`base_model.contract.json` is generated at runtime and remains git-ignored.

The current x/y boundary settings are preserved from evidence:
`Anti-Symmetric` on x and `Symmetric` on y. This is a physics-review warning,
not a contract-generation failure.
```

- [ ] **Step 5: Add DEV_LOG entry**

Append to `DEV_LOG.md`:

```markdown
## 2026-06-19 - Planned Template Contract Stage B1

- Goal: generate strict template profile and runtime verified contract from Stage B0.1 probe evidence.
- Safety: B1 is offline JSON validation only; no solve, no `.fsp` mutation, no job creation.
- Stop gate: verified contract enables later real 2×2 approval request, not real execution.
```

- [ ] **Step 6: Commit**

```bash
git add README.md SOP.md docs/WINDOWS_RUNBOOK.md templates/metasurface/README.md DEV_LOG.md
git commit -m "docs: document strict template contract workflow"
```

---

### Task 7: Full local verification and safety scans

**Files:**
- No planned source edits. If a scan fails, fix only the file and line that caused the failure, then rerun the failed command.

**Interfaces:**
- Consumes: all code and docs from Tasks 1-6.
- Produces: verified local B1 implementation ready for Windows contract generation.

- [ ] **Step 1: Run compileall**

Run:

```bash
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
```

Expected: exit code `0`.

- [ ] **Step 2: Run full pytest**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass. If the Mac sandbox blocks `127.0.0.1` binding in `tests/test_rpc_client_contract.py`, rerun this exact command outside the sandbox with approval and record that reason in the final report.

- [ ] **Step 3: Run forbidden-operation scan**

Run:

```bash
rg -n "run\\(|runjobs\\(|runanalysis\\(|save\\(|set\\(|setnamed\\(|delete\\(|addrect|addcircle|addfdtd|addmesh|addplane|addpower|putv|importdataset" scripts/generate_template_contract.py src/template_contract.py
```

Expected: no matches.

- [ ] **Step 4: Confirm runtime contract remains untracked**

Run:

```bash
git check-ignore templates/metasurface/base_model.contract.json
```

Expected output:

```text
templates/metasurface/base_model.contract.json
```

- [ ] **Step 5: Confirm strict profile is tracked or staged**

Run:

```bash
git ls-files templates/metasurface/template-inspection-profile.json
```

Expected output:

```text
templates/metasurface/template-inspection-profile.json
```

- [ ] **Step 6: Commit verification notes if docs changed during fixes**

If Task 7 required doc edits, commit them:

```bash
git add README.md SOP.md docs/WINDOWS_RUNBOOK.md templates/metasurface/README.md DEV_LOG.md
git commit -m "docs: record strict template contract verification"
```

If no files changed, do not create an empty commit.

---

### Task 8: Windows runtime contract generation and checkpoint stop

**Files:**
- Runtime output only: `templates/metasurface/base_model.contract.json` on Windows. This file is git-ignored.
- Modify: `DEV_LOG.md` only if recording Windows results in git is requested by the human operator.

**Interfaces:**
- Consumes:
  - `templates/metasurface/template-inspection-profile.json`
  - Windows `templates/metasurface/base_model.probe.json`
  - `scripts/windows/generate_template_contract.bat`
- Produces: Windows runtime contract report.

- [ ] **Step 1: Sync Windows checkout**

On Windows, in `F:\lumerical-fdtd-auto-design\fdtd-auto-design`:

```bat
git pull
git status --short --branch
```

Expected: branch is up to date and clean before generation.

- [ ] **Step 2: Generate contract**

Run:

```bat
scripts\windows\generate_template_contract.bat
```

Expected output:

```text
template_contract status=verified fingerprint=<64 hex chars>
```

- [ ] **Step 3: Inspect generated contract summary**

Run:

```bat
.venv\Scripts\python.exe -c "import json; p='templates/metasurface/base_model.contract.json'; d=json.load(open(p, encoding='utf-8')); print(d['status'], d['verified'], d['contract_fingerprint']); print([k for k,v in d['checks'].items() if v['status']!='pass'])"
```

Expected output shape:

```text
verified True <64 hex chars>
[]
```

- [ ] **Step 4: Confirm no runtime contract is tracked**

Run:

```bat
git status --short
```

Expected: no tracked modifications from `base_model.contract.json`. If docs were updated to record the Windows fingerprint, only docs should be modified.

- [ ] **Step 5: Stop and report**

Report:

```text
Stage B1 complete.
Contract status: verified
Contract fingerprint: <64 hex chars>
Failed checks: []
Confirmed: no solve, no .fsp mutation, no save, no job creation, no real sweep.
Stopped before real 2x2 SimulationPlan approval.
```

Do not start RPC, do not start Lumerical, and do not create a real job in Stage B1.

---

## Final Verification Checklist

- `templates/metasurface/template-inspection-profile.json` exists and is tracked.
- `templates/metasurface/base_model.contract.json` is generated on Windows and git-ignored.
- Contract status is `verified`.
- Contract fingerprint is a 64-character SHA-256 hex string.
- All contract checks have `status="pass"`.
- Contract warnings include `physics_review_required`.
- Full local tests pass.
- Forbidden-operation scan has no matches in Stage B1 scripts/helpers.
- Final report explicitly says Stage B1 is not real-run approval.

## Self-Review

- Spec coverage: Tasks 1-5 implement strict profile, profile file, contract generation, validation, CLI, and Windows wrapper. Tasks 6-8 cover docs, local verification, Windows generation, and the stop gate.
- Placeholder scan: this plan contains concrete paths, functions, snippets, commands, and expected outputs. It does not use deferred implementation markers.
- Type consistency: profile and contract helper names are consistent across tasks: `validate_inspection_profile`, `inspection_profile_fingerprint`, `generate_template_contract`, `contract_fingerprint`, and `validate_template_contract`.
