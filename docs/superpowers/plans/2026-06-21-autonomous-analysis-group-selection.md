# Autonomous Analysis Group Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 FDTD MCP 在 Windows v242 建模过程中自动枚举并缓存 Object Library，根据结构化分析意图高置信度选择官方 analysis group，安全探测可配置参数，确定性配置并回读验证，失败时按策略回退自定义 group。

**Architecture:** Windows RPC 新增版本绑定的 `ObjectLibraryCatalog` 和同会话隔离探测器；纯 Python 层新增 intent resolver、matcher 和 parameter resolver；现有 `/analysis-groups` 与 DeviceRecipe build 调用统一的 `AnalysisGroupService`。离线 compile 只生成 runtime resolution instructions，Windows build 才能依据当前 catalog 选择 `script_id`，并产出 execution fingerprint。

**Tech Stack:** Python 3.10+、Flask API v1、raw Lumerical v242 lumapi、FastMCP、pytest、JSON 原子缓存、现有 SHA-256 fingerprint helpers。

## Global Constraints

- Mac 端不得导入 `lumapi`。
- Windows FDTD v242 是 Object Library ID、参数和默认值的唯一运行时事实来源。
- 不猜测 `script_id`，不使用网页标题替代实际 `addobject;` 枚举结果。
- 首次连接只枚举 ID；仅对相关 shortlist 候选按需插入探测。
- 仅在会话空闲、工程可保存恢复时探测；不启动第二个 FDTD 会话。
- 恢复验证失败后禁止继续写当前工程，也不得自动回退 custom。
- 自动参数优先级固定为 `parameter_overrides > Recipe 明确值 > 模型可证明推导值 > 官方默认值`。
- 未确定参数保留官方默认值并披露，不由 Agent 猜数值。
- 最终自动选择门固定为最高分 `>= 0.85` 且与第二名分差 `>= 0.15`。
- shortlist 核心词分数门固定为 `>= 0.35`，最多探测 3 个候选。
- `prefer_builtin=true` 失败时回退 custom；`require_builtin=true` 失败时结构化报错。
- 保持现有精确 69-tool MCP 注册表，不新增工具。
- `dry_run=true` 不执行 probe，不声称未探测候选已验证。
- 不运行 C4/C5，不改变 real sweep 审批门，不产生物理结论。
- Windows runtime catalog 位于 `%LOCALAPPDATA%\fdtd-mcp\object-library\`，不得提交 Git。

---

## File Structure

### 新建文件

- `src/object_library_catalog.py`
  - 安装身份、catalog 读写、枚举缓存、probe 记录。
- `src/analysis_group_selection.py`
  - intent 归一化、候选初筛/复评、参数确定性解析。
- `src/analysis_group_runtime.py`
  - lumapi bridge、共享操作门、隔离探测、官方 group 创建与验证服务。
- `tests/test_object_library_catalog.py`
  - catalog 生命周期和身份失效测试。
- `tests/test_analysis_group_selection.py`
  - intent、评分和参数解析纯函数测试。
- `tests/test_analysis_group_runtime.py`
  - probe、恢复、setup、回读和 fallback 测试。
- `scripts/windows/object_library_analysis_group_smoke.py`
  - 不求解的 Windows v242 manual smoke。
- `tests/test_object_library_smoke_static.py`
  - Windows smoke 静态契约。

### 修改文件

- `rpc_server.py`
  - SessionManager catalog 初始化/状态；AnalysisGroupService 注入；route/build 串接；共享操作门。
- `src/windows_fdtd_adapter.py`
  - 保留低层 custom/explicit 创建原语；新增 verified builtin 创建、删除和属性回读辅助。
- `src/device_recipe.py`
  - analysis intent schema；runtime instructions；base script；compile fingerprint。
- `src/rpc_client/client.py`
  - 扩展 analysis group request；使用正式 recipe build 方法。
- `src/tools/analysis_groups.py`
  - 透传 intent/context/overrides。
- `src/tools/recipes.py`
  - 修正 approved build 调用；返回 runtime execution report。
- `tests/test_rpc_server_contract.py`
- `tests/test_rpc_client_contract.py`
- `tests/test_mcp_analysis_group_tools.py`
- `tests/test_device_recipe.py`
- `tests/test_fdtd_20_step_fake_lumapi.py`
- `tests/test_mcp_stdio_acceptance.py`
- `tests/test_mcp_registration.py`
- `README.md`
- `AGENTS.md`
- `TECH_STACK.md`
- `docs/MCP_USER_GUIDE.md`
- `docs/FDTD_OPERATIONS_V1.md`
- `docs/DEVICE_RECIPE_V1.md`
- `docs/RPC_API_V1.md`
- `docs/WINDOWS_RUNBOOK.md`
- `src/knowledge/prompts/lumerical_analysis_groups.md`
- `DEV_LOG.md`
- `PITFALLS.md`
- `RETROSPECTIVE.md`

---

### Task 1: Version-bound Object Library catalog

**Files:**
- Create: `src/object_library_catalog.py`
- Create: `tests/test_object_library_catalog.py`

**Interfaces:**
- Produces: `resolve_object_library_root(environ: Mapping[str, str] | None = None) -> Path`
- Produces: `build_installation_identity(solver_version: str, python_executable: str, lumapi_file: str | None) -> dict`
- Produces: `identity_fingerprint(identity: dict) -> str`
- Produces: `ObjectLibraryCatalog(root: Path)`
- Produces: `ObjectLibraryCatalog.ensure(identity: dict, enumerate_ids: Callable[[], list[str]]) -> dict`
- Produces: `ObjectLibraryCatalog.get_probe(script_id: str) -> dict | None`
- Produces: `ObjectLibraryCatalog.put_probe(script_id: str, probe: dict) -> dict`
- Produces: `ObjectLibraryCatalog.summary() -> dict`

- [ ] **Step 1: Write failing catalog identity and cache tests**

```python
# tests/test_object_library_catalog.py
from pathlib import Path

from src.object_library_catalog import (
    ObjectLibraryCatalog,
    build_installation_identity,
    identity_fingerprint,
)


def identity(version="2024 R2.4", lumapi_sha="sha256:aaa"):
    return {
        "product": "FDTD",
        "solver_version": version,
        "path_version_tag": "v242",
        "lumapi_sha256": lumapi_sha,
    }


def test_same_identity_reuses_catalog_without_enumerating(tmp_path):
    calls = []
    store = ObjectLibraryCatalog(tmp_path)
    first = store.ensure(identity(), lambda: calls.append("enumerate") or ["box", "farfield"])
    second = store.ensure(identity(), lambda: calls.append("again") or ["wrong"])

    assert calls == ["enumerate"]
    assert first["script_ids"] == ["box", "farfield"]
    assert second["script_ids"] == ["box", "farfield"]
    assert second["catalog_cached"] is True


def test_version_or_lumapi_hash_change_creates_new_catalog(tmp_path):
    store = ObjectLibraryCatalog(tmp_path)
    store.ensure(identity(), lambda: ["v1"])
    changed = store.ensure(
        identity(version="2024 R2.5", lumapi_sha="sha256:bbb"),
        lambda: ["v2"],
    )

    assert changed["script_ids"] == ["v2"]
    assert len(list(tmp_path.glob("catalog-*.json"))) == 2


def test_unknown_version_requires_path_tag_and_lumapi_hash_for_disk_cache(tmp_path):
    unstable = {
        "product": "FDTD",
        "solver_version": "unknown",
        "path_version_tag": "",
        "lumapi_sha256": "",
    }
    calls = []
    store = ObjectLibraryCatalog(tmp_path)
    first = store.ensure(unstable, lambda: calls.append(1) or ["a"])
    second_store = ObjectLibraryCatalog(tmp_path)
    second = second_store.ensure(unstable, lambda: calls.append(2) or ["b"])

    assert calls == [1, 2]
    assert first["status"] == "identity_unstable"
    assert second["script_ids"] == ["b"]
    assert list(tmp_path.glob("catalog-*.json")) == []


def test_probe_records_are_atomic_and_version_scoped(tmp_path):
    store = ObjectLibraryCatalog(tmp_path)
    store.ensure(identity(), lambda: ["power_box"])
    store.put_probe("power_box", {
        "status": "verified_analysis_group",
        "setup_properties": [],
        "analysis_properties": [],
        "analysis_results": [{"name": "T", "type_code": 0}],
        "settable_properties": [],
        "probe_evidence": {},
    })

    assert store.get_probe("power_box")["analysis_results"][0]["name"] == "T"
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: Run the catalog tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_object_library_catalog.py -q
```

Expected: collection fails because `src.object_library_catalog` does not exist.

- [ ] **Step 3: Implement identity, atomic JSON storage, ensure, probe and summary**

```python
# src/object_library_catalog.py
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .fdtd_schema import fingerprint_json

CATALOG_SCHEMA_VERSION = "1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: str | None) -> str:
    if not path:
        return ""
    file = Path(path)
    if not file.is_file():
        return ""
    digest = hashlib.sha256()
    with file.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _path_version_tag(python_executable: str) -> str:
    for part in Path(python_executable).parts:
        if part.lower().startswith("v") and part[1:].isdigit():
            return part
    return ""


def resolve_object_library_root(
    environ: Mapping[str, str] | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    if env.get("STATE_ROOT"):
        return Path(env["STATE_ROOT"]) / "object-library"
    if env.get("LOCALAPPDATA"):
        return Path(env["LOCALAPPDATA"]) / "fdtd-mcp" / "object-library"
    return Path.cwd() / "runtime" / "object-library"


def build_installation_identity(
    solver_version: str,
    python_executable: str = sys.executable,
    lumapi_file: str | None = None,
) -> dict:
    return {
        "product": "FDTD",
        "solver_version": str(solver_version or "unknown"),
        "path_version_tag": _path_version_tag(python_executable),
        "lumapi_sha256": _sha256_file(lumapi_file),
    }


def identity_is_stable(identity: dict) -> bool:
    if identity.get("solver_version") not in {"", None, "unknown"}:
        return True
    return bool(identity.get("path_version_tag") and identity.get("lumapi_sha256"))


def identity_fingerprint(identity: dict) -> str:
    return fingerprint_json(identity)


class ObjectLibraryCatalog:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.Lock()
        self._catalog: dict | None = None
        self._path: Path | None = None

    def _write_atomic(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temp.replace(path)

    def ensure(
        self,
        identity: dict,
        enumerate_ids: Callable[[], list[str]],
    ) -> dict:
        with self._lock:
            stable = identity_is_stable(identity)
            fingerprint = identity_fingerprint(identity)
            path = self.root / f"catalog-{fingerprint.removeprefix('sha256:')}.json"
            if stable and path.is_file():
                self._catalog = json.loads(path.read_text(encoding="utf-8"))
                self._path = path
                return {**self._catalog, "catalog_cached": True}

            script_ids = sorted({str(item) for item in enumerate_ids() if str(item)})
            payload = {
                "schema_version": CATALOG_SCHEMA_VERSION,
                "installation_identity": identity,
                "identity": fingerprint,
                "status": "ready" if stable else "identity_unstable",
                "generated_at": _utc_now(),
                "script_ids": script_ids,
                "probes": {},
            }
            self._catalog = payload
            self._path = path if stable else None
            if stable:
                self._write_atomic(path, payload)
            return {**payload, "catalog_cached": False}

    def get_probe(self, script_id: str) -> dict | None:
        if self._catalog is None:
            return None
        return self._catalog.get("probes", {}).get(script_id)

    def put_probe(self, script_id: str, probe: dict) -> dict:
        if self._catalog is None:
            raise RuntimeError("Object Library catalog is not initialized.")
        self._catalog.setdefault("probes", {})[script_id] = {
            **probe,
            "probed_at": _utc_now(),
        }
        if self._path is not None:
            self._write_atomic(self._path, self._catalog)
        return self._catalog["probes"][script_id]

    def data(self) -> dict:
        return dict(self._catalog or {})

    def summary(self) -> dict:
        catalog = self._catalog or {}
        verified = sum(
            probe.get("status") == "verified_analysis_group"
            for probe in catalog.get("probes", {}).values()
        )
        return {
            "status": catalog.get("status", "unavailable"),
            "identity": catalog.get("identity", ""),
            "script_id_count": len(catalog.get("script_ids", [])),
            "verified_analysis_group_count": verified,
            "generated_at": catalog.get("generated_at"),
            "catalog_path": str(self._path) if self._path else None,
        }
```

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```zsh
.venv/bin/python -m pytest tests/test_object_library_catalog.py -q
```

Expected: all catalog tests pass.

- [ ] **Step 5: Commit Task 1**

```zsh
git add src/object_library_catalog.py tests/test_object_library_catalog.py
git commit -m "feat: add versioned object library catalog"
```

---

### Task 2: Enumerate catalog at session start and disclose status

**Files:**
- Modify: `rpc_server.py`
- Modify: `tests/test_rpc_server_contract.py`
- Modify: `src/tools/session.py`

**Interfaces:**
- Consumes: `ObjectLibraryCatalog.ensure(...)`
- Produces: `SessionManager.configure_object_library(catalog: ObjectLibraryCatalog) -> None`
- Produces: session start/status field `object_library`
- Produces: `_enumerate_object_library_ids(fdtd) -> list[str]`

- [ ] **Step 1: Write failing session catalog tests**

```python
# append to tests/test_rpc_server_contract.py
def test_session_start_enumerates_object_library_once(
    server_module, monkeypatch, tmp_path
):
    from src.object_library_catalog import ObjectLibraryCatalog

    class RawFdtd:
        def __init__(self):
            self.addobject_calls = 0

        def getversion(self):
            return "2024 R2.4"

        def addobject(self):
            self.addobject_calls += 1
            return ["power_box", "farfield_box"]

        def close(self):
            pass

    raw = RawFdtd()

    class FakeLumapi:
        __file__ = None

        @staticmethod
        def FDTD(hide=False):
            return raw

    manager = server_module.SessionManager()
    manager._fdtd = None
    manager.configure_object_library(ObjectLibraryCatalog(tmp_path))
    monkeypatch.setattr(server_module, "_import_lumapi", lambda: FakeLumapi)

    result = manager.start(hide=True)

    assert raw.addobject_calls == 1
    assert result["object_library"]["status"] in {"ready", "identity_unstable"}
    assert result["object_library"]["script_id_count"] == 2
    assert manager.status()["object_library"]["script_id_count"] == 2
    manager.close()


def test_catalog_enumeration_failure_keeps_session_active(
    server_module, monkeypatch, tmp_path
):
    from src.object_library_catalog import ObjectLibraryCatalog

    class RawFdtd:
        def getversion(self):
            return "2024 R2.4"

        def addobject(self):
            raise RuntimeError("library unavailable")

        def close(self):
            pass

    class FakeLumapi:
        __file__ = None

        @staticmethod
        def FDTD(hide=False):
            return RawFdtd()

    manager = server_module.SessionManager()
    manager._fdtd = None
    manager.configure_object_library(ObjectLibraryCatalog(tmp_path))
    monkeypatch.setattr(server_module, "_import_lumapi", lambda: FakeLumapi)

    result = manager.start()

    assert manager.is_connected is True
    assert result["object_library"]["status"] == "unavailable"
    assert (
        result["object_library"]["enumeration_error"]["type"]
        == "object_library_enumeration_failed"
    )
    manager.close()
```

- [ ] **Step 2: Run session tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest \
  tests/test_rpc_server_contract.py::test_session_start_enumerates_object_library_once \
  tests/test_rpc_server_contract.py::test_catalog_enumeration_failure_keeps_session_active \
  -q
```

Expected: fail because SessionManager has no catalog configuration/status.

- [ ] **Step 3: Wire catalog into SessionManager without making startup fatal**

Implement these exact additions:

```python
# rpc_server.py imports
from src.object_library_catalog import (
    ObjectLibraryCatalog,
    build_installation_identity,
    resolve_object_library_root,
)


class SessionManager:
    _object_library_catalog = None
    _object_library_status = {"status": "unavailable"}

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
```

In `start`, call `_initialize_object_library(lumapi, version)` only after FDTD construction succeeds and add the returned summary to the response. In `status`, include `object_library`; in `close`, retain disk catalog but reset session-visible status to catalog summary or `unavailable`.

In `create_app`, configure a default catalog only for real `SessionManager`; injected fake sessions remain untouched:

```python
if isinstance(session, SessionManager) and session._object_library_catalog is None:
    session.configure_object_library(
        ObjectLibraryCatalog(resolve_object_library_root())
    )
```

Update the `fdtd_session_start` docstring return example in `src/tools/session.py` to include `object_library`.

- [ ] **Step 4: Run session and existing contract tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_rpc_server_contract.py -q
```

Expected: all RPC server contract tests pass.

- [ ] **Step 5: Commit Task 2**

```zsh
git add rpc_server.py src/tools/session.py tests/test_rpc_server_contract.py
git commit -m "feat: initialize object library catalog with session"
```

---

### Task 3: Intent resolver and deterministic two-stage matcher

**Files:**
- Create: `src/analysis_group_selection.py`
- Create: `tests/test_analysis_group_selection.py`

**Interfaces:**
- Produces: `MATCH_POLICY_VERSION = "1.0"`
- Produces: `resolve_analysis_intent(explicit: dict | None, recipe_context: dict | None) -> dict`
- Produces: `shortlist_candidates(catalog: dict, intent: dict, context: dict, limit: int = 3) -> list[dict]`
- Produces: `rank_probed_candidates(candidates: list[dict], intent: dict, context: dict) -> list[dict]`
- Produces: `choose_high_confidence(ranked: list[dict]) -> dict | None`

- [ ] **Step 1: Write failing intent and matcher tests**

```python
# tests/test_analysis_group_selection.py
import pytest

from src.analysis_group_selection import (
    choose_high_confidence,
    rank_probed_candidates,
    resolve_analysis_intent,
    shortlist_candidates,
)


def test_explicit_intent_wins_over_context():
    result = resolve_analysis_intent(
        {"kind": "far_field", "outputs": ["directivity"]},
        {"outputs": ["T"], "monitors": [{"type": "power_monitor"}]},
    )
    assert result["kind"] == "far_field"
    assert result["source"] == "explicit"


def test_context_infers_transmission_from_output_and_power_monitor():
    result = resolve_analysis_intent(
        None,
        {
            "outputs": ["T"],
            "fom": {"result": "T"},
            "monitors": [{"type": "power_monitor", "name": "mon"}],
        },
    )
    assert result["kind"] == "transmission"
    assert result["source"] == "derived"
    assert "output:T" in result["evidence"]


def test_ambiguous_context_stays_unknown():
    result = resolve_analysis_intent(None, {"outputs": [], "monitors": []})
    assert result["kind"] == "unknown"


@pytest.mark.parametrize(
    ("output", "kind"),
    [
        ("absorbed_power", "absorption"),
        ("directivity", "far_field"),
        ("polarization_ellipse", "polarization"),
        ("effective_mode_area", "mode_area"),
        ("modal_volume", "modal_volume"),
        ("cw_movie", "movie"),
        ("net_power_flow", "net_power_flow"),
    ],
)
def test_context_derives_supported_intents_from_structured_outputs(output, kind):
    result = resolve_analysis_intent(
        None,
        {"outputs": [output], "fom": {"result": output}, "monitors": []},
    )
    assert result["kind"] == kind
    assert result["source"] == "derived"


def test_shortlist_uses_real_ids_and_is_deterministic():
    catalog = {
        "script_ids": [
            "farfield_projection_box",
            "power_transmission_box",
            "rounded_cylinder",
        ],
        "probes": {},
    }
    intent = {"kind": "transmission", "outputs": ["T"]}
    first = shortlist_candidates(catalog, intent, {}, limit=3)
    second = shortlist_candidates(catalog, intent, {}, limit=3)
    assert first == second
    assert [item["script_id"] for item in first] == ["power_transmission_box"]


def test_probe_evidence_reaches_high_confidence_gate():
    candidates = [{
        "script_id": "power_transmission_box",
        "probe": {
            "status": "verified_analysis_group",
            "setup_properties": [{"name": "x span", "type_code": 2}],
            "analysis_properties": [],
            "analysis_results": [{"name": "T", "type_code": 0}],
        },
    }]
    ranked = rank_probed_candidates(
        candidates,
        {"kind": "transmission", "outputs": ["T"]},
        {
            "monitors": [{"type": "power_monitor"}],
            "fom": {"result": "T"},
        },
    )
    assert ranked[0]["score"] == 0.85
    assert choose_high_confidence(ranked)["script_id"] == "power_transmission_box"


def test_small_gap_does_not_auto_select():
    assert choose_high_confidence([
        {"script_id": "a", "score": 0.90},
        {"script_id": "b", "score": 0.80},
    ]) is None
```

- [ ] **Step 2: Run selection tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_analysis_group_selection.py -q
```

Expected: collection fails because selection module does not exist.

- [ ] **Step 3: Implement explicit intent vocabulary and deterministic scoring**

```python
# src/analysis_group_selection.py
from __future__ import annotations

import re

MATCH_POLICY_VERSION = "1.0"
SHORTLIST_THRESHOLD = 0.35
AUTO_SELECT_THRESHOLD = 0.85
AUTO_SELECT_GAP = 0.15

VALID_INTENTS = {
    "transmission",
    "net_power_flow",
    "absorption",
    "far_field",
    "polarization",
    "mode_area",
    "modal_volume",
    "movie",
    "unknown",
}

INTENT_TOKENS = {
    "transmission": {"transmission", "power", "box"},
    "net_power_flow": {"power", "flow", "transmission", "box"},
    "absorption": {"absorption", "absorbed", "power"},
    "far_field": {"farfield", "far", "field", "projection", "directivity"},
    "polarization": {"polarization", "ellipse", "farfield"},
    "mode_area": {"mode", "area", "effective"},
    "modal_volume": {"modal", "mode", "volume", "cavity"},
    "movie": {"movie", "cw"},
    "unknown": set(),
}

OUTPUT_INTENTS = {
    "t": "transmission",
    "transmission": "transmission",
    "net_power_flow": "net_power_flow",
    "power_flow": "net_power_flow",
    "absorbed_power": "absorption",
    "absorption": "absorption",
    "directivity": "far_field",
    "far_field": "far_field",
    "farfield": "far_field",
    "polarization_ellipse": "polarization",
    "polarization": "polarization",
    "effective_mode_area": "mode_area",
    "mode_area": "mode_area",
    "modal_volume": "modal_volume",
    "cw_movie": "movie",
    "movie": "movie",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", str(value).lower())
        if token
    }


def resolve_analysis_intent(
    explicit: dict | None,
    recipe_context: dict | None,
) -> dict:
    context = recipe_context or {}
    if explicit:
        raw_kind = str(explicit.get("kind", "unknown"))
        kind = raw_kind if raw_kind in VALID_INTENTS else "unknown"
        return {
            **explicit,
            "kind": kind,
            "raw_kind": raw_kind,
            "outputs": list(explicit.get("outputs", [])),
            "source": "explicit",
            "evidence": [f"explicit:{raw_kind}"],
        }

    outputs = [str(item) for item in context.get("outputs", [])]
    monitor_types = {
        str(item.get("type", item.get("monitor_type", ""))).lower()
        for item in context.get("monitors", [])
        if isinstance(item, dict)
    }
    fom_result = str((context.get("fom") or {}).get("result", ""))
    evidence = []
    normalized_outputs = [
        re.sub(r"[^a-z0-9]+", "_", item.lower()).strip("_")
        for item in [*outputs, fom_result]
        if item
    ]
    derived_kinds = {
        OUTPUT_INTENTS[item]
        for item in normalized_outputs
        if item in OUTPUT_INTENTS
    }
    if len(derived_kinds) == 1:
        kind = next(iter(derived_kinds))
        evidence.extend(
            f"output:{item}"
            for item in normalized_outputs
            if OUTPUT_INTENTS.get(item) == kind
        )
        if kind == "transmission" and any("power" in item for item in monitor_types):
            evidence.append("monitor:power")
        return {
            "kind": kind,
            "outputs": outputs,
            "source": "derived",
            "evidence": evidence,
        }
    if ("T" in outputs or fom_result == "T") and not derived_kinds:
        evidence.append("output:T")
        if any("power" in item for item in monitor_types):
            evidence.append("monitor:power")
        return {
            "kind": "transmission",
            "outputs": outputs or ["T"],
            "source": "derived",
            "evidence": evidence,
        }
    return {
        "kind": "unknown",
        "outputs": outputs,
        "source": "derived",
        "evidence": [],
    }


def _base_score(script_id: str, intent: dict) -> tuple[float, list[str]]:
    wanted = INTENT_TOKENS[intent["kind"]]
    actual = _tokens(script_id)
    if not wanted or not (wanted & actual):
        return 0.0, []
    overlap = len(wanted & actual) / len(wanted)
    return round(0.45 * overlap, 12), [
        f"id_token:{token}" for token in sorted(wanted & actual)
    ]


def shortlist_candidates(
    catalog: dict,
    intent: dict,
    context: dict,
    limit: int = 3,
) -> list[dict]:
    candidates = []
    probes = catalog.get("probes", {})
    for script_id in catalog.get("script_ids", []):
        probe = probes.get(script_id)
        if probe and probe.get("status") == "not_analysis_group":
            continue
        score, reasons = _base_score(script_id, intent)
        if score >= SHORTLIST_THRESHOLD:
            candidates.append({
                "script_id": script_id,
                "score": score,
                "match_reasons": reasons,
                "probe": probe,
            })
    return sorted(
        candidates,
        key=lambda item: (-item["score"], item["script_id"].lower()),
    )[:limit]


def rank_probed_candidates(
    candidates: list[dict],
    intent: dict,
    context: dict,
) -> list[dict]:
    requested_outputs = {str(item) for item in intent.get("outputs", [])}
    fom_result = str((context.get("fom") or {}).get("result", ""))
    has_power_monitor = any(
        "power" in str(item.get("type", item.get("monitor_type", ""))).lower()
        for item in context.get("monitors", [])
        if isinstance(item, dict)
    )
    ranked = []
    for candidate in candidates:
        probe = candidate.get("probe") or {}
        if probe.get("status") != "verified_analysis_group":
            continue
        score, reasons = _base_score(candidate["script_id"], intent)
        result_names = {
            str(item.get("name"))
            for item in probe.get("analysis_results", [])
        }
        property_names = {
            str(item.get("name")).lower()
            for key in ("setup_properties", "analysis_properties")
            for item in probe.get(key, [])
        }
        if requested_outputs & result_names:
            score += 0.25
            reasons.append("result:" + sorted(requested_outputs & result_names)[0])
        intent_tokens = INTENT_TOKENS[intent["kind"]]
        if any(_tokens(name) & intent_tokens for name in property_names):
            score += 0.15
            reasons.append("parameter:intent_match")
        if has_power_monitor and intent["kind"] in {"transmission", "net_power_flow"}:
            score += 0.10
            reasons.append("monitor:power")
        if fom_result and fom_result in result_names:
            score += 0.05
            reasons.append(f"fom:{fom_result}")
        ranked.append({
            **candidate,
            "score": round(min(score, 1.0), 12),
            "match_reasons": reasons,
        })
    return sorted(
        ranked,
        key=lambda item: (-item["score"], item["script_id"].lower()),
    )


def choose_high_confidence(ranked: list[dict]) -> dict | None:
    if not ranked or ranked[0]["score"] < AUTO_SELECT_THRESHOLD:
        return None
    if len(ranked) > 1 and ranked[0]["score"] - ranked[1]["score"] < AUTO_SELECT_GAP:
        return None
    return ranked[0]
```

- [ ] **Step 4: Run selection tests to verify GREEN**

Run:

```zsh
.venv/bin/python -m pytest tests/test_analysis_group_selection.py -q
```

Expected: all intent and matcher tests pass.

- [ ] **Step 5: Commit Task 3**

```zsh
git add src/analysis_group_selection.py tests/test_analysis_group_selection.py
git commit -m "feat: add deterministic analysis group matcher"
```

---

### Task 4: Safe same-session candidate inspector

**Files:**
- Create: `src/analysis_group_runtime.py`
- Create: `tests/test_analysis_group_runtime.py`

**Interfaces:**
- Produces: `SessionOperationGate.acquire(kind: str, timeout: float = 5.0)`
- Produces: `LumapiBridge(session_or_backend: Any)`
- Produces: `AnalysisGroupInspector(bridge, catalog, work_root, operation_gate)`
- Produces: `AnalysisGroupInspector.inspect(script_id: str) -> dict`
- Consumes: `ObjectLibraryCatalog.put_probe`

- [ ] **Step 1: Write failing probe, restore and cache tests**

```python
# tests/test_analysis_group_runtime.py
from pathlib import Path

import pytest

from src.analysis_group_runtime import (
    AnalysisGroupInspector,
    AnalysisRuntimeError,
    LumapiBridge,
    SessionOperationGate,
)
from src.object_library_catalog import ObjectLibraryCatalog


class ProbeFdtd:
    def __init__(self):
        self.project = ["original"]
        self.saved = {}
        self.loaded = []
        self.selected = None
        self.properties = {"x span": 1e-6}
        self.layout = True
        self._model_file = "original.fsp"

    def layoutmode(self):
        return 1 if self.layout else 0

    def save(self, path):
        self.saved[str(path)] = list(self.project)
        self._model_file = str(path)

    def load(self, path):
        self.project = list(self.saved[str(path)])
        self.loaded.append(str(path))
        self._model_file = str(path)

    def newproject(self):
        self.project = []

    def addobject(self, script_id):
        self.project.append(script_id)
        self.selected = script_id

    def set(self, name, value):
        if name == "name":
            self.selected = value

    def queryuserprop(self, name):
        return {"name": ["x span"], "type": [2]}

    def queryanalysisprop(self, name):
        return {"name": ["make plots"], "type": [0]}

    def queryanalysisresult(self, name):
        return {"name": ["T"], "type": [0]}

    def getnamed(self, name, prop=None):
        return self.properties.get(prop)

    def querynamed(self, name):
        return "name\nx span"

    def ls(self):
        return list(self.project)


def ready_catalog(tmp_path):
    catalog = ObjectLibraryCatalog(tmp_path / "catalog")
    catalog.ensure(
        {
            "product": "FDTD",
            "solver_version": "2024 R2.4",
            "path_version_tag": "v242",
            "lumapi_sha256": "sha256:abc",
        },
        lambda: ["power_transmission_box"],
    )
    return catalog


def test_probe_restores_project_and_caches_schema(tmp_path):
    fdtd = ProbeFdtd()
    catalog = ready_catalog(tmp_path)
    inspector = AnalysisGroupInspector(
        LumapiBridge(fdtd),
        catalog,
        tmp_path / "work",
        SessionOperationGate(),
    )

    result = inspector.inspect("power_transmission_box")

    assert result["status"] == "verified_analysis_group"
    assert result["analysis_results"] == [{"name": "T", "type_code": 0}]
    assert result["probe_evidence"]["restore_verified"] is True
    assert fdtd.project == ["original"]
    assert fdtd._model_file == "original.fsp"
    assert catalog.get_probe("power_transmission_box")["status"] == "verified_analysis_group"


def test_cached_verified_probe_does_not_insert_again(tmp_path):
    fdtd = ProbeFdtd()
    catalog = ready_catalog(tmp_path)
    inspector = AnalysisGroupInspector(
        LumapiBridge(fdtd), catalog, tmp_path / "work", SessionOperationGate()
    )
    first = inspector.inspect("power_transmission_box")
    add_count = len([item for item in fdtd.saved])
    second = inspector.inspect("power_transmission_box")
    assert second == first
    assert len(fdtd.saved) == add_count


def test_restore_failure_stops_without_fallback(tmp_path):
    class BrokenRestore(ProbeFdtd):
        def load(self, path):
            raise RuntimeError("cannot restore")

    inspector = AnalysisGroupInspector(
        LumapiBridge(BrokenRestore()),
        ready_catalog(tmp_path),
        tmp_path / "work",
        SessionOperationGate(),
    )
    with pytest.raises(AnalysisRuntimeError) as exc:
        inspector.inspect("power_transmission_box")
    assert exc.value.error_type == "analysis_probe_restore_failed"


def test_probe_refuses_analysis_mode_without_switching_layout(tmp_path):
    fdtd = ProbeFdtd()
    fdtd.layout = False
    inspector = AnalysisGroupInspector(
        LumapiBridge(fdtd),
        ready_catalog(tmp_path),
        tmp_path / "work",
        SessionOperationGate(),
    )
    with pytest.raises(AnalysisRuntimeError) as exc:
        inspector.inspect("power_transmission_box")
    assert exc.value.error_type == "analysis_probe_unavailable"
    assert fdtd.saved == {}


def test_probe_failed_is_not_retried_in_same_inspector_session(tmp_path):
    class BrokenProbe(ProbeFdtd):
        def __init__(self):
            super().__init__()
            self.query_calls = 0

        def queryuserprop(self, name):
            self.query_calls += 1
            raise RuntimeError("temporary query failure")

    fdtd = BrokenProbe()
    inspector = AnalysisGroupInspector(
        LumapiBridge(fdtd),
        ready_catalog(tmp_path),
        tmp_path / "work",
        SessionOperationGate(),
    )
    first = inspector.inspect("power_transmission_box")
    second = inspector.inspect("power_transmission_box")
    assert first["status"] == "probe_failed"
    assert second == first
    assert fdtd.query_calls == 1


def test_probe_failed_can_retry_once_after_inspector_restart(tmp_path):
    class RecoveringProbe(ProbeFdtd):
        def __init__(self):
            super().__init__()
            self.fail = True

        def queryuserprop(self, name):
            if self.fail:
                raise RuntimeError("temporary query failure")
            return super().queryuserprop(name)

    fdtd = RecoveringProbe()
    catalog = ready_catalog(tmp_path)
    first = AnalysisGroupInspector(
        LumapiBridge(fdtd), catalog, tmp_path / "work1", SessionOperationGate()
    )
    assert first.inspect("power_transmission_box")["status"] == "probe_failed"
    fdtd.fail = False
    restarted = AnalysisGroupInspector(
        LumapiBridge(fdtd), catalog, tmp_path / "work2", SessionOperationGate()
    )
    assert (
        restarted.inspect("power_transmission_box")["status"]
        == "verified_analysis_group"
    )


def test_non_analysis_object_is_cached_without_retry(tmp_path):
    class StructureObject(ProbeFdtd):
        def queryanalysisprop(self, name):
            raise RuntimeError("not an analysis group")

    fdtd = StructureObject()
    inspector = AnalysisGroupInspector(
        LumapiBridge(fdtd),
        ready_catalog(tmp_path),
        tmp_path / "work",
        SessionOperationGate(),
    )
    first = inspector.inspect("power_transmission_box")
    second = inspector.inspect("power_transmission_box")
    assert first["status"] == "not_analysis_group"
    assert second == first


def test_operation_gate_allows_nested_probe_inside_recipe_build():
    gate = SessionOperationGate()
    with gate.acquire("recipe_build"):
        assert gate.active_kind == "recipe_build"
        with gate.acquire("analysis_probe"):
            assert gate.active_kind == "analysis_probe"
        assert gate.active_kind == "recipe_build"
    assert gate.active_kind is None
```

- [ ] **Step 2: Run runtime tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_analysis_group_runtime.py -q
```

Expected: collection fails because runtime module does not exist.

- [ ] **Step 3: Implement bridge, operation gate and isolated inspector**

Implement:

```python
# src/analysis_group_runtime.py
from __future__ import annotations

import shutil
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .fdtd_schema import fingerprint_json


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
        self.raw = getattr(session_or_backend, "fdtd", None) or session_or_backend

    def call(self, name: str, *args):
        method = getattr(self.raw, name, None)
        if not callable(method):
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
```

The implementation must not catch `analysis_probe_restore_failed` and continue. Keep the work directory path only in the structured error so a Windows user can inspect recovery evidence.

- [ ] **Step 4: Run runtime tests to verify GREEN**

Run:

```zsh
.venv/bin/python -m pytest tests/test_analysis_group_runtime.py -q
```

Expected: probe and restore tests pass.

- [ ] **Step 5: Commit Task 4**

```zsh
git add src/analysis_group_runtime.py tests/test_analysis_group_runtime.py
git commit -m "feat: add isolated analysis group probe"
```

---

### Task 5: Deterministic parameter resolver

**Files:**
- Modify: `src/analysis_group_selection.py`
- Modify: `tests/test_analysis_group_selection.py`

**Interfaces:**
- Produces: `normalize_property_type(type_code: int) -> str`
- Produces: `resolve_analysis_parameters(probe: dict, overrides: dict, recipe_context: dict) -> dict`
- Produces result keys: `applied`, `defaults_preserved`, `unresolved`, `sources`

- [ ] **Step 1: Write failing parameter priority and type tests**

```python
# append to tests/test_analysis_group_selection.py
from src.analysis_group_selection import (
    AnalysisSelectionError,
    resolve_analysis_parameters,
)


PROBE = {
    "setup_properties": [
        {"name": "x span", "type_code": 2, "default_value": 2e-6, "default_readable": True},
        {"name": "material", "type_code": 5, "default_value": "Si", "default_readable": True},
    ],
    "analysis_properties": [
        {"name": "make plots", "type_code": 0, "default_value": 1, "default_readable": True},
    ],
}


def test_override_beats_context_and_default():
    result = resolve_analysis_parameters(
        PROBE,
        {"x span": 4e-6},
        {"solver": {"x span": 3e-6}},
    )
    assert result["applied"]["x span"] == 4e-6
    assert result["sources"]["x span"] == "parameter_overrides"


def test_solver_span_is_used_when_unique_and_override_absent():
    result = resolve_analysis_parameters(
        PROBE,
        {},
        {"solver": {"x span": 3e-6}},
    )
    assert result["applied"]["x span"] == 3e-6
    assert result["defaults_preserved"]["material"] == "Si"


def test_unknown_override_is_rejected():
    with pytest.raises(AnalysisSelectionError) as exc:
        resolve_analysis_parameters(PROBE, {"not real": 1}, {})
    assert exc.value.error_type == "analysis_parameter_unknown"


def test_type_mismatch_is_rejected():
    with pytest.raises(AnalysisSelectionError) as exc:
        resolve_analysis_parameters(PROBE, {"x span": "wide"}, {})
    assert exc.value.error_type == "analysis_parameter_type_mismatch"
```

- [ ] **Step 2: Run parameter tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_analysis_group_selection.py -q
```

Expected: fail because parameter resolver symbols do not exist.

- [ ] **Step 3: Implement type normalization, aliases and priority**

Add:

```python
# src/analysis_group_selection.py
class AnalysisSelectionError(Exception):
    def __init__(
        self,
        error_type: str,
        message: str,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.details = details or {}


TYPE_NAMES = {
    0: "number",
    1: "string",
    2: "length",
    3: "time",
    4: "frequency",
    5: "material",
    6: "matrix",
}

PROPERTY_ALIASES = {
    "x span": ("x span", "x_span"),
    "y span": ("y span", "y_span"),
    "z span": ("z span", "z_span"),
    "wavelength start": ("wavelength start", "wavelength_start"),
    "wavelength stop": ("wavelength stop", "wavelength_stop"),
}


def normalize_property_type(type_code: int) -> str:
    return TYPE_NAMES.get(type_code, "unknown")


def _compatible(type_name: str, value) -> bool:
    if type_name in {"number", "length", "time", "frequency"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name in {"string", "material"}:
        return isinstance(value, str)
    if type_name == "matrix":
        return isinstance(value, list)
    return True


def _context_value(name: str, context: dict):
    aliases = PROPERTY_ALIASES.get(name, (name, name.replace(" ", "_")))
    containers = [
        context.get("explicit_properties", {}),
        context.get("solver", {}),
    ]
    for container in containers:
        for alias in aliases:
            if alias in container:
                return container[alias], "recipe_context"

    matching = []
    for section in ("monitors", "sources"):
        for item in context.get(section, []):
            props = item.get("properties", {}) if isinstance(item, dict) else {}
            for alias in aliases:
                if alias in props:
                    matching.append(props[alias])
    if len(matching) == 1:
        return matching[0], "recipe_context"
    return None, None


def resolve_analysis_parameters(
    probe: dict,
    overrides: dict,
    recipe_context: dict,
) -> dict:
    schema = {
        item["name"]: item
        for key in ("setup_properties", "analysis_properties")
        for item in probe.get(key, [])
    }
    unknown = sorted(set(overrides) - set(schema))
    if unknown:
        raise AnalysisSelectionError(
            "analysis_parameter_unknown",
            "parameter_overrides contains unknown analysis parameters.",
            {"parameters": unknown},
        )

    applied = {}
    defaults = {}
    unresolved = []
    sources = {}
    for name, item in schema.items():
        type_name = normalize_property_type(item.get("type_code", -1))
        if name in overrides:
            value = overrides[name]
            source = "parameter_overrides"
        else:
            value, source = _context_value(name, recipe_context)
        if source:
            if not _compatible(type_name, value):
                raise AnalysisSelectionError(
                    "analysis_parameter_type_mismatch",
                    f"Parameter {name!r} is incompatible with {type_name}.",
                    {"parameter": name, "type": type_name},
                )
            applied[name] = value
            sources[name] = source
        elif item.get("default_readable"):
            defaults[name] = item.get("default_value")
        else:
            unresolved.append({
                "name": name,
                "type": type_name,
                "reason": "no_unique_source_and_default_unreadable",
            })
    return {
        "applied": applied,
        "defaults_preserved": defaults,
        "unresolved": unresolved,
        "sources": sources,
    }
```

- [ ] **Step 4: Run selection suite to verify GREEN**

Run:

```zsh
.venv/bin/python -m pytest tests/test_analysis_group_selection.py -q
```

Expected: all matcher and parameter tests pass.

- [ ] **Step 5: Commit Task 5**

```zsh
git add src/analysis_group_selection.py tests/test_analysis_group_selection.py
git commit -m "feat: resolve analysis group parameters safely"
```

---

### Task 6: Runtime AnalysisGroupService, setup and fallback

**Files:**
- Modify: `src/analysis_group_runtime.py`
- Modify: `src/windows_fdtd_adapter.py`
- Modify: `tests/test_analysis_group_runtime.py`
- Modify: `tests/test_analysis_group_builtin.py`

**Interfaces:**
- Produces: `AnalysisGroupService(adapter, bridge, catalog, inspector)`
- Produces: `AnalysisGroupService.create(body: dict) -> dict`
- Produces: `WindowsFdtdAdapter.create_verified_builtin_analysis_group(...) -> dict`
- Produces: `WindowsFdtdAdapter.delete_named_object(name: str) -> None`
- Preserves: existing custom `analysis_group_create` behavior

- [ ] **Step 1: Write failing high-confidence, fallback and verification tests**

```python
# append to tests/test_analysis_group_runtime.py
from src.analysis_group_runtime import AnalysisGroupService
from src.windows_fdtd_adapter import WindowsFdtdAdapter


class BuildFdtd(ProbeFdtd):
    def __init__(self):
        super().__init__()
        self.runsetup_calls = []

    def setnamed(self, name, prop, value):
        self.properties[prop] = value

    def select(self, name):
        self.selected = name

    def runsetup(self):
        self.runsetup_calls.append(self.selected)

    def delete(self):
        if self.selected in self.project:
            self.project.remove(self.selected)

    def eval(self, script):
        if script.startswith("addanalysisgroup"):
            self.project.append("custom")


def service(tmp_path, fdtd=None):
    raw = fdtd or BuildFdtd()
    catalog = ready_catalog(tmp_path)
    inspector = AnalysisGroupInspector(
        LumapiBridge(raw), catalog, tmp_path / "work", SessionOperationGate()
    )
    return AnalysisGroupService(
        adapter=WindowsFdtdAdapter(raw),
        bridge=LumapiBridge(raw),
        catalog=catalog,
        inspector=inspector,
    ), raw


def test_service_selects_probes_configures_and_verifies_builtin(tmp_path):
    runtime, fdtd = service(tmp_path)
    result = runtime.create({
        "name": "power_analysis",
        "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
        "recipe_context": {
            "solver": {"x span": 3e-6},
            "monitors": [{"type": "power_monitor"}],
            "outputs": ["T"],
            "fom": {"result": "T"},
        },
        "parameter_overrides": {},
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "",
        "properties": {},
        "dry_run": False,
    })

    assert result["source"] == "builtin"
    assert result["script_id"] == "power_transmission_box"
    assert result["parameters"]["applied"]["x span"] == 3e-6
    assert result["setup_verified"] is True
    assert result["physical_conclusion"] is False
    assert fdtd.runsetup_calls == ["power_analysis"]


def test_low_confidence_falls_back_to_custom(tmp_path):
    runtime, _ = service(tmp_path)
    result = runtime.create({
        "name": "unknown_analysis",
        "analysis_intent": {"kind": "unknown", "outputs": []},
        "recipe_context": {},
        "parameter_overrides": {},
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "",
        "properties": {},
        "dry_run": False,
    })
    assert result["source"] == "custom"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "no_high_confidence_match"


def test_require_builtin_rejects_low_confidence(tmp_path):
    runtime, _ = service(tmp_path)
    with pytest.raises(AnalysisRuntimeError) as exc:
        runtime.create({
            "name": "required",
            "analysis_intent": {"kind": "unknown", "outputs": []},
            "recipe_context": {},
            "parameter_overrides": {},
            "prefer_builtin": False,
            "require_builtin": True,
            "script_id": "",
            "properties": {},
            "dry_run": False,
        })
    assert exc.value.error_type == "builtin_analysis_group_no_high_confidence_match"


def test_dry_run_never_executes_probe(tmp_path):
    runtime, fdtd = service(tmp_path)
    before = dict(fdtd.saved)
    result = runtime.create({
        "name": "power_analysis",
        "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
        "recipe_context": {"outputs": ["T"]},
        "parameter_overrides": {},
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "",
        "properties": {},
        "dry_run": True,
    })
    assert fdtd.saved == before
    assert result["probe_required"] is True
```

- [ ] **Step 2: Run runtime suite to verify RED**

Run:

```zsh
.venv/bin/python -m pytest \
  tests/test_analysis_group_runtime.py \
  tests/test_analysis_group_builtin.py \
  -q
```

Expected: fail because service and verified builder helpers do not exist.

- [ ] **Step 3: Add low-level verified builtin helpers to the adapter**

Add methods that do not choose candidates:

```python
# src/windows_fdtd_adapter.py
def create_verified_builtin_analysis_group(
    self,
    script_id: str,
    name: str,
) -> dict:
    script = _compile_builtin_analysis_group_script(script_id, name, {})
    self._backend.eval(script)
    return {"name": name, "source": "builtin", "script_id": script_id}


def delete_named_object(self, name: str) -> None:
    self._backend.eval(f'select({format_lsf_value(name)});\\ndelete;')
```

Keep current `analysis_group_create` for custom creation and backward-compatible adapter dry-run tests. Runtime catalog validation belongs to `AnalysisGroupService`, not the low-level adapter.

- [ ] **Step 4: Implement AnalysisGroupService**

Add to `src/analysis_group_runtime.py`:

```python
from .analysis_group_selection import (
    AnalysisSelectionError,
    choose_high_confidence,
    rank_probed_candidates,
    resolve_analysis_intent,
    resolve_analysis_parameters,
    shortlist_candidates,
)


class AnalysisGroupService:
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
```

The bridge contract is intentionally `runsetup(name)`, but its raw lumapi implementation is fixed to `select(name)` followed by parameterless `runsetup()`, matching the official script command. Lock this behavior with the Windows manual smoke in Task 10.

- [ ] **Step 5: Run runtime and legacy adapter tests to verify GREEN**

Run:

```zsh
.venv/bin/python -m pytest \
  tests/test_analysis_group_runtime.py \
  tests/test_analysis_group_builtin.py \
  -q
```

Expected: all tests pass and prior explicit-ID adapter behavior remains covered.

- [ ] **Step 6: Commit Task 6**

```zsh
git add \
  src/analysis_group_runtime.py \
  src/windows_fdtd_adapter.py \
  tests/test_analysis_group_runtime.py \
  tests/test_analysis_group_builtin.py
git commit -m "feat: create verified analysis groups at runtime"
```

---

### Task 7: RPC, RpcClient and MCP pass-through

**Files:**
- Modify: `rpc_server.py`
- Modify: `src/rpc_client/client.py`
- Modify: `src/tools/analysis_groups.py`
- Modify: `tests/test_rpc_server_contract.py`
- Modify: `tests/test_rpc_client_contract.py`
- Modify: `tests/test_mcp_analysis_group_tools.py`

**Interfaces:**
- Consumes: `AnalysisGroupService.create(body)`
- Extends: `RpcClient.analysis_group_create(..., analysis_intent, recipe_context, parameter_overrides)`
- Preserves: MCP tool name `fdtd_analysis_group_create`

- [ ] **Step 1: Write failing RPC route and pass-through tests**

Add an injectable service fake:

```python
# tests/test_rpc_server_contract.py
def test_analysis_group_route_passes_runtime_selection_fields(
    server_module, fake_session
):
    class FakeService:
        def __init__(self):
            self.body = None

        def create(self, body):
            self.body = body
            return {
                "name": body["name"],
                "source": "builtin",
                "script_id": "power_transmission_box",
                "physical_conclusion": False,
            }

    service = FakeService()
    app = server_module.create_app(
        fake_session,
        analysis_group_service=service,
    )
    response = app.test_client().post("/analysis-groups", json={
        "name": "power_analysis",
        "properties": {},
        "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
        "recipe_context": {"outputs": ["T"]},
        "parameter_overrides": {"x span": 2e-6},
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "",
        "dry_run": False,
    })

    assert response.status_code == 200
    assert service.body["analysis_intent"]["kind"] == "transmission"
    assert service.body["parameter_overrides"]["x span"] == 2e-6
```

Update the RpcClient parameterized case to expect:

```python
(
    "analysis_group_create",
    (
        "ag",
        {},
        True,
        True,
        False,
        "",
        {"kind": "transmission", "outputs": ["T"]},
        {"outputs": ["T"]},
        {"x span": 2e-6},
    ),
    "POST",
    "/analysis-groups",
    {
        "name": "ag",
        "properties": {},
        "dry_run": True,
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "",
        "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
        "recipe_context": {"outputs": ["T"]},
        "parameter_overrides": {"x span": 2e-6},
    },
)
```

Update the MCP fake signature and assertion so `fdtd_analysis_group_create` forwards all three new fields unchanged.

- [ ] **Step 2: Run contract tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest \
  tests/test_rpc_server_contract.py \
  tests/test_rpc_client_contract.py \
  tests/test_mcp_analysis_group_tools.py \
  -q
```

Expected: fail on missing create_app injection and missing client fields.

- [ ] **Step 3: Instantiate and inject AnalysisGroupService in create_app**

Extend the signature:

```python
def create_app(
    session_manager=None,
    job_store=None,
    sweep_runner=None,
    backend=None,
    object_library_catalog=None,
    analysis_group_service=None,
) -> Flask:
```

Build the default service only when not injected:

```python
catalog = object_library_catalog
if catalog is None and isinstance(session, SessionManager):
    catalog = session._object_library_catalog

operation_gate = SessionOperationGate()
if analysis_group_service is None and catalog is not None:
    bridge = LumapiBridge(backend if backend is not None else session)
    inspector = AnalysisGroupInspector(
        bridge,
        catalog,
        resolve_object_library_root() / "probe-work",
        operation_gate,
    )
    analysis_group_service = AnalysisGroupService(
        adapter, bridge, catalog, inspector
    )
```

Map `AnalysisRuntimeError` to the API v1 error envelope. Replace the route body with:

```python
if analysis_group_service is None:
    return _success(adapter.analysis_group_create(
        name=_required(data, "name"),
        properties=data.get("properties", {}),
        dry_run=data.get("dry_run", False),
        prefer_builtin=data.get("prefer_builtin", False),
        require_builtin=data.get("require_builtin", False),
        script_id=data.get("script_id", ""),
    ))
return _success(analysis_group_service.create({
    "name": _required(data, "name"),
    "properties": data.get("properties", {}),
    "analysis_intent": data.get("analysis_intent"),
    "recipe_context": data.get("recipe_context", {}),
    "parameter_overrides": data.get("parameter_overrides", {}),
    "prefer_builtin": data.get("prefer_builtin", False),
    "require_builtin": data.get("require_builtin", False),
    "script_id": data.get("script_id", ""),
    "dry_run": data.get("dry_run", False),
}))
```

Use the same `operation_gate` around `/simulation/run` and `/recipes/build` so probe, solve and build writes are mutually exclusive. Do not hold it around read-only status/results routes.

- [ ] **Step 4: Extend RpcClient and MCP wrapper**

Use this client signature:

```python
def analysis_group_create(
    self,
    name: str,
    properties: dict,
    dry_run: bool = False,
    prefer_builtin: bool = False,
    require_builtin: bool = False,
    script_id: str = "",
    analysis_intent: dict | None = None,
    recipe_context: dict | None = None,
    parameter_overrides: dict | None = None,
) -> dict:
    return self._post("/analysis-groups", {
        "name": name,
        "properties": properties,
        "dry_run": dry_run,
        "prefer_builtin": prefer_builtin,
        "require_builtin": require_builtin,
        "script_id": script_id,
        "analysis_intent": analysis_intent or {},
        "recipe_context": recipe_context or {},
        "parameter_overrides": parameter_overrides or {},
    })
```

Pass the same fields from `src/tools/analysis_groups.py`. Update its docstring to state that the MCP performs deterministic runtime matching and does not guess numeric parameters.

- [ ] **Step 5: Run contract tests and registry guard**

Run:

```zsh
.venv/bin/python -m pytest \
  tests/test_rpc_server_contract.py \
  tests/test_rpc_client_contract.py \
  tests/test_mcp_analysis_group_tools.py \
  tests/test_mcp_registration.py \
  -q
```

Expected: all pass; deliverable registry remains exactly 69 tools.

- [ ] **Step 6: Commit Task 7**

```zsh
git add \
  rpc_server.py \
  src/rpc_client/client.py \
  src/tools/analysis_groups.py \
  tests/test_rpc_server_contract.py \
  tests/test_rpc_client_contract.py \
  tests/test_mcp_analysis_group_tools.py
git commit -m "feat: expose autonomous analysis group selection"
```

---

### Task 8: DeviceRecipe runtime instructions and build execution fingerprint

**Files:**
- Modify: `src/device_recipe.py`
- Modify: `src/tools/recipes.py`
- Modify: `src/rpc_client/client.py`
- Modify: `rpc_server.py`
- Modify: `tests/test_device_recipe.py`
- Modify: `tests/test_rpc_server_contract.py`
- Modify: `tests/test_rpc_client_contract.py`
- Modify: `tests/test_mcp_stdio_acceptance.py`

**Interfaces:**
- Produces compile fields: `base_script`, `analysis_group_instructions`, `match_policy_version`
- Preserves compile alias: `script == base_script`
- Produces build fields: `analysis_groups`, `execution_fingerprint`, `manifest_path`
- Uses: `RpcClient.recipe_build(...)`

- [ ] **Step 1: Write failing Recipe normalization and compile split tests**

Replace the old “builtin compiles directly to addobject” expectation:

```python
# tests/test_device_recipe.py
def test_builtin_analysis_group_compiles_to_runtime_instruction():
    recipe = {
        **MINIMAL_RECIPE,
        "outputs": ["T"],
        "fom": {"result": "T"},
        "analysis_groups": [{
            "type": "analysis_group",
            "name": "analysis_builtin",
            "analysis_intent": {
                "kind": "transmission",
                "outputs": ["T"],
            },
            "prefer_builtin": True,
            "require_builtin": False,
            "script_id": "",
            "parameter_overrides": {"x span": "${pillar_radius} * 4"},
            "properties": {},
        }],
    }

    result = compile_recipe(recipe)

    assert result["ok"] is True
    assert "addobject(" not in result["base_script"]
    assert 'save("device_model")' not in result["base_script"]
    assert result["script"] == result["base_script"]
    assert result["analysis_group_instructions"] == [{
        "name": "analysis_builtin",
        "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "",
        "parameter_overrides": {"x span": 4e-7},
        "properties": {},
        "recipe_context": {
            "solver": {},
            "sources": [],
            "monitors": [],
            "outputs": ["T"],
            "fom": {"result": "T"},
        },
    }]
    assert result["match_policy_version"] == "1.0"


def test_custom_analysis_group_stays_in_base_script():
    recipe = {
        **MINIMAL_RECIPE,
        "analysis_groups": [{
            "type": "analysis_group",
            "name": "custom",
            "prefer_builtin": False,
            "require_builtin": False,
            "properties": {"x": 0},
        }],
    }
    result = compile_recipe(recipe)
    assert "addanalysisgroup;" in result["base_script"]
    assert result["analysis_group_instructions"] == []
```

- [ ] **Step 2: Run DeviceRecipe tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_device_recipe.py -q
```

Expected: fail because runtime instruction fields do not exist and addobject is still emitted.

- [ ] **Step 3: Add analysis-specific normalization and compile split**

Replace generic analysis normalization with:

```python
def _normalize_analysis_groups(items: Any, param_names: set) -> List[dict]:
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        intent = item.get("analysis_intent") or {}
        overrides = dict(item.get("parameter_overrides", {}))
        for name, value in overrides.items():
            if isinstance(value, str) and "${" in value:
                ast = parse_expression(value)
                _check_param_refs(ast, param_names)
        normalized.append({
            "type": item.get("type", "analysis_group"),
            "name": item.get("name", ""),
            "properties": dict(item.get("properties", {})),
            "analysis_intent": {
                "kind": intent.get("kind", "unknown"),
                "outputs": list(intent.get("outputs", [])),
                **{
                    key: intent[key]
                    for key in ("region_role", "direction")
                    if key in intent
                },
            },
            "prefer_builtin": bool(item.get("prefer_builtin", False)),
            "require_builtin": bool(item.get("require_builtin", False)),
            "script_id": str(item.get("script_id", "")),
            "parameter_overrides": overrides,
        })
    return normalized
```

Preserve top-level optional `outputs` and `fom` in `normalized_recipe`. During compile:

```python
runtime_instructions = []
custom_groups = []
for group in normalized.get("analysis_groups", []):
    runtime = bool(
        group.get("prefer_builtin")
        or group.get("require_builtin")
        or group.get("script_id")
    )
    if runtime:
        overrides = {
            name: (
                evaluate_expression(parse_expression(value), param_values)
                if isinstance(value, str) and "${" in value
                else value
            )
            for name, value in group.get("parameter_overrides", {}).items()
        }
        runtime_instructions.append({
            **group,
            "parameter_overrides": overrides,
            "recipe_context": {
                "solver": dict(normalized.get("solver", {})),
                "sources": normalized.get("sources", []),
                "monitors": normalized.get("monitors", []),
                "outputs": normalized.get("outputs", []),
                "fom": normalized.get("fom", {}),
            },
        })
    else:
        custom_groups.append(group)
```

Generate only `custom_groups` into `base_script`. Add `analysis_group_instructions` and `MATCH_POLICY_VERSION` to compile data before computing `compile_fingerprint`; return:

```python
{
    "script": base_script,
    "base_script": base_script,
    "analysis_group_instructions": runtime_instructions,
    "match_policy_version": MATCH_POLICY_VERSION,
    # existing fields unchanged
}
```

Remove the existing `# === Save Model ===` / `save("device_model")` section from the compiler. Saving is a Windows build responsibility after all runtime analysis instructions have succeeded. Keep `script` as a backward-compatible alias of `base_script`; neither field may save a model implicitly.

- [ ] **Step 4: Write failing runtime Recipe build test**

```python
# tests/test_rpc_server_contract.py
def test_recipe_build_executes_runtime_analysis_instructions(
    server_module, fake_session, tmp_path
):
    from src.device_recipe import compile_recipe

    recipe = {
        **MINIMAL_RECIPE,
        "outputs": ["T"],
        "analysis_groups": [{
            "type": "analysis_group",
            "name": "power_analysis",
            "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
            "prefer_builtin": True,
            "properties": {},
        }],
    }
    compiled = compile_recipe(recipe)

    class FakeService:
        def __init__(self):
            self.calls = []

        def create(self, body):
            self.calls.append(body)
            return {
                "name": body["name"],
                "source": "builtin",
                "script_id": "power_transmission_box",
                "parameters": {"applied": {}, "defaults_preserved": {}},
                "setup_verified": True,
                "physical_conclusion": False,
            }

    service = FakeService()
    output = tmp_path / "device.fsp"
    app = server_module.create_app(
        fake_session,
        analysis_group_service=service,
    )
    response = app.test_client().post("/recipes/build", json={
        "recipe": recipe,
        "compile_fingerprint": compiled["compile_fingerprint"],
        "output_fsp": str(output),
        "approved": True,
    })

    payload = response.get_json()
    assert response.status_code == 200
    assert len(service.calls) == 1
    assert payload["analysis_groups"][0]["source"] == "builtin"
    assert payload["execution_fingerprint"].startswith("sha256:")
    assert Path(payload["manifest_path"]).is_file()
```

- [ ] **Step 5: Run build test to verify RED**

Run:

```zsh
.venv/bin/python -m pytest \
  tests/test_device_recipe.py \
  tests/test_rpc_server_contract.py::test_recipe_build_executes_runtime_analysis_instructions \
  -q
```

Expected: compile tests pass after Step 3; runtime build test fails because build ignores instructions.

- [ ] **Step 6: Execute runtime instructions before final save and write manifest**

Refactor `/recipes/build`:

```python
compiled = compile_recipe(recipe)
# approval and compile fingerprint checks remain first
adapter.project_new(name=f"recipe_build_{Path(output_fsp).stem}", discard_unsaved=True)
session.eval(compiled["base_script"])

analysis_results = []
for instruction in compiled["analysis_group_instructions"]:
    if analysis_group_service is None:
        raise RpcError(
            "object_library_enumeration_failed",
            "Runtime analysis group selection is unavailable.",
            503,
        )
    analysis_results.append(
        analysis_group_service.create({
            **instruction,
            "dry_run": False,
        })
    )

save_result = session.save(str(output_fsp))
execution_data = {
    "compile_fingerprint": compiled["compile_fingerprint"],
    "analysis_groups": analysis_results,
}
execution_fingerprint = fingerprint_json(execution_data)
manifest_path = Path(str(output_fsp) + ".build.json")
manifest_path.write_text(
    json.dumps({
        "schema_version": "1.0",
        "model_path": str(output_fsp),
        "compile_fingerprint": compiled["compile_fingerprint"],
        "execution_fingerprint": execution_fingerprint,
        "analysis_groups": analysis_results,
        "physical_conclusion": False,
    }, indent=2, ensure_ascii=False, sort_keys=True),
    encoding="utf-8",
)
```

Return `analysis_groups`, `execution_fingerprint`, `manifest_path`. Ensure no save occurs if an instruction raises.

- [ ] **Step 7: Fix MCP build to call the typed RpcClient method**

Replace the nonexistent `rpc.call("device_recipe_build", ...)` path in `src/tools/recipes.py`:

```python
rpc_result = rpc.recipe_build(
    recipe=recipe,
    compile_fingerprint=compile_result["compile_fingerprint"],
    output_fsp=output_fsp,
    approved=True,
)
return {
    "ok": rpc_result.get("ok", False),
    "approved": True,
    "rpc_result": rpc_result,
    "compile_report": compile_result,
}
```

Update RpcClient contract and MCP stdio compile assertions for `base_script`, `analysis_group_instructions`, and `match_policy_version`. Do not add a new MCP tool.

- [ ] **Step 8: Run Recipe, RPC, client and stdio tests**

Run:

```zsh
.venv/bin/python -m pytest \
  tests/test_device_recipe.py \
  tests/test_rpc_server_contract.py \
  tests/test_rpc_client_contract.py \
  tests/test_mcp_stdio_acceptance.py \
  tests/test_mcp_registration.py \
  -q
```

Expected: all pass, exact tool count remains 69.

- [ ] **Step 9: Commit Task 8**

```zsh
git add \
  src/device_recipe.py \
  src/tools/recipes.py \
  src/rpc_client/client.py \
  rpc_server.py \
  tests/test_device_recipe.py \
  tests/test_rpc_server_contract.py \
  tests/test_rpc_client_contract.py \
  tests/test_mcp_stdio_acceptance.py
git commit -m "feat: resolve analysis groups during recipe build"
```

---

### Task 9: Fake-lumapi end-to-end autonomous selection

**Files:**
- Modify: `tests/test_fdtd_20_step_fake_lumapi.py`
- Modify: `tests/test_analysis_group_runtime.py`
- Modify: `tests/test_mcp_registration.py`

**Interfaces:**
- Fake backend supports the exact v242 calls used by catalog, inspector and builder.
- Acceptance proves `intent → enumerate → shortlist → probe → configure → runsetup → readback`.

- [ ] **Step 1: Extend FakeFdtdBackend with Object Library behavior**

Add state and methods:

```python
class FakeFdtdBackend:
    def __init__(self):
        # existing fields
        self._saved_projects = {}
        self._selected = None
        self._object_library = ["power_transmission_box", "rounded_cylinder"]
        self._analysis_defaults = {
            "power_transmission_box": {
                "x span": 2e-6,
                "make plots": 1,
            },
        }
        self.runsetup_calls = []

    def layoutmode(self):
        return 1

    def addobject(self, script_id=None):
        if script_id is None:
            return list(self._object_library)
        if script_id not in self._object_library:
            raise RuntimeError("unknown Object Library ID")
        self._objects[script_id] = {
            "object_type": "analysis_group",
            **self._analysis_defaults.get(script_id, {}),
        }
        self._selected = script_id

    def queryuserprop(self, name):
        return {"name": ["x span"], "type": [2]}

    def queryanalysisprop(self, name):
        return {"name": ["make plots"], "type": [0]}

    def queryanalysisresult(self, name):
        return {"name": ["T"], "type": [0]}

    def getnamed(self, name, prop):
        return self._objects[name].get(prop)

    def querynamed(self, name):
        return "name\\nx span\\nmake plots"

    def setnamed(self, name, prop, value):
        self._objects[name][prop] = value

    def set(self, prop, value):
        if prop == "name" and self._selected:
            self._objects[value] = self._objects.pop(self._selected)
            self._selected = value

    def select(self, name):
        self._selected = name

    def runsetup(self):
        self.runsetup_calls.append(self._selected)

    def save(self, path):
        import copy
        self._saved_projects[str(path)] = copy.deepcopy(self._objects)

    def load(self, path):
        import copy
        self._objects = copy.deepcopy(self._saved_projects[str(path)])

    def newproject(self):
        self._objects.clear()

    def ls(self):
        return list(self._objects)
```

If the adapter uses script-based addobject for final insertion, extend `_eval_impl` to parse `addobject("...")` and `select(...); delete;` consistently with these methods.

- [ ] **Step 2: Add an autonomous analysis group acceptance test**

```python
def test_autonomous_builtin_analysis_group_flow(
    server_module, fake_backend, tmp_path
):
    from src.analysis_group_runtime import (
        AnalysisGroupInspector,
        AnalysisGroupService,
        LumapiBridge,
        SessionOperationGate,
    )
    from src.object_library_catalog import ObjectLibraryCatalog
    from src.windows_fdtd_adapter import WindowsFdtdAdapter

    catalog = ObjectLibraryCatalog(tmp_path / "catalog")
    catalog.ensure(
        {
            "product": "FDTD",
            "solver_version": "2024 R2.4",
            "path_version_tag": "v242",
            "lumapi_sha256": "sha256:fake",
        },
        fake_backend.addobject,
    )
    bridge = LumapiBridge(fake_backend)
    service = AnalysisGroupService(
        WindowsFdtdAdapter(fake_backend),
        bridge,
        catalog,
        AnalysisGroupInspector(
            bridge, catalog, tmp_path / "probe", SessionOperationGate()
        ),
    )
    app = server_module.create_app(
        backend=fake_backend,
        object_library_catalog=catalog,
        analysis_group_service=service,
    )
    response = app.test_client().post("/analysis-groups", json={
        "name": "power_analysis",
        "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
        "recipe_context": {
            "solver": {"x span": 3e-6},
            "monitors": [{"type": "power_monitor"}],
            "outputs": ["T"],
            "fom": {"result": "T"},
        },
        "prefer_builtin": True,
        "parameter_overrides": {},
        "properties": {},
    })
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["source"] == "builtin"
    assert payload["script_id"] == "power_transmission_box"
    assert payload["parameters"]["verification"]["x span"]["matched"] is True
    assert fake_backend.runsetup_calls == ["power_analysis"]
```

- [ ] **Step 3: Run fake integration and registry tests**

Run:

```zsh
.venv/bin/python -m pytest \
  tests/test_fdtd_20_step_fake_lumapi.py \
  tests/test_analysis_group_runtime.py \
  tests/test_mcp_registration.py \
  -q
```

Expected: all pass, including the original 20-step flow and exact 69-tool registry.

- [ ] **Step 4: Commit Task 9**

```zsh
git add \
  tests/test_fdtd_20_step_fake_lumapi.py \
  tests/test_analysis_group_runtime.py \
  tests/test_mcp_registration.py
git commit -m "test: cover autonomous analysis group workflow"
```

---

### Task 10: Windows v242 smoke, documentation and final verification

**Files:**
- Create: `scripts/windows/object_library_analysis_group_smoke.py`
- Create: `tests/test_object_library_smoke_static.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `TECH_STACK.md`
- Modify: `docs/MCP_USER_GUIDE.md`
- Modify: `docs/FDTD_OPERATIONS_V1.md`
- Modify: `docs/DEVICE_RECIPE_V1.md`
- Modify: `docs/RPC_API_V1.md`
- Modify: `docs/WINDOWS_RUNBOOK.md`
- Modify: `src/knowledge/prompts/lumerical_analysis_groups.md`
- Modify: `DEV_LOG.md`
- Modify: `PITFALLS.md`
- Modify: `RETROSPECTIVE.md`

**Interfaces:**
- Produces Windows command:
  - `"F:\Program Files\Lumerical\v242\python\python.exe" scripts\windows\object_library_analysis_group_smoke.py --rpc http://127.0.0.1:5000 --output "%LOCALAPPDATA%\fdtd-mcp\object-library-smoke"`
- Produces report fields:
  - `technical_smoke`
  - `physical_conclusion`
  - `catalog_enumerated`
  - `probe_restore_verified`
  - `setup_verified`
  - `ok`

- [ ] **Step 1: Write failing static smoke tests**

```python
# tests/test_object_library_smoke_static.py
from pathlib import Path

SCRIPT = (
    Path(__file__).parent.parent
    / "scripts"
    / "windows"
    / "object_library_analysis_group_smoke.py"
)


def content():
    return SCRIPT.read_text(encoding="utf-8")


def test_smoke_is_non_solver_technical_evidence():
    text = content()
    assert '"technical_smoke": True' in text
    assert '"physical_conclusion": False' in text
    assert "/simulation/run" not in text
    assert "/jobs/start" not in text


def test_smoke_checks_catalog_probe_setup_and_restore():
    text = content()
    assert "/session/start" in text
    assert "/analysis-groups" in text
    assert '"prefer_builtin": True' in text
    assert '"require_builtin": True' in text
    assert '"catalog_enumerated"' in text
    assert '"probe_restore_verified"' in text
    assert '"setup_verified"' in text


def test_smoke_writes_fsp_and_json_report():
    text = content()
    assert "/project/save" in text
    assert "object_library_model.fsp" in text
    assert "object_library_smoke_report.json" in text
```

- [ ] **Step 2: Run smoke static tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_object_library_smoke_static.py -q
```

Expected: fail because the smoke script does not exist.

- [ ] **Step 3: Implement the Windows no-solve smoke**

The script must:

1. `GET /health`.
2. `POST /session/start` with `hide=true`.
3. Assert `object_library.script_id_count > 0`.
4. `POST /project/new`.
5. Create a minimal FDTD region, source and power monitor only if the chosen intent requires context; do not run solve.
6. Call `/analysis-groups` with:

```python
{
    "name": "object_library_smoke_analysis",
    "analysis_intent": {
        "kind": "transmission",
        "outputs": ["T"],
    },
    "recipe_context": {
        "solver": {
            "x span": 1.2e-6,
            "y span": 1.2e-6,
            "z span": 1.0e-6,
        },
        "monitors": [{"type": "power_monitor", "name": "mon"}],
        "outputs": ["T"],
        "fom": {"result": "T"},
    },
    "parameter_overrides": {},
    "prefer_builtin": True,
    "require_builtin": True,
    "script_id": "",
    "properties": {},
    "dry_run": False,
}
```

7. If v242 names do not produce a `transmission` shortlist, the script may accept `--intent-kind`, `--output-name`, and `--script-id` arguments. `--script-id` must still be verified against the live catalog by the RPC server.
8. Save `object_library_model.fsp`.
9. Write a report where:

```python
report["catalog_enumerated"] = (
    session_payload.get("object_library", {}).get("script_id_count", 0) > 0
)
report["probe_restore_verified"] = bool(
    analysis_payload.get("probe", {}).get("restore_verified")
)
report["setup_verified"] = bool(analysis_payload.get("setup_verified"))
report["ok"] = all((
    report["catalog_enumerated"],
    report["probe_restore_verified"],
    report["setup_verified"],
    analysis_payload.get("source") == "builtin",
))
```

10. Always label `physical_conclusion=False`; do not read or interpret a physical result.

- [ ] **Step 4: Run smoke static tests to verify GREEN**

Run:

```zsh
.venv/bin/python -m pytest tests/test_object_library_smoke_static.py -q
```

Expected: all static smoke tests pass.

- [ ] **Step 5: Update current-state documentation**

Make these exact state changes:

- `README.md`: change “requires verified caller-provided script_id” to “first session enumerates live v242 catalog; high-confidence intent matching probes and configures official groups; low confidence falls back”.
- `AGENTS.md`: retain “ID 不可猜测” and add “runtime selection must use current catalog/probe evidence”.
- `TECH_STACK.md`: add the three new internal modules and catalog path; keep tool count 69.
- `docs/MCP_USER_GUIDE.md`: document the `analysis_intent`, `recipe_context`, `parameter_overrides` request and decision report.
- `docs/FDTD_OPERATIONS_V1.md`: describe enumerate → shortlist → probe → configure → runsetup → readback.
- `docs/DEVICE_RECIPE_V1.md`: document runtime instructions and `execution_fingerprint`.
- `docs/RPC_API_V1.md`: document request fields, session catalog status and new error types.
- `docs/WINDOWS_RUNBOOK.md`: add the Windows manual smoke command and acceptance fields.
- `src/knowledge/prompts/lumerical_analysis_groups.md`: replace the “future recommended flow” section with the implemented behavior and retain official API sources.
- `DEV_LOG.md`: append dated implementation and verification commands.
- `PITFALLS.md`: record that unprobed candidates cannot reach final confidence from ID tokens alone, requiring two-stage scoring.
- `RETROSPECTIVE.md`: state that autonomous official-group selection is technically verified only after Windows smoke; do not claim physical validation.

- [ ] **Step 6: Run full offline verification**

Run:

```zsh
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
.venv/bin/python -m pytest -q
scripts/macos/install_mcp.sh --help
.venv/bin/python scripts/validate_parameter_file.py \
  --parameter-file tests/fixtures/synthetic_parameters.json
.venv/bin/python - <<'PY'
from src.server import collect_registered_tool_names_for_tests
names = collect_registered_tool_names_for_tests()
assert len(names) == 69
assert len(set(names)) == 69
print({"count": len(names), "unique": len(set(names))})
PY
git diff --check
git status --short
```

Expected:

- compileall exit 0.
- full pytest has 0 failures.
- installer help exit 0.
- parameter validation has `ok=true` and `physical_conclusion=false`.
- registry prints `count=69`, `unique=69`.
- `git diff --check` exit 0.
- only intended implementation/docs files appear before commit.

- [ ] **Step 7: Commit offline-complete implementation**

```zsh
git add \
  scripts/windows/object_library_analysis_group_smoke.py \
  tests/test_object_library_smoke_static.py \
  README.md AGENTS.md TECH_STACK.md \
  docs/MCP_USER_GUIDE.md \
  docs/FDTD_OPERATIONS_V1.md \
  docs/DEVICE_RECIPE_V1.md \
  docs/RPC_API_V1.md \
  docs/WINDOWS_RUNBOOK.md \
  src/knowledge/prompts/lumerical_analysis_groups.md \
  DEV_LOG.md PITFALLS.md RETROSPECTIVE.md
git commit -m "docs: deliver autonomous analysis group workflow"
```

- [ ] **Step 8: Run Windows v242 manual smoke**

Windows CMD:

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git pull --ff-only
scripts\windows\restart_rpc.bat
"F:\Program Files\Lumerical\v242\python\python.exe" scripts\windows\object_library_analysis_group_smoke.py --rpc http://127.0.0.1:5000 --output "%LOCALAPPDATA%\fdtd-mcp\object-library-smoke"
```

Expected report:

```json
{
  "technical_smoke": true,
  "physical_conclusion": false,
  "catalog_enumerated": true,
  "probe_restore_verified": true,
  "setup_verified": true,
  "ok": true
}
```

If no candidate passes because actual v242 IDs tokenize differently, inspect the returned catalog candidates and rerun with a live enumerated `--script-id`. Do not hard-code an unverified ID into the repository. Update only the deterministic token aliases needed to match actual v242 evidence, add a regression test, rerun full offline verification, and repeat this smoke.

- [ ] **Step 9: Record Windows evidence and final commit**

Append the date, commit, selected live `script_id`, catalog identity, report path and the five acceptance booleans to `DEV_LOG.md` and `RETROSPECTIVE.md`. Do not commit `%LOCALAPPDATA%` runtime JSON or `.fsp`.

```zsh
git add DEV_LOG.md RETROSPECTIVE.md
git commit -m "docs: record object library smoke"
git status --short
```

Expected: clean worktree.

---

## Final Requirement Traceability

| Spec requirement | Implemented by |
| --- | --- |
| First-session enumeration and version cache | Tasks 1–2 |
| Version/hash invalidation and unstable identity behavior | Task 1 |
| Explicit/derived intent | Task 3 |
| Deterministic shortlist and confidence gate | Task 3 |
| Same-session isolated probe and restore | Task 4 |
| Setup/Analysis/Result/default discovery | Task 4 |
| Safe parameter priority and type checks | Task 5 |
| `runsetup` and readback | Task 6 |
| fallback vs require behavior | Task 6 |
| RPC/MCP decision report | Task 7 |
| DeviceRecipe runtime resolution and fingerprints | Task 8 |
| Fake end-to-end workflow | Task 9 |
| 69-tool registry unchanged | Tasks 7–10 |
| Windows v242 no-solve smoke | Task 10 |
| Documentation and evidence boundary | Task 10 |
