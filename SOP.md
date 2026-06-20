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
2. 本地启动或重启（默认端口 5000）：
   ```cmd
   scripts\windows\restart_rpc.bat
   ```
3. 健康检查：
   ```cmd
   curl http://127.0.0.1:5000/health
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
   ssh -L 5000:localhost:5000 32482@192.168.31.26
   # 或直连: export FDTD_RPC_URL=http://192.168.31.26:5000
   ```
4. 验证连接：
   ```bash
   curl http://localhost:5000/health
   ```

## SOP-004 - 原生 metasurface sweep 端到端验证

1. 确保 Windows RPC Server 正在运行。
2. 确认 `templates/metasurface/base_model.fsp` 已按 SOP-002b 安装。
3. 先走 mock 或 plan；真实运行前必须获得审批摘要确认。
4. Mac 端通过 `/jobs/start` 启动 `real metasurface-sweep`，预期 HTTP 202 返回 `job_id`。
5. 记录并返回 `job_id` 后停止轮询；收到飞书终态通知后，再读取 `/jobs/<job_id>`、task、quality 和 evidence。

旧 `scripts/smoke_test.py` 仅用于历史 Autosweep baseline，不再作为新 v1 验收入口。

```bash
python scripts/v1_smoke_test.py --rpc http://localhost:5000
```

## SOP-004b - 新 v1 smoke 验证

1. Windows 本地确认 `scripts\windows\restart_rpc.bat` 健康检查通过。
2. 运行（Mac 端需先建立 `5000` 隧道；Windows 本机可直接跑）：
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
   - `fdtd.setnamed("FDTD", "express mode", EXPRESS_MODE)` 在每次 `load()` 后 `save()` 前
   - 当前 CPU 模板/resource 使用默认 `EXPRESS_MODE=0`；只有明确改为 GPU 时才设 `EXPRESS_MODE=1`
5. 端口未被幽灵进程占用（`netstat -ano | findstr 5000`）。

## SOP-006 - 交付

1. 确保新增脚本可通过 `python scripts/xxx.py --help` 打印使用说明。
2. 更新 `DEV_LOG.md`。
3. 如果发现踩坑或可复用经验，写入对应文档。

## SOP-007 - 从自然语言到真实仿真

1. Agent 将自然语言需求编译为 Plan JSON。
2. 调用 `fdtd_simulation_plan_validate` 规范化、验证和指纹。
3. 向用户展示 `defaults_applied`、assumptions、warnings、task count 和 fingerprint。
4. 获得用户明确批准后调用 `fdtd_simulation_plan_approve`。
5. 用返回的 Plan 审批启动 `fdtd_simulation_plan_start(mode="mock")`。
6. 对于 real：另外生成 template contract 和真实运行摘要，取得单独批准后以 `mode="real"` 启动。
7. 审批或模板指纹变化后绝不复用旧审批。
8. 启动后保存并返回 `job_id`，结束当前 Agent 工作；只有用户明确询问进度时才调用一次轻量 status，不用单次长 HTTP/MCP 调用等待。
9. 完成后生成 summary、质量报告和关键可视化，再交由人工判断物理合理性。

## SOP-008 - Job 状态、失败和恢复

1. 每个 job 创建独立目录，复制或记录输入 config、模板和代码版本。
2. 每个 task 写独立 JSON，至少包含 ID、参数、状态、模型路径、开始/结束时间、错误和结果路径。
3. 失败时先读取 `status.json`、`summary.json` 和短 `run.log` 尾部，不先下载全量模型。
4. 服务重启时，残留 `running` job 会转为 `partial`，残留 `running` task 会转为 `failed/interrupted`；不会自动重新求解。
5. 临时 session/IO 错误允许原参数重试一次；物理参数、mesh、boundary、scheduler 或模板指纹变化必须形成新 job/revision。
6. `resume` 只跳过已有完整结果的 task，不覆盖历史结果。
7. real metasurface resume 返回 `resume_conflict` 当模板缺失、无指纹或 SHA-256 变化时；必须创建新 job。
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
.venv/bin/python -m pytest -q
```

## SOP-010 - Template contract 工作流

Stage A 只读 inventory 的完整流程：

```text
install -> inventory -> stop -> review inventory -> commit strict profile
```

Stage A 在 inventory 审核后停止。不得在 inventory 阶段创建 strict profile、生成 verified contract 或启动真实运行。

1. 在 Windows 上安装模板 (`install_metasurface_template.bat`)。
2. 运行只读 inventory (`inspect_metasurface_template.bat`)。
3. 审核 `base_model.inventory.json`：
   - `inventory_only=true`、`status=inventory`。
   - 模板 SHA-256 有效、Lumerical 版本不为 unknown。
   - known objects 均 `count=1`、`status=pass`。
   - objects 非空、errors 为空。
4. 根据真实 inventory 编写 strict contract profile（进入 Stage B）。
5. 不提交 runtime inventory/contract JSON。
6. 不在此阶段修改 RPC guard 或启动真实 sweep。

### Stage B1 - strict profile and contract

1. Sync Windows checkout to current `origin/main`.
2. Confirm `templates/metasurface/base_model.probe.json` has `stage_b1_ready=true`.
3. Run `scripts\windows\generate_template_contract.bat`.
4. Confirm `status=verified`, `verified=true`, all checks pass.
5. Do not start a real SimulationPlan job in Stage B1.
6. Report contract fingerprint and stop for separate real-run approval.

## SOP-012 - Real 2×2 SimulationPlan preflight

1. Confirm Stage B1 contract exists on Windows: `templates\metasurface\base_model.contract.json`.
2. Run `scripts\windows\build_real_run_preflight_packet.bat`.
3. Confirm output contains `status=ready_for_human_approval`.
4. Inspect `runtime\approvals\real_2x2_preflight.json`.
5. Report plan fingerprint, template SHA, contract fingerprint, task count, resource, express mode, mesh accuracy, and warnings.
6. Stop. Do not call `fdtd_simulation_plan_start(mode="real")` until the human approves this exact packet.

## SOP-013 - Stage C2 real result review

1. 确认 Stage C1 job 已结束，且不会在 C2 启动、resume 或扩大任何真实仿真。
2. 从 Windows job 目录只复制 evidence-first 文件：`manifest.json`、`status.json`、`summary.json`、`quality_report.json`、`results/sweep_results.csv`、`results/sweep_summary.json`、`evidence/index.json`、关键 SVG 和 task JSON。
3. 默认不复制 `models/*.fsp`；只有调试或人工明确要求时才单独复制模型文件。
4. 将 C0 preflight packet 与 C1 evidence 放到 git-ignored `runtime/reviews/<job_id>/`。
5. 运行：
   ```bash
   .venv/bin/python scripts/collect_real_result_review.py \
     --job-dir runtime/reviews/<job_id>/evidence_copy \
     --preflight runtime/reviews/<job_id>/approval/real_2x2_preflight.json \
     --output-dir runtime/reviews/<job_id>
   ```
6. 审核 `review.json` 和 `real_2x2_review.md`：软件链可以自动判定 pass/fail；物理正确性必须由人审核。
7. 若报告建议扩大 sweep 或改变物理设置，必须进入新的 plan/preflight/approval 阶段，不能由 C2 自动启动。

## SOP-011 - Stage B0.x 模板只读探针工作流

```text
Stage A inventory
→ Stage B0 discovery probe
→ Stage B0.1 evidence correction probe
→ review stage_b1_ready
→ Stage B1 strict profile
```

1. 推送代码到 origin/main。
2. Windows `git pull --ff-only`。
3. 运行 `scripts\windows\probe_metasurface_template.bat`。
4. 审核 `base_model.probe.json`：
   - `probe_only=true`、`status=probe`。
   - 安装身份可确认（路径版本标签、lumapi SHA-256）。
   - 对象身份证据（root 与 ::model 同名对象对比结论）。
   - source strategy 分类明确。
   - 结构候选属性完整（含 material、坐标、span）。
   - FDTD 配置可读（dimension、boundary conditions、mesh accuracy）。
   - model 参数可读（ratio、height、period 真实值/类型）。
   - monitors 和分析组验证通过。
   - `cleanup_state=closed`。
5. 不提交 runtime probe JSON。
6. 停在 Stage B0 checkpoint，不进入 Stage B1。
7. 不在此阶段创建 strict profile、contract 或启动真实 sweep。

## SOP-014 - Stage C3 production sweep design packet

1. 确认 C2 `review.json` 存在，且 `software_chain_verdict=pass`。
2. 确认 Stage B1 `templates/metasurface/base_model.contract.json` 仍为 `verified`。
3. 运行：
   ```bash
   .venv/bin/python scripts/build_production_sweep_packet.py \
     --review runtime/reviews/job_20260619_213418_metasurface_sweep/review.json \
     --contract templates/metasurface/base_model.contract.json \
     --output runtime/approvals/production_sweep_c3_packet.json
   ```
4. 审核 packet：`status=ready_for_human_approval`、`task_count=25`、CPU、`express_mode=0`、`include_models=false`、template SHA 和 contract fingerprint 匹配。
5. C3 只生成 packet，不调用 `/jobs/start`，不 resume，不重启 RPC，不修改 `.fsp`。
6. 如果用户批准该 exact packet，后续进入 Stage C4 才允许提交 `compiled_request` 启动真实 sweep。
7. 若需要高度超过 700 nm 或改变 mesh/boundary/source/template，必须另起模板/mesh review，不得复用 C3 默认 packet。


## SOP-015 - 持久 job 飞书通知与 Agent 退出

1. Windows 用户环境设置 `FDTD_FEISHU_WEBHOOK`，Webhook 不写入 Git 或 job 输入。
2. 重启 RPC 服务，让 `pythonw.exe` 继承环境变量。
3. `/jobs/plan` 创建持久 job 后发送 `planned`；mock/real 到达 `succeeded`、`failed` 或 `partial` 后发送终态通知。
4. Agent 提交长任务并确认收到 `job_id` 后停止轮询；只有用户明确询问进度时才做一次只读查询。
5. 用户收到飞书后，让 Agent 读取 `status.json`、`summary.json`、`quality_report.json` 和 evidence-first 结果。
6. 飞书发送失败只查 `run.log`，不得据此重跑或改变 job 状态。
7. 2026-06-20 已完成 Windows mock smoke：持久 job 成功、飞书收到 `succeeded`，且未启动 FDTD。

## SOP-016 - Mac、CMD 与 PowerShell 命令边界

1. Mac 本地命令使用 `zsh`；Windows `.bat`、`cd /d`、`set` 使用 CMD；`Invoke-RestMethod`、`$env:`、反引号续行使用 PowerShell。
2. 同一代码块不得混用三种 shell。远程操作时先标明命令在哪台机器、哪个 shell 执行。
3. Windows 路径在 Markdown 中保持字面反斜杠；交付前扫描 `\f`、`\b`、`\r` 等隐藏控制字符。
4. 能调用仓库脚本时优先调用脚本，不把复杂 PowerShell 压进 `.bat` 或 zsh 单行命令。
