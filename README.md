# Lumerical FDTD 自动化开发

## 项目用途

本项目用于开发 Lumerical FDTD/FDE/EME 光学仿真器的自动化脚本和工具链。通过 Python `lumapi` 接口驱动 Lumerical 求解器，实现参数化扫描、优化、版图生成和结果后处理的自动化流程，减少手动 GUI 操作的重复劳动，提高光子器件设计的迭代效率。

典型应用场景包括但不限于：光波导模式求解、光栅耦合器优化、微环谐振器设计、MMI 分束器、逆向设计等。

## 当前状态

- 阶段：MVP 验证完成，通用建模能力补全中
- 最近更新：2026-06-18 — Git 初始化，知识库扩充（3 份 Lumerical 参考文档），Windows RPC Server 通用端点补丁已应用（待重启验证）
- 主要下一步：
  - **阻塞**：Windows 本地重启 RPC Server（补丁已写入，需 `.bat` 方式重启）
  - 验证 11 个新端点 → Mac RPC Client 补方法 → MCP Server 接线
  - MCP Server 接入 Claude Code（创建 `.mcp.json`）

## 核心文档

- `AGENTS.md`：项目专属代理规则。
- `REQUIREMENTS.md`：目标、范围、非目标和验收标准。
- `TECH_STACK.md`：技术栈、命令、服务和依赖。
- `DEV_LOG.md`：按日期记录的开发日志。
- `PITFALLS.md`：项目专属错误和修复方案。
- `SOP.md`：项目内可重复执行的流程。
- `RETROSPECTIVE.md`：复盘记录和可复用经验。
