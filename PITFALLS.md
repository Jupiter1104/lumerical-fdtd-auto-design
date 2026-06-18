# 项目踩坑

这个文件用于记录项目专属错误、缺陷和修复方案。

## 条目格式

```md
## YYYY-MM-DD - 简短标题

- 现象：
- 根因：
- 修复：
- 预防：
```

## 2026-06-18 - Lumerical 自动保存弹出交互窗口（来源：微信文章经验）

- 现象：脚本调用 `save()` 时 Lumerical 弹出文件已存在的确认对话框，阻塞自动化流程。
- 根因：Lumerical 默认在文件覆盖时会弹窗确认。
- 修复：使用固定文件名并在保存前先 `switchtolayout()` 确认当前视图；必要时在 lumapi 中设置 `setnamed("::model", "save on exit", 0)` 关闭退出保存提示。
- 预防：所有仿真脚本统一用固定文件名 + 路径管理，写入 RPC Server 的 `save()` 封装中做自动覆盖处理。

## 2026-06-18 - 监视器与波导结构重叠导致功率读数偏高（来源：微信文章经验）

- 现象：仿真结果中的透射功率异常偏高，与物理预期不符。
- 根因：FDTD 频域监视器（frequency-domain monitor）的尺寸过大或位置不当，与相邻波导或其他结构重叠，监视器截获了非目标路径的场。
- 修复：缩小监视器截面尺寸，仅覆盖目标波导截面，确保不与相邻结构重叠。在脚本中添加监视器位置和大小的自动校验。
- 预防：建模完成后，脚本应输出监视器坐标供人工或自动检查；RPC Server 可在仿真前做基本几何检查。

## 2026-06-18 - Lumerical Python 解释器路径（已确认：v242 嵌入式 Python）

- 现象：系统 Python 无法 `import lumapi`。
- 根因：`lumapi` 模块仅在 Lumerical 安装目录的 `api/python` 子目录下可用，需通过 `sys.path.append` 注入。
- **实际方案（联调确认）**：使用 Lumerical v242 自带的嵌入式 Python。
  - Python 路径：`F:\Program Files\Lumerical\v242\python\python.exe`
  - API 路径：`F:\Program Files\Lumerical\v242\api\python`（在 `rpc_server.py` 顶部通过 `sys.path.append` 注入）
  - MATLAB Engine 安装在 Lumerical Python 中（`pip install matlab.engine`）
- 预防：RPC Server 顶部硬编码 `LUMAPI_PATH`，启动脚本使用完整 Python 路径。

## 2026-06-18 - 无报错但结果物理错误——最危险的失败模式（来源：光子芯语文章）

- 现象：仿真正常完成、无任何 error/warning，但结果（损耗、分束比、场分布等）在物理上是错误的。Agent 将错误结果当作真实结果，基于此继续优化，浪费大量计算资源。
- 根因：
  - 网格步长设置不当（太粗导致数值色散，但 FDTD 不会报错）。
  - 边界条件选择不当（如该用 PML 的地方用了金属边界，产生非物理反射）。
  - 光源模式与波导模式不匹配，激发高阶模或辐射模。
  - AI 不具备物理直觉，无法"感觉"到 S 参数曲线上的 ripple 是网格反射伪影还是真实的谐振。
- 修复：
  - MCP 工具层加入**物理合理性检查**：仿真完成后自动做基础校验（如无源器件总透过率应 ≤ 1、互易性检查等）。
  - 关键仿真结果自动生成可视化图表（S 参数曲线、场分布图），方便人工快速扫一眼判断。
  - 对优化迭代中的异常跳变（如损耗突然从 0.3dB 跳到 3dB）自动标记并暂停，要求人工确认。
- 预防：
  - **人工兜底原则**（写入 AGENTS.md）：Agent 负责执行，人负责判断物理正确性。交付前必须有人工审核步骤。
  - 每个仿真任务在首次运行时应使用保守的高精度设置（mesh accuracy ≥ 3）建立 baseline，后续优化可适当降低精度。
  - 积累已知-good 的仿真配置模板（网格、边界条件、光源设置），新任务从模板出发而非从零开始。

## 2026-06-18 - Lumerical 版本迁移注意：ANSYS → Synopsys

- 背景：2026 R1 起 Lumerical 归属 Synopsys，安装路径可能从 `ANSYS Inc` 变为其他。
- 当前版本：**v242 (2024 R2)**，仍属 ANSYS 体系，路径 `F:\Program Files\Lumerical\v242\`。
- 预防：升级 Lumerical 版本时需同步更新 `rpc_server.py` 顶部的 `LUMAPI_PATH` 和 Python 路径。

## 2026-06-18 - 脏会话导致 sweep 卡死（来源：联调实测）

- 现象：`fdtd.load(template)` 在 Phase 1 循环中无限阻塞，sweep 永远停在 "generating .fsp files"。
- 根因：前一次扫参遗留的作业队列未清理，FDTD 会话处于脏状态。`fdtd.load()` 在脏会话中等待前一个作业状态，但该作业已不存在。
- 修复：Phase 1 循环开始时调用 `fdtd.clearjobs()` 清理作业队列。
- 预防：每次 sweep 开始前显式清理会话状态（clearjobs + switchtolayout）。写入 RPC Server 代码规范。

## 2026-06-18 - Load(template) 覆盖 express mode / resource 不匹配导致无效

- 现象：Phase 3 报告 "0 valid, 4 missing"，所有仿真结果无效。GPU headless 模式下特别明显。
- 根因：每次 `fdtd.load(template)` 会重新加载模板文件，模板里保存的 FDTD 设置会覆盖之前 setnamed 的值；同时 `express mode` 必须和 resource 匹配，CPU 模板/CPU resource 应为 `0`，GPU 才应为 `1`。
- 修复：把 `setnamed("FDTD", "express mode", EXPRESS_MODE)` 移到循环内，`switchtolayout()` 之后、`save()` 之前。当前 CPU sweep 默认 `EXPRESS_MODE=0`。
- 预防：**模板 load 后必须按 resource 重新设置运行时参数**。模板文件保存的是设计基准，不保存运行时优化参数。在 SOP 中写入此规则。

## 2026-06-18 - SSH 远程部署 RPC Server 代码不可靠（来源：联调实测）

- 现象：Mac 端通过 SSH 修改 Windows `rpc_server.py` 后，无法可靠重启服务。
- 根因：
  1. Windows OpenSSH 服务以非交互会话运行，`start /MIN` 命令需要桌面 session 才能创建窗口/进程。
  2. `taskkill /F` 杀掉的 Python 进程可能被父进程或系统自动重启。
  3. 多次启动失败后同一端口（5003）被多个僵尸进程抢占，新进程无法监听。
  4. SSH heredoc/引号嵌套在 Windows bash 环境下极容易出错。
- 修复（建议方案，待下次验证）：Windows 端配好 git，通过 `git pull` 拉取最新代码 + 本地 `.bat` 脚本重启 RPC Server，而非 Mac SSH 远程推送。
- 预防：
  - **Windows RPC Server 代码更新统一走 git pull + 本地 .bat 重启**，避免 SSH 远程折腾。
  - Mac 端只通过 curl 验证端点，不通过 SSH 修改 Windows 文件。
  - 在 `SOP.md` 中新增"更新 RPC Server 代码"流程。

## 2026-06-18 - RPC Server、Client 和 MCP 契约漂移

- 现象：Windows Server 使用 `success` 和 `/session/stop`、`/sim/*`，Mac Client 按 `ok` 和 `/session/close`、`/sweep/*` 调用；模块分别能导入，但端到端不可用。
- 根因：先分别实现各层，没有唯一 API 契约和跨层测试。
- 修复：已冻结 RPC API v1，统一 `ok` envelope、路由和错误类型；Client 将超时标记为远端状态未知；旧路由只在 Server 保留薄兼容别名。
- 预防：任何端点变更必须同时更新 Server、Client、MCP wrapper、smoke test，并运行 fake-server 契约测试。

## 2026-06-18 - 顶层导入 lumapi 阻断 Mac 离线测试

- 现象：仅导入 `rpc_server.py` 就因 Mac 没有 `ansys.lumerical.core`/`lumapi` 而失败，无法运行 Flask 契约测试。
- 根因：模块加载阶段立即导入 Windows 专属仿真后端。
- 修复：把 lumapi 导入延迟到 `/session/start`，并通过 `create_app(session_manager)` 注入 fake backend。
- 预防：平台专属或重型依赖必须在实际使用点加载；HTTP 契约层应可脱离真实求解器测试。

## 2026-06-18 - raw v242 lumapi 没有 `fdtd.getversion()` Python 方法

- 现象：FDTD 实例已创建，但 `/session/start` 因 `AttributeError: 'FDTD' object has no attribute 'getversion'` 返回 500。
- 根因：raw v242 lumapi 并非所有 script command 都映射为 Python 方法。
- 修复：版本读取优先调用 Python 方法；不存在时执行 `__rpc_version=getversion;` 并用 `getv()` 读取。版本探测失败只返回 `unknown`，不使会话启动失败。
- 预防：对 raw lumapi 命令先验证 Python 映射；非核心元数据探测不得破坏已成功建立的求解器会话。

## 2026-06-18 - raw lumapi `fdtd.close()` 窗口已关但 API 不返回

- 现象：v1 smoke 已完成 GUI 启动、建模和保存 `.fsp`，调用旧 `/session/stop` 后 FDTD 窗口关闭，但 HTTP 请求 60 秒超时，后续 `/status` 也被卡住。
- 根因：raw lumapi `fdtd.close()` 可能在窗口关闭后仍不返回；若 RPC 持锁同步等待 close，会把服务线程和会话状态一起拖住。
- 修复：`/session/close` 先摘除 `_fdtd` 和模型路径，再后台调用 `fdtd.close()`；超过短超时返回 `close_state=timed_out`，保持 RPC 服务可用。
- 预防：释放外部 GUI/仿真后端时不要在请求线程内无限等待；close/cleanup 应可超时、可记录、可恢复。

## 2026-06-18 - 批处理窗口关闭导致 RPC 进程退出

- 现象：`restart_rpc.bat` 启动时健康检查通过，但用户关闭批处理窗口后 `5004` 立即不可连接，PID 文件残留。
- 根因：用控制台 `python.exe` 从批处理窗口启动 Flask，进程生命周期受控制台窗口影响。
- 修复：Windows 管理脚本改为 `.bat` 薄入口 + `manage_rpc.ps1`，后台服务优先使用 Lumerical 同目录 `pythonw.exe`，并自动清理陈旧 PID。
- 预防：需要常驻的 Windows GUI/仿真控制进程不要直接挂在交互 `.bat` 控制台下；用 `pythonw.exe` 或正式服务管理器承载。

## 2026-06-18 - 长任务只保存在进程内存

- 现象：Flask 重启、Windows 重启或线程异常后，Agent 不知道哪些样本已完成，也无法可靠 resume。
- 根因：把后台线程和内存字典当成作业系统，没有逐 job/task 落盘。
- 修复：每个 job 写 `status.json`、`summary.json`、`run.log`，每个 sample/task 写独立 JSON；模型和结果使用稳定路径。
- 预防：长任务创建时先落盘 manifest 和 task plan，再启动求解；状态接口从磁盘事实构建响应。

## 2026-06-18 - 用单次 RPC/MCP 调用等待长仿真

- 现象：调用超时或 Agent 上下文被阻塞，但 Windows 求解可能仍在运行，导致误判失败和重复启动。
- 根因：没有区分“启动作业”和“等待作业完成”。
- 修复：启动接口立即返回 `job_id/task_id`，使用轻量 status 轮询；HTTP 超时只表示请求状态未知。
- 预防：预计超过 30 秒的操作一律异步；重复请求使用幂等键。

## 2026-06-18 - 全量回传逐点 FSP 导致传输和上下文膨胀

- 现象：大 sweep 下载数百个 `.fsp`，传输时间、磁盘和 Agent 状态输出明显膨胀。
- 根因：归档没有区分“结果证据”和“调试资产”。
- 修复：默认只回传 manifest、状态、任务 JSON、结果表、质量报告和关键图；完整 `.fsp` 归档按需开启。
- 预防：results API 提供 evidence-only 默认模式和显式 `include_models` 选项。

## 2026-06-18 - 失败后自动扩大扫描或修改求解设置

- 现象：Agent 根据 warning 直接增加任务数、改变 mesh/scheduler，计算成本失控且新旧结果不可比较。
- 根因：把“诊断建议”和“执行下一轮”合成一个动作。
- 修复：只生成结构化 next-run 建议，列出原因、配置差异、新任务数和审批要求。
- 预防：任何扩大参数空间、改变物理设置或新增真实求解都必须形成新 plan 和新审批。

## 2026-06-18 - 把历史 Autosweep baseline 当成新项目运行依赖

- 现象：新 `5004` job 服务通过 HTTP bridge 调旧 Autosweep 服务，遇到旧 lumapi stale session / RPC 健康检查不可靠时，新 job 状态也被拖成失败。
- 根因：把“历史上验证过的 4/4 sweep baseline”混同为“当前架构的运行时依赖”，导致新服务继承旧目录、旧端口、旧会话状态和旧启动脚本问题。
- 修复：`metasurface-sweep` 已改为新项目内原生 `NativeSweepRunner`，每个参数点是独立 task；旧模板只通过一次性安装脚本迁移到 `templates/metasurface/base_model.fsp`。
- 预防：当前运行文档不得指示新项目调用旧 Autosweep 端口或 `FDTD_SWEEP_RPC_URL`；历史 baseline 只能作为算法/模板来源和回归参照。

## 2026-06-18 - 真实 job 审批字段必须精确匹配

- 现象：用户已批准真实运行，但 `/jobs/start` 仍返回 `403 approval_required`。
- 根因：服务端契约要求 `approval.approved_for == "real_run"`；把字段写成更具体的 human-readable tag（如 `task10_real_2x2...`）会被视为未批准。
- 修复：真实运行请求使用：
  ```json
  {"approval": {"approved": true, "approved_for": "real_run"}}
  ```
- 预防：真实运行的上下文说明放在审批摘要和 job log，不放进 `approved_for` 字段；若要记录任务名，后续应新增独立 metadata 字段。
