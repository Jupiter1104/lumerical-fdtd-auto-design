# 技术栈

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Mac (Agent 控制端)                                                      │
│                                                                          │
│  Claude Code / Hermes Agent                                              │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────┐                                             │
│  │  fdtd-mcp-server (Mac)  │  ← 本项目核心交付物（已实现）                │
│  │  - FastMCP 框架          │                                             │
│  │  - 光子学领域知识         │                                             │
│  │  - 扫参流水线控制         │                                             │
│  │  - 结果下载               │                                             │
│  └──────────┬──────────────┘                                             │
│             │  HTTP (requests) 或 SSH Tunnel                              │
└─────────────┼────────────────────────────────────────────────────────────┘
              │
┌─────────────┼────────────────────────────────────────────────────────────┐
│  Windows (仿真端)                                                         │
│             ▼                                                            │
│  ┌──────────────────────────┐                                            │
│  │  rpc_server.py (常驻)    │  ← 超表面扫参流水线                        │
│  │  - Flask HTTP API        │                                            │
│  │  - 4 阶段扫参引擎         │                                            │
│  │  - MATLAB Engine 后处理   │                                            │
│  │  - GUI/headless 双模式    │                                            │
│  └──────────┬───────────────┘                                            │
│             │  lumapi (v242 raw API)                                     │
│             ▼                                                            │
│  ┌──────────────────────────┐                                            │
│  │  Lumerical FDTD v242     │  ← headless (生产) / GUI (调试)            │
│  │  + MATLAB R2024b Engine  │                                            │
│  └──────────────────────────┘                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

## Windows 端（仿真引擎 + RPC 服务）

- OS：Windows 11（OpenSSH Server 已启用）
- **Python**：Lumerical v242 嵌入式 Python 3.9
  - 路径：`F:\Program Files\Lumerical\v242\python\python.exe`
  - API 路径：`F:\Program Files\Lumerical\v242\api\python`（通过 `sys.path.append` 导入）
- **Lumerical**：v242，raw `lumapi` 模块（非 PyLumerical）
- **MATLAB**：R2024b Engine for Python（保留给旧 baseline 和未来扩展；新原生 Phase 4 使用标准库 CSV/JSON/SVG）
- RPC 框架：**Flask**
- 依赖（安装在 Lumerical 自带 Python 中）：
  - `flask`：HTTP RPC 服务
  - `lumapi`：Lumerical Python API（路径注入，非 pip 安装）
  - `matlab.engine`：MATLAB Engine
  - `numpy`、`scipy`：数值计算 + `.mat` 输出

### 历史 Sweep RPC API

以下端点描述 Windows 上曾验证过的旧超表面 sweep baseline。新 `rpc_server.py` 不再桥接该服务；原生 `metasurface-sweep` 已纳入 API v1 `/jobs/start`。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 健康检查 → `{"ok":true, "fdtd_connected":bool, "matlab_connected":bool, "active_task":str}` |
| POST | `/session/start` | 启动 FDTD + MATLAB。body: `{"hide": bool}`（默认 false=GUI） |
| POST | `/session/close` | 关闭会话 |
| POST | `/session/pause` | 暂停供人工检查。body: `{"seconds": 300}` |
| POST | `/sweep/config` | 下发扫参配置（JSON body） |
| GET | `/sweep/config` | 读取当前配置 |
| POST | `/sweep/run` | 启动扫参。body: `{"phases": [1,2,3,4]}` → `{"ok":true, "task_id":"sweep_..."}` |
| GET | `/sweep/status?task_id=...` | 轮询进度 |
| GET | `/results` | 列出 results/ 和 figures/ 目录 |
| GET | `/results/<path>` | 下载结果文件 |

该 baseline 返回格式为 `{"ok": true/false, ...}`。它仅作为历史参考，不是当前 v1 运行时依赖。

### RPC API v1 契约

仓库内 API v1 已冻结并由离线测试覆盖：

- 成功统一返回 `{"ok": true, ...}`。
- 失败统一返回 `{"ok": false, "error": {"type": str, "message": str, "details": {}}}`。
- 参数错误使用 HTTP 400，无活动/重复会话使用 409，文件不存在使用 404，未处理后端异常使用 500。
- HTTP 超时返回 `timeout` 且标记 `remote_state=unknown`，不等于远端仿真失败。
- `lumapi` 延迟到 `/session/start` 时导入，因此 Mac 可在无 Lumerical 环境运行契约测试。
- raw v242 没有 `fdtd.getversion()` Python 方法，版本读取通过 script command `getversion` 兼容。
- raw lumapi `fdtd.close()` 可能在窗口关闭后不返回；`/session/close` 先摘除 RPC 会话，再后台关闭后端，超时返回 `close_state=timed_out`。
- `/jobs/*` v1 已实现：plan、start、status、tasks、resume；支持 `geometry-smoke` 和逐 sample `metasurface-sweep`。真实 `metasurface-sweep` 由新服务内的 `NativeSweepRunner` 异步执行。
- metasurface 模板通过 `scripts\windows\install_metasurface_template.bat` 安装到 `templates\metasurface\base_model.fsp`；每个真实 sweep 的 `manifest.json` 记录模板绝对路径、大小、mtime 和 SHA-256。
- 旧 `/session/stop`、`/sim/*`、`/geom/*` 等路由仅在 Server 端作为弃用别名保留；Client/MCP 只调用 v1。
- 文件参数限制到 Windows workspace/job root 仍需后续强化；当前通用 model 端点仍需受控网络环境。
- 通用 `/debug/eval` 仅作为调试入口，不作为默认自然语言建模入口。

已实现与下一阶段预留的高层端点分组：

```text
/session/*          会话和 GUI/headless 生命周期
/model/*            保存、加载、版本化模型
/geometry/*         typed 几何和仿真对象
/debug/*            受审计的 eval/getv/setv 调试入口
/simulation/*       当前模型的短 smoke 运行和结果读取
/jobs/plan          创建 planned job，落盘 task 清单但不执行
/jobs/start         创建并执行 geometry-smoke 或 metasurface-sweep job
/jobs/<id>          读取 manifest/status/summary
/jobs/<id>/tasks    读取 task 摘要
/jobs/<id>/resume   仅重试 pending/failed task
```

### 持久 Job/Task 数据模型

长任务状态必须写入磁盘，不能只依赖 Flask 线程内存：

```text
jobs/<job_id>/
├── manifest.json         # 软件版本、代码版本、模板和依赖
├── status.json           # 当前阶段和轻量进度
├── summary.json          # 完成数、失败数、缺失数、结果索引
├── run.log
├── inputs/
│   └── request.json      # 原始请求快照
├── tasks/
│   └── <task_id>.json    # 参数、状态、时间、错误、结果路径
├── models/
├── results/
└── evidence/
```

`resume` 只跳过已有完整结果的 task；任何 mesh、boundary、FOM 或参数范围变化都必须创建新 job 或新 plan revision。

### 运行模式和审批

| 模式 | 是否调用求解器 | 用途 | 可否作为物理证据 |
|---|---:|---|---:|
| `plan` | 否 | schema 校验、任务展开、成本和覆盖风险预览 | 否 |
| `mock` | 否或使用合成结果 | 验证 RPC、状态机、后处理和报告链 | 否 |
| `real` | 是 | 真实 sweep、优化或整器件验证 | 通过质量门和人工审核后才可 |

`real` 前必须生成审批摘要，至少包含 config/model、job 目录、总任务数或最大迭代数、GUI 状态、scheduler、资源、输出覆盖风险和预期结果。

## Mac 端（fdtd-mcp-server）

- OS：macOS（Apple Silicon）
- 语言：Python 3.10+
- **不安装 Lumerical，不依赖 `lumapi`。**
- MCP 框架：**FastMCP**（`mcp.server.fastmcp`）
- 依赖：
  - `mcp>=1.0.0`：MCP 协议
  - `requests`：HTTP 客户端，调用 Windows RPC
  - `numpy`、`matplotlib`、`pandas`：本地数据分析与可视化

### 实际文件结构

```
src/
├── server.py              # FastMCP 入口
├── tools/
│   ├── session.py         # fdtd_health, fdtd_session_start/close/pause
│   ├── model.py           # fdtd_save, fdtd_load
│   ├── geometry.py        # FDTD region, rectangle, circle
│   ├── simulation.py      # fdtd_sweep_config_get/set, fdtd_sweep_run/status/monitor
│   ├── analysis.py        # fdtd_results_list, fdtd_results_download
│   └── export_.py         # GDS/data export
├── knowledge/
│   ├── embedded.py        # 器件模板 + 故障排除 + 最佳实践
│   └── prompts/
│       ├── lumerical_api.md   # Lumerical API 速查
│       └── workflow.md        # 仿真工作流指南
└── rpc_client/
    └── client.py          # Windows RPC HTTP 客户端
scripts/
└── smoke_test.py          # 7 步端到端验证
tests/
├── test_rpc_server_contract.py
├── test_rpc_client_contract.py
├── test_mcp_registration.py
└── test_v1_smoke.py
rpc_server.py              # ← 本文件在 Windows 端，Mac 端不运行
```

### MCP 工具一览（22 个）

| 模块 | 工具 |
|---|---|
| Session | `fdtd_health`, `fdtd_session_start(hide)`, `fdtd_session_pause(seconds)`, `fdtd_session_close` |
| Model | `fdtd_save`, `fdtd_load` |
| Geometry | `fdtd_add_fdtd_region`, `fdtd_add_rect`, `fdtd_add_circle` |
| Sweep | `fdtd_sweep_config_get`, `fdtd_sweep_config_set(...)`, `fdtd_sweep_run(phases)`, `fdtd_sweep_status(task_id)`, `fdtd_sweep_monitor(task_id)` |
| Results | `fdtd_results_list`, `fdtd_results_download(filepath)` |
| Export | `fdtd_export_gds`, `fdtd_export_data` |
| Knowledge | `fdtd_device_template`, `fdtd_list_devices`, `fdtd_troubleshoot`, `fdtd_best_practices` |

`model.py`、`geometry.py` 和 `export_.py` 已完成注册。离线验证命令：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

过渡期限制：新 API v1 默认仍在 `5004` 开发验证；真实 2×2 原生 sweep 通过后再切默认端口到 `5000`。

## 连接方式

```bash
# === 新 v1 smoke / 通用建模 / 原生 sweep（在 Windows 本机） ===
set FDTD_RPC_URL=http://127.0.0.1:5004

# === SSH 隧道 ===
ssh -L 5004:localhost:5004 32482@192.168.31.26
export FDTD_RPC_URL=http://localhost:5004
```

## 命令

```bash
# === Windows 端 ===

# 安装依赖
F:\Program Files\Lumerical\v242\python\python.exe -m pip install flask numpy scipy

# 新 v1 服务：Windows 本地双击或命令行
scripts\windows\restart_rpc.bat

# 安装 metasurface 模板（一次性数据迁移；不是运行时旧项目依赖）
scripts\windows\install_metasurface_template.bat "E:\CLAUDE_workspace\Lumerical_autosweep\base_model.fsp"

# 新 v1 smoke：不求解，只打开 GUI、建最小模型、保存 .fsp、关闭
F:\Program Files\Lumerical\v242\python\python.exe scripts\v1_smoke_test.py

# === Mac 端 ===

# 安装依赖
pip install mcp requests

# 新 v1 smoke 可通过 SSH 隧道触发，但 GUI 可见性取决于 Windows 桌面/RDP 会话
python scripts/v1_smoke_test.py --rpc http://localhost:5004

# 启动 MCP Server（供 Claude Code / Hermes 调用）
FDTD_RPC_URL=http://localhost:5004 python -m src.server
```

## 环境变量

| 变量 | 位置 | 说明 |
|---|---|---|
| `FDTD_RPC_URL` | Mac | Windows RPC Server 地址 |
| `FDTD_PYTHON` | Windows | 管理脚本使用的 Lumerical Python，默认 `F:\Program Files\Lumerical\v242\python\python.exe` |
| `FDTD_RPC_PORT` | Windows | 新 v1 服务端口，默认 `5004` |
| `LUMAPI_PATH` | Windows | raw lumapi API 路径覆盖；默认从 Lumerical Python 相对路径推断 |

## 关键约束

- **双模式**：`hide=False` (GUI 调试) / `hide=True` (headless 批量)。RDP 断开时 GUI 模式可能无法创建窗口。
- **express mode 必须匹配 resource**：CPU 模板/CPU resource 使用 `express mode=0`；GPU 才使用 `express mode=1`。`NativeSweepRunner` 在每次 `load()` 后、`save()` 前按 `EXPRESS_MODE` 设置，避免模板 load 覆盖运行时设置。
- **脏会话清理**：每次 sweep 前 `fdtd.clearjobs()` 清理前次遗留作业队列。
- **单实例**：FDTD 单机 license，RPC Server 为互斥点。
- **文件路径**：Windows 路径必须正斜杠（C++ 层要求）。仿真结果在 Windows 端，通过 HTTP 下载回 Mac。
- **异步长任务**：求解请求只负责启动并返回 ID；状态轮询默认返回摘要和短日志尾部。
- **证据优先**：默认下载 JSON/CSV/NPZ/MAT、关键图和最终 `.fsp`，不默认下载全部逐点模型。
- **完成不等于通过**：solver 状态、数据完整性、数值质量和人工物理审核是不同层级。
