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

## 2026-06-18 - Load(template) 覆盖 express mode 导致 0 valid（来源：联调实测）

- 现象：Phase 3 报告 "0 valid, 4 missing"，所有仿真结果无效。GPU headless 模式下特别明显。
- 根因：`fdtd.setnamed("FDTD", "express mode", 1)` 设在循环外面，但每次 `fdtd.load(template)` 会重新加载模板文件，模板里保存的 FDTD 设置会覆盖之前 setnamed 的值。
- 修复：把 `setnamed("FDTD", "express mode", 1)` 移到循环内，`switchtolayout()` 之后、`save()` 之前。这样每个 .fsp 文件都会正确启用 express mode。
- 预防：**模板 load 后必须重新设置运行时参数**。模板文件保存的是设计基准，不保存运行时优化参数。在 SOP 中写入此规则。

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
