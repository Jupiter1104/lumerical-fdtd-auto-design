# 开发日志

这个文件用于按日期记录项目开发过程。

## 条目格式

```md
## YYYY-MM-DD - 简短标题

- 目标：
- 修改：
- 验证：
- 后续：
```

## 2026-06-17 - 项目初始化

- 目标：从工作台模板创建 Lumerical FDTD 自动化开发项目。
- 修改：创建项目文件夹，填充全部 8 个核心文档，在 WORKSPACE.md 中登记。
- 验证：目录结构完整，文档交叉一致。
- 后续：对齐真实环境，确定架构。

## 2026-06-17 - 架构确定：Mac → SSH → Windows（已废弃）

- 目标：根据真实运行环境确定系统架构。
- 背景：Lumerical 在 Windows 11 上，单机 License，SSH/Python/lumapi 全栈就绪。
- 架构决定：采用 SSH + 远程脚本执行方案。
- 备注：此方案基于 headless 假定，已被下一版本架构取代。

## 2026-06-17 - 架构修正：Mac → HTTP RPC → Windows（GUI 可见）

- 目标：用户澄清核心需求——**Mac Agent 控制 FDTD，Windows 上实时看到 GUI**。
- 关键变化：headless → GUI 可见，SSH 短命脚本 → 持久 RPC Server，Mac 通过 HTTP 下发指令。
- 修改：重写 TECH_STACK、REQUIREMENTS、AGENTS。
- 后续：编写 rpc_server.py、smoke_test.py。

## 2026-06-18 - 外部经验注入：微信文章《Vibe Coding 驱动仿真软件》

- 目标：从社区已验证的 Lumerical 自动化实践中提取可复用经验。
- 来源：微信公众号文章（作者已验证 Lumerical FDTD/EME/FDE/INTERCONNECT + HFSS + CST 的全自动建模与优化）。
- 关键收获：
  1. **Python 路径**：必须使用 Lumerical 自带的嵌入式 Python（如 2025 R1 的 `C:\Program Files\ANSYS Inc\v251\Lumerical\python-3.9.9-embed-amd64\python.exe`），系统 Python 无法导入 lumapi。
  2. **常见陷阱**：`save()` 弹窗阻塞流程、监视器与波导重叠导致功率偏高。
  3. **Prompt 模式**：量化验收条件 + 固定文件名 + 自主迭代闭环 + 明确交付物（.fsp + 仿真报告）。
  4. **适用广度**：同方法适用于 Lumerical EME、FDE、INTERCONNECT 以及 Ansys HFSS、CST 等其他仿真软件。
  5. **自主迭代**：Agent 的完整闭环 = 写代码 → 跑仿真 → 读结果 → 发现问题 → 改代码 → 重新跑，人工只需定义问题和验收标准。
- 修改：
  - 更新 `TECH_STACK.md`：新增 Lumerical 自带 Python 路径说明。
  - 更新 `AGENTS.md`：新增"自动化仿真原则"和"已知 Agent 易犯错误"章节。
  - 填充 `PITFALLS.md`：新增 3 条已知陷阱及修复方案。
  - 更新全局 `REUSE_LOG.md`：沉淀 Vibe Coding 驱动仿真软件的通用模式。
- 验证：文档交叉一致性检查通过（TECH_STACK 的 Python 路径与 PITFALLS、AGENTS 一致）。
- 后续：
  - 在 rpc_server.py 中实现防御性处理（自动覆盖保存、监视器位置校验）。
  - 设计 MCP 工具 schema 时融入这些经验（每个工具自带验收提示）。
  - 剩余参考资料（COMSOL MCP、Lumerical 官方 API）仍需学习。

## 2026-06-18 - 外部经验注入：光子芯语《AI Agent 在光子学仿真中的边界》

- 目标：从行业综述角度理解 AI Agent + 光子学仿真的能力边界和风险。
- 来源：微信公众号「光子芯语」。
- 关键收获：
  1. **最大风险——无报错但物理错误**：网格/边界条件设置不当，仿真正常完成但结果在物理上是错的。Agent 会把错误结果当真并基于此继续优化。这是最危险的失败模式。
  2. **多物理场是增量点不是短板**：作者修正了之前"多物理场需要人工介入"的观点——不同求解器 API/数据格式各异，写胶水代码正是 Agent 的强项。本项目应预留跨求解器编排能力。
  3. **人-AI 协作模式**：人判物理、AI 执行。Agent 负责全自动执行和 API 编排，人负责定义问题、审核物理合理性。
  4. **版本迁移风险**：Lumerical 归属从 ANSYS（2025 R1 及之前）变为 Synopsys（2026 R1 起），API 路径可能变化。RPC Server 需要版本检测和适配层。
  5. **工具生态**：Claude Code / Codex / Cursor / Trae / Kimi Code 等均可用于此模式，核心逻辑相同。
- 修改：
  - `PITFALLS.md`：新增"无报错物理错误"和"版本迁移"两条陷阱。
  - `AGENTS.md`：新增"人判物理 AI 执行"核心工作模式；非目标中增加多物理场扩展预留和版本适配要求；自动化仿真原则更新为来自社区实践。
  - `REQUIREMENTS.md`：范围新增"物理合理性自动检查"和"跨求解器编排预留"；已确认新增远程桌面和版本迁移信息。
- 验证：文档交叉一致性检查通过。
- 后续：
  - 设计 RPC Server 的 `get_lumerical_path()` 版本检测逻辑。
  - 设计 MCP 工具的物理合理性检查 schema（总透过率 ≤ 1、互易性、跳变标记）。
  - 用户确认 Lumerical 具体版本号。
  - 用户发来 COMSOL MCP 和 Lumerical 官方 API 参考资料。

## 2026-06-18 - 参考架构分析：COMSOL Multiphysics MCP Server

- 目标：从成熟的仿真软件 MCP 实现中提取可直接复用的架构模式。
- 来源：[github.com/wjc9011/COMSOL_Multiphysics_MCP](https://github.com/wjc9011/COMSOL_Multiphysics_MCP)（MIT 协议，80+ MCP 工具，已生产验证）。
- 关键架构发现：
  1. **FastMCP 框架**：使用 `mcp.server.fastmcp.FastMCP`，`@mcp.tool()` 装饰器注册工具。与我们将采用的 MCP 框架一致。
  2. **Singleton SessionManager**：单例模式管理 `mph.Client` 连接和多模型追踪。我们映射为 RPC Client 单例（管理到 Windows 的 HTTP 连接）。
  3. **工具分层注册**：`register_session_tools(mcp)` → `register_model_tools(mcp)` → ... → `register_results_tools(mcp)`，每层独立文件。我们直接复用这个模式。
  4. **统一返回格式**：`{"success": True/False, ...}`，所有工具一致。已纳入我们的 RPC API 设计。
  5. **领域知识嵌入**：`knowledge/embedded.py` 包含 TOPIC_GUIDES（物理场快速指南）、TROUBLESHOOTING（5 类常见错误的因果和修复）、BEST_PRACTICES（5 个建模类别的最佳实践），全部暴露为 MCP 工具。我们映射为光子学器件模板 + Lumerical 常见陷阱。
  6. **Knowledge Prompts**：`knowledge/prompts/*.md` 存储 API 参考、物理指南、工作流教程，通过 `docs_get()` 工具暴露。我们映射为 Lumerical API 参考 + 器件设计模板 + 仿真工作流指南。
  7. **Async Solver**：`async_handler/solver.py` 用线程实现异步求解 + 进度追踪 + 取消。长 FDTD 仿真直接复用此模式。
  8. **工具命名规范**：`{domain}_{action}`（如 `geometry_add_block`、`study_solve`、`results_evaluate`）。我们的命名：`fdtd_session_start`、`fdtd_add_rect`、`fdtd_run`、`fdtd_get_result`。
  9. **版本控制**：`model_save_version()` 带时间戳保存 + `_latest` 副本。FDTD `.fsp` 文件同样需要。
  10. **Dual Interface**：所有工具函数先写成纯函数（可脱离 MCP 测试），再用 `@mcp.tool()` 包装。保证可测试性。
- 架构差异分析：
  | 维度 | COMSOL MCP | 本项目 |
  |------|-----------|--------|
  | 仿真软件位置 | 与 MCP Server 同机 | **跨机器**（Windows 远程） |
  | API 调用方式 | 直接 mph Python API | **HTTP RPC 转发** |
  | 会话管理 | mph.Client 单例 | RPC Client 单例 → Windows Flask |
  | GUI 可见性 | 未提及 | **核心需求**（GUI 不 hide） |
  | 知识库 | PDF 向量检索（chromadb） | 光子学设计规则 + Lumerical 陷阱 |
- 修改：
  - 重写 `TECH_STACK.md`：三层架构图（MCP→RPC→仿真），新增 Mac 端 MCP 模块设计树，工具命名规范。
- 验证：架构设计完整覆盖 COMSOL MCP 的 10 个最佳实践，并适配本项目的跨机器特点。
- 后续：
  - 编写 `src/server.py`（FastMCP 入口）。
  - 编写 `src/rpc_client/client.py`（Windows RPC HTTP 封装）。
  - 编写 `rpc_server.py`（Windows 端 Flask 服务）。
  - 用户发来 Lumerical 官方 API 链接。

## 2026-06-18 - 参考架构分析：Ansys Optical Automation 官方库

- 目标：学习 Ansys 官方的光学仿真自动化库设计模式。
- 来源：[github.com/ansys/optical-automation](https://github.com/ansys/optical-automation)（MIT 协议，官方维护，覆盖 Speos/Zemax/Lumerical）。
- 关键发现：
  1. **Windows Registry 检测 Lumerical 路径**：`lumerical_core/utils.py` 中 `get_lumerical_install_location(version)` 通过 `winreg` 读取 `HKEY_LOCAL_MACHINE\Software\ANSYS, Inc.\Lumerical v{version}` 注册表键获取安装路径。**比硬编码路径更健壮**，应纳入 RPC Server。
  2. **多工具互操作**：`interop_process/` 包含 BSDF、rayfile、coating 等数据格式在 Speos/Zemax/Lumerical 之间的转换器。验证了"跨求解器编排"的可行性。
  3. **应用示例结构**：`application/` 下每个脚本是独立的功能模块（`Setup Radiance Sensors.py`、`BSDF_converter_example.py`），命名直观。我们 `scripts/` 目录可借鉴此模式。
  4. **Lumerical 模块很薄**：官方库中 Lumerical 只有 `utils.py`（路径检测），主要自动化在 Speos。说明 Lumerical 的 Python API 自动化仍在社区驱动阶段，我们的项目有先发价值。
- 修改：
  - `PITFALLS.md`：更新 Python 路径检测方案，从硬编码改为注册表查询 + 硬编码回退。
  - `TECH_STACK.md`：Windows 端新增 Lumerical 路径自动检测逻辑说明。
- 后续：将 `get_lumerical_install_location()` 模式实现到 `rpc_server.py` 启动逻辑中。

## 2026-06-18 - 首版代码实现

- 目标：基于全部参考资料，实现最小可跑版本（MVP）。
- 修改：
  - **`rpc_server.py`**（Windows 端，300+ 行）：Flask RPC Server，包含 SessionManager 单例、12 个 API 端点（health/status/session start/stop/file save/load/eval/getv/setv/run/getresult/getelectric/geom addfdtd/addrect/addcircle）。使用 PyLumerical 自动发现，支持系统 Python。
  - **`src/rpc_client/client.py`**（Mac 端，150+ 行）：RpcClient HTTP 封装，统一返回格式 `{"success": bool, ...}`，14 个方法。
  - **`src/server.py`**（Mac 端，50+ 行）：FastMCP 入口，注册 6 个工具模块 + 知识库模块。
  - **`src/tools/session.py`**（6 个工具）：fdtd_session_start/stop/status/eval/getv/setv。
  - **`src/tools/model.py`**（2 个工具）：fdtd_save/load。
  - **`src/tools/geometry.py`**（3 个工具）：fdtd_add_fdtd_region/add_rect/add_circle。
  - **`src/tools/simulation.py`**（3 个工具）：fdtd_run/get_result/get_electric。
  - **`src/tools/analysis.py`**（2 个工具）：fdtd_sweep（参数扫描）、fdtd_physical_check（物理合理性检查）。
  - **`src/tools/export_.py`**（2 个工具）：fdtd_export_gds/export_data。
  - **`src/knowledge/embedded.py`**（200+ 行）：光子学领域知识 — 4 组器件模板（MMI/waveguide/grating/ring）、5 类故障排除、5 类最佳实践。4 个 MCP 工具。
  - **`src/knowledge/prompts/lumerical_api.md`**：Lumerical FDTD Python API 快速参考。
  - **`src/knowledge/prompts/workflow.md`**：FDTD 仿真工作流指南（含 SOI waveguide 和 MMI 1x2 专项指导）。
  - **`scripts/smoke_test.py`**（6 项测试）：健康检查→启动会话→eval 命令→状态→简单仿真→停止。
  - **`SOP.md`**：重写为 6 条 SOP（Windows 搭建/Mac 搭建/启动 RPC/端到端验证/新建脚本/交付）。
- 总计：18 个 MCP 工具 + 4 个知识库工具 = **22 个工具**，覆盖完整仿真流程。
- 验证：代码结构完整，待 Windows 环境实测。
- 后续：
  - 在 Windows 上测试 `rpc_server.py`。
  - Mac 端运行 `scripts/smoke_test.py`。
  - 编写第一个真实器件脚本（如 waveguide mode sweep）。
  - 编写 MCP 配置文件（`.mcp.json` / `opencode.json`）。

## 2026-06-18 - 首版代码与跨平台联调实战

- 目标：与 Windows 端实际 RPC Server 联调，验证 Mac→Windows FDTD 控制链路。
- 实际 Windows 环境：
  - **Lumerical v242**，使用自带 Python `F:\Program Files\Lumerical\v242\python\python.exe`（非 PyLumerical）
  - **MATLAB R2024b Engine** 用于 Phase 4 后处理
  - **RPC Server** 是 metasurface 超表面扫参流水线（4 阶段：生成 .fsp → 并行求解 → S 参数提取 → MATLAB 热力图）
  - **FDTD 生产模式 headless**（`hide=True`），因批量 load 在 GUI 模式下内存碎片化
- 通信链路：Mac → SSH Tunnel (L 5002→localhost:5002) → Windows RPC Server
- 联调中发现并修复的 bug（用户侧）：
  1. **Sweep 卡死**：`fdtd.load()` 在脏会话中阻塞。修复：Phase 1 循环内加 `fdtd.clearjobs()`。
  2. **0 valid / 4 missing**：headless GPU 求解器需要 express mode，但 `load(template)` 覆盖了模板外的 `setnamed`。修复：把 `setnamed("FDTD", "express mode", 1)` 移到循环内，每次 load 后重新设置。
- 端到端测试结果：**4/4 有效，0 缺失，Phase 3 耗时 1.4s** ✅
  6/7 项 smoke test 通过（Session close 超时属已知锁争用，不影响功能）
- Mac 端代码对齐：
  - `src/rpc_client/client.py`：重写为实际 API（`ok` 格式、sweep 端点）
  - `src/tools/session.py`：`fdtd_health/session_start/session_close`
  - `src/tools/simulation.py`：`fdtd_sweep_config_get/set`、`fdtd_sweep_run/status/monitor`
  - `src/tools/analysis.py`：`fdtd_results_list/download`
  - `scripts/smoke_test.py`：匹配实际 API，自动跳过已建 session
- 后续：
  - Windows 恢复后用端口 5001（当前用 5002 绕过幽灵进程）
  - Session close 锁争用修复
  - MCP Server 对接 Claude Code / Hermes

## 2026-06-18 - 技术栈升级：采用官方 PyLumerical（ansys-lumerical-core）

- 目标：将 Windows 端从"嵌入式 Python + 原始 lumapi"升级为官方 PyLumerical。
- 来源：[github.com/ansys/pylumerical](https://github.com/ansys/pylumerical)（Ansys 官方，MIT 协议，PyPI 发布）。
- 关键发现：
  1. **`ansys-lumerical-core` 是官方 Python 封装**：`pip install ansys-lumerical-core` → `import ansys.lumerical.core as lumapi`。PyPI 上直接安装，不需要嵌入式 Python。
  2. **自动发现链**：`LUMERICAL_HOME` env var → Windows Registry (`SOFTWARE\ANSYS, Inc.\Lumerical`) → 文件系统搜索（`C:\Program Files\Lumerical\`、`C:\Program Files\Ansys Inc\Lumerical`）→ `/opt/lumerical/`（Linux）。版本自动匹配最新。
  3. **上下文管理器**：`with lumapi.FDTD(hide=False) as fdtd:` — 自动清理会话，原生支持 GUI 可见/隐藏。
  4. **Pythonic API**：`fdtd.addfdtd(x=0, x_span=8e-6, ...)`、`fdtd.addgaussian(properties=OrderedDict(...))`、`fdtd.run()`、`fdtd.getelectric("monitor")`。
  5. **多求解器支持**：FDTD、MODE、DEVICE、INTERCONNECT 全部可用。
  6. **内置 lumopt2**：逆向设计优化包直接内置。
  7. **依赖**：`numpy>=1.26`、`scipy>=1.10`、`matplotlib>=3.10`、`autograd>=1.6`。
- **对项目的根本影响**：
  - Windows RPC Server 不再需要嵌入式 Python → 系统 Python + `pip install ansys-lumerical-core` 即可。
  - 路径管理从"硬编码 + 注册表拼接"简化为"自动发现 + `LUMERICAL_HOME` 回退"。
  - RPC Server 的 `lumapi` 会话管理可复用 PyLumerical 的 context manager 模式。
  - API 风格从原始 `lumapi.eval()` 升级为 Pythonic 方法调用。
- 修改：
  - `TECH_STACK.md`：架构图、Windows 端技术栈、命令、环境变量全面更新。
  - `PITFALLS.md`：Python 路径问题的根因和修复从"嵌入式 Python"改写为"使用 PyLumerical"，标注为已解决。
- 验证：PyLumerical 是 PyPI 发布的官方包，与所有 Lumerical 2022 R1+ 兼容。
- 后续：
  - Windows 端 `pip install ansys-lumerical-core`。
  - 基于 PyLumerical 的 context manager 模式编写 `rpc_server.py` 会话管理。
  - 全部参考资料学习完毕，准备编码。

## 2026-06-18 - 项目版控 + 知识库扩充 + 终极目标差距分析 + Step 1 启动

- 目标：
  1. Git 初始化，做好版本管理。
  2. 学习新增的三份 Lumerical 参考文档。
  3. 评估"Mac 发号施令→自主建模→自主仿真→扫参→MCP 可移植"的完整度差距。
  4. 开始执行补全计划 Step 1（Windows RPC Server 加通用 lumapi 端点）。
- 修改：
  - **Git init**：`git init` + `.gitignore`，2 次提交：
    1. `2e73ce6` 初始提交（26 文件，2582 行）
    2. `8abc719` 知识库新增（3 文件，1742 行）
  - **知识库扩充**（用户新增 3 个参考文档）：
    - `lumerical_command_index.md`（26KB）：完整 Script/Python API 命令索引，含使用/禁用场景、常见坑、官方 URL。
    - `lumerical_fdtd_automation_manual.md`（32KB）：AI Agent 控制 FDTD 工程手册，7 层架构图、对象速查、Agent 操作规范、失败分类、错误排查。
    - `source_map.md`（20KB）：官方文档资料地图，按优先级（P0/P1/P2）整理的 URL 索引。
  - **差距分析**：写定了 5 步补全计划 → `plans/distributed-inventing-pixel.md`。
    - 完成度：Mac 发号施令 80% | 自主建模 0% | 自主仿真+扫参 90% | MCP 可移植 40%
  - **Step 1 实施（Windows RPC Server 补丁）**：
    - 从 Windows 拉取实际 `rpc_server.py`（415 行，全局变量模式）。
    - 编写补丁脚本 `patch_rpc.py`，参考仓库内 `rpc_server.py` 的 11 个通用端点设计，转换为 `ok` 格式。
    - 通过 SSH stdin 方式执行补丁（避开此前 heredoc 引号地狱）：**补丁成功**！
    - Windows 文件状态：`rpc_server.py` 636 行（+221 行），语法检查通过，`.bak` 备份已生成。
    - **重启受阻**：Windows SSH 会话不支持 `start /MIN`（无桌面 console），多次尝试后旧进程未杀干净，端口 5003 被多进程抢占。
  - **更新 `DEV_LOG.md`**：追加本次开发记录。
  - **TECH_STACK.md**：RPC API 端点表已由上次 neat-freak 更新，无需额外修改。
- 关键教训（来自重启失败）：
  1. **SSH + `start /MIN` 不可靠**：Windows OpenSSH 服务以非交互会话运行，`start` 命令需要桌面 session。
  2. **进程残留**：`taskkill /F` 杀掉的 Python 进程可能被父进程或 Job Manager 自动重启。
  3. **技术路线反思**：RPC 架构本身没问题（持久会话是必需），但**部署更新方式**需要改进——建议改为 git pull + 本地 .bat 重启，而非 Mac SSH 远程折腾。
- 验证：
  - Git log：2 次提交，无未追踪文件（除 `Dephasing.svg`）。
  - Windows 端 `rpc_server.py`：`/eval` 和 `_rpc_eval` 字符串确认存在，636 行，语法 OK。
  - 健康检查仍返回旧数据（旧进程抢占端口）。
- 后续（下次继续）：
  - **最高优先**：在 Windows 本地用 `.bat` 重启 RPC Server（非 SSH remote）。
  - 验证 11 个新端点（curl 逐个测试）。
  - Step 2：Mac RPC Client 补方法。
  - Step 3：MCP Server 接线 geometry/model/export。
  - Step 4：创建 `.mcp.json`。

## 2026-06-18 - 迁移旧 Autosweep 生产经验到新 RPC 项目

- 目标：把旧项目经过真实 9/25/49 点及长流程验证的可靠性经验补入新项目文档，作为后续开发约束。
- 修改：
  - `AGENTS.md`：增加结构化计划、`plan/mock/real`、真实运行审批、持久 job/task、异步、恢复、质量门和 evidence-first 规则。
  - `REQUIREMENTS.md`：增加计划编译、作业持久化、审批、质量报告、幂等恢复等范围和验收标准。
  - `TECH_STACK.md`：补充 RPC API v1 契约、job/task 目录、运行模式和审批模型。
  - `SOP.md`：新增自然语言到真实仿真、失败恢复、RPC/MCP 契约变更流程。
  - `PITFALLS.md`：记录契约漂移、内存作业、阻塞长调用、全量模型回传和自动扩大扫描风险。
  - `RETROSPECTIVE.md`、`README.md` 和 MCP 工作流提示同步更新。
- 验证：文档路径、术语和现有代码状态交叉检查；未运行真实 FDTD。
- 后续：按文档顺序先统一 API v1 和测试，再实现持久 job/task 状态机。

## 2026-06-18 - 完成 RPC API v1 与离线契约测试

- 目标：统一通用 Windows Server、Mac `RpcClient` 与 MCP 包装的路由、响应和错误语义；不实现持久 job/task。
- 修改：
  - `rpc_server.py`：增加 `create_app()` 和 fake backend 注入；lumapi 延迟加载；统一 `ok`/结构化 error；新增 v1 路由；旧路由作为带弃用元数据的薄别名。
  - `src/rpc_client/client.py`：补齐 model/debug/simulation/geometry 方法；统一连接、超时、HTTP、非 JSON 和下载错误；超时明确标记远端状态未知。
  - `src/server.py`：注册 model、geometry、export 模块；修正 export 的 `ok` 判断。
  - `tests/`：增加 Server、Client 和 MCP 注册三层离线检查。
  - `requirements-dev.txt`：记录 Mac 离线测试依赖。
- 验证：
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`60 passed`。
  - `import rpc_server; import src.server`：在无 lumapi 的 Mac 上通过。
- 未验证：Windows 本地实际 lumapi/FDTD 会话和已部署 sweep Server；必须通过 git pull + 本地 `.bat` 重启后做最小真实 smoke。
- 下一步：Windows 验证通过后，实现落盘 job/task 状态机与 `plan/mock/real`。

## 2026-06-18 - Windows v1 常驻服务与 smoke 联调

- 目标：在不影响旧 `5003` sweep 服务的前提下，用新 clone 目录验证仓库内 API v1。
- 修改：
  - 新增 `scripts/windows/manage_rpc.ps1` 与 `.bat` 薄入口，默认管理 `127.0.0.1:5004`。
  - 管理脚本使用 PID 文件、日志目录、健康检查和 `pythonw.exe` 常驻启动，避免批处理窗口关闭时杀掉服务。
  - 新增 `scripts/v1_smoke_test.py`：health → GUI session → 最小几何 → 保存 `.fsp` → 旧 `/session/stop` 兼容 → final health。
  - 新增 `docs/RPC_API_V1.md` 和 `docs/WINDOWS_RUNBOOK.md` 作为接手者入口。
- 验证：
  - Mac 离线：`.venv/bin/python -m pytest -q`，`65 passed`。
  - Windows：`0cdf639` 已同步到 `F:\lumerical-fdtd-auto-design\fdtd-auto-design`，用户本地重启后 `5004` health 通过。
  - 真实 smoke 已通过 GUI session、status、FDTD region、silicon rectangle 和 model save，生成 `smoke-output\rpc_v1_smoke_20260618_180752.fsp`。
  - 失败点收窄为旧 `/session/stop` → raw lumapi `fdtd.close()` 不返回；仓库已加入 close detach/timeout 修复。
  - Windows 同步并本地重启后，完整 v1 smoke 通过，生成 `smoke-output\rpc_v1_smoke_20260618_181844.fsp`。
- 后续：
  - 设计并实现持久 job/task 状态机。

## 2026-06-18 - 持久 job/task 状态机第一版

- 目标：让新 `5004` API v1 具备落盘 job/task、幂等、审批和 resume 地基。
- 修改：
  - 新增 `src/job_store.py`，负责 `jobs/` 目录、manifest/status/task/summary、幂等索引和 resume 选择。
  - `rpc_server.py` 增加 `/jobs/plan`、`/jobs/start`、`/jobs/<job_id>`、`/jobs/<job_id>/tasks`、`/jobs/<job_id>/resume`。
  - `RpcClient` 增加 job helper 方法。
- 验证：
  - `.venv/bin/python -m compileall rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`81 passed`。
  - Windows `5004` 同步到 `74d1274` 并由本地 `restart_rpc.bat` 重启后，真实 `/jobs/start` `geometry-smoke` 通过：
    - `job_id`: `job_20260618_184622_geometry_smoke`
    - `state`: `succeeded`
    - task 计数：`1 succeeded / 0 failed`
    - 产物：`F:\lumerical-fdtd-auto-design\fdtd-auto-design\jobs\job_20260618_184622_geometry_smoke\models\task_0001.fsp`（462512 bytes）
    - 收尾状态：`/status` 返回 `connected=false`，说明短 job 已释放会话
- 后续：
  - 将旧 sweep/后处理接入持久 job/task，并补质量报告和 evidence-first 结果回传。

## 2026-06-18 - 接入 metasurface sweep job evidence

- 目标：把旧 `5003` Autosweep 的 sweep/后处理能力接到新 `5004` 持久 job/task 状态机，并补质量报告和 evidence-first 回传。
- 修改：
  - 新增 `metasurface-sweep` job 类型。
  - 新增 `src/sweep_job.py`，负责 sweep task 构建、mock artifact、`5003` 桥接、quality report 和 evidence index。
  - `summary.json` 自动汇入 `quality_report.json` 和 `evidence/index.json`。
  - `rpc_server.py` 的 real sweep 通过 `FDTD_SWEEP_RPC_URL` 桥接旧 `5003` baseline。
- 验证：
  - `.venv/bin/python -m compileall rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`91 passed in 14.79s`。
  - Windows 待同步并重启后验证 `mock metasurface-sweep` 和短 `real metasurface-sweep` smoke。
- 后续：
  - 把旧 sweep 内部 sample 映射为逐 task，实现 sample-level resume。
