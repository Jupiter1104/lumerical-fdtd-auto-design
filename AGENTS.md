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
- **非目标**：不做 RPC Server 公网暴露/强安全认证；不做多机集群调度。
- **语言**：代码注释和变量名使用英文；文档正文使用中文。
- **交付前检查**：每个脚本必须含最小可运行示例，在 `DEV_LOG.md` 中记录运行结果。
- **Headless 必查**：`clearjobs()` 在 sweep 前；`express mode` 在每次 `load()` 后 `save()` 前设置。违反即 0 valid。

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

## 验证

常见改动需要执行的检查：

```bash
# === Windows 端 ===

# 1. 验证 lumapi 可用
F:\Program Files\Lumerical\v242\python\python.exe -c "import lumapi; print('OK')"

# 2. 启动 RPC Server
F:\Program Files\Lumerical\v242\python\python.exe rpc_server.py --port 5003

# 3. 本地验证
curl http://localhost:5003/health

# === Mac 端 ===

# 4. 建立 SSH 隧道
ssh -L 5003:localhost:5003 32482@192.168.31.26

# 5. 端到端 smoke test
python scripts/smoke_test.py --rpc http://localhost:5003

# 6. 启动 MCP Server（供 Claude Code 调用）
FDTD_RPC_URL=http://localhost:5003 python -m src.server
```
