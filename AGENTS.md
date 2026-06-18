# 项目代理指令

这个文件记录项目专属规则。当它比全局工作台规则更具体时，以本文件为准。

## 启动阅读

在本项目中开始工作前，按顺序阅读：

1. 根目录 `AGENTS.md`。
2. 根目录 `WORKSPACE.md`。
3. 全局 `workspace/` 日志和 SOP。
4. 本文件。
5. `README.md`.
6. `REQUIREMENTS.md`.
7. `TECH_STACK.md`.
8. 存在时阅读 `DEV_LOG.md`、`PITFALLS.md`、`SOP.md` 和 `RETROSPECTIVE.md`。
9. 其他与当前任务相关的本地文档。

## 项目边界

- **架构硬约束**：
  - FDTD 仿真 **只在 Windows 端运行**。Mac 端不安装 Lumerical，不导入 `lumapi`。
  - Windows 端必须运行 **RPC Server**（Flask），持有持久 lumapi 会话。
  - Mac 端通过 **HTTP**（直连或 SSH 隧道）调用 RPC Server。
  - **双模式**：`hide=False`（GUI 调试，需 RDP 连接）/ `hide=True`（headless 批量，生产默认）。
- **License 硬约束**：软件只能在 Windows 上运行（v242，单机 domain=0）。
- **可复现性**：仿真结果必须可由脚本完整复现。
- **平台隔离**：RPC Server 代码只跑在 Windows 上，MCP Server 和控制脚本只跑在 Mac 上。
- **Windows 代码更新**：Windows 端代码通过 `git pull --ff-only` + 本地 `.bat` 重启来更新。SSH 可用于只读检查、拉代码和读取日志；不要通过 SSH 反复启动需要桌面会话的 FDTD GUI。
- **非目标**：不做 RPC Server 公网暴露/强安全认证；不做多机集群调度。
- **语言**：代码注释和变量名使用英文；文档正文使用中文。
- **交付前检查**：每个脚本必须含最小可运行示例，在 `DEV_LOG.md` 中记录运行结果。
- **Headless 必查**：`clearjobs()` 在 sweep 前；`express mode` 在每次 `load()` 后 `save()` 前设置。违反即 0 valid。
- **自然语言不直接执行**：用户需求必须先编译为可检查的结构化计划，至少包含器件、材料、光源、监视器、边界、网格、参数空间、FOM、验收条件、任务数和输出目录。
- **运行模式分级**：默认先走 `plan`；软件链验证走 `mock`；只有真实求解才进入 `real`。`plan/mock` 结果不得作为物理证据。
- **真实运行审批**：任何 `real` sweep、优化或整器件验证前，必须报告任务数、最大迭代数、模型/配置路径、GUI 状态、调度与资源、输出覆盖风险，并取得针对该运行的明确批准。
- **作业必须落盘**：长任务不得只存在于 Flask 线程内存。每个 job 和 sample/task 必须有稳定 ID、状态文件、日志、输入快照、结果路径和可恢复信息。
- **异步优先**：预计超过 30 秒的操作应立即返回 `job_id/task_id`，由状态接口轮询；MCP 工具不得用单次长 HTTP 请求等待求解结束。
- **恢复不改物理**：`resume` 只能跳过已完成样本或重试临时 session/IO 失败，不得静默扩大扫描、修改 mesh/boundary、切换 scheduler 或覆盖原始结果。
- **结果质量门**：solver 完成不等于任务通过。交付前必须生成结构化质量结论，并区分 `pass`、`warning`、`fail`。
- **证据优先回传**：默认回传 manifest、status、summary、任务记录、标量结果和关键图；逐点 `.fsp` 只在调试或明确要求时传输。

## 核心工作模式：人判物理，AI 执行

这是本项目最重要的协作原则，来自社区的实践经验：

**Agent 负责**：全自动执行（写代码 → 跑仿真 → 读结果 → 发现问题 → 修改 → 重跑），跨求解器 API 编排，数据汇总和报告生成。
**人负责**：定义问题和验收标准，判断物理正确性，审核最终结果。

Agent **不具备**物理直觉。它能处理报错（语法错误、网格不收敛），但无法识别"仿真正常完成但结果物理错误"的情况。因此：

- 每个仿真任务交付前，人必须审核关键结果的物理合理性。
- Agent 应主动生成可快速扫一眼的可视化（S 参数曲线、场分布图），而非仅输出数字。
- 优化过程中如出现异常跳变（损耗突然变化 > 1dB），Agent 应暂停并标记，而非继续迭代。

## 自动化仿真原则（来源：社区 Vibe Coding 仿真实践经验）

这些原则适用于所有通过 Agent 驱动的 Lumerical 仿真任务：

1. **量化验收条件**：每个仿真任务必须有可量化的成功标准（如"损耗 < 0.5dB""不均衡度 < 5%"）。如果验收条件可能无法达成，指定最大迭代次数。
2. **固定文件名**：所有 `save()` 操作使用固定路径和文件名，避免 Lumerical 弹出覆盖确认对话框。
3. **监视器位置检查**：频域监视器截面不得与相邻波导或其他结构重叠，否则功率读数偏高。建模完成后应校验监视器坐标。
4. **自主迭代闭环**：Agent 应自主完成"写代码 → 运行仿真 → 读取结果 → 发现问题 → 修改代码 → 重新运行"的完整循环，不依赖人工中途介入。
5. **交付物约定**：每个任务完成后应产出 (a) Lumerical `.fsp` 工程文件、(b) 结构化仿真报告（含器件结构图、光场分布、关键性能指标）。

## 已知 Agent 易犯错误（写入 RPC Server 时需防御性处理）

1. 使用系统 Python 而非 Lumerical 自带 Python，导致 `import lumapi` 失败。
2. `save()` 不指定完整路径，导致弹出交互窗口。
3. 监视器尺寸过大，与相邻波导重叠，功率读数偏高。
4. 仿真精度（mesh accuracy）设置不当——太低结果不准，太高仿真时间过长。
5. RPC Server、Mac Client 和 MCP 工具的路径或返回字段不一致，导致各层单独可运行但链路不可用。
6. 将长任务状态只保存在进程内存，服务重启后无法恢复或审计。
7. 把求解器正常结束误判为物理结果合格，跳过质量报告和人工审核。

## 验证

常见改动需要执行的检查：

```bash
# === Windows 端 ===

# 1. 验证 lumapi 可用
F:\Program Files\Lumerical\v242\python\python.exe -c "import lumapi; print('OK')"

# 2. 启动新 v1 RPC Server（端口 5004）
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
scripts\windows\restart_rpc.bat

# 3. 本地验证
curl http://127.0.0.1:5004/health

# 3b. 首次真实 sweep 前安装 metasurface 模板
scripts\windows\install_metasurface_template.bat "E:\CLAUDE_workspace\Lumerical_autosweep\base_model.fsp"

# === Mac 端 ===

# 4. 建立 SSH 隧道
ssh -L 5004:localhost:5004 32482@192.168.31.26

# 5. 新 v1 smoke test
python scripts/v1_smoke_test.py --rpc http://localhost:5004

# 6. 启动 MCP Server（供 Claude Code 调用）
FDTD_RPC_URL=http://localhost:5004 python -m src.server
```
