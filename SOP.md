# 项目 SOP

这个文件用于记录项目内可重复执行的流程。

## SOP-001 - Windows 端环境搭建

1. 确认 Lumerical v242 已安装并在 license 有效期内。
2. Python 使用 Lumerical 自带的：`F:\Program Files\Lumerical\v242\python\python.exe`。
3. 安装依赖：
   ```cmd
   F:\Program Files\Lumerical\v242\python\python.exe -m pip install flask numpy scipy
   ```
4. 验证：
   ```cmd
   F:\Program Files\Lumerical\v242\python\python.exe -c "import lumapi; import matlab.engine; import numpy; import scipy; print('OK')"
   ```

## SOP-002 - Windows 端启动新 v1 RPC Server

1. 进入 Windows 项目目录：
   ```cmd
   cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
   ```
2. 本地启动或重启（默认端口 5004）：
   ```cmd
   scripts\windows\restart_rpc.bat
   ```
3. 健康检查：
   ```cmd
   curl http://127.0.0.1:5004/health
   ```
4. 真实 v1 smoke（不求解）：
   ```cmd
   "F:\Program Files\Lumerical\v242\python\python.exe" scripts\v1_smoke_test.py
   ```
5. 如需同步代码，优先用 `git pull --ff-only`；若代理正常且工作树干净，可运行 `scripts\windows\update_and_restart.bat`。

## SOP-002b - 安装 metasurface 模板

1. 首次运行真实 `metasurface-sweep` 前，在 Windows 项目目录执行：
   ```cmd
   cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
   scripts\windows\install_metasurface_template.bat "E:\CLAUDE_workspace\Lumerical_autosweep\base_model.fsp"
   ```
2. 预期输出包含目标路径、字节数和 SHA-256。
3. 这是一次性模板迁移，不是运行时旧 Autosweep 依赖；之后新服务只读取 `templates\metasurface\base_model.fsp`。
4. `.fsp` 被 Git 忽略，不要提交模板二进制。

## SOP-003 - Mac 端环境搭建

1. 确保 Python 3.10+ 可用。
2. 安装依赖：
   ```bash
   pip install requests
   ```
3. 建立 SSH 隧道（推荐）或直连：
   ```bash
   ssh -L 5004:localhost:5004 32482@192.168.31.26
   # 或直连: export FDTD_RPC_URL=http://192.168.31.26:5004
   ```
4. 验证连接：
   ```bash
   curl http://localhost:5004/health
   ```

## SOP-004 - 原生 metasurface sweep 端到端验证

1. 确保 Windows RPC Server 正在运行。
2. 确认 `templates/metasurface/base_model.fsp` 已按 SOP-002b 安装。
3. 先走 mock 或 plan；真实运行前必须获得审批摘要确认。
4. Mac 端通过 `/jobs/start` 启动 `real metasurface-sweep`，预期 HTTP 202 返回 `job_id`。
5. 轮询 `/jobs/<job_id>` 和 `/jobs/<job_id>/tasks`，完成后检查 quality/evidence。

旧 `scripts/smoke_test.py` 仅用于历史 Autosweep baseline，不再作为新 v1 验收入口。

```bash
python scripts/v1_smoke_test.py --rpc http://localhost:5004
```

## SOP-004b - 新 v1 smoke 验证

1. Windows 本地确认 `scripts\windows\restart_rpc.bat` 健康检查通过。
2. 运行（Mac 端需先建立 `5004` 隧道；Windows 本机可直接跑）：
   ```cmd
   "F:\Program Files\Lumerical\v242\python\python.exe" scripts\v1_smoke_test.py
   ```
3. 预期：health、session start、status、geometry、save、legacy `/session/stop` 和 final health 全部通过。
4. 若失败，先看 `logs\rpc_server.err.log`；不得通过 SSH 反复启动 GUI 会话。

## SOP-005 - 扫参前检查清单

1. `base_model.fsp` 模板完好，含 `::model::s_params` 分析组。
2. 模板参数 `ratio`、`height`、`period` 已定义。
3. `manifest.json` 会记录模板 `path`、`sha256`、`size_bytes` 和 `modified_at`；如果模板指纹变化，应创建新 job，不要静默 resume 旧 job。
4. `NativeSweepRunner` 内：
   - `fdtd.clearjobs()` 在 Phase 1 循环前
   - `fdtd.setnamed("FDTD", "express mode", 1)` 在每次 `load()` 后 `save()` 前
5. 端口未被幽灵进程占用（`netstat -ano | findstr 5004`）。

## SOP-006 - 交付

1. 确保新增脚本可通过 `python scripts/xxx.py --help` 打印使用说明。
2. 更新 `DEV_LOG.md`。
3. 如果发现踩坑或可复用经验，写入对应文档。

## SOP-007 - 从自然语言到真实仿真

1. 将用户需求整理为 `SimulationPlan`：器件、材料、光源、监视器、边界、网格、参数空间、FOM、验收条件和最大预算。
2. 运行 `plan`，验证 schema、路径、单位和对象名，展开任务并报告总数。
3. 必要时运行 `mock`，验证 RPC、job/task 状态、后处理和报告链；明确标记为非物理数据。
4. 生成真实运行审批摘要：config/model、job 目录、GUI 状态、scheduler、资源、任务数或最大迭代数、输出覆盖风险。
5. 只有用户明确批准该摘要后，才以 `real` 启动作业。
6. 启动后保存 `job_id`，使用轻量 status 接口轮询，不用单次长 HTTP/MCP 调用等待。
7. 完成后生成 summary、质量报告和关键可视化，再交由人工判断物理合理性。

## SOP-008 - Job 状态、失败和恢复

1. 每个 job 创建独立目录，复制或记录输入 config、模板和代码版本。
2. 每个 task 写独立 JSON，至少包含 ID、参数、状态、模型路径、开始/结束时间、错误和结果路径。
3. 失败时先读取 `status.json`、`summary.json` 和短 `run.log` 尾部，不先下载全量模型。
4. 服务重启时，残留 `running` job 会转为 `partial`，残留 `running` task 会转为 `failed/interrupted`；不会自动重新求解。
5. 临时 session/IO 错误允许原参数重试一次；物理参数、mesh、boundary、scheduler 或模板指纹变化必须形成新 job/revision。
6. `resume` 只跳过已有完整结果的 task，不覆盖历史结果。
7. 不因失败自动扩大扫描；下一轮以建议文件和新审批处理。

当前 `/jobs/*` v1 已实现：plan、start、status、tasks、resume。`geometry-smoke` 已真实通过；`metasurface-sweep` 已接入逐 sample task、原生 Phase 1-4、quality report 和 evidence index。真实 sweep 由 `/jobs/start` 异步返回 `202 + job_id`。

## SOP-009 - RPC/MCP 契约变更

1. 先更新唯一 API v1 契约和测试样例。
2. 同步修改 Windows RPC Server、Mac `RpcClient`、MCP tool wrapper 和 smoke test。
3. 按变更范围覆盖成功、参数错误、无会话、重复启动、HTTP 错误、连接失败、超时和非 JSON 响应。
4. 在无 Windows/Lumerical 环境下运行 mock/fake-server 契约测试。
5. 最后在 Windows 本地重启 RPC Server，并用最小真实 smoke 验证。

离线测试：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
.venv/bin/python -m pytest -q  # 当前 112 项
```
