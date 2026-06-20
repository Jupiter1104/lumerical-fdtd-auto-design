# 可交付个人 FDTD MCP 设计

## 决策

将现有项目收敛为一套可重复部署、可切换 Windows 工作站、可被 Codex、Claude Code 和 Hermes 使用的个人 FDTD MCP。

首版交付采用仓库原生双端部署：

- Mac 运行 MCP Server。
- Windows 运行 RPC Server 和 Lumerical FDTD。
- 项目目录可通过 ToDesk 传输，不依赖 Git、PyPI 或容器。
- 一个 MCP 进程只连接一台 Windows；切换电脑时修改 `FDTD_RPC_URL` 并重启 MCP。
- 交付验收只验证安装、协议、工具、参数传递和 mock 持久作业，不要求真实物理仿真。

## 背景

当前项目已经具备 API v1、Mac `RpcClient`、FastMCP 工具、SimulationPlan、审批、持久 job/task、结果下载、质量报告和飞书通知。现阶段缺口不是仿真物理结果，而是把已有能力收敛成一套个人可以在当前 Windows 和实验室 Windows 工作站之间迁移的 MCP 交付物。

用户已经拥有可覆盖 2π 的参数集。该参数集是 MCP 的输入数据，不是本项目要重新发现或验证的物理成果。项目开发不得以 C4/C5 真实 sweep、2π phase library 或器件优化结果作为 MCP 交付前置条件。

## 目标

1. 在 Mac 上通过一个安装命令创建运行环境，并生成 Codex、Claude Code、Hermes 三种 MCP 配置。
2. 在任意满足环境要求的 Windows 工作站上，通过首次配置完成 RPC 部署，此后可双击启动、停止、查询和重启。
3. 支持 SSH 隧道和可信局域网直连，两种模式只通过 `FDTD_RPC_URL` 区分。
4. 默认暴露精简的 API v1 MCP 工具面，并默认开放 raw Lumerical `eval/getv/setv` 高级能力。
5. 使用 MCP stdio 协议、health、SimulationPlan 参数传递和 mock job 完成交付验收，不启动真实 FDTD 求解。
6. 项目目录被 ToDesk 覆盖更新时，Windows 本机配置、日志、PID 和持久 job 不丢失。

## 非目标

- 不在本阶段运行 C4/C5 真实 sweep。
- 不判断用户参数是否真的覆盖 2π，也不验证器件物理正确性。
- 不支持一台 MCP 同时连接多台 Windows。
- 不在 MCP 运行中动态切换 Windows。
- 不支持 Linux、Slurm、集群队列或多机调度。
- 不发布 PyPI 包，不制作 macOS App，不制作 Windows 安装程序。
- 不提供公网暴露、API Key、TLS 或多用户认证。
- 不保证非 Lumerical v242 版本兼容。
- 不开发 Codex、Claude Code 或 Hermes 专属业务逻辑；三者共享同一个 stdio MCP Server。

## 总体架构

```text
Codex / Claude Code / Hermes
            │ MCP stdio
            ▼
Mac FDTD MCP Server
  ├─ Session / Model / Geometry
  ├─ Debug: eval / getv / setv
  ├─ SimulationPlan / Approval
  ├─ Persistent Job / Results
  └─ Knowledge
            │ HTTP API v1
            ▼
当前 Windows 或实验室 Windows
  ├─ RPC Server
  ├─ Persistent JobStore
  ├─ raw lumapi
  └─ Lumerical FDTD v242
```

### 组件边界

#### Mac MCP Server

- 是 Codex、Claude Code 和 Hermes 的唯一 Agent 入口。
- 通过 stdio 提供 MCP，不开放额外 HTTP MCP 端口。
- 不导入 `lumapi`，不直接读取 Windows 文件系统。
- 启动时只读取一个 `FDTD_RPC_URL`。
- Windows 离线时仍允许 MCP 进程启动和列出工具；具体工具调用返回结构化连接错误。

#### Windows RPC Server

- 是 Lumerical FDTD 的唯一执行入口。
- 使用 Lumerical v242 自带 Python 和 raw `lumapi`。
- 继续提供 HTTP API v1、持久 JobStore、结果文件和飞书通知。
- Server 端可保留 legacy HTTP 别名兼容旧脚本，但这些别名不再通过 MCP 暴露。

#### 连接

- SSH 隧道模式：Windows RPC 只监听 `127.0.0.1`；Mac 的 `FDTD_RPC_URL` 指向本地隧道端口，例如 `http://127.0.0.1:5501`。
- 局域网模式：Windows RPC 监听 `0.0.0.0`；Mac 的 `FDTD_RPC_URL` 指向 Windows 私网地址，例如 `http://192.168.1.20:5000`。
- 局域网模式仅允许 Windows“专用网络”防火墙范围，不配置公网端口映射。
- SSH 隧道断开时只报告连接失败，不自动回退到局域网地址或另一台电脑。

## MCP 工具面

交付版默认注册 32 个工具。

### Session

- `fdtd_health`
- `fdtd_session_start`
- `fdtd_session_pause`
- `fdtd_session_close`

### Model

- `fdtd_save`
- `fdtd_load`

### Geometry

- `fdtd_add_fdtd_region`
- `fdtd_add_rect`
- `fdtd_add_circle`

### Debug

- `fdtd_eval`
- `fdtd_getv`
- `fdtd_setv`

Debug 工具默认开启。它们用于执行 typed tools 尚未覆盖的 Lumerical 脚本，属于高级能力：

- 不自动创建持久 job。
- 不承诺 resume、飞书通知、审批或质量报告。
- 不得把环境变量、飞书 Webhook 或其他进程秘密写入返回值。
- 长任务和可恢复工作流仍优先使用 Job/SimulationPlan 工具。

### SimulationPlan

- `fdtd_simulation_plan_validate`
- `fdtd_simulation_plan_approve`
- `fdtd_simulation_plan_start`
- `fdtd_simulation_plan_real_preflight`
- `fdtd_simulation_plan_production_preflight`

### Persistent Jobs

- `fdtd_job_plan`
- `fdtd_job_start`
- `fdtd_job_status`
- `fdtd_job_tasks`
- `fdtd_job_resume`
- `fdtd_metasurface_sweep_plan`
- `fdtd_metasurface_sweep_start`

### Results and export

- `fdtd_results_list`
- `fdtd_results_download`
- `fdtd_export_gds`
- `fdtd_export_data`

### Knowledge

- `fdtd_device_template`
- `fdtd_list_devices`
- `fdtd_troubleshoot`
- `fdtd_best_practices`

### 不再注册的工具

以下 legacy 工具从交付版 MCP 注册表移除：

- `fdtd_sweep_config_get`
- `fdtd_sweep_config_set`
- `fdtd_sweep_run`
- `fdtd_sweep_status`
- `fdtd_sweep_monitor`

对应 Python 兼容代码可以保留一轮版本，但不得出现在 `tools/list` 中，也不得出现在新人使用指南的推荐路径中。

## Mac 部署

### 安装入口

仓库提供：

```zsh
./scripts/macos/install_mcp.sh
```

安装脚本必须：

1. 要求 macOS 和 Python 3.10 或更高版本。
2. 在项目根创建或复用 `.venv`。
3. 从独立运行时依赖文件安装 MCP 所需依赖；测试依赖不属于默认安装。
4. 让用户选择 SSH 隧道或局域网直连。
5. 接受或交互获取最终 `FDTD_RPC_URL`。
6. 调用 `/health`；health 失败时允许生成配置，但必须清楚标记连接尚未验证并返回非零状态。
7. 根据当前项目绝对路径生成三种客户端配置。
8. 修改现有用户配置前创建带时间戳备份。
9. 只新增或替换名为 `fdtd` 的 MCP 条目，不覆盖其他 MCP、模型、权限或环境配置。
10. 可重复执行；重复执行不得产生重复 `fdtd` 条目。
11. 写入前先解析并验证三份目标配置；任一配置无法安全解析时，三份配置均不修改。
12. 三份配置作为一次事务写入；任一写入失败时，从本次备份恢复已经修改的文件。

### 客户端配置目标

#### Codex

修改：

```text
~/.codex/config.toml
```

生成等价配置：

```toml
[mcp_servers.fdtd]
command = "${PROJECT_ROOT}/.venv/bin/python"
args = ["-m", "src.server"]
cwd = "${PROJECT_ROOT}"

[mcp_servers.fdtd.env]
FDTD_RPC_URL = "${SELECTED_FDTD_RPC_URL}"
```

示例中的 `${PROJECT_ROOT}` 和 `${SELECTED_FDTD_RPC_URL}` 表示安装脚本写入的实际绝对值，不作为运行时 shell 展开变量保留。

#### Claude Code

修改项目根：

```text
.mcp.json
```

生成：

```json
{
  "mcpServers": {
    "fdtd": {
      "command": "${PROJECT_ROOT}/.venv/bin/python",
      "args": ["-m", "src.server"],
      "cwd": "${PROJECT_ROOT}",
      "env": {
        "FDTD_RPC_URL": "${SELECTED_FDTD_RPC_URL}"
      }
    }
  }
}
```

安装脚本写入时将 `${PROJECT_ROOT}` 和 `${SELECTED_FDTD_RPC_URL}` 替换为实际字符串。

#### Hermes

修改：

```text
~/.hermes/config.yaml
```

生成等价配置：

```yaml
mcp_servers:
  fdtd:
    command: "${PROJECT_ROOT}/.venv/bin/python"
    args:
      - "-m"
      - "src.server"
    cwd: "${PROJECT_ROOT}"
    env:
      FDTD_RPC_URL: "${SELECTED_FDTD_RPC_URL}"
```

安装脚本写入时将两个变量替换为实际字符串。Hermes 中 `fdtd` 同时作为可启用 toolset：

- 如果 `toolsets` 是显式列表且不含 `fdtd`，追加 `fdtd`。
- 如果 `toolsets` 不存在，保持不存在，让 Hermes 使用默认工具选择逻辑。
- 安装脚本不得删除、排序或重写现有其他 `toolsets`。

### 配置备份

修改前备份到：

```text
原文件名.backup-YYYYMMDD-HHMMSS
```

如果解析失败、目标格式非法或写入中断：

- 三份原文件均恢复为安装前内容。
- 临时文件删除。
- 输出失败文件、错误阶段和备份位置。

## Windows 部署

### 传输

用户通过 ToDesk 将项目目录复制到 Windows。ToDesk 只负责文件传输，不是运行时依赖。

### 首次配置入口

仓库提供：

```cmd
scripts\windows\setup_rpc.bat
```

该入口调用 PowerShell 配置逻辑，并完成：

1. 检查 Windows 版本和项目目录。
2. 检测或要求选择 Lumerical v242 Python：

   ```text
   F:\Program Files\Lumerical\v242\python\python.exe
   ```

3. 验证 `import lumapi`。
4. 安装或验证 Flask 等 Windows RPC 运行依赖。
5. 选择连接模式：`ssh` 或 `lan`。
6. 设置监听地址：
   - `ssh` → `127.0.0.1`
   - `lan` → `0.0.0.0`
7. 设置端口，默认 `5000`。
8. `lan` 模式下创建仅适用于 Windows“专用网络”的入站防火墙规则；`ssh` 模式不创建入站规则。
9. 启动 RPC 并调用 `/health`。
10. 输出配置路径、PID、日志路径和 health 结果。

### Windows 本机状态目录

不可被 ToDesk 覆盖更新的状态统一放在：

```text
%LOCALAPPDATA%\fdtd-mcp\
├── config\rpc.env
├── logs\rpc_server.out.log
├── logs\rpc_server.err.log
├── run\rpc_server.pid
└── jobs\
```

`rpc.env` 至少记录：

```text
FDTD_PYTHON=F:\Program Files\Lumerical\v242\python\python.exe
LUMAPI_PATH=F:\Program Files\Lumerical\v242\api\python
FDTD_RPC_HOST=127.0.0.1
FDTD_RPC_PORT=5000
FDTD_JOB_ROOT=C:\Users\USERNAME\AppData\Local\fdtd-mcp\jobs
```

示例使用 SSH 模式；LAN 模式只把 `FDTD_RPC_HOST` 改为 `0.0.0.0`。配置程序写入当前用户真实的 `%LOCALAPPDATA%` 路径。

Webhook 仍只从 Windows 用户环境变量 `FDTD_FEISHU_WEBHOOK` 读取，不写入 `rpc.env`。

### 日常双击入口

继续提供：

- `scripts\windows\start_rpc.bat`
- `scripts\windows\status_rpc.bat`
- `scripts\windows\stop_rpc.bat`
- `scripts\windows\restart_rpc.bat`

这些入口必须统一读取 `%LOCALAPPDATA%\fdtd-mcp\config\rpc.env`，并显示：

- 当前监听地址和端口。
- PID 是否存在、是否匹配本项目 RPC。
- health 是否可访问。
- stdout/stderr 日志路径。

关闭 `.bat` 窗口不得终止后台 RPC；后台继续使用 `pythonw.exe`。

## 参数集传递

用户已有的 2π 参数集只用于验证 MCP 是否能无损表达和传递参数。

验收参数文件由用户保存在本地，不要求提交 Git。安装后的验证命令接受：

```text
--parameter-file /absolute/path/to/parameters.json
```

验证只检查：

- JSON 可解析。
- 参数数组顺序、长度和数值在 validate → normalize → compile 后符合既有 SimulationPlan 规范。
- task count 与参数组合一致。
- 编译请求不擅自裁剪、扩展或替换用户参数。
- 不调用 `/jobs/start` real 模式。
- 不声明参数覆盖 2π，不生成物理结论。

仓库自动测试使用合成参数 fixture 验证同一数据契约，不复制用户的真实参数。

## 数据流

### 客户端启动

```text
Client
→ 启动项目目录/.venv/bin/python -m src.server
→ MCP initialize
→ tools/list
→ Windows 可以离线
```

### 普通工具调用

```text
tools/call
→ Mac MCP tool
→ RpcClient
→ FDTD_RPC_URL + API v1 route
→ Windows RPC
→ structured v1 envelope
→ MCP result
```

### 持久任务

```text
SimulationPlan / job request
→ plan/approval checks
→ /jobs/start
→ job_id
→ Agent 返回 job_id 后停止轮询
→ Windows 持久状态 + 飞书终态通知
→ 用户要求后读取 status/results
```

## 错误处理

### Mac 安装

- Python 版本不满足：停止，不创建 `.venv` 或客户端配置。
- 依赖安装失败：保留 pip 输出，不写客户端配置。
- health 失败：显示 URL、错误类型、SSH/防火墙建议；不尝试真实任务。
- 客户端配置无法解析：停止并保持原文件，不进行猜测性重写。

### MCP 调用

- 连接失败：返回目标 URL、API 路径和 `connection_error`。
- 超时：返回 `remote_state=unknown`，不得解释为 FDTD 失败。
- 非 JSON 或 envelope 非法：返回 `invalid_response`。
- debug eval 失败：返回 RPC/Lumerical 错误摘要，不自动重试破坏性命令。

### Windows 管理

- PID 文件陈旧：状态命令明确标记；启动前安全清理陈旧 PID。
- 端口被占用：显示占用端口和 PID，不启动第二个 RPC。
- Lumerical Python/lumapi 不可用：拒绝启动并显示配置文件路径。
- 防火墙配置失败：LAN setup 失败，不以“已可远程连接”状态结束。
- health 失败：显示日志尾部，不自动启动 FDTD real job。

## 交付验收

### 1. 静态验收

- 运行时依赖和测试依赖分离。
- Mac、Windows 安装/管理脚本都支持 `--help` 或等价帮助。
- 配置模板不包含开发机固定绝对路径。
- `tools/list` 精确返回本 spec 的 32 个工具。
- `tools/list` 不包含任何 `fdtd_sweep_*`。

### 2. Mac MCP 协议验收

通过真实子进程 stdio 完成：

1. `initialize`
2. `tools/list`
3. `tools/call(fdtd_health)`
4. `tools/call(fdtd_simulation_plan_validate)`
5. `tools/call(fdtd_job_start)`，请求为 mock

协议测试不得通过直接导入 Python 函数代替 stdio。

### 3. 三客户端验收

- Codex 能发现 `fdtd` MCP 和完整目标工具面。
- Claude Code 能发现同一工具面。
- Hermes 能加载 `mcp_servers.fdtd`，并把工具作为 `fdtd` toolset 提供。
- 三个客户端调用同一个 `fdtd_health` 时返回一致 API v1 语义。

### 4. 两种连接验收

- SSH 隧道模式可通过本地 URL 调用 `/health`。
- LAN 模式可从 Mac 通过 Windows 私网 IP 调用 `/health`。
- 切换模式通过修改配置并重启 MCP 完成，不要求代码修改。

### 5. 非物理工作流验收

- 用户参数文件完成 validate/normalize/compile 无损检查。
- `plan` 或 `mock` job 返回稳定 `job_id`。
- job 的 manifest、status、summary 和 task 文件落盘到 `%LOCALAPPDATA%\fdtd-mcp\jobs`。
- mock 终态可发送飞书通知。
- 全流程不启动真实 FDTD 求解，不产生物理结论。

### 6. 可迁移验收

将同一项目目录通过 ToDesk 复制到第二台 Windows 后：

1. 运行 `setup_rpc.bat`。
2. 选择该机器的 Lumerical v242 Python。
3. 完成 health。
4. 在 Mac 修改 `FDTD_RPC_URL` 并重启 MCP。
5. 无代码修改即可使用相同工具面。

## 文档交付

实现完成后，当前入口文档必须面向 MCP 交付重写：

- `README.md`：五分钟安装、两种连接方式、三客户端入口、快速验收。
- `docs/MCP_USER_GUIDE.md`：完整工具目录、debug 工具边界、参数文件验证、客户端配置。
- `docs/WINDOWS_RUNBOOK.md`：首次配置、双击管理、状态目录、防火墙和迁移。
- `docs/RPC_API_V1.md`：MCP 实际依赖的 API v1 路由。
- `REQUIREMENTS.md`：把“可交付个人 MCP”设为当前验收目标；物理实验保留为使用场景，不作为开发完成标准。

## 版本与发布边界

- 首个可交付版本标记为 `0.1.0`。
- 版本号必须能通过 Python 包元数据或 `src` 内单一版本常量读取，不能在多个文档中手工维护。
- 发布产物是 Git/ToDesk 可复制的仓库目录，不发布 PyPI。
- `0.1.0` 的完成定义是本 spec 的全部验收项通过，不包含真实 sweep。

## 实现原则

- 复用现有 FastMCP、RpcClient、JobStore 和 Windows 管理脚本。
- 不重写已验证的 API v1 和持久 job 状态机。
- 不引入数据库、队列、容器或额外守护进程。
- 配置生成使用结构化 TOML/JSON/YAML 读写，不用字符串替换破坏用户配置。
- 所有配置写入采用临时文件加原子替换。
- 测试不得访问真实飞书、启动 FDTD 或依赖用户真实参数文件。
