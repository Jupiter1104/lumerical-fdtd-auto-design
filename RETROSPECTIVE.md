# 复盘

这个文件用于阶段复盘和记录可复用经验。

## 条目格式

```md
## YYYY-MM-DD - 复盘标题

- 有效做法：
- 无效做法：
- 可复用经验：
- 下一步调整：
```

<!-- 暂无记录，随开发推进追加 -->

## 2026-06-18 - 从旧 Autosweep 项目迁移生产经验

- 有效做法：保留新项目的 Mac MCP → HTTP RPC → Windows 持久 lumapi 会话架构；该架构比旧项目每次通过 SSH 启动脚本更适合 GUI 可见和通用建模。
- 无效做法：继续堆几何端点而不先统一 Server/Client/MCP 契约；长任务只存在内存；把 solver completed 当成物理通过。
- 可复用经验：成熟自动化的核心不是更多 API，而是可验证计划、持久 job/task、`plan/mock/real` 分级、真实运行审批、幂等恢复、质量门和 evidence-first 回传。
- 下一步调整：先完成 RPC API v1 与契约测试，再实现 job/task 状态机，之后接入 geometry/model/export 和自然语言 recipe。

## 2026-06-18 - Windows v1 smoke 前置验证

- 有效做法：先把新 v1 服务隔离到 `5004`，保留旧 `5003` sweep 环境；用离线契约测试保证 Mac 端和 Server 语义稳定。
- 无效做法：把复杂 PowerShell 逻辑写进 `.bat` 单行，错误容易被窗口吞掉；用 `python.exe` 挂在批处理窗口下不适合常驻服务。
- 可复用经验：Windows 常驻控制进程应集中到 PowerShell 管理脚本，`.bat` 只做入口；Python 后台服务优先用 `pythonw.exe`。
- 下一步调整：真实 v1 smoke 已通过；进入持久 job/task 设计。
