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

## SOP-003 - Mac 端环境搭建

1. 确保 Python 3.10+ 可用。
2. 安装依赖：
   ```bash
   pip install requests
   ```
3. 建立 SSH 隧道（推荐）或直连：
   ```bash
   ssh -L 5003:localhost:5003 32482@192.168.31.26
   ssh -L 5004:localhost:5004 32482@192.168.31.26
   # 或直连: export FDTD_RPC_URL=http://192.168.31.26:5003
   ```
4. 验证连接：
   ```bash
   curl http://localhost:5003/health
   ```

## SOP-004 - 端到端验证

1. 确保 Windows RPC Server 正在运行。
2. Session 已启动（`fdtd_connected=true`）。
3. Mac 端运行 smoke test：
   ```bash
   python scripts/smoke_test.py --rpc http://localhost:5003
   ```
4. 预期：4/4 valid, 0 missing。

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
3. RPC Server `_run_pipeline` 内：
   - `fdtd.clearjobs()` 在 Phase 1 循环前
   - `fdtd.setnamed("FDTD", "express mode", 1)` 在每次 `load()` 后 `save()` 前
4. 端口未被幽灵进程占用（`netstat -ano | findstr 5003`）。

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
4. 临时 session/IO 错误允许原参数重试一次；物理参数、mesh、boundary 或 scheduler 变化必须形成新 revision。
5. `resume` 只跳过已有完整结果的 task，不覆盖历史结果。
6. 不因失败自动扩大扫描；下一轮以建议文件和新审批处理。

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
.venv/bin/python -m pytest -q  # 当前 65 项
```
