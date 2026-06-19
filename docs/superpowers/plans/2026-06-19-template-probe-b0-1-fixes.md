# Template Probe Stage B0.1 Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正 Stage B0 模板探针的错误证据判断，补齐 Windows v242 上 FDTD solver、边界条件、全局网格精度、CPU/Express Mode 与 lumapi DLL 环境证据，并明确计算 `stage_b1_ready`。

**Architecture:** 保留现有 `ProbeAdapter` 与 runtime `base_model.probe.json`，只增加三个聚焦能力：可测试的 lumapi 环境准备、固定对象的 `getnamed → selected get` 只读回退、纯函数式 Stage B1 readiness 计算。不得创建 strict profile、verified contract、RPC real guard 或真实 job。

**Tech Stack:** Python 3.10+、Lumerical v242 embedded Python/raw `lumapi`、pytest、Windows batch、JSON/SHA-256。

---

## 范围和硬约束

本计划只修改：

- `src/template_probe.py`
- `scripts/probe_metasurface_template.py`
- `scripts/windows/probe_metasurface_template.bat`（仅在环境诊断需要时）
- `tests/test_template_probe.py`
- `.gitignore`（仅当验证发现缺失）
- `README.md`
- `SOP.md`
- `DEV_LOG.md`
- `PITFALLS.md`（仅记录真实确认的新陷阱）
- `docs/WINDOWS_RUNBOOK.md`
- `templates/metasurface/README.md`

禁止修改：

- `rpc_server.py`
- `src/job_store.py`
- `src/native_sweep.py`
- `src/simulation_plan.py`
- `src/plan_compilers/`
- `src/tools/`
- `/jobs/*` 契约
- MCP real 逻辑

禁止创建：

- `templates/metasurface/template-inspection-profile.json`
- `templates/metasurface/base_model.contract.json`

探针禁止调用：

- `run`
- `runjobs`
- `runanalysis`
- `save`
- `set`
- `setnamed`
- `delete`
- `add*`
- `putv`
- `importdataset`

允许的新增只读操作只有固定对象上的：

- `groupscope`
- `select`
- `get`
- `getnamed`
- `getnamednumber`
- `getnumber`
- `selectall`
- `load`
- `close`

所有 runtime probe JSON 继续被 Git 忽略。`stage_b1_ready=true` 只表示可以开始编写 strict profile，不是 real approval。

## 当前可信基线

- HEAD：`3e950b5`
- 正常开发环境：`232 passed`
- Template SHA-256：
  `03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176`
- Pillar：`::model::pillar`
- Pillar material：`Si3N4 (Silicon Nitride) - Kischkat`
- Substrate：`::model::substrate`
- Substrate material：`SiO2 (Glass) - Palik`
- Source：`::model::s_params::source`
- Source type：`PlaneSource`
- Analysis group：`::model::s_params`
- Model parameters：`ratio≈0.8`、`height=7e-7`、`period=4.7e-7`
- 安装身份：`v242` 路径标签与 `lumapi.py` SHA-256 可确认

以下结论不可信，必须修正：

- root 路径不可读并不能证明 `independent_objects`
- 当前默认 `"FDTD"` 不是已确认的 canonical probe path
- CPU、Express Mode、六个边界条件和全局 `mesh accuracy` 尚未被真实读取

---

### Task 1: 修正 FakeProbeFdtd，只读模拟 selected-object fallback

**Files:**

- Modify: `tests/test_template_probe.py`

- [ ] **Step 1: 为 FakeProbeFdtd 增加选择状态和 `select/get` 只读 API**

在 `FakeProbeFdtd.__init__` 中增加：

```python
self._selected_name = None
```

增加：

```python
def select(self, name):
    self.calls.append(("select", name))
    matches = [
        entry
        for entry in self._objects.get(self._scope, [])
        if entry[0] == name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one object named {name!r} in {self._scope}, "
            f"found {len(matches)}"
        )
    self._selected_name = name

def get(self, prop, index=None):
    self.calls.append(("get", prop, index))
    if index is not None:
        name, obj_type, props = self._selected[index - 1]
    else:
        matches = [
            entry
            for entry in self._objects.get(self._scope, [])
            if entry[0] == self._selected_name
        ]
        if len(matches) != 1:
            raise RuntimeError("No uniquely selected object")
        name, obj_type, props = matches[0]
    if prop == "name":
        return name
    if prop == "type":
        return obj_type
    if prop in props:
        return props[prop]
    raise RuntimeError(
        f"Property {prop!r} not found on "
        f"{self._scope}::{name}"
    )
```

更新 class docstring，把 `select` 和 selected `get` 加入允许操作。

- [ ] **Step 2: 给 baseline FDTD 和 mesh 补真实测试属性**

`::model::FDTD` 的 properties 至少包含：

```python
{
    "express mode": 0,
    "dimension": "3D",
    "mesh accuracy": 3,
    "simulation time": 5e-12,
    "x min bc": "PML",
    "x max bc": "PML",
    "y min bc": "Periodic",
    "y max bc": "Periodic",
    "z min bc": "PML",
    "z max bc": "PML",
    "x": 0.0,
    "y": 0.0,
    "z": 4.13e-7,
    "x span": 4.7e-7,
    "y span": 4.7e-7,
    "z span": 1.38e-6,
}
```

`::model::mesh` 的 properties 至少包含：

```python
{
    "based on a structure": 0,
    "override x mesh": 1,
    "override y mesh": 1,
    "override z mesh": 1,
    "dx": 5e-9,
    "dy": 5e-9,
    "dz": 5e-9,
    "x": 0.0,
    "y": 0.0,
    "z": 3.5e-7,
    "x span": 4.7e-7,
    "y span": 4.7e-7,
    "z span": 7e-7,
}
```

- [ ] **Step 3: 增加 getnamed 失败、selected get 成功的场景**

在 `getnamed()` 中支持 scenario：

```python
if (
    self._scenario == "solver_getnamed_unreadable"
    and path == "::model::FDTD"
):
    raise RuntimeError("Solver properties unavailable through getnamed")
```

增加 `express_mode_one`、`source_script_evidence` 和 `source_unresolved` 场景。脚本证据场景必须包含明确的 `addplane` 或 source 创建字符串；unresolved 场景的脚本不含 source 创建/配置关键词。

- [ ] **Step 4: 增加 Fake API 测试**

```python
def test_fake_probe_fdtd_supports_fixed_selected_get():
    fdtd = FakeProbeFdtd()
    fdtd.groupscope("::model")
    fdtd.select("FDTD")
    assert fdtd.get("express mode") == 0
    assert fdtd.get("x min bc") == "PML"
```

并把 `select` 加入允许操作测试。

- [ ] **Step 5: 运行测试，确认测试夹具通过**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py::test_fake_probe_fdtd_supports_fixed_selected_get \
  tests/test_template_probe.py::test_fake_probe_fdtd_has_no_forbidden_operations \
  -q
```

Expected: `2 passed`。

- [ ] **Step 6: 提交**

```bash
git add tests/test_template_probe.py
git commit -m "test: extend template probe readonly fake"
```

---

### Task 2: 实现可测试的 Windows lumapi 环境准备

**Files:**

- Modify: `src/template_probe.py`
- Modify: `scripts/probe_metasurface_template.py`
- Test: `tests/test_template_probe.py`

- [ ] **Step 1: 写环境准备失败测试**

增加测试：

```python
def test_prepare_lumapi_environment_adds_api_and_bin_paths(
    tmp_path, monkeypatch
):
    from src.template_probe import prepare_lumapi_environment

    version_root = tmp_path / "v242"
    api_python = version_root / "api" / "python"
    bin_path = version_root / "bin"
    api_python.mkdir(parents=True)
    bin_path.mkdir()

    fake_sys_path = []
    monkeypatch.setenv("PATH", "existing")
    diagnostics = prepare_lumapi_environment(
        version_root=version_root,
        sys_path=fake_sys_path,
        environ=os.environ,
        platform_name="win32",
        add_dll_directory=lambda path: object(),
    )

    assert fake_sys_path == [str(api_python)]
    assert os.environ["PATH"].split(os.pathsep)[0] == str(bin_path)
    assert diagnostics["api_python_path"] == str(api_python)
    assert diagnostics["bin_path"] == str(bin_path)
    assert diagnostics["dll_directory_added"] is True
    assert diagnostics["errors"] == []
```

增加重复调用测试，断言 `sys.path`、`PATH` 和 DLL handle 数量不重复增加。

增加路径缺失测试，断言 diagnostics 包含：

```python
{
    "api_python_exists": False,
    "bin_exists": False,
    "errors": [...]
}
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py -k "prepare_lumapi_environment" -q
```

Expected: FAIL，`prepare_lumapi_environment` 尚不存在。

- [ ] **Step 3: 在 `src/template_probe.py` 实现最小环境准备**

增加模块级句柄：

```python
_DLL_DIRECTORY_HANDLES = {}
```

增加：

```python
def derive_version_root(python_executable) -> Path:
    executable = Path(python_executable).resolve()
    if executable.parent.name.lower() == "python":
        return executable.parent.parent
    return executable.parent


def prepare_lumapi_environment(
    *,
    version_root=None,
    python_executable=None,
    sys_path=None,
    environ=None,
    platform_name=None,
    add_dll_directory=None,
) -> dict:
    import sys

    sys_path = sys.path if sys_path is None else sys_path
    environ = os.environ if environ is None else environ
    platform_name = sys.platform if platform_name is None else platform_name
    python_executable = (
        sys.executable if python_executable is None else python_executable
    )
    root = (
        derive_version_root(python_executable)
        if version_root is None
        else Path(version_root).resolve()
    )
    api_python = root / "api" / "python"
    bin_path = root / "bin"
    diagnostics = {
        "version_root": str(root),
        "api_python_path": str(api_python),
        "bin_path": str(bin_path),
        "api_python_exists": api_python.is_dir(),
        "bin_exists": bin_path.is_dir(),
        "sys_path_added": False,
        "path_added": False,
        "dll_directory_added": False,
        "errors": [],
    }

    if api_python.is_dir():
        api_text = str(api_python)
        if api_text not in sys_path:
            sys_path.append(api_text)
            diagnostics["sys_path_added"] = True
    else:
        diagnostics["errors"].append({
            "type": "api_python_missing",
            "path": str(api_python),
        })

    if bin_path.is_dir():
        bin_text = str(bin_path)
        path_parts = [
            item for item in environ.get("PATH", "").split(os.pathsep)
            if item
        ]
        if bin_text not in path_parts:
            environ["PATH"] = os.pathsep.join([bin_text, *path_parts])
            diagnostics["path_added"] = True
        if platform_name.startswith("win"):
            dll_adder = (
                getattr(os, "add_dll_directory", None)
                if add_dll_directory is None
                else add_dll_directory
            )
            if dll_adder is not None and bin_text not in _DLL_DIRECTORY_HANDLES:
                _DLL_DIRECTORY_HANDLES[bin_text] = dll_adder(bin_text)
                diagnostics["dll_directory_added"] = True
    else:
        diagnostics["errors"].append({
            "type": "bin_missing",
            "path": str(bin_path),
        })

    return diagnostics
```

- [ ] **Step 4: 让 `import_lumapi()` 返回模块和诊断**

替换现有实现：

```python
def import_lumapi():
    diagnostics = prepare_lumapi_environment()
    module = importlib.import_module("lumapi")
    return module, diagnostics
```

调整 `run_probe()`/`build_probe()` 的依赖注入，使测试可以传入固定 diagnostics，不在测试进程污染真实 PATH。

`probe["installation"]["environment_preparation"]` 必须保存 diagnostics。

- [ ] **Step 5: 运行环境测试**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py -k "lumapi_environment or installation" -q
```

Expected: 所选测试全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add src/template_probe.py scripts/probe_metasurface_template.py \
  tests/test_template_probe.py
git commit -m "fix: prepare lumerical probe environment"
```

---

### Task 3: 修正重复对象的证据分类

**Files:**

- Modify: `scripts/probe_metasurface_template.py`
- Test: `tests/test_template_probe.py`

- [ ] **Step 1: 写三种严格分类测试**

保留现有 identical/different 测试，再增加：

```python
def test_identically_named_objects_with_unreadable_side_are_unresolved():
    module = load_probe_module()

    class RootUnreadableFdtd(FakeProbeFdtd):
        def getnamed(self, path, prop):
            if path.startswith("::") and not path.startswith("::model::"):
                raise RuntimeError("root canonical path unavailable")
            return super().getnamed(path, prop)

    evidence = module.ProbeAdapter(
        RootUnreadableFdtd()
    ).probe_identically_named_objects()
    pillar = next(item for item in evidence if item["name"] == "pillar")
    assert pillar["conclusion"] == "unresolved_scope_alias"
    assert pillar["unreadable_paths"] == ["::pillar"]
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py \
  -k "identically_named_objects" -q
```

Expected: unreadable 测试 FAIL，当前返回 `independent_objects`。

- [ ] **Step 3: 实现三态判断**

将比较逻辑改为：

```python
unreadable_paths = set()
different_readable_value = False

for prop in stable_properties:
    values = {}
    readable_values = {}
    for entry in entries:
        try:
            value = _jsonable(
                self._fdtd.getnamed(entry["path"], prop)
            )
            values[entry["path"]] = {
                "status": "readable",
                "value": value,
            }
            readable_values[entry["path"]] = value
        except Exception as exc:
            unreadable_paths.add(entry["path"])
            values[entry["path"]] = {
                "status": "unreadable",
                "error": str(exc),
            }
    comparison["property_comparison"][prop] = values
    if len(readable_values) == len(entries):
        encoded = {
            stable_json({"value": value})
            for value in readable_values.values()
        }
        if len(encoded) > 1:
            different_readable_value = True

comparison["unreadable_paths"] = sorted(unreadable_paths)
if unreadable_paths:
    comparison["conclusion"] = "unresolved_scope_alias"
elif different_readable_value:
    comparison["conclusion"] = "independent_objects"
else:
    comparison["conclusion"] = "possible_alias_or_identical"
```

从 `src.template_probe` 导入 `stable_json`，避免重复实现序列化。

- [ ] **Step 4: 运行聚焦测试**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py \
  -k "identically_named_objects" -q
```

Expected: 三种分类全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/probe_metasurface_template.py tests/test_template_probe.py
git commit -m "fix: classify unresolved template scope aliases"
```

---

### Task 4: 实现固定 FDTD solver 的只读属性回退

**Files:**

- Modify: `scripts/probe_metasurface_template.py`
- Test: `tests/test_template_probe.py`

- [ ] **Step 1: 写 solver 读取失败测试**

增加：

```python
def test_fdtd_configuration_prefers_model_solver_path():
    module = load_probe_module()
    fdtd = FakeProbeFdtd()
    config = module.ProbeAdapter(fdtd).probe_fdtd_configuration()
    assert config["canonical_path"] == "::model::FDTD"
    assert config["properties"]["dimension"]["value"] == "3D"
    assert config["properties"]["dimension"]["read_method"] == "getnamed"


def test_fdtd_configuration_falls_back_to_selected_get():
    module = load_probe_module()
    fdtd = FakeProbeFdtd(scenario="solver_getnamed_unreadable")
    config = module.ProbeAdapter(fdtd).probe_fdtd_configuration()
    assert config["properties"]["express_mode"] == {
        "status": "readable",
        "value": 0,
        "read_method": "selected_get",
        "scope": "::model",
        "object_name": "FDTD",
    }
    assert fdtd.calls[-1] == ("groupscope", "::")
```

增加六个边界条件和全局 mesh accuracy 断言。

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py -k "fdtd_configuration" -q
```

Expected: FAIL，当前返回扁平值且默认路径为 `"FDTD"`。

- [ ] **Step 3: 增加固定属性读取 helper**

在 `ProbeAdapter` 中增加：

```python
def _read_fixed_object_property(
    self,
    *,
    canonical_path: str,
    scope: str,
    object_name: str,
    property_name: str,
) -> dict:
    try:
        return {
            "status": "readable",
            "value": _jsonable(
                self._fdtd.getnamed(canonical_path, property_name)
            ),
            "read_method": "getnamed",
            "path": canonical_path,
        }
    except Exception as getnamed_exc:
        try:
            self._fdtd.groupscope(scope)
            self._fdtd.select(object_name)
            return {
                "status": "readable",
                "value": _jsonable(self._fdtd.get(property_name)),
                "read_method": "selected_get",
                "scope": scope,
                "object_name": object_name,
            }
        except Exception as selected_exc:
            return {
                "status": "unreadable",
                "path": canonical_path,
                "getnamed_error": str(getnamed_exc),
                "selected_get_error": str(selected_exc),
            }
        finally:
            self._fdtd.groupscope("::")
```

该 helper 不接受来自 CLI、JSON 或用户输入的对象路径；仅由代码内固定参数调用。

- [ ] **Step 4: 重写 `probe_fdtd_configuration()`**

固定：

```python
canonical_path = "::model::FDTD"
scope = "::model"
object_name = "FDTD"
```

属性映射：

```python
properties = {
    "type": "type",
    "dimension": "dimension",
    "express_mode": "express mode",
    "mesh_accuracy": "mesh accuracy",
    "simulation_time": "simulation time",
    "x_min_bc": "x min bc",
    "x_max_bc": "x max bc",
    "y_min_bc": "y min bc",
    "y_max_bc": "y max bc",
    "z_min_bc": "z min bc",
    "z_max_bc": "z max bc",
    "x": "x",
    "y": "y",
    "z": "z",
    "x_span": "x span",
    "y_span": "y span",
    "z_span": "z span",
}
```

CPU 证据只能由真实读取值生成：

```python
express = result["properties"]["express_mode"]
cpu_confirmed = (
    express.get("status") == "readable"
    and express.get("value") == 0
)
result["cpu_express_mode_evidence"] = {
    "express_mode_value": (
        express.get("value")
        if express.get("status") == "readable"
        else None
    ),
    "cpu_confirmed": cpu_confirmed,
    "evidence_source": express.get("read_method"),
}
```

- [ ] **Step 5: 增加 CPU fail-closed 测试**

```python
def test_fdtd_cpu_requires_real_zero_express_mode():
    module = load_probe_module()
    config = module.ProbeAdapter(
        FakeProbeFdtd(scenario="express_mode_one")
    ).probe_fdtd_configuration()
    assert config["cpu_express_mode_evidence"]["cpu_confirmed"] is False
```

再覆盖 unreadable。

- [ ] **Step 6: 运行 FDTD 测试**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py -k "fdtd_configuration or fdtd_cpu" -q
```

Expected: 全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add scripts/probe_metasurface_template.py tests/test_template_probe.py
git commit -m "fix: read canonical fdtd solver configuration"
```

---

### Task 5: 分离全局 mesh accuracy 与 mesh override 证据

**Files:**

- Modify: `scripts/probe_metasurface_template.py`
- Test: `tests/test_template_probe.py`

- [ ] **Step 1: 写新的 mesh 输出测试**

```python
def test_mesh_configuration_separates_global_and_override_mesh():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    fdtd = adapter.probe_fdtd_configuration()
    mesh = adapter.probe_mesh_configuration()

    assert fdtd["properties"]["mesh_accuracy"]["value"] == 3
    assert mesh["global_mesh_accuracy_source"] == "::model::FDTD"
    override = next(
        item for item in mesh["overrides"]
        if item["path"] == "::model::mesh"
    )
    assert override["properties"]["dx"]["value"] == 5e-9
    assert override["properties"]["override_x_mesh"]["value"] == 1
    assert "mesh_accuracy" not in override["properties"]
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py -k "mesh_configuration" -q
```

Expected: FAIL，当前输出是 `meshes` 且错误读取 `mesh accuracy`。

- [ ] **Step 3: 重写 mesh override 探针**

固定 canonical path `::model::mesh`，使用 `_read_fixed_object_property()`。

属性映射：

```python
properties = {
    "type": "type",
    "based_on_a_structure": "based on a structure",
    "override_x_mesh": "override x mesh",
    "override_y_mesh": "override y mesh",
    "override_z_mesh": "override z mesh",
    "dx": "dx",
    "dy": "dy",
    "dz": "dz",
    "x": "x",
    "y": "y",
    "z": "z",
    "x_span": "x span",
    "y_span": "y span",
    "z_span": "z span",
}
```

返回：

```python
{
    "global_mesh_accuracy_source": "::model::FDTD",
    "overrides": [
        {
            "path": "::model::mesh",
            "properties": {...},
        }
    ],
}
```

- [ ] **Step 4: 运行 mesh 测试**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py -k "mesh_configuration" -q
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/probe_metasurface_template.py tests/test_template_probe.py
git commit -m "fix: separate global and override mesh evidence"
```

---

### Task 6: 让 source strategy 只依据明确证据分类

**Files:**

- Modify: `scripts/probe_metasurface_template.py`
- Test: `tests/test_template_probe.py`

- [ ] **Step 1: 收紧 source 测试**

将宽松测试：

```python
assert result["classification"] in (
    "analysis_group_setup", "unresolved",
)
```

替换为两个明确测试：

```python
def test_source_strategy_without_explicit_evidence_is_unresolved():
    module = load_probe_module()
    result = module.ProbeAdapter(
        FakeProbeFdtd(scenario="source_unresolved")
    ).probe_source_strategy()
    assert result["classification"] == "unresolved"
    assert result["evidence"]["source_objects_found"] == []
    assert "primary_source" not in result["evidence"]


def test_source_strategy_requires_script_creation_evidence():
    module = load_probe_module()
    result = module.ProbeAdapter(
        FakeProbeFdtd(scenario="source_script_evidence")
    ).probe_source_strategy()
    assert result["classification"] == "analysis_group_setup"
    assert result["evidence"]["script_source_evidence"]
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py -k "source_strategy" -q
```

Expected: unresolved 测试 FAIL。

- [ ] **Step 3: 从脚本审计中生成布尔证据，不保存全文**

修改 `_read_script_text_safely()`，增加：

```python
source_markers = (
    "addplane",
    "addgaussian",
    "addmode",
    "adddipole",
    "addtfsf",
    "setglobalsource",
    "wavelength start",
    "wavelength stop",
    "injection axis",
)
lowered = text.lower()
source_evidence = [
    marker for marker in source_markers if marker in lowered
]
```

返回中仅加入 marker 名称：

```python
"source_markers": source_evidence
```

不得返回脚本文本。

- [ ] **Step 4: 重写分类**

```python
if source_objects:
    classification = "explicit_object"
elif script_source_evidence:
    classification = "analysis_group_setup"
elif global_source_evidence:
    classification = "global_source"
else:
    classification = "unresolved"
```

当前没有可靠 global source 读取时，`global_source_evidence=[]`，不得猜测。

- [ ] **Step 5: 运行 source 测试**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py -k "source_strategy or scripts_only" -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add scripts/probe_metasurface_template.py tests/test_template_probe.py
git commit -m "fix: require explicit source strategy evidence"
```

---

### Task 7: 增加纯函数 Stage B1 readiness 与结构化 warning

**Files:**

- Modify: `src/template_probe.py`
- Modify: `scripts/probe_metasurface_template.py`
- Test: `tests/test_template_probe.py`

- [ ] **Step 1: 写 readiness 通过和失败测试**

增加：

```python
def test_stage_b1_readiness_passes_only_complete_probe():
    from src.template_probe import evaluate_stage_b1_readiness

    readiness = evaluate_stage_b1_readiness(
        template_sha_matches=True,
        installation_confirmable=True,
        fdtd_configuration={
            "canonical_path": "::model::FDTD",
            "properties": {
                "dimension": {"status": "readable", "value": "3D"},
                "express_mode": {"status": "readable", "value": 0},
                "mesh_accuracy": {"status": "readable", "value": 3},
                "x_min_bc": {"status": "readable", "value": "PML"},
                "x_max_bc": {"status": "readable", "value": "PML"},
                "y_min_bc": {"status": "readable", "value": "Periodic"},
                "y_max_bc": {"status": "readable", "value": "Periodic"},
                "z_min_bc": {"status": "readable", "value": "PML"},
                "z_max_bc": {"status": "readable", "value": "PML"},
            },
            "cpu_express_mode_evidence": {"cpu_confirmed": True},
        },
        resolved_roles={
            "pillar": True,
            "substrate": True,
            "source": True,
            "monitors": True,
            "analysis_group": True,
        },
        model_parameters={
            "ratio": {"value": 0.8},
            "height": {"value": 7e-7},
            "period": {"value": 4.7e-7},
        },
        errors=[],
    )
    assert readiness == {"ready": True, "blockers": []}
```

参数化失败测试必须逐个覆盖：

- template SHA mismatch
- installation unconfirmable
- canonical FDTD path 缺失
- Express Mode unreadable
- Express Mode 非 0
- dimension unreadable
- mesh accuracy unreadable
- 任一 boundary unreadable
- 任一 required role 未解析
- 任一 model parameter unreadable
- errors 非空

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py -k "stage_b1_readiness" -q
```

Expected: FAIL，函数不存在。

- [ ] **Step 3: 实现纯函数**

在 `src/template_probe.py` 增加：

```python
EXPECTED_TEMPLATE_SHA256 = (
    "03ba1f3ea9db6e86caa9c5458bcf84b6"
    "adb92db6c0664e60f262e2f5edde0176"
)


def _is_readable(properties, key):
    return properties.get(key, {}).get("status") == "readable"


def evaluate_stage_b1_readiness(
    *,
    template_sha_matches,
    installation_confirmable,
    fdtd_configuration,
    resolved_roles,
    model_parameters,
    errors,
) -> dict:
    blockers = []
    if not template_sha_matches:
        blockers.append("template_sha_mismatch")
    if not installation_confirmable:
        blockers.append("installation_unconfirmable")
    if fdtd_configuration.get("canonical_path") != "::model::FDTD":
        blockers.append("canonical_fdtd_unconfirmed")

    properties = fdtd_configuration.get("properties", {})
    required_properties = (
        "dimension",
        "express_mode",
        "mesh_accuracy",
        "x_min_bc",
        "x_max_bc",
        "y_min_bc",
        "y_max_bc",
        "z_min_bc",
        "z_max_bc",
    )
    for key in required_properties:
        if not _is_readable(properties, key):
            blockers.append(f"fdtd_property_unreadable:{key}")

    if not fdtd_configuration.get(
        "cpu_express_mode_evidence", {}
    ).get("cpu_confirmed"):
        blockers.append("cpu_express_mode_unconfirmed")

    for role in (
        "pillar", "substrate", "source",
        "monitors", "analysis_group",
    ):
        if not resolved_roles.get(role):
            blockers.append(f"role_unresolved:{role}")

    for name in ("ratio", "height", "period"):
        parameter = model_parameters.get(name, {})
        if "value" not in parameter:
            blockers.append(f"model_parameter_unreadable:{name}")

    if errors:
        blockers.append("probe_has_errors")
    return {"ready": not blockers, "blockers": blockers}
```

- [ ] **Step 4: 在 `build_probe()` 组装 resolved roles**

固定判断：

```python
resolved_roles = {
    "pillar": _has_readable_candidate(
        role_candidates, "pillar", "::model::pillar"
    ),
    "substrate": _has_readable_candidate(
        role_candidates, "substrate", "::model::substrate"
    ),
    "source": (
        source.get("classification") == "explicit_object"
        and any(
            item.get("path") == "::model::s_params::source"
            for item in source.get("evidence", {}).get(
                "source_objects_found", []
            )
        )
    ),
    "monitors": bool(monitors),
    "analysis_group": (
        analysis_group.get("::model::s_params", {}).get("exists")
        is True
    ),
}
```

计算：

```python
readiness = evaluate_stage_b1_readiness(
    template_sha_matches=(
        template_id["sha256"] == EXPECTED_TEMPLATE_SHA256
    ),
    installation_confirmable=install_id["confirmable"],
    fdtd_configuration=fdtd_config,
    resolved_roles=resolved_roles,
    model_parameters=model_params,
    errors=errors,
)
```

输出顶层：

```python
"stage_b1_ready": readiness["ready"],
"stage_b1_blockers": readiness["blockers"],
```

每个 blocker 同时生成结构化 warning：

```python
warnings.append({
    "type": "stage_b1_blocker",
    "blocker": blocker,
})
```

`status` 仍只取决于 probe 是否执行成功；readiness false 不自动把 `status=probe` 改成错误。

- [ ] **Step 5: 更新 failure probe**

`_failure_probe()` 必须包含：

```python
"stage_b1_ready": False,
"stage_b1_blockers": ["probe_failed"],
```

- [ ] **Step 6: 运行 readiness 和 orchestration 测试**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py \
  -k "stage_b1 or build_probe or cleanup" -q
```

Expected: 全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add src/template_probe.py scripts/probe_metasurface_template.py \
  tests/test_template_probe.py
git commit -m "feat: gate strict profile on probe evidence"
```

---

### Task 8: 完整离线验证、安全扫描与文档同步

**Files:**

- Modify: `README.md`
- Modify: `SOP.md`
- Modify: `DEV_LOG.md`
- Modify: `docs/WINDOWS_RUNBOOK.md`
- Modify: `templates/metasurface/README.md`
- Modify: `PITFALLS.md` only if verification confirms a new v242 behavior

- [ ] **Step 1: 运行聚焦测试**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_probe.py \
  tests/test_template_contract.py \
  tests/test_template_inspector.py \
  -q
```

Expected: 全部 PASS，数量不得少于修改前的 `63 passed`。

- [ ] **Step 2: 运行 compileall**

Run:

```bash
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
```

Expected: exit `0`，无输出。

- [ ] **Step 3: 运行完整 pytest**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: 全部 PASS，测试数量大于 `232`。

如果仅因受限环境的 `PermissionError: socket.bind` 失败：

1. 保存原始错误摘要；
2. 在允许 localhost 的正常开发环境重新运行；
3. 只有正常环境全绿才可记录完整 pytest 通过；
4. 真实 assertion failure 不得归因于沙箱。

- [ ] **Step 4: 运行禁止操作扫描**

Run:

```bash
! rg -n \
  '\\.(run|runjobs|runanalysis|save|set|setnamed|delete|putv|importdataset)\\(' \
  scripts/probe_metasurface_template.py src/template_probe.py
```

Run:

```bash
! rg -n \
  '\\b(addrect|addcircle|addfdtd|addmesh|addplane|addpower|addgaussian|addmode|adddipole|addtfsf)\\s*\\(' \
  scripts/probe_metasurface_template.py src/template_probe.py
```

Expected: 两条命令 exit `0`、无匹配。

注意：脚本审计 marker 可以作为普通字符串存在；扫描必须锁定 Python 调用形态，不能把 marker 字符串误报为执行。

- [ ] **Step 5: 运行 runtime artifact 和 diff 检查**

Run:

```bash
git ls-files \
  'templates/metasurface/base_model.probe.json' \
  'templates/metasurface/base_model.inventory.json' \
  'templates/metasurface/base_model.contract.json' \
  'templates/metasurface/*.fsp'
```

Expected: 无输出。

Run:

```bash
git diff --check
git status --short --branch
```

Expected: `git diff --check` exit `0`；只显示预期文档修改。

- [ ] **Step 6: 更新文档**

文档必须明确：

```text
Stage B0.1 只修复 probe evidence。
stage_b1_ready 不是 real approval。
Windows probe 前不得声称 Stage B1 ready。
```

README 的下一步在 Windows 复验前写：

```text
当前下一步：Windows 重新运行 Stage B0.1 只读 probe；
只有 stage_b1_ready=true 才编写 Stage B1 strict profile。
```

SOP 新增/更新：

```text
Stage A inventory
→ Stage B0 discovery probe
→ Stage B0.1 evidence correction probe
→ review stage_b1_ready
→ Stage B1 strict profile
```

WINDOWS_RUNBOOK 增加精确命令：

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git pull --ff-only
scripts\windows\probe_metasurface_template.bat
type templates\metasurface\base_model.probe.json
```

- [ ] **Step 7: 记录离线验证并提交**

DEV_LOG 记录：

- 修正了哪些证据判断；
- 聚焦测试数量；
- 完整测试数量；
- 禁止操作扫描；
- 尚未运行 Windows probe；
- 未进入 Stage B1。

Commit:

```bash
git add README.md SOP.md DEV_LOG.md docs/WINDOWS_RUNBOOK.md \
  templates/metasurface/README.md PITFALLS.md
git commit -m "docs: document template probe evidence gate"
```

如果 `PITFALLS.md` 未修改，不要把它加入 `git add`。

- [ ] **Step 8: 推送**

Run:

```bash
git status --short --branch
git push origin main
```

Expected: push 成功；本地 `main` 与 `origin/main` 同步。

---

### Task 9: Windows v242 只读复验与停止门

**Files:**

- Runtime only: `templates/metasurface/base_model.probe.json`
- Modify after evidence: `DEV_LOG.md`
- Modify after evidence if status wording changes: `README.md`

- [ ] **Step 1: Windows 同步**

在 Windows 本地执行：

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git status --short --branch
git pull --ff-only
git rev-parse --short HEAD
```

Expected:

- 工作树无用户修改；
- HEAD 等于 Mac 推送的最新 commit。

- [ ] **Step 2: 运行一次只读 probe**

```cmd
scripts\windows\probe_metasurface_template.bat
```

不得重启 RPC Server，不得启动 job 或 sweep。

- [ ] **Step 3: 读取结果**

```cmd
type templates\metasurface\base_model.probe.json
```

必须核对：

- `probe_only=true`
- `status=probe`
- `errors=[]`
- `cleanup_state=closed`
- template SHA 与 Stage A 完全一致
- installation identity `confirmable=true`
- environment preparation 中 api/python 与 bin 均存在
- canonical FDTD path 为 `::model::FDTD`
- Express Mode 可读且为 `0`
- `cpu_confirmed=true`
- dimension 可读
- global mesh accuracy 可读
- 六个 boundary conditions 全部可读
- source 仍为 `::model::s_params::source`
- model parameters 全部可读
- `stage_b1_ready` 与 blockers 一致

- [ ] **Step 4: 检查没有副作用**

Windows 执行：

```cmd
git status --short
```

只允许出现被忽略的 runtime JSON；不得出现 tracked 修改。

确认：

- 没有新 `.fsp`
- 没有新 `jobs\job_*`
- 没有 simulation results
- 没有运行、保存或修改模板

- [ ] **Step 5: 按结果处理停止门**

若：

```json
"stage_b1_ready": true
```

则状态记为：

```text
Stage B0.1 complete; Stage B1 ready
```

但仍然停止，不创建 strict profile。

若为 false：

```text
Stage B0.1 complete; Stage B1 blocked
```

必须逐项报告 `stage_b1_blockers`，不得绕过。

- [ ] **Step 6: 更新最终运行记录**

DEV_LOG 记录：

- Windows HEAD
- probe fingerprint
- template SHA
- environment preparation diagnostics
- duplicate-object 修正结论
- canonical FDTD path 和每个关键属性的 read method
- Express Mode/CPU
- dimension、mesh accuracy、simulation time
- 六个 boundary conditions
- mesh override
- source strategy
- warnings/errors/cleanup
- `stage_b1_ready` 和 blockers
- 明确未进入 Stage B1

README 只更新当前状态和下一步。

- [ ] **Step 7: 提交运行记录并推送**

```bash
git add README.md DEV_LOG.md
git commit -m "docs: record Stage B0.1 windows probe"
git push origin main
git status --short --branch
```

Expected: clean，`main...origin/main` 无 ahead/behind。

---

## 最终报告格式

执行代理最终必须报告：

1. 每个 Task 的 commit hash。
2. 新建和修改文件。
3. compileall 原始结果。
4. 聚焦 pytest 与完整 pytest 原始结果。
5. 禁止操作扫描结果。
6. Windows HEAD。
7. probe status、fingerprint、`stage_b1_ready`。
8. Template SHA 是否与 Stage A 一致。
9. lumapi environment preparation diagnostics。
10. 重复对象修正后的结论。
11. canonical FDTD path 与每个属性的读取方法。
12. Express Mode 与 CPU 确认结果。
13. dimension、mesh accuracy、simulation time。
14. 六个 boundary conditions。
15. Mesh override 的 flags、dx/dy/dz、坐标和 span。
16. source strategy 修正结论。
17. warnings、errors、cleanup state。
18. 明确确认未求解、未修改模板、未保存 `.fsp`、未创建 job。
19. git status 与 origin/main 同步状态。
20. 明确写出 `Stage B1 ready` 或 `Stage B1 blocked`。
21. 明确确认已停在 Stage B0.1，未进入 Stage B1。

## Plan self-review

- Spec coverage：环境准备、对象证据、FDTD fallback、CPU、边界、全局/override mesh、source fail-closed、readiness、Windows 复验和停止门均有独立任务。
- Scope：未包含 strict profile、contract、RPC guard 或真实运行。
- Placeholder scan：无 TBD/TODO/“稍后实现”。
- Type consistency：FDTD property evidence 统一使用 `{status, value, read_method, ...}`；readiness 只消费该结构。
- Safety：新增 `select/get` 仅用于固定 `::model::FDTD` 与 `::model::mesh`，不开放任意脚本或任意对象输入。
