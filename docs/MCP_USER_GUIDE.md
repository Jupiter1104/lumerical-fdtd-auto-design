# FDTD MCP 用户指南 v0.1.0

## 五分钟安装

### macOS

```bash
# 1. 进入项目目录
cd fdtd-auto-design

# 2. 运行安装脚本
bash scripts/macos/install_mcp.sh --rpc-url http://localhost:5000 --connection-mode ssh-tunnel
```

### Windows

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
scripts\windows\setup_rpc.bat -ConnectionMode ssh
scripts\windows\restart_rpc.bat
```

## 两种连接方式

### SSH 隧道（推荐）

```bash
# Mac 端建立隧道
ssh -L 5000:localhost:5000 32482@192.168.31.26

# 验证
curl http://localhost:5000/health
```

### 局域网直连

```cmd
# Windows 端使用 LAN 模式
scripts\windows\setup_rpc.bat -ConnectionMode lan
```

```bash
# Mac 端直连
export FDTD_RPC_URL=http://192.168.31.26:5000
curl $FDTD_RPC_URL/health
```

## 三客户端配置

安装脚本会自动配置以下客户端：

### Codex

配置文件写入 `[mcp_servers.fdtd]` TOML 块。

### Claude Code

更新 `.mcp.json`，保留已有 MCP Server，仅替换 `fdtd`：

```json
{
  "mcpServers": {
    "fdtd": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/fdtd-auto-design",
      "env": {
        "FDTD_RPC_URL": "http://localhost:5000"
      }
    }
  }
}
```

### Hermes

在 YAML 配置的 `toolsets` 中追加 `fdtd`。

## 69 个 MCP 工具

本版本提供 69 个 MCP 工具，覆盖完整 FDTD 操作闭环：

| 类别 | 工具数 | 工具 |
|------|--------|------|
| Session | 4 | fdtd_health, fdtd_session_start/pause/close |
| Project | 5 | fdtd_project_new/load/save/status, fdtd_switch_to_layout |
| Objects | 8 | fdtd_object_create/list/get/update/copy/rename/delete, fdtd_group_update |
| Materials | 6 | fdtd_material_create/list/get/update/assign/fit_diagnose |
| Solver | 6 | fdtd_solver_get/update, fdtd_mesh_diagnose, fdtd_resource_estimate, fdtd_simulation_run/status |
| Sources | 3 | fdtd_source_create/get/update |
| Monitors | 3 | fdtd_monitor_create/get/update |
| Analysis | 3 | fdtd_analysis_group_create/get/update；支持官方 Object Library `script_id` 优先 |
| Results | 4 | fdtd_result_list/describe/read, fdtd_results_download |
| Raw | 3 | fdtd_eval/getv/setv |
| Recipes | 3 | fdtd_device_recipe_validate/compile/build |
| Sweeps | 3 | fdtd_generic_sweep_validate/plan/start |
| Plans | 5 | fdtd_simulation_plan_validate/approve/start/real_preflight/production_preflight |
| Jobs | 7 | fdtd_job_plan/start/status/tasks/resume, fdtd_metasurface_sweep_plan/start |
| Export | 2 | fdtd_export_gds/export_data |
| Knowledge | 4 | fdtd_device_template, fdtd_list_devices, fdtd_troubleshoot, fdtd_best_practices |

## Analysis Group 官方库优先示例

通过 `analysis_intent` 描述分析目标，由系统自动枚举、匹配、探针、配置和验证官方 analysis group：

```json
{
  "name": "analysis_builtin",
  "analysis_intent": {
    "kind": "transmission",
    "outputs": ["T"]
  },
  "recipe_context": {
    "solver": {
      "x span": 1.2e-6,
      "y span": 1.2e-6,
      "z span": 1.0e-6
    },
    "monitors": [{"type": "power_monitor", "name": "mon"}],
    "outputs": ["T"],
    "fom": {"result": "T"}
  },
  "parameter_overrides": {},
  "prefer_builtin": true,
  "require_builtin": true,
  "script_id": "",
  "properties": {},
  "dry_run": false
}
```

### 决策流程

1. **enumerate**：首次 session 枚举 live v242 Object Library catalog，写入 `runtime/object_library_catalog.json`。
2. **shortlist**：`analysis_intent` + `recipe_context` 从 catalog 中产出确定性候选列表及置信度。
3. **probe**：高置信度候选通过只读探针获取真实 setup/analysis properties、results 和 settable 属性。
4. **configure**：`parameter_overrides` 安全合并到探针参数中，优先级：`parameter_overrides` > `recipe_context` > 探针默认值。
5. **runsetup**：运行 analysis group 的 setup script，获取实际返回值。
6. **readback**：`getnamed` 读回每个 applied 参数并比对预期值。

### 决策报告字段

响应包含 `source`（`"builtin"` 或 `"custom"`）、`script_id`、`match_confidence`、`match_reasons`、`probe.restore_verified`、`setup_verified`、`candidates`、`fallback_used`、`fallback_reason` 和 `physical_conclusion`（始终 `false`）。

`script_id` 必须来自 Ansys 官方文档或 Windows v242 `addobject;` 枚举。未提供 `script_id` 时由系统自动匹配；`prefer_builtin=true` 低置信度安全回退自定义 group；`require_builtin=true` 无可用官方候选时报错。

## 运行模式

| 模式 | 用途 | 调用求解器 |
|------|------|------------|
| `plan` | 校验、任务展开、成本预览 | 否 |
| `mock` | 验证软件链 | 否 |
| `real` | 真实求解 | 是（需审批） |

## 注意事项

- 所有 `plan`/`mock` 模式无需 Windows/Lumerical，可在 Mac 端离线运行
- `real` 模式需要 Windows 端 RPC Server 正常运行且获得明确批准
- 预计超过 30 秒的任务返回 `job_id`，通过飞书通知终态
- 未经批准不启动真实求解
