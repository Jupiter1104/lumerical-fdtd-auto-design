# Official Analysis Group MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MCP/RPC analysis-group creation prefer Lumerical official Object Library analysis groups when a verified `script_id` is provided, with safe fallback to custom `addanalysisgroup`.

**Architecture:** Add a narrow typed extension to the existing `/analysis-groups` path. `WindowsFdtdAdapter.analysis_group_create` will choose `addobject("script_id")` only when `prefer_builtin` or `require_builtin` is requested and a `script_id` is supplied; otherwise it keeps the current `addanalysisgroup` behavior. MCP and `RpcClient` will pass the new fields through without guessing Object Library IDs.

**Tech Stack:** Python, Flask RPC API v1, FastMCP wrappers, pytest, existing fake lumapi backend.

## Global Constraints

- Mac side must not import `lumapi`.
- No real FDTD solve or sweep in this plan.
- Do not guess Object Library `script_id`; use only caller-provided or future enumerated IDs.
- `prefer_builtin=true` with no `script_id` falls back to custom `addanalysisgroup`.
- `require_builtin=true` with no `script_id` returns a clear validation error.
- Responses must disclose `source`, `script_id`, and `fallback_used`.

---

### Task 1: Adapter and RPC behavior

**Files:**
- Modify: `src/windows_fdtd_adapter.py`
- Modify: `rpc_server.py`
- Test: `tests/test_analysis_group_builtin.py`

**Interfaces:**
- Consumes: `analysis_group_create(name, properties, dry_run, prefer_builtin, require_builtin, script_id)`
- Produces: response fields `source`, `script_id`, `fallback_used`, and dry-run `script`

- [x] Write failing tests for custom fallback, builtin dry-run, and require-builtin missing ID.
- [x] Implement minimal adapter branch:
  - builtin: `addobject("script_id"); set("name","..."); ...`
  - fallback: existing `addanalysisgroup;`
  - require missing: `AdapterError("builtin_analysis_group_required", ...)`
- [x] Pass new request fields from `/analysis-groups` to adapter.
- [x] Run focused tests.

### Task 2: Mac client and MCP wrapper pass-through

**Files:**
- Modify: `src/rpc_client/client.py`
- Modify: `src/tools/analysis_groups.py`
- Test: `tests/test_rpc_client_contract.py`
- Test: `tests/test_mcp_analysis_group_tools.py`

**Interfaces:**
- Consumes: MCP body with `name`, `properties`, `dry_run`, `prefer_builtin`, `require_builtin`, `script_id`
- Produces: unchanged RPC API body

- [x] Write failing client contract test for new fields.
- [x] Write failing MCP wrapper test proving it extracts `name/properties/dry_run` instead of passing the whole body as `name`.
- [x] Implement minimal pass-through.
- [x] Run focused tests.

### Task 3: DeviceRecipe compilation hint

**Files:**
- Modify: `src/device_recipe.py`
- Test: `tests/test_device_recipe.py`
- Modify: `docs/DEVICE_RECIPE_V1.md`

**Interfaces:**
- Consumes: `analysis_groups[]` entries with optional `prefer_builtin`, `require_builtin`, `script_id`
- Produces: compiled script using `addobject` when `script_id` is present and builtin is preferred/required; otherwise custom group.

- [x] Write failing recipe compile test for builtin analysis group.
- [x] Preserve new optional fields in normalization.
- [x] Generate `addobject("script_id")` for builtin recipe entries.
- [x] Document the fields.
- [x] Run focused tests.

### Task 4: Verification and docs

**Files:**
- Modify: `DEV_LOG.md`
- Modify: `PITFALLS.md` if a new pitfall appears

- [x] Run `compileall`, full `pytest`, parameter validation, and `git diff --check`.
- [x] Commit implementation.
