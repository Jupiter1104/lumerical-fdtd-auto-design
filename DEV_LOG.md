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

- 目标：把旧 Autosweep 的 sweep/后处理能力接到新 `5004` 持久 job/task 状态机，并补质量报告和 evidence-first 回传。
- 修改：
  - 新增 `metasurface-sweep` job 类型。
  - 新增 `src/sweep_job.py`，负责 sweep task 构建、mock artifact、旧 Autosweep bridge、quality report 和 evidence index。
  - `summary.json` 自动汇入 `quality_report.json` 和 `evidence/index.json`。
  - `rpc_server.py` 的 real sweep 通过 `FDTD_SWEEP_RPC_URL` 桥接旧 Autosweep baseline；当前部署端口为 `5005`。
- 验证：
  - `.venv/bin/python -m compileall rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`92 passed in 14.81s`。
  - Windows `mock metasurface-sweep` 通过：
    - `job_id`: `job_20260618_201618_metasurface_sweep`
    - `state`: `succeeded`
    - result completeness：`4 valid / 0 missing`
    - quality conclusion：`pass`
    - evidence policy：`evidence-only`，不包含逐点模型
  - 旧 Autosweep 实际部署端口已由 `5003` 调整为 `5005`；`5004` 和 `5005` health 均通过。
  - Windows 待加载端口修正后验证短 `real metasurface-sweep` smoke。
- 后续：
  - 把旧 sweep 内部 sample 映射为逐 task，实现 sample-level resume。

## 2026-06-18 - 原生 metasurface sweep Phase 1-3 离线实现

- 目标：停止依赖旧 Autosweep RPC，先在新项目内实现逐 sample 原生生成、求解和结果提取。
- 修改：
  - `src/sweep_job.py` 将 sweep 展开为稳定的 `metasurface-sample` task 网格。
  - `src/job_store.py` 增加 `enqueue`、task 更新、运行日志和 interrupted recovery 地基。
  - 新增 `src/native_sweep.py`：Phase 1 生成逐点 `.fsp`，Phase 2 调用一次 `runjobs()`，Phase 3 逐点读取 `T` 与 `S21_Gn` 并写 `results/task_*.json`。
  - Phase 3 支持单样本失败隔离，优先读取 task 已记录的 `outputs.model_file`，缺失 `S`/提取异常只失败对应样本。
- 验证：
  - `.venv/bin/python -m pytest tests/test_native_sweep.py -q`：`7 passed`。
  - `.venv/bin/python -m pytest tests/test_job_store.py tests/test_sweep_job.py -q`：`15 passed`。
  - `.venv/bin/python -m compileall -q src/native_sweep.py tests/test_native_sweep.py`：通过。
- 后续：
  - 进入 Phase 4：CSV、质量报告和 SVG evidence；随后接 Flask 异步协调器。

## 2026-06-18 - 原生 metasurface sweep Phase 4 evidence 产物

- 目标：在新项目内完成原生 sweep 的 evidence-first 聚合，不依赖旧 MATLAB 后处理。
- 修改：
  - `src/sweep_job.py` 新增 `write_job_artifacts()`，聚合 `results/task_*.json` 为 `results/sweep_results.csv`、`results/sweep_summary.json`、`quality_report.json` 和 `evidence/index.json`。
  - 使用标准库生成 `evidence/transmission_heatmap.svg` 与 `evidence/phase_heatmap.svg`，避免新增 Windows Lumerical Python 依赖。
  - 质量报告覆盖缺样本、零有效样本、透过率越界，并固定 `requires_human_review=true`。
  - `NativeSweepRunner` 已在 phases 包含 `4` 时调用聚合，随后 `JobStore.finalize()` 将 quality/evidence 汇入 `summary.json`。
- 验证：
  - `.venv/bin/python -m pytest tests/test_sweep_job.py tests/test_native_sweep.py tests/test_job_store.py -q`：`27 passed`。
  - `.venv/bin/python -m compileall -q src/sweep_job.py src/native_sweep.py tests/test_sweep_job.py tests/test_native_sweep.py`：通过。
- 后续：
  - 接入 Flask 异步协调器，移除旧 Autosweep bridge 依赖，并恢复全量离线测试。

## 2026-06-18 - Flask `/jobs/start` 接入原生异步 sweep

- 目标：把 `real metasurface-sweep` 从旧 Autosweep bridge 切换为新项目内的 `NativeSweepRunner`，并保持长任务异步。
- 修改：
  - `rpc_server.py` 移除 `run_deployed_sweep` / `FDTD_SWEEP_RPC_URL` bridge 路径。
  - 新增 `SweepCoordinator`，同一时间只允许一个 real metasurface sweep；`/jobs/start` 先落盘 job，再返回 HTTP 202 和 `job_id`，后台线程执行原生 Phase 1-4。
  - sweep 活跃时拒绝破坏性 session/model/geometry/debug/simulation 操作，返回 `sweep_running`。
  - `mock metasurface-sweep` 保持同步执行，并补写 CSV、quality report、SVG 和 evidence index。
  - README、RPC API v1、TECH_STACK、SOP 和 workflow prompt 同步改为原生 v1 sweep 口径。
- 验证：
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`110 passed`。
  - `rg "run_deployed_sweep|FDTD_SWEEP_RPC_URL|_metasurface_sweep_executor|5005" rpc_server.py src tests`：无匹配。
- 后续：
  - 模板安装/指纹校验；同步 Windows 后在 `5004` 做真实 2×2 原生 sweep 验证。

## 2026-06-18 - 模板安装脚本与运行时指纹

- 目标：让原生 metasurface sweep 使用受控本地模板，并在每个 job manifest 中留下可审计指纹。
- 修改：
  - 新增 `scripts/windows/install_metasurface_template.ps1` 与 `.bat`，把用户指定 `.fsp` 复制到 `templates\metasurface\base_model.fsp` 并打印 SHA-256。
  - 新增 `templates/metasurface/README.md`，记录模板必需对象、安装命令和 `.fsp` 不入 Git 的约束。
  - `NativeSweepRunner` 在启动时计算模板 SHA-256、文件大小、mtime 和绝对路径，写入 `manifest.template`。
  - `JobStore.update_manifest()` 支持原子更新 manifest 顶层 metadata。
- 验证：
  - `.venv/bin/python -m pytest tests/test_native_sweep.py tests/test_job_store.py -q`：`21 passed`。
  - `.venv/bin/python -m pytest -q`：`112 passed`。
  - `git check-ignore -v templates/metasurface/base_model.fsp`：命中 `.gitignore` 的 `*.fsp`。
  - Mac 本机无 `pwsh`/`powershell`，安装脚本需在 Windows 同步后真实验证。
- 后续：
  - Windows 安装模板、重启 `5004`，执行真实 2×2 原生 sweep 验证。

## 2026-06-18 - 文档切换到原生异步 sweep 口径

- 目标：让 README、SOP、API 文档和运维手册都反映当前事实：新项目不再通过旧 Autosweep bridge 执行真实 sweep。
- 背景：
  - 旧 bridge 真实 job `job_20260618_202255_metasurface_sweep` 暴露旧 lumapi stale-session / 启动健康检查问题。
  - 架构决策：不继续修旧 RPC，把 sweep 迁入新 `5004` v1 服务，由 `NativeSweepRunner` 原生执行。
- 修改：
  - `AGENTS.md`、`REQUIREMENTS.md`、`TECH_STACK.md`、`SOP.md`、`docs/RPC_API_V1.md`、`docs/WINDOWS_RUNBOOK.md` 和 `README.md` 更新为原生逐 sample sweep、HTTP 202 异步启动、模板安装和 manifest 指纹口径。
  - `PITFALLS.md` 记录“历史 Autosweep baseline 不应作为当前运行依赖”。
- 验证：
  - 文档检查确认当前运行入口不再要求 `5005` / `FDTD_SWEEP_RPC_URL`。
- 注意：
  - 目前只完成离线和文档切换；尚未声明真实原生 2×2 sweep 已通过。

## 2026-06-18 - 修正 express mode 与 CPU/GPU resource 对应

- 目标：避免当前 CPU 模板被代码强制改成 GPU express mode，导致真实仿真无法运行。
- 背景：用户确认当前放入 Windows 项目内的 `base_model.fsp` 未勾选 express mode，resource 使用 CPU；`express mode=1` 对应 GPU，`0` 对应 CPU，不匹配会无法仿真。
- 修改：
  - `sweep.config.EXPRESS_MODE` 默认改为 `0`。
  - `NativeSweepRunner` 每次 `load()` 后按 `EXPRESS_MODE` 设置 FDTD `express mode`，默认 CPU，只有显式配置才启用 GPU/`1`。
  - 测试覆盖默认 CPU/0 和显式 GPU/1 两种路径。
  - `AGENTS.md`、`SOP.md`、`TECH_STACK.md`、`PITFALLS.md` 修正旧的“headless 必开 express mode=1”说法。
- 验证：
  - 聚焦 express-mode 测试通过；待全量验证后同步 Windows。

## 2026-06-18 - Task 9 本地验证、Windows 同步与真实 2×2 准备

- 目标：把原生异步 sweep 最新代码同步到 Windows，安装模板，重启 `5004`，完成真实 2×2 前的 mock/evidence 准备检查。
- 本地验证：
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`113 passed`。
  - `rg 'requests|run_deployed_sweep|FDTD_SWEEP_RPC_URL|127\.0\.0\.1:5005' src/sweep_job.py src/native_sweep.py rpc_server.py`：无输出。
- 同步：
  - Mac 推送到 GitHub：`44aefd6 fix: default metasurface sweep to cpu express mode`。
  - Windows `F:\lumerical-fdtd-auto-design\fdtd-auto-design` 已 `git pull --ff-only` 到 `44aefd6`。
- 模板：
  - 用户将 CPU 模板放在 Windows 项目根目录 `base_model.fsp`。
  - 已用 `scripts\windows\install_metasurface_template.ps1 -Source .\base_model.fsp` 安装到 `templates\metasurface\base_model.fsp`。
  - 模板大小：`728975` bytes。
  - SHA-256：`03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176`。
  - 用户确认模板未勾选 express mode，resource 使用 CPU；代码默认 `EXPRESS_MODE=0`。
- Windows 服务：
  - 已通过管理脚本重启 `127.0.0.1:5004`，PID `37336`。
  - `/health`：`ok=true`, `api_version=v1`, `connected=false`。
  - `/status`：`connected=false`，未占用 FDTD session/license。
- mock 2×2：
  - job_id：`job_20260618_234751_metasurface_sweep`。
  - state：`succeeded`。
  - task：`4 succeeded / 0 failed`。
  - quality：`pass`。
  - evidence：`results/sweep_results.csv`、`results/sweep_summary.json`、`quality_report.json`、`evidence/index.json`、`transmission_heatmap.svg`、`phase_heatmap.svg` 均已生成。
- 后续：
  - Task 10 真实 2×2 前必须给出审批摘要：4 samples、phases `[1,2,3,4]`、CPU/`EXPRESS_MODE=0`、模板 SHA、输出目录、license/覆盖风险，并等待用户明确批准。

## 2026-06-18 - Task 10 真实 2×2 原生 sweep 通过

- 目标：在开发期 `5004` 上完成一次真实 `metasurface-sweep` 2×2 验证，确认新 job/task 状态机、原生 Phase 1-4、质量报告和 evidence-first 输出都能跑通。
- 审批摘要：
  - `mode=real`，`job_type=metasurface-sweep`，phases `[1,2,3,4]`。
  - 参数：`ratio=[0.2,0.8]` × `period=[390e-9,540e-9]`，`height=700e-9`。
  - 资源：CPU，`EXPRESS_MODE=0`，`FDTD_PROCESSES=1`，`FDTD_CAPACITY=1`。
  - Mesh：继承 `base_model.fsp` 模板，本次不修改网格精度。
  - 模板 SHA-256：`03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176`。
- 真实运行：
  - job_id：`job_20260618_235801_metasurface_sweep`。
  - HTTP 启动：`202`，初始 `4 pending`。
  - Phase 1：4 个 `.fsp` 模型生成成功。
  - Phase 2：4 个 task 进入 `solving`。
  - Phase 3/4：结果提取和 evidence 写出成功。
- 结果：
  - state：`succeeded`。
  - task：`4 succeeded / 0 failed`。
  - quality：`pass`，`valid_count=4`，`missing_count=0`，仍要求人工物理审核。
  - CSV：
    - `ratio=0.2, period=390e-9`：`T=0.9672581224386152`，`phase=-0.6737631333967985`。
    - `ratio=0.8, period=390e-9`：`T=0.7300105242892926`，`phase=-1.9698575481531564`。
    - `ratio=0.2, period=540e-9`：`T=0.9679605819741104`，`phase=-0.6426061423354885`。
    - `ratio=0.8, period=540e-9`：`T=0.9353412881476056`，`phase=-0.9494834757797856`。
  - Evidence：`results/sweep_results.csv`、`results/sweep_summary.json`、`quality_report.json`、`evidence/index.json`、`transmission_heatmap.svg`、`phase_heatmap.svg` 均已生成。
- 发现：
  - 审批字段必须为 `{"approved": true, "approved_for": "real_run"}`；带任务名的 human-readable tag 会被正确拒绝为 `approval_required`。
- 后续：
  - Task 11：真实 2×2 通过后，将新服务默认端口从 `5004` 提升到 `5000`，并在 Windows 同步后做 health/mock smoke。

## 2026-06-18 - Task 11 默认端口提升到 5000

- 目标：完成真实 2×2 后，把新 v1 服务从开发期 `5004` 推进到默认 `5000`。
- 修改：
  - `rpc_server.py` CLI 默认端口改为 `5000`。
  - `scripts/windows/manage_rpc.ps1` 在未设置 `FDTD_RPC_PORT` 时默认使用 `5000`。
  - `scripts/v1_smoke_test.py` 默认 RPC URL 改为 `http://127.0.0.1:5000`。
  - README、REQUIREMENTS、TECH_STACK、SOP、AGENTS、RPC API 和 Windows runbook 同步当前端口口径。
  - 新增 `tests/test_default_ports.py` 锁定默认端口。
- 验证：
  - `.venv/bin/python -m pytest tests/test_default_ports.py -q`：`1 passed`。
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests && .venv/bin/python -m pytest -q`：`114 passed`。
- Windows 同步：
  - 提交：`a81d6a8 feat: promote native rpc service to port 5000`。
  - Windows 已 `git pull --ff-only` 到 `a81d6a8`。
  - 因 `UpdateAndRestart` 本次进程加载的是拉取前旧脚本，重启阶段仍尝试使用旧默认 `5004`；已改为显式 `FDTD_RPC_PORT=5000` 启动新服务。
  - `5000` health/status：`ok=true`、`connected=false`，PID `39440`。
  - `5000` mock 2×2：job_id `job_20260619_000703_metasurface_sweep`，`4 succeeded / 0 failed`，quality `pass`。
- 注意：
  - Windows 连接表仍短暂显示旧 `5004` listener / PID `37336`，但该 PID 已无进程对象，`5004` HTTP 不响应；当前可用服务为 `5000`。

## 2026-06-19 - MCP 接入持久 jobs API

- 目标：让 Claude Code / MCP 直接调用当前已验证的 `/jobs/*` 状态机，而不是旧 `/sweep/*`。
- 修改：
  - 新增 `src/tools/jobs.py`，注册 `fdtd_job_plan/start/status/tasks/resume`。
  - 新增 metasurface 便捷工具 `fdtd_metasurface_sweep_plan/start`，默认 mock、CPU、`EXPRESS_MODE=0`，real 需要 `approved=True` 后才写入 `approved_for=real_run`。
  - `.mcp.json` 默认指向 `FDTD_RPC_URL=http://localhost:5000`。
  - 旧 `fdtd_sweep_*` 标记为 legacy compatibility。
- 验证：
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`124 passed`。
  - `rg -n "localhost:5001|127\\.0\\.0\\.1:5001|5001" src/server.py README.md TECH_STACK.md docs/RPC_API_V1.md .mcp.json tests/test_mcp_config.py || true`：无输出。
  - `rg -n 'sweep_config|sweep_run|sweep_status|/sweep' src/tools/jobs.py tests/test_mcp_jobs_tools.py`：无输出。

## 2026-06-19 - SimulationPlan MVP

- 目标：把自然语言 Agent 与已验证 `/jobs/*` 执行链之间增加可审批的结构化计划层。
- 实现：
  - SimulationPlan v0.1 默认值、校验、任务预算和稳定 SHA-256。
  - Plan 审批、real 双层审批和模板契约本地防线。
  - metasurface period/height compiler。
  - 三个 MCP Plan 工具：`fdtd_simulation_plan_validate/approve/start`。
  - real metasurface resume 模板指纹保护。
  - 离线 approved mock 端到端测试。
- 限制：未启动真实 FDTD；材料、光源、监视器、边界和网格仍继承模板。
- 验证：见 Task 9 最终输出。
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`158 passed`。

## 2026-06-19 - SimulationPlan strict-input validation 修复

- 目标：拒绝非 object section、未知字段和 physics 中放错层级的物理要求。
- 修改：
  - `src/simulation_plan.py`：新增 `KNOWN_TOP_KEYS`、`KNOWN_SECTION_KEYS` 和 `_validate_input_structure()`，在规范化前检查顶层/各 section 的字段名；section 非 dict 时返回 `plan_validation_error`；未知字段列出完整路径。
  - `tests/test_simulation_plan.py`：新增 6 个严格输入测试（sweep=list、未知 section 字段、physics 错层字段、未知顶层字段、intent=string、最小合法 Plan 仍通过）。
- 验证：
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`164 passed`。

## 2026-06-19 - sweep axis 字段互斥校验

- 目标：axis=period 时拒绝 height_values_m/fixed_period_m；axis=height 时拒绝 period_values_m/fixed_height_m。
- 修改：
  - `src/simulation_plan.py`：新增 `PERIOD_ONLY_FIELDS`/`HEIGHT_ONLY_FIELDS` 集合及 `_validate_sweep_axis_fields()`，在 `validate_simulation_plan` 中于 normalize 前检查输入 sweep 的 axis 与冲突字段。
  - `tests/test_simulation_plan.py`：新增 4 个测试 — period 冲突拒绝、height 冲突拒绝、合法 period 回归、合法 height 回归。
- 验证：
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`168 passed`。

## 2026-06-19 - Template Contract Stage A

- 目标：建立纯 Python 指纹工具和 Windows 只读模板 inventory。
- 安全边界：只读打开模板；不求解、不修改、不保存；inventory 不能批准 real。
- 实现：
  - 新增 `src/template_contract.py` 的稳定 JSON、SHA-256、原子写入和 inventory profile 校验。
  - 新增受控 inventory profile、只读 Lumerical adapter、inventory CLI 和 Windows `.bat` 入口。
  - runtime inventory/contract JSON 被 Git 忽略。
- Windows inventory：尚未执行；等待离线验证和 Windows 同步。
- 离线验证：
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`189 passed`。
  - 禁止操作扫描：无匹配。
  - Git tracked-artifact 扫描：无 runtime inventory/contract 或 `.fsp` 文件被跟踪。
- Windows inventory（`6a640f8`，LAPTOP-OR14JLNC）：
  - 状态：`status=inventory`，`inventory_only=true`，`errors=[]`。
  - 模板 SHA-256：`03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176`。
  - inventory fingerprint：`d3b37899e2b753c9fb2b93981f9c3026d0f69243858ac8ea7abb918379f3d1f2`。
  - known objects 全部 `count=1`、`status=pass`。
  - objects：12 个（root 6 + ::model 6）。
  - cleanup_state：`closed`。
  - ⚠️ `lumerical_version=unknown`：raw v242 lumapi `eval()` 不可用，`getversion` 无 Python 映射；此行为与 RPC Server 一致（PITFALLS.md 已记录）。
  - role 候选：
    - pillar：`::pillar`（Circle）或 `::model::pillar`（Circle）
    - substrate：`::substrate`（Rectangle）或 `::model::substrate`（Rectangle）
    - source：对象树中无独立 source 对象；可能嵌入 FDTD 设置
    - monitors：`::field`（DFTMonitor）和/或 `::model::field`（DFTMonitor）
  - v242 兼容性修复：
    - `get_version()` 加 try-except 返回 "unknown"（commit `2734bdd`）。
    - `inventory_objects()` 改用原生 `groupscope/selectall/getnumber/get` 替代 `eval()`（commit `6a640f8`）。
  - 未运行求解、未修改模板、未保存 `.fsp`、未创建 real job。

## 2026-06-19 - Template Contract Stage B0

- 目标：定向只读探针，解决 Stage A 遗留的 4 个不确定问题。
- 实现：
  - 新增 `src/template_probe.py`：指纹、安装身份检测、版本可确认性验证。
  - 新增 `scripts/probe_metasurface_template.py`：`ProbeAdapter`（18 个只读方法）、`build_probe`、`run_probe`、CLI。
  - 新增 `scripts/windows/probe_metasurface_template.bat`：Windows 入口。
  - 新增 `tests/test_template_probe.py`：`FakeProbeFdtd`（5 种场景）和 43 个测试。
- 探针能力：
  - 作用域枚举（`::`、`::model`、`::s_params`、`::model::s_params`）。
  - 同名对象证据对比（root vs ::model，stable properties 比较）。
  - 结构候选只读探测（pillar/substrate 的 material、坐标、span、radius）。
  - FDTD 配置（dimension、express mode、boundary conditions、simulation time）。
  - Mesh 配置（mesh accuracy）。
  - Model 参数（ratio、height、period 真实值/类型/读取方法）。
  - Source strategy 分类（explicit_object / analysis_group_setup / unresolved）。
  - 脚本只读审计（SHA-256 + 字节数 + 摘要，不保存全文）。
  - Monitors 枚举（坐标、span、frequency）。
  - Analysis group 验证（路径、类型、result naming T/S/S21_Gn）。
  - 安装身份（路径版本标签、lumapi SHA-256、可确认性）。
- 离线验证：
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`232 passed`。
  - 禁止操作扫描：`scripts/probe_metasurface_template.py` 无匹配。
  - Git tracked-artifact 扫描：`base_model.probe.json` 不在跟踪中。
- Windows probe：尚未执行；等待推送和 Windows 同步。
- Windows probe（`c93d4b7`，LAPTOP-OR14JLNC）：
  - 状态：`status=probe`，`probe_only=true`，`errors=[]`，`cleanup_state=closed`。
  - 模板 SHA-256 与 Stage A 一致：`03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176`。
  - probe fingerprint：`590aa2fe80aea642a4bcc61d12b80b32c23ddd7833593e1545287d39215af6fd`。
  - 安装身份：`confirmable=true`，`path_version_tag=v242`，`version_warning=true`（预期行为）。
  - **关键发现——root 对象不可通过 getnamed 访问**：
    - `::FDTD`、`::pillar`、`::substrate` 等 root scope 对象在 `getnamednumber` 中可计数，但 `getnamed("::XXX", ...)` 返回 "no items matching"。
    - 只有 `::model::` scope 下的对象可通过 `getnamed` 读取属性。
    - 结论：root 和 ::model 下同名对象是 **independent_objects**；实际运行属性在 `::model::` scope。
  - **Pillar**：`::model::pillar`，Circle，material=`Si3N4 (Silicon Nitride) - Kischkat`（非猜测的 TiO2），radius=`1.88e-7`，z=`3.5e-7`，z span=`7e-7`。x span/y span 对 Circle 不适用。
  - **Substrate**：`::model::substrate`，Rectangle，material=`SiO2 (Glass) - Palik`，z=`-5.57e-7`，z span=`1.11e-6`，x/y span=`9.4e-7`。
  - **Source**：`explicit_object`，路径 `::model::s_params::source`，类型 `PlaneSource`。setup script SHA-256 `fd0b51f5...`（6188 bytes），analysis script SHA-256 `07470696...`（15478 bytes）。
  - **Monitors**：6 个，含 `::model::field`（2D Y-normal DFTMonitor）、`::model::s_params::T`（2D Z-normal DFTMonitor）、`::model::s_params::R`（2D Z-normal DFTMonitor）、index monitors。
  - **Analysis group**：`::model::s_params` 类型 Analysis Group，脚本中检测到 `T` 和 `S21_Gn` 结果命名。
  - **Model 参数**：ratio=`0.8`（float）、height=`7e-7`（float）、period=`4.7e-7`（float），均通过 `getnamed` 可读。
  - **FDTD 配置**：root `FDTD` 不可通过 `getnamed` 直接访问；需使用 `::model::FDTD`。`express_mode` 不可读（`::model::FDTD` 无此属性）。
  - **Mesh**：`::model::mesh` 存在但 `mesh accuracy` 属性不可读。
  - 未运行求解、未修改模板、未保存 `.fsp`、未创建 real job。

## 2026-06-19 - Template Contract Stage B0.1 证据修正

- 目标：修正 Stage B0 probe 错误证据判断，补齐 FDTD/mesh/CPU/boundary 只读，增加 stage_b1_ready。
- 修正：select/selected get API; prepare_lumapi_environment; 三态对象分类; _read_fixed_object_property; canonical ::model::FDTD; 分离 global/override mesh; source_markers 证据; evaluate_stage_b1_readiness。
- 离线验证：244 passed, compileall PASS, 禁止操作扫描 PASS。
- Windows probe: 待执行。stage_b1_ready 不是 real approval。


## 2026-06-19 - Stage B0.1 Windows re-probe results

- Windows HEAD: 1087980, LAPTOP-OR14JLNC.
- status=probe, errors=[], cleanup_state=closed.
- stage_b1_ready=true, stage_b1_blockers=[].
- probe fingerprint: a8e7e2ee4265f607012c54b85e29a01f55ede9220cb37b12033be6f471c017d6.
- Template SHA matches Stage A.
- FDTD: canonical ::model::FDTD, 16 props readable, cpu_confirmed=true (express_mode=0).
- dimension=3D, mesh_accuracy=6.0, sim_time=5e-11.
- Boundaries: x=Anti-Symmetric, y=Symmetric, z=PML.
- Pillar: ::model::pillar, Si3N4, radius=1.88e-7.
- Substrate: ::model::substrate, SiO2.
- Source: explicit_object, ::model::s_params::source.
- Model params: ratio=0.8, height=7e-7, period=4.7e-7.
- Duplicate objects: all unresolved_scope_alias.
- No solve, no modify, no job created.
- Stage B0.1 complete; Stage B1 ready. Stopped, not entering Stage B1.


## 2026-06-19 - Planned Template Contract Stage B1

- Goal: generate strict template profile and runtime verified contract from Stage B0.1 probe evidence.
- Safety: B1 is offline JSON validation only; no solve, no .fsp mutation, no job creation.
- Stop gate: verified contract enables later real 2x2 approval request, not real execution.


## 2026-06-19 - Stage B1 Windows contract generation

- Windows HEAD: 11d7b99, LAPTOP-OR14JLNC.
- Contract: status=verified, verified=True, all 16 checks pass.
- Contract fingerprint: bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1.
- No solve, no .fsp mutation, no job creation, no real sweep.
- Stage B1 complete. Stopped before real 2x2 SimulationPlan approval.


## 2026-06-19 - Planned Stage C0 real 2x2 preflight

- Goal: build an approval packet for the first real 2x2 SimulationPlan run.
- Safety: C0 is local JSON validation only; no FDTD solve, no real job, no RPC start.
- Important fix: real-run guard must accept verified Stage B1 contract shape.
- Stop gate: user must approve the exact generated packet before Stage C1.


## 2026-06-19 - Stage C0 Windows preflight packet

- Windows HEAD: 4970204, LAPTOP-OR14JLNC.
- Contract confirmed: verified=True, fingerprint=bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1.
- Preflight status: ready_for_human_approval, task_count=4.
- Plan fingerprint: e8c957df2c8112c876142998ecb088fa9c78f4a6c34037834a1cddae24c87810.
- Template SHA: 03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176.
- Execution: CPU, express_mode=0, processes=1, capacity=1, hide=True, mesh_accuracy=6.
- Failed checks: [], warnings: physics_review_required, version_unknown_warning.
- No FDTD solve, no .fsp mutation, no real job created.
- Stage C0 complete. Stopped before Stage C1 real run approval.


## 2026-06-19 - Stage C1 real 2x2 SimulationPlan run

- Approval: user explicitly approved exact Stage C0 packet.
- Plan fingerprint: e8c957df2c8112c876142998ecb088fa9c78f4a6c34037834a1cddae24c87810.
- Request: real `metasurface-sweep`, 2x2 period sweep, CPU, express_mode=0, processes=1, capacity=1, phases=[1,2,3,4].
- RPC: Windows service restarted on 127.0.0.1:5000; Mac used SSH tunnel local 5501 -> Windows 127.0.0.1:5000 because local 5000 was occupied by macOS Control Center.
- Job: `job_20260619_213418_metasurface_sweep`; `/jobs/start` returned HTTP 202.
- Final state: `succeeded`; tasks succeeded 4/4, failed 0.
- Template SHA recorded in manifest: `03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176`.
- Quality report: conclusion=`pass`, valid_count=4, missing_count=0, requires_human_review=true.
- Results:
  - task_0001 ratio=0.2, period=390 nm, T=0.9672581224, phase=-0.6737631334 rad.
  - task_0002 ratio=0.8, period=390 nm, T=0.7300105243, phase=-1.9698575482 rad.
  - task_0003 ratio=0.2, period=540 nm, T=0.9679605820, phase=-0.6426061423 rad.
  - task_0004 ratio=0.8, period=540 nm, T=0.9353412881, phase=-0.9494834758 rad.
- Evidence: `evidence/index.json`, `evidence/transmission_heatmap.svg`, `evidence/phase_heatmap.svg`, `results/sweep_results.csv`, `quality_report.json`.
- Note: polling script expected terminal state `completed`, but service uses `succeeded`; manual interrupt of polling did not affect the completed job.

## 2026-06-19 - Stage C2 real result review

- 目标：为 C1 真实 2×2 SimulationPlan job 增加 evidence-only 拉取、本地审计和人类可读报告流程。
- 实现：`src/real_result_review.py`、`scripts/collect_real_result_review.py` 和测试。
- 从 Windows 复制 14 个 evidence-first 文件（JSON/CSV/SVG/tasks），0 个 .fsp 模型文件。
- 生成 `runtime/reviews/job_20260619_213418_metasurface_sweep/review.json` 和 `real_2x2_review.md`。
- 软件链结论: pass (7/7 chain checks pass)。物理审核: human_review_required。Phase span: 1.3273 rad，远低于 2π。
- 约束：C2 不启动 FDTD、不创建 job、不 resume、不重启 RPC、不修改模板。

## 2026-06-19 - Planned Stage C3 production sweep design packet

- 目标：基于 C2 审计结论，为下一轮更大但有界的真实 sweep 写执行计划；本阶段只准备审批包，不启动 FDTD。
- 计划文件：`docs/superpowers/plans/2026-06-19-production-sweep-design-packet.md`。
- 默认路线：25-task `ratio × height` 粗扫，ratio `[0.2, 0.35, 0.5, 0.65, 0.8]`，height `[500, 550, 600, 650, 700] nm`，fixed period `470 nm`，CPU，`EXPRESS_MODE=0`，`include_models=false`。
- 安全边界：Stage C0 的 2×2 preflight 继续锁死为 4 tasks；C3 必须新增独立 production packet builder。高度不超过 `700 nm`，避免越过当前模板/mesh 已验证边界。
- 后续：交给 Claude Code 执行 C3 plan；生成 `runtime/approvals/production_sweep_c3_packet.json` 后停在人工审批，Stage C4 才能在明确批准 exact packet 后启动真实 sweep。

## 2026-06-19 - Stage C3 production sweep design packet

- 目标：基于 C2 真实结果审计，生成下一轮有界真实 sweep 的审批包，而不是直接启动求解。
- 设计：默认 25 tasks，sweep.axis=height，ratio [0.2, 0.35, 0.5, 0.65, 0.8]，height [500, 550, 600, 650, 700] nm，fixed period 470 nm，CPU，EXPRESS_MODE=0，include_models=false。
- 安全边界：高度不超过 700 nm，保持在 Stage B0.1 已探测的 mesh envelope 内；高于 700 nm 的 taller-pillar 扫描需要单独模板/mesh 审核。
- 约束：C3 不启动 FDTD、不创建 job、不 resume、不重启 RPC、不修改模板或 .fsp。
- 后续：人工审批 exact C3 packet 后，Stage C4 才能启动真实 production-discovery sweep。


- 验证：compileall exit 0；pytest -q 全量通过 292 passed；forbidden-operation scan 无实际调用；生成 runtime/approvals/production_sweep_c3_packet.json，status=ready_for_human_approval，task_count=25。


## 2026-06-19 - Persistent job Feishu notifications

- 复用旧 Autosweep 的标准库飞书 Webhook 模式，接入新项目持久 JobStore。
- `/jobs/plan` 通知 planned；mock/real 通知 succeeded、failed、partial；普通 SimulationPlan 校验和 preflight 不通知。
- 通知采用 `notifications.json` 幂等记录，Webhook 只从 `FDTD_FEISHU_WEBHOOK` 读取，发送失败不影响 job 状态。
- Agent 工作流改为提交后返回 job_id 并停止轮询，收到飞书后再分析。
- 验证：focused/full pytest 与 compileall 通过；2026-06-20 Windows mock smoke 返回持久 job，飞书收到 `succeeded`，未启动 FDTD。

## 2026-06-20 - 0.1.0 Windows minimal solver smoke 返修

- 目标：修复 Windows 本机 manual smoke 暴露的 typed adapter 和 smoke 脚本不连贯问题；不启动 sweep、不改变物理任务边界。
- 现象：smoke 报告 `technical_smoke=true`、`physical_conclusion=false`，核心 RPC→lumapi→solve→result 链路通，但 `fdtd_region`、`monitor_create`、`analysis_group_create`、`project_save` 和 `result_download` 步骤失败，且 GUI 出现保存提示。
- 修改：`fdtd_region` 创建脚本不再 `set("name", ...)`；power monitor 自动先设置 `override global monitor settings=1`；RPC 增加 `/project/save` 和 `/project/load` alias；minimal smoke 的 analysis group 使用空属性，result download 改为 `/results/mon/T/download`。
- 验证：新增 5 个回归测试先红后绿；`compileall` 通过；`pytest -q` 全量通过 539 passed；参数文件验证保持 `physical_conclusion=false`。
- 后续：Windows 端 `git pull --ff-only` 后重新执行 `scripts\windows\minimal_solver_smoke.py`。

## 2026-06-20 - Windows minimal solver smoke 运行时收敛

- 目标：修复 Windows 本机复测中 `/simulation/run` 超过 120 秒后被外部 `/session/close` 干扰，导致后续 save/result 级联失败的问题；仍只做单模型技术 smoke。
- 现象：HEAD=67a2ca0 时，建结构、FDTD 区域、光源、监视器和 analysis group 均已通过；`/simulation/run` HTTP read timeout，日志显示仿真中途出现外部 `/session/close`，后续 `project_save`、`result_read_value`、`result_download` 报 `session_not_active`。
- 修改：minimal smoke 显式设置低成本 FDTD 参数（`mesh accuracy=1`、`simulation time=50e-15`、`auto shutoff min=1e-3`），固定 source/monitor 位置和 spans，把 run timeout 提升到 300 秒；若 run 失败，立即落 `smoke_report.json` 并退出，避免级联误报。
- 验证：静态回归测试先红后绿，`tests/test_minimal_solver_smoke_static.py` 聚焦验证通过。
- 后续：Windows 端更新到新 HEAD 后，在没有其他 Agent/脚本调用 `/session/close` 的情况下重跑 manual smoke。

## 2026-06-20 - Windows minimal solver smoke 通过

- Windows manual smoke：`technical_smoke=true`、`physical_conclusion=false`、`ok=true`，14/14 步通过。
- 验证链路：health、session_start、project_new、object_create、fdtd_region、source_create、monitor_create、analysis_group_create、simulation_run、simulation_status、project_save、result_list、result_read_value、result_download。
- 产物：`smoke_model.fsp`、`smoke_report.json`、`downloaded_results.json`。
- 现场必要容差：FDTD 冷启动需约 17-20 秒，`session_start` timeout 固化为 30 秒；同步 run 预算固化为 600 秒。端口 `5001` 仅作为 `5000` 被僵尸 TCP 条目锁死时的临时 `--rpc` 参数，不改项目默认端口。
- 注意：`mon/T` 负值只作为结果读取证据，不构成物理结论。

## 2026-06-20 - 官方 Analysis Group 知识补齐

- 目标：为“添加分析组时优先使用官方自带分析组”先补官方来源依据，不直接猜测库对象 ID。
- 来源：Ansys 官方 Analysis Groups、Object Library、Object Library objects and related analysis、`addanalysisgroup` 和 `addobject` 文档。
- 结论：自定义空白 group 用 `addanalysisgroup`；官方 Object Library 预定义对象/analysis group 用 `addobject("script_ID")`；`addobject;` 可在目标版本枚举可用对象名。
- 修改：新增 `src/knowledge/prompts/lumerical_analysis_groups.md`，并同步 `lumerical_fdtd_automation_manual.md`、`lumerical_command_index.md`、`source_map.md`。
- 后续：实现 MCP 行为前，应先在 Windows v242 侧做只读 `addobject;` 枚举，把确认过的 `script_ID` 写入 registry；未确认 ID 不得由 Agent 猜测。

## 2026-06-20 - MCP analysis group 官方库优先行为

- 目标：实现 `fdtd_analysis_group_create` 在用户提供已确认 `script_id` 时优先走官方 Object Library `addobject("script_id")`，否则安全回退自定义 `addanalysisgroup`。
- 范围：RPC `/analysis-groups`、Mac `RpcClient`、MCP wrapper 和 DeviceRecipe 编译透传 `prefer_builtin`、`require_builtin`、`script_id`。
- 约束：不新增 MCP 工具，不猜测官方库 ID，不启动 FDTD solve；`require_builtin=true` 且无 `script_id` 返回结构化错误。

## 2026-06-21 - 自主 Object Library analysis group 工作流

- 目标：实现从会话枚举到 readback 验证的完整自动化 Object Library 工作流，不依赖预先确认的 `script_id`。
- 实现：
  - 新增 `src/object_library_catalog.py`：首次 session 枚举 live v242 catalog，持久化到 `runtime/object_library_catalog.json`。
  - 新增 `src/analysis_group_selection.py`：intent 解析、确定性短列表生成（`shortlist_candidates`）、探针后 confidence 排序（`rank_probed_candidates`）、高置信度选择（`choose_high_confidence`）。
  - 新增 `src/analysis_group_runtime.py`：`AnalysisGroupService` 协调 enumerate → shortlist → probe → configure → runsetup → readback 全流程；创建 `verified analysis group`、参数合并和读回验证。
  - 新增 `src/analysis_group_inspector.py`：只读 `ObjectLibraryInspector` 探针，获取 script properties/results/settable 属性，确保 `restore_verified`。
  - 新增 `tests/test_object_library_catalog.py`、`tests/test_analysis_group_selection.py`：覆盖 catalog 空/损坏/版本变化、shortlist 确定性、prefer/require 回退路径。
  - 新增 `tests/test_analysis_group_runtime.py`、`tests/test_analysis_group_builtin.py`：覆盖 fake backend 下完整 workflow、参数验证、setup 失败和回退。
  - DeviceRecipe build 注入 `runtime_instructions` 和 `execution_fingerprint`。
  - `src/tools/analysis_groups.py` 透传 `analysis_intent`、`recipe_context`、`parameter_overrides`。
- 验证：
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：全量通过（539+ passed）。
  - `.venv/bin/python -m pytest tests/test_object_library_smoke_static.py -q`：3 passed。
  - 工具数保持 69/69。
  - Windows `object_library_analysis_group_smoke.py` 已创建但尚未在 Windows 上执行（Task 10 Step 8 留给人工）。
- 后续：
  - Windows v242 manual smoke 执行并确认 `catalog_enumerated=true`、`probe_restore_verified=true`、`setup_verified=true`、`ok=true`。
  - 若 v242 实际 ID 与默认 `transmission` intent 不匹配，用 `--intent-kind` / `--script-id` 参数调整并记录真实 ID / catalog identity。
