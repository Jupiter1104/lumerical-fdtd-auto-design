# Lumerical FDTD 自动化开发

## 项目用途

本项目用于开发 Lumerical FDTD/FDE/EME 光学仿真器的自动化脚本和工具链。通过 Python `lumapi` 接口驱动 Lumerical 求解器，实现参数化扫描、优化、版图生成和结果后处理的自动化流程，减少手动 GUI 操作的重复劳动，提高光子器件设计的迭代效率。

典型应用场景包括但不限于：光波导模式求解、光栅耦合器优化、微环谐振器设计、MMI 分束器、逆向设计等。

## 当前状态

- 阶段：MVP 验证完成，通用建模能力补全中
- 文档基线：2026-06-18 — API v1、Windows 本地重启脚本、真实 smoke 和短 job 流程已对齐到代码
- 已验证基础：Mac → SSH Tunnel/HTTP → Windows v242 → 4 点真实 sweep，结果 4/4 valid
- 当前代码状态：仓库内通用 `rpc_server.py`、Mac `RpcClient` 和 MCP 已统一为 API v1；Windows `5004` 已加载 close detach/timeout 修复和持久 `/jobs/*`。`geometry-smoke` 已真实通过；`metasurface-sweep` 已切换为新项目原生逐 sample job，包含 Phase 1-4、quality report 和 evidence index；`real metasurface-sweep` 现在由 `/jobs/start` 异步返回 `202 + job_id`
- 注意：当前仍在原生 sweep 过渡验证期。旧 Autosweep 只作为历史 baseline，不再是新 `rpc_server.py` 的运行时依赖
- 主要下一步：
  - Windows 同步并验证短 `real metasurface-sweep` 2×2 job
  - 补模板安装/指纹校验和 resume 指纹保护
  - MCP Server 接入 Claude Code（创建 `.mcp.json`）

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
