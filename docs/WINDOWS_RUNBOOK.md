# Windows 本地运维手册

## 机器与路径

- Windows 项目路径：`F:\lumerical-fdtd-auto-design\fdtd-auto-design`
- Lumerical Python：`F:\Program Files\Lumerical\v242\python\python.exe`
- v1 RPC 端口：`127.0.0.1:5000`
- 日志：`logs\rpc_server.err.log`、`logs\rpc_server.out.log`
- PID：`runtime\rpc_server.pid`

本文命令按代码块标记的 shell 执行：`cmd` 仅用于 CMD，`powershell` 仅用于 PowerShell；不要把两者与 Mac zsh 语法混用。

## 更新代码

在 Windows 本地 CMD：

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git pull --ff-only
```

如果 GitHub 代理正常且工作树干净，也可以运行：

```cmd
scripts\windows\update_and_restart.bat
```

注意：

- 发现工作树有本地修改时，脚本会拒绝更新。
- 不要用 Mac SSH 远程编辑 Windows 文件。

## 启动、停止和状态

```cmd
scripts\windows\restart_rpc.bat
scripts\windows\status_rpc.bat
scripts\windows\stop_rpc.bat
```

实现细节：

- `.bat` 只是入口，实际逻辑在 `scripts\windows\manage_rpc.ps1`。
- 后台服务优先使用 `pythonw.exe`，避免批处理窗口关闭时终止 RPC 进程。
- 停止脚本只会停止 PID 文件记录且命令行匹配本项目的进程。

## v1 Smoke

不运行求解，只验证 GUI 会话、最小几何、保存和旧路由兼容：

```cmd
"F:\Program Files\Lumerical\v242\python\python.exe" scripts\v1_smoke_test.py
```

成功标准：

- health 返回 `api_version=v1`。
- `/session/start` 成功并打开 FDTD GUI。
- 添加 FDTD region 和 silicon rectangle 成功。
- `smoke-output\*.fsp` 生成。
- 旧 `/session/stop` 返回弃用元数据。
- 最终 health 显示 `connected=false`。

## Minimal solver smoke

运行一次固定低成本模型，验证 RPC → lumapi → solve → result → download 闭环。该 smoke 是技术验收，不产生物理结论。

```cmd
"F:\Program Files\Lumerical\v242\python\python.exe" scripts\windows\minimal_solver_smoke.py --rpc http://127.0.0.1:5000 --output "%LOCALAPPDATA%\fdtd-mcp\smoke"
```

若 `5000` 被 Windows 僵尸 TCP 条目临时锁死，可在启动 RPC 时改用其他端口，并同步修改 `--rpc`，例如 `http://127.0.0.1:5001`。

成功标准：

- `technical_smoke=true`
- `physical_conclusion=false`
- `ok=true`
- 14/14 步通过：health、session_start、project_new、object_create、fdtd_region、source_create、monitor_create、analysis_group_create、simulation_run、simulation_status、project_save、result_list、result_read_value、result_download
- 产物包含 `smoke_model.fsp`、`smoke_report.json`、`downloaded_results.json`

## Metasurface 模板安装

首次运行真实原生 `metasurface-sweep` 前，安装已验证模板：

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
scripts\windows\install_metasurface_template.bat "E:\CLAUDE_workspace\Lumerical_autosweep\base_model.fsp"
```

说明：

- 这是一次性数据迁移，不是运行时旧项目依赖。
- 目标文件是 `templates\metasurface\base_model.fsp`，该 `.fsp` 被 Git 忽略。
- 每个真实 sweep 的 `manifest.json` 会记录模板 SHA-256、大小和修改时间。

## 模板只读 inventory

安装模板后，在 Windows 本地运行一次只读 inventory：

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git pull --ff-only
scripts\windows\inspect_metasurface_template.bat
type templates\metasurface\base_model.inventory.json
```

成功标准：

- `inventory_only=true`
- `status=inventory`
- Lumerical version 不是 "unknown"
- 所有 known objects 的 `count=1` 且 `status=pass`
- objects 列表非空
- `cleanup_state=closed`
- 未创建真实 job

Inventory 仅用于发现对象，不能批准真实运行。

## 模板定向只读探针 (Stage B0)

Inventory 审核后，运行定向探针解决遗留不确定性：

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git pull --ff-only
scripts\windows\probe_metasurface_template.bat
type templates\metasurface\base_model.probe.json
```

成功标准：

- `probe_only=true`、`status=probe`
- 安装身份可确认（`confirmable=true`，路径版本标签可读）
- 对象身份证据完整（同名对象对比结论）
- source strategy 分类明确
- 结构候选属性、FDTD 配置、model 参数完整
- `cleanup_state=closed`
- 未创建真实 job

探针输出不能授权真实运行。

## Generate Stage B1 template contract

From `F:\lumerical-fdtd-auto-design\fdtd-auto-design`:

    git pull --ff-only
    scripts\windows\generate_template_contract.bat

Expected result:

    template_contract status=verified fingerprint=<64 hex chars>

This command reads JSON evidence only. It must not open Lumerical, mutate `.fsp`, or create jobs.

## Build Stage C0 real 2x2 approval packet

From `F:\lumerical-fdtd-auto-design\fdtd-auto-design`:

    git pull --ff-only
    scripts\windows\build_real_run_preflight_packet.bat

Expected:

    real_2x2_preflight status=ready_for_human_approval ...

This command reads JSON evidence and writes `runtime\approvals\real_2x2_preflight.json`.
It must not start RPC real mode or run FDTD.

## Object Library analysis group smoke

验证 Object Library catalog 枚举、intent 匹配、探针、配置和 runsetup readback 全链路，不运行求解：

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git pull --ff-only
scripts\windows\restart_rpc.bat
"F:\Program Files\Lumerical\v242\python\python.exe" scripts\windows\object_library_analysis_group_smoke.py --rpc http://127.0.0.1:5000 --output "%LOCALAPPDATA%\fdtd-mcp\object-library-smoke"
```

若 `5000` 被僵尸 TCP 条目锁死，改用 `--rpc http://127.0.0.1:5001`。

若 v242 实际 ID tokenize 方式与默认 `transmission` intent 不匹配，可用 `--intent-kind`、`--output-name` 和 `--script-id` 参数。`--script-id` 仍由 RPC server 验证是否存在于 live catalog。

成功标准（不运行求解）：

- `technical_smoke=true`
- `physical_conclusion=false`
- `catalog_enumerated=true`
- `probe_restore_verified=true`
- `setup_verified=true`
- `ok=true`

产物：`object_library_model.fsp`、`object_library_smoke_report.json`。

## 当前已知状态（2026-06-20）

- Windows clone 已同步并加载 close detach/timeout 修复。
- `5004` 已完成开发期真实验证：v1 smoke 全流程通过，真实 2×2 原生 `metasurface-sweep` 结果 4/4 valid、quality `pass`。
- 新服务默认端口已切换为 `5000`；Windows 同步后用 `restart_rpc.bat` 启动。
- 0.1.0 minimal solver smoke 产物：`%LOCALAPPDATA%\fdtd-mcp\smoke\smoke_model.fsp`、`smoke_report.json`、`downloaded_results.json`。
- 新代码已支持原生逐 sample `metasurface-sweep`，`real` 启动返回 HTTP 202。
- 0.1.0 minimal solver smoke 已通过，证明通用建模/求解/结果下载闭环可用；该 smoke 不作为物理结论。
- analysis group 创建支持官方 Object Library 优先：提供已确认 `script_id` 时使用 `addobject("script_id")`，否则按 `prefer_builtin/require_builtin` 策略回退或报错。
- 可选物理工作流的 C3 25-task production sweep packet 已生成并冻结；未获 exact packet 人工批准不得启动。
- 飞书持久 job 通知已通过 Windows mock smoke；Agent 提交后默认不轮询。
- 当前执行基础设施已够用，后续优先推进批准后的真实设计工作流。

## 故障排查

### `5000` 连不上

```cmd
scripts\windows\status_rpc.bat
type logs\rpc_server.err.log
```

若 PID 文件存在但进程已退出，`restart_rpc.bat` 会自动清理陈旧 PID。

### 批处理窗口关闭后服务退出

确认已同步到 `ca4cf6a` 或之后版本。管理脚本应使用 `pythonw.exe` 启动后台服务。

### `git pull` 失败并提到 `127.0.0.1:17891`

Windows Git 全局代理指向本机端口。确认代理程序正在运行，或临时绕过：

```cmd
git -c http.proxy= -c https.proxy= pull --ff-only
```

### `/session/start` 报 `getversion`

确认 Windows clone 至少为：

```cmd
git rev-parse --short HEAD
```

应为 `0cdf639` 或之后版本。然后运行 `restart_rpc.bat` 让服务进程加载新代码。

### `/session/stop` 或 `/session/close` 超时

确认已同步到包含 close detach/timeout 修复的提交。修复版会先把 RPC 状态标记为断开，再后台请求 raw lumapi 关闭；如果 `fdtd.close()` 不返回，响应仍会包含 `close_state=timed_out`，服务不会被永久占住。

## Stage C3 production sweep packet

在 Windows CMD 中，确认 `base_model.contract.json` 和 C2 review artifact 存在后运行：

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
scripts\windows\build_production_sweep_packet.bat
```

预期输出包含：

```text
production_sweep_c3 status=ready_for_human_approval task_count=25
```

该命令只在本地生成审批包，不得启动 FDTD、调用 `/jobs/start`、resume job 或修改 `.fsp`。



## 飞书持久 Job 通知

设置用户环境变量：

```powershell
setx FDTD_FEISHU_WEBHOOK "https://open.feishu.cn/open-apis/bot/v2/hook/你的Webhook"
```

`setx` 只影响后续进程。关闭当前 RPC 后，在 Windows CMD 中运行 `scripts\windows\restart_rpc.bat`，让新 `pythonw.exe` 继承变量。不要把 Webhook 写入仓库、请求 JSON 或日志。

不启动 FDTD 的 smoke：

```powershell
$body = @{
  mode = "mock"
  job_type = "geometry-smoke"
} | ConvertTo-Json
Invoke-RestMethod `
  -Uri "http://127.0.0.1:5000/jobs/start" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

成功标准：

- HTTP 返回持久 `job_id`。
- 飞书收到 `FDTD job succeeded`。
- job 目录的 `notifications.json` 只含发送状态和时间，不含 Webhook。
- `run.log` 含发送成功记录。
- 不启动真实 FDTD 求解。

2026-06-20 已完成上述 Windows mock smoke。Agent 获得 `job_id` 后应结束当前工作，不主动轮询；用户收到飞书后再读取结果。
