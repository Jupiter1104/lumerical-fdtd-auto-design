# Lumerical FDTD 自动化开发

## 项目用途

本项目用于开发 Lumerical FDTD/FDE/EME 光学仿真器的自动化脚本和工具链。通过 Python `lumapi` 接口驱动 Lumerical 求解器，实现参数化扫描、优化、版图生成和结果后处理的自动化流程，减少手动 GUI 操作的重复劳动，提高光子器件设计的迭代效率。

典型应用场景包括但不限于：光波导模式求解、光栅耦合器优化、微环谐振器设计、MMI 分束器、逆向设计等。

## 当前状态

- 阶段：MVP 验证完成，通用建模能力补全中
- 文档基线：2026-06-18 — API v1、Windows 本地重启脚本、真实 smoke 和短 job 流程已对齐到代码
- 已验证基础：Mac → SSH Tunnel/HTTP → Windows v242 → 4 点真实 sweep，结果 4/4 valid
- 当前代码状态：仓库内通用 `rpc_server.py`、Mac `RpcClient` 和 MCP 已统一为 API v1；Windows `5004` 已完成真实 2×2 原生 `metasurface-sweep` 验证，结果 4/4 valid、quality `pass`。新服务默认端口已提升为 `5000`；`metasurface-sweep` 由 `/jobs/start` 异步返回 `202 + job_id`，包含 Phase 1-4、quality report 和 evidence index。
- 注意：旧 Autosweep 只作为历史 baseline，不再是新 `rpc_server.py` 的运行时依赖。
- MCP Server 已新增 `/jobs/*` 工具：`fdtd_job_plan/start/status/tasks/resume`，以及 metasurface 便捷工具 `fdtd_metasurface_sweep_plan/start`。旧 `fdtd_sweep_*` 仅保留为 legacy compatibility。
- SimulationPlan v0.1 已支持 metasurface unit-cell：默认值披露、任务预算、SHA-256 指纹、Plan 审批、mock 编译和 MCP 执行。
- mock 前必须批准默认值和假设；real 还需要匹配同一 Plan 指纹的真实运行审批与模板契约。
- real metasurface resume 会重新校验模板 SHA-256；模板变化时拒绝恢复。
- 当前 checkpoint：Stage C2 real result review。C1 已完成真实 2×2 SimulationPlan run，job `job_20260619_213418_metasurface_sweep` 为 `succeeded`，4/4 task 成功，quality `pass`。C2 已将 evidence-only 结果复制到本地 git-ignored `runtime/reviews/` 并生成 `review.json` 与 `real_2x2_review.md`。软件链结论为 `pass`；物理结论仍需人工审核，且 2×2 phase span 约 `1.3273 rad`，不足以作为最终 2π phase library。

## 核心文档

- `AGENTS.md`：项目专属代理规则。
- `REQUIREMENTS.md`：目标、范围、非目标和验收标准。
- `TECH_STACK.md`：技术栈、命令、服务和依赖。
- `DEV_LOG.md`：按日期记录的开发日志。
- `PITFALLS.md`：项目专属错误和修复方案。
- `SOP.md`：项目内可重复执行的流程。
- `RETROSPECTIVE.md`：复盘记录和可复用经验。
- `docs/RPC_API_V1.md`：API v1 路由、错误语义和兼容别名。
- `docs/WINDOWS_RUNBOOK.md`：Windows 本地启动、同步、smoke 与故障排查。
- `templates/metasurface/README.md`：原生 metasurface sweep 模板安装与结构要求。

## 目标操作链

```text
自然语言需求
  -> 结构化 SimulationPlan
  -> plan 校验与成本预览
  -> 可选 mock 软件链验证
  -> 明确批准 real
  -> Windows 异步 job/task 执行
  -> 结果提取与质量报告
  -> 人工物理审核
  -> 建议下一轮，不自动扩大计算
```
