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
- **MATLAB**：R2024b Engine for Python（Phase 4 后处理热力图）
- RPC 框架：**Flask**
- 依赖（安装在 Lumerical 自带 Python 中）：
  - `flask`：HTTP RPC 服务
  - `lumapi`：Lumerical Python API（路径注入，非 pip 安装）
  - `matlab.engine`：MATLAB Engine
  - `numpy`、`scipy`：数值计算 + `.mat` 输出

### RPC API 端点

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

返回格式统一为 `{"ok": true/false, ...}`。

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
│   ├── simulation.py      # fdtd_sweep_config_get/set, fdtd_sweep_run/status/monitor
│   └── analysis.py        # fdtd_results_list, fdtd_results_download
├── knowledge/
│   ├── embedded.py        # 器件模板 + 故障排除 + 最佳实践
│   └── prompts/
│       ├── lumerical_api.md   # Lumerical API 速查
│       └── workflow.md        # 仿真工作流指南
└── rpc_client/
    └── client.py          # Windows RPC HTTP 客户端
scripts/
└── smoke_test.py          # 7 步端到端验证
rpc_server.py              # ← 本文件在 Windows 端，Mac 端不运行
```

### MCP 工具一览（15 个）

| 模块 | 工具 |
|---|---|
| Session | `fdtd_health`, `fdtd_session_start(hide)`, `fdtd_session_pause(seconds)`, `fdtd_session_close` |
| Sweep | `fdtd_sweep_config_get`, `fdtd_sweep_config_set(...)`, `fdtd_sweep_run(phases)`, `fdtd_sweep_status(task_id)`, `fdtd_sweep_monitor(task_id)` |
| Results | `fdtd_results_list`, `fdtd_results_download(filepath)` |
| Knowledge | `fdtd_device_template`, `fdtd_list_devices`, `fdtd_troubleshoot`, `fdtd_best_practices` |

## 连接方式

```bash
# === 同局域网直连 ===
export FDTD_RPC_URL=http://192.168.31.26:5003

# === SSH 隧道（推荐，更安全） ===
ssh -L 5003:localhost:5003 32482@192.168.31.26
export FDTD_RPC_URL=http://localhost:5003
```

## 命令

```bash
# === Windows 端 ===

# 安装依赖
F:\Program Files\Lumerical\v242\python\python.exe -m pip install flask numpy scipy

# 启动 RPC Server
F:\Program Files\Lumerical\v242\python\python.exe rpc_server.py --port 5003

# === Mac 端 ===

# 安装依赖
pip install mcp requests

# 运行 smoke test
python scripts/smoke_test.py --rpc http://localhost:5003

# 启动 MCP Server（供 Claude Code / Hermes 调用）
FDTD_RPC_URL=http://localhost:5003 python -m src.server
```

## 环境变量

| 变量 | 位置 | 说明 |
|---|---|---|
| `FDTD_RPC_URL` | Mac | Windows RPC Server 地址 |
| `LUMAPI_PATH` | Windows | Lumerical API 路径（硬编码在 rpc_server.py 顶部） |

## 关键约束

- **双模式**：`hide=False` (GUI 调试) / `hide=True` (headless 批量)。RDP 断开时 GUI 模式可能无法创建窗口。
- **Headless 必开 express mode**：`fdtd.setnamed("FDTD", "express mode", 1)` 必须在每次 `load()` 后、`save()` 前设置，模板 load 会覆盖。
- **脏会话清理**：每次 sweep 前 `fdtd.clearjobs()` 清理前次遗留作业队列。
- **单实例**：FDTD 单机 license，RPC Server 为互斥点。
- **文件路径**：Windows 路径必须正斜杠（C++ 层要求）。仿真结果在 Windows 端，通过 HTTP 下载回 Mac。
