# 需求

## 目标

构建一套 **Mac 端 Agent 通过 HTTP RPC 远程控制 Windows 上 FDTD GUI** 的自动化工具链。用户在 Mac 端编写控制脚本或交互式操作，指令下发到 Windows 端的常驻 RPC 服务，由 lumapi 驱动 FDTD GUI 即时执行。用户可以**在 Windows 屏幕上实时看到 FDTD GUI 的建模、网格、仿真、结果等全部操作过程**。

## 用户

- 本项目作者：在 Mac 端做光子器件设计和脚本开发，同时能从 Windows 屏幕实时观察 FDTD GUI 的操作过程。
- 核心诉求：不需要每次手动操作 FDTD GUI，但**希望看到 GUI 上发生的事情**（建模过程、场分布动画、仿真进度等）。

## 范围

- 范围内：
  - **Windows RPC Server**：常驻进程，持有一个 lumapi 会话，打开 FDTD GUI，暴露 HTTP 接口供 Mac 调用。
  - **Mac 端控制脚本**：通过 HTTP 调用 RPC Server 的 lumapi 指令，实现完整仿真流程。
  - lumapi 指令封装：`eval()`、`setnamed()`、`getresult()` 等常用操作的 HTTP 映射。
  - 常见器件的参数化建模（波导、光栅、微环、MMI 等）。
  - 参数扫描自动化（单参数 sweep、多参数 grid search）。
  - 仿真结果提取和传输回 Mac（JSON/CSV/NPZ，或通过共享文件夹）。
  - 优化循环集成（与 `scipy.optimize` 或 `nevergrad` 对接）。
  - GDS 版图导出辅助。
  - 仿真日志和元数据管理。
  - **物理合理性自动检查**：仿真完成后自动做基础校验（总透过率 ≤ 1、互易性、异常跳变标记等）。
  - **跨求解器编排预留**：架构设计支持未来扩展至 Lumerical EME/FDE/INTERCONNECT 乃至非 Lumerical 求解器的编排。

- 范围外：
  - 其他电磁仿真工具的**首期实现**（COMSOL、CST 等）——架构预留但首版不实现。
  - Web 界面或多人协作。
  - 集群/多机并行调度（单机 license 不支持）。
  - RPC Server 做公网暴露或强安全认证。

## 验收标准

- 标准 1：Windows 端启动 RPC Server 后，FDTD GUI 出现在 Windows 桌面。Mac 端发送 `getversion()` 指令，1 秒内返回版本号。
- 标准 2：Mac 端运行一条脚本，完成"建模 → 仿真 → 提取 S 参数 → 回传结果到 Mac"全流程，全程 FDTD GUI 在 Windows 上可见每一步操作。
- 标准 3：参数扫描脚本可遍历参数空间，结果以 CSV/NPZ 格式存入 Mac 本地目录。
- 标准 4：优化脚本可与至少一种优化算法对接，在给定设计空间内自动寻找目标性能，每次迭代的建模变化在 Windows GUI 上可见。
- 标准 5：每个脚本可通过 `--help` 查看参数说明。
- 标准 6：RPC Server 已在运行时，再次启动应被拒绝并给出清晰报错。

## 已确认

- License 类型：单机用户 License（domain=0，非浮动）。
- OpenSSH Server：Windows 端已在运行。
- Windows 端环境：Python (v242 embedded) + lumapi + MATLAB R2024b 全栈就绪。
- **Lumerical 版本**：v242（2024 R2），raw lumapi，路径 `F:\Program Files\Lumerical\v242\python\python.exe`。
- **MATLAB**：R2024b Engine 已集成，Phase 4 后处理用。
- **运行模式**：headless (`hide=True`) 为生产默认；GUI (`hide=False`) 仅在 RDP 连接时可用。
- 用户看 Windows 屏幕的方式：远程桌面（RDP）为主。
- 通信方式：SSH 隧道（`ssh -L 5003:localhost:5003`）或局域网直连。
- 结果回传：HTTP `/results/<path>` 下载，已验证可用。

## 开放问题

- 问题：RPC Server 是否加通用 lumapi 端点（`/eval`, `/geom/*`），支持自然语言建模？（当前只有 sweep 端点）
- 问题：MCP Server 何时接入 Claude Code？
- 问题：扩展至更多器件类型（MMI、波导模式等）的优先级？
