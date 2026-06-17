# Lumerical FDTD 自动化资料地图

状态说明：
- 来源优先级：官方文档 / 官方开发者文档 / 官方课程 / 示例 / 非官方。
- 手册适用性：Yes 表示可进入工程手册；Partial 表示只摘取局部规则；No 表示只作为背景。
- 优先级：P0 是自动化 Agent 必须掌握；P1 是常用扩展；P2 是背景或场景示例。
- 本资料地图基于 2026-06-01 可公开访问网页检索结果整理，未登录 Ansys Customer Portal。

## FDTD 基础与对象设置

| 标题 | URL | 来源类型 | 适合学习的内容 | 适合进入工程手册 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| Finite Difference Time Domain (FDTD) solver introduction | https://optics.ansys.com/hc/en-us/articles/360034914633-FDTD-solver | 官方文档 | FDTD 基本物理、网格、材料、边界、source/monitor 类型概览 | Yes | P0 |
| FDTD solver - Simulation Object | https://optics.ansys.com/hc/en-us/articles/360034382534-FDTD-solver-Simulation-Object | 官方文档 | simulation region 属性、mesh accuracy、boundary、autoshutoff、status/benchmark 结果 | Yes | P0 |
| Plane wave and beam source - Simulation object | https://optics.ansys.com/hc/en-us/articles/360034382854-Sources-Plane-wave-and-Beam | 官方文档 | plane/beam source 设置、周期/斜入射边界配合 | Yes | P0 |
| Field time monitor - Simulation object | https://optics.ansys.com/hc/en-us/articles/360034902353-Monitors-Field-time | 官方文档 | time monitor 数据、内存风险、down sample、结果字段 | Yes | P1 |
| Analysis Groups - Simulation object | https://optics.ansys.com/hc/en-us/articles/360034382454-Analysis-Groups-Simulation-object | 官方文档 | analysis group 的容器/后处理定位 | Yes | P1 |
| Material Database in FDTD and MODE | https://optics.ansys.com/hc/en-us/articles/360034394614-Material-Database-in-FDTD-and-MODE | 官方文档 | 默认材料库、材料数据、材料修改风险 | Partial | P1 |
| Bloch boundary conditions in FDTD and MODE | https://optics.ansys.com/hc/en-us/articles/360034382714-Bloch-boundary-conditions-in-FDTD-and-MODE | 官方文档 | 周期结构斜入射时 Bloch 与 periodic 的差异 | Yes | P1 |
| Periodic boundary conditions in FDTD and MODE | https://optics.ansys.com/hc/en-us/articles/360034382734-Periodic-boundary-conditions-in-FDTD-and-MODE | 官方文档 | 周期单元边界设置原则 | Yes | P1 |
| Always extend structures through PML boundary conditions | https://optics.ansys.com/hc/en-us/articles/360034382414-Always-extend-structures-through-PML-boundary-conditions | 官方文档 | PML 区域中结构延伸规则 | Yes | P1 |

## Script Language / .lsf

| 标题 | URL | 来源类型 | 适合学习的内容 | 适合进入工程手册 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| Lumerical scripting language - By category | https://optics.ansys.com/hc/en-us/articles/360037228834-Lumerical-scripting-language-By-category | 官方文档 | 命令分类、.lsf 用途、对象/运行/数据命令入口 | Yes | P0 |
| Lumerical Scripting Language | https://developer.ansys.com/docs/lumerical/scripting-language | 官方开发者文档 | 脚本语言定位、命令库、可从 .lsf/CLI/对象中执行 | Yes | P0 |
| addfdtd - Script command | https://optics.ansys.com/hc/en-us/articles/360034924173-addfdtd-Script-command | 官方文档 | 添加 FDTD solver region | Yes | P0 |
| addmesh - Script command | https://optics.ansys.com/hc/en-us/articles/360034924253-addmesh | 官方文档 | mesh override 区域设置 | Yes | P0 |
| addrect - Script command | https://optics.ansys.com/hc/en-us/articles/360034404214-addrect-Script-command | 官方文档 | 矩形几何与材料赋值 | Yes | P0 |
| addcircle - Script command | https://optics.ansys.com/hc/en-us/articles/360034404114-addcircle-Script-command | 官方文档 | 圆/柱状几何 | Yes | P1 |
| addplane - Script command | https://optics.ansys.com/hc/en-us/articles/360034924413-addplane | 官方文档 | plane source 创建与波长范围设置 | Yes | P0 |
| adddipole - Script command | https://optics.ansys.com/hc/en-us/articles/360034924393-adddipole | 官方文档 | dipole source 创建 | Partial | P1 |
| adddftmonitor - Script command | https://optics.ansys.com/hc/en-us/articles/36957320687763-adddftmonitor-Script-command | 官方文档 | frequency-domain monitor 创建，替代 deprecated addpower/addprofile | Yes | P0 |
| addtime - Script command | https://optics.ansys.com/hc/en-us/articles/360034404494-addtime | 官方文档 | time monitor 创建 | Yes | P1 |
| addanalysisgroup - Script command | https://optics.ansys.com/hc/en-us/articles/360034404074-addanalysisgroup-Script-command | 官方文档 | analysis group 创建 | Yes | P1 |
| newproject - Script command | https://optics.ansys.com/hc/en-us/articles/360034931473-newproject-Script-command | 官方文档 | 创建新 project；注意旧项目不会自动保存 | Partial | P1 |
| set - Script command | https://optics.ansys.com/hc/en-us/articles/360034928773-set-Script-command | 官方文档 | 设置当前选中对象属性 | Yes | P0 |
| setnamed - Script command | https://optics.ansys.com/hc/en-us/articles/360034928793-setnamed-Script-command | 官方文档 | 按名称设置对象属性 | Yes | P0 |
| get - Script command | https://optics.ansys.com/hc/en-us/articles/360034928873-get-Script-command | 官方文档 | 读取选中对象属性 | Yes | P0 |
| switchtolayout - Script command | https://optics.ansys.com/hc/en-us/articles/360034923993-switchtolayout | 官方文档 | 从 analysis mode 回 layout mode，修改对象前必须考虑 | Yes | P0 |
| layoutmode - Script command | https://optics.ansys.com/hc/en-us/articles/360034924033-layoutmode | 官方文档 | 判断当前模式，避免修改对象报错 | Yes | P0 |
| run - Script command | https://optics.ansys.com/hc/en-us/articles/360034931333-run-Script-command | 官方文档 | 运行当前仿真，CPU/GPU resource type | Yes | P0 |
| runjobs - Script command | https://optics.ansys.com/hc/en-us/articles/360034931373-runjobs-Script-command | 官方文档 | Job queue 批量运行与错误处理 | Yes | P1 |
| load - Script command | https://optics.ansys.com/hc/en-us/articles/360034410834-load-Script-command | 官方文档 | 加载 .fsp/.ldev 等项目文件 | Yes | P0 |
| save - Script command | https://optics.ansys.com/hc/en-us/articles/360034410814-save-Script-command | 官方文档 | 保存项目及结果 | Yes | P0 |
| getresult - Script command | https://optics.ansys.com/hc/en-us/articles/360034409854-getresult | 官方文档 | 获取 dataset 结果 | Yes | P0 |
| getdata - Script command | https://optics.ansys.com/hc/en-us/articles/360034409834-getdata | 官方文档 | 获取 raw data | Yes | P0 |
| haveresult - Script command | https://optics.ansys.com/hc/en-us/articles/360034409894-haveresult-Script-command | 官方文档 | 检查 dataset 是否存在 | Yes | P0 |
| havedata - Script command | https://optics.ansys.com/hc/en-us/articles/360034930213-havedata-Script-command | 官方文档 | 检查 raw data 是否存在 | Yes | P0 |
| transmission - Script command | https://optics.ansys.com/hc/en-us/articles/360034405354-transmission-Script-command | 官方文档 | 功率 monitor 的归一化透射计算 | Yes | P0 |
| runanalysis - Script command | https://optics.ansys.com/hc/en-us/articles/360034409874-runanalysis-Script-command | 官方文档 | 运行 analysis object 脚本 | Yes | P1 |
| savedata - Script command | https://optics.ansys.com/hc/en-us/articles/360034411174-savedata-Script-command | 官方文档 | 保存 workspace 到 .ldf | Yes | P1 |
| write - Script command | https://optics.ansys.com/hc/en-us/articles/360034411134-write-Script-command | 官方文档 | 输出文本/CSV，safe mode 限制 | Yes | P1 |
| struct - Script command | https://optics.ansys.com/hc/en-us/articles/360034409574-struct-Script-command | 官方文档 | 批量属性设置、sweep 参数结构 | Yes | P1 |

## Python API / lumapi / PyLumerical

| 标题 | URL | 来源类型 | 适合学习的内容 | 适合进入工程手册 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| Python API overview | https://optics.ansys.com/hc/en-us/articles/360037824513-Python-API-overview | 官方文档 | lumapi/lumopt/lumslurm 总入口 | Yes | P0 |
| Python API - Lumapi | https://developer.ansys.com/docs/lumerical/python-lumapi | 官方开发者文档 | Lumapi 能力、remote API、Python 工作流 | Yes | P0 |
| Ansys Lumerical for developers | https://developer.ansys.com/docs/lumerical | 官方开发者文档 | Lumerical Automation API、PyLumerical、支持语言 | Yes | P0 |
| Installation and Getting Started - Python API | https://optics.ansys.com/hc/en-us/articles/39744901602707-Installation-and-Getting-Started-Python-API | 官方文档 | lumapi 导入路径、系统/许可要求 | Yes | P0 |
| Session Management - Python API | https://optics.ansys.com/hc/en-us/articles/360041873053-Session-Management-Python-API | 官方文档 | FDTD session、hide、remoteArgs、serverArgs、with context、close | Yes | P0 |
| Script Commands as Methods - Python API | https://optics.ansys.com/hc/en-us/articles/360041579954-Script-commands-as-methods-Python-API | 官方文档 | Python 中调用 LSF 命令、keyword/property 映射 | Yes | P0 |
| Working with Simulation Objects - Python API | https://optics.ansys.com/hc/en-us/articles/39744946400659-Working-with-Simulation-Objects-Python-API | 官方文档 | add object 返回 SimObject、dict/attribute 访问、重名风险 | Yes | P0 |
| Passing Data - Python API | https://optics.ansys.com/hc/en-us/articles/360041401434-Passing-Data-Python-API | 官方文档 | Python/Lumerical 数据类型转换、性能注意 | Yes | P0 |
| Accessing Simulation Results - Python API | https://optics.ansys.com/hc/en-us/articles/39744236202771-Accessing-Simulation-Results-Python-API | 官方文档 | getresult/getdata 到 Python dict/NumPy | Yes | P0 |
| Lumerical Python API Reference | https://optics.ansys.com/hc/en-us/articles/38660003331859-Lumerical-Python-API-Reference | 官方文档 | 构造函数、SimObject、结果对象参考 | Yes | P0 |
| lumapi - Lumerical.eval - Python API Method | https://optics.ansys.com/hc/en-us/articles/360043166434-lumapi-Lumerical-eval-Python-API-Method | 官方文档 | 执行 .lsf 字符串，减少 API call | Yes | P0 |
| lumapi - Lumerical.getv - Python API method | https://optics.ansys.com/hc/en-us/articles/39748719848211-lumapi-Lumerical-getv-Python-API-method | 官方文档 | 从 Lumerical workspace 取变量 | Partial | P1 |
| lumapi - Lumerical.close - Python API Method | https://optics.ansys.com/hc/en-us/articles/39746549400723-lumapi-Lumerical-close-Python-API-Method | 官方文档 | 显式关闭 session | Yes | P1 |
| Interop Server - Remote API | https://optics.ansys.com/hc/en-us/articles/15499581457811-Interop-Server-Remote-API | 官方文档 | Linux remote API、安全边界、证书、端口 | Partial | P1 |
| PyLumerical Basic FDTD Simulation - Lumerical style commands | https://lumerical.docs.pyansys.com/version/stable/examples/Sessions_and_Objects/fdtd_example1_lsf.html | 官方/Ansys PyAnsys 文档 | `ansys.lumerical.core` 风格示例 | Partial | P1 |

## Parameter sweep / optimization

| 标题 | URL | 来源类型 | 适合学习的内容 | 适合进入工程手册 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| Parameter sweeps, Optimization and Monte Carlo analysis overview | https://optics.ansys.com/hc/en-us/articles/360034922853-Parameter-sweeps-Optimization-and-Monte-Carlo-analysis-overview | 官方文档 | sweep/optimization/Monte Carlo/S-parameter sweep 定位 | Yes | P0 |
| addsweep - Script command | https://optics.ansys.com/hc/en-us/articles/360034930413-addsweep-Script-command | 官方文档 | 创建 sweep/optimization/Monte Carlo/S-parameter sweep | Yes | P0 |
| setsweep - Script command | https://optics.ansys.com/hc/en-us/articles/360034930473-setsweep-Script-command | 官方文档 | 设置 sweep 属性 | Yes | P0 |
| addsweepparameter - Script command | https://optics.ansys.com/hc/en-us/articles/360034930493-addsweepparameter-Script-command | 官方文档 | 添加 sweep 参数 | Yes | P0 |
| addsweepresult - Script command | https://optics.ansys.com/hc/en-us/articles/360034410034-addsweepresult-Script-command | 官方文档 | 添加 sweep 结果 | Yes | P0 |
| runsweep - Script command | https://optics.ansys.com/hc/en-us/articles/360034931413-runsweep-Script-command | 官方文档 | 执行 sweep/optimization，CPU/GPU resource type | Yes | P0 |
| getsweepresult - Script command | https://optics.ansys.com/hc/en-us/articles/360034409814-getsweepresult-Script-command | 官方文档 | 获取 sweep/optimization 结果与 best FOM | Yes | P0 |
| havesweepresult - Script command | https://optics.ansys.com/hc/en-us/articles/360034409954-havesweepresult-Script-command | 官方文档 | 检查 sweep 结果 | Yes | P1 |
| savesweep - Script command | https://optics.ansys.com/hc/en-us/articles/360034410014-savesweep-Script-command | 官方文档 | 将 sweep 点保存成独立仿真文件 | Yes | P1 |

## Inverse design / lumopt

| 标题 | URL | 来源类型 | 适合学习的内容 | 适合进入工程手册 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| Photonic Inverse Design Overview - Python API | https://optics.ansys.com/hc/en-us/articles/360049853854-Photonic-Inverse-Design-Overview-Python-API | 官方文档 | lumopt、adjoint、shape/topology、FOM 与约束 | Yes | P0 |
| Photonic Inverse Design with Lumopt | https://developer.ansys.com/docs/lumerical/python-lumopt | 官方开发者文档 | Lumopt 能力、模块随 Lumerical Python 提供 | Yes | P0 |
| Getting Started with lumopt - Python API | https://optics.ansys.com/hc/en-us/articles/360050995394-Getting-Started-with-lumopt-Python-API | 官方文档 | lumopt 入门与 examples | Yes | P1 |
| Optimizable Geometry - Python API | https://optics.ansys.com/hc/en-us/articles/360052044913-Optimizable-Geometry-Python-API | 官方文档 | FunctionDefinedPolygon、ParameterizedGeometry、bounds、dx | Yes | P0 |
| Inverse design of y-branch | https://optics.ansys.com/hc/en-us/articles/360042305274-Inverse-design-of-y-branch | 官方示例 | 参数化优化、ModeMatch FOM、wavelengths、bounds | Yes | P1 |
| Inverse design of waveguide crossing | https://optics.ansys.com/hc/en-us/articles/360042305314-Inverse-design-of-waveguide-crossing | 官方示例 | waveguide crossing inverse design workflow | Partial | P2 |
| Inverse Design of a Splitter Using Topology Optimization | https://optics.ansys.com/hc/en-us/articles/1500007182141-Inverse-Design-of-a-Splitter-Using-Topology-Optimization | 官方示例 | topology optimization 场景 | Partial | P2 |

## 数据读取与后处理

| 标题 | URL | 来源类型 | 适合学习的内容 | 适合进入工程手册 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| Accessing Simulation Results - Python API | https://optics.ansys.com/hc/en-us/articles/39744236202771-Accessing-Simulation-Results-Python-API | 官方文档 | dataset 到 Python dict、raw data 到 NumPy | Yes | P0 |
| getresult - Script command | https://optics.ansys.com/hc/en-us/articles/360034409854-getresult | 官方文档 | dataset 获取、字段访问 | Yes | P0 |
| getdata - Script command | https://optics.ansys.com/hc/en-us/articles/360034409834-getdata | 官方文档 | raw monitor data 获取 | Yes | P0 |
| transmission - Script command | https://optics.ansys.com/hc/en-us/articles/360034405354-transmission-Script-command | 官方文档 | normalized transmission FOM | Yes | P0 |
| grating - Script command | https://optics.ansys.com/hc/en-us/articles/360034927213-grating-Script-command | 官方文档 | grating order efficiency | Partial | P1 |
| vtksave - Script command | https://optics.ansys.com/hc/en-us/articles/360034411354-vtksave-Script-command | 官方文档 | dataset 导出 VTK | Partial | P2 |
| matlabsave / matlabload docs | https://optics.ansys.com/hc/en-us/articles/360034408034-matlabload-Script-command | 官方文档 | MATLAB .mat 交换；matlabsave 页需进一步确认 | Partial | P2 |

## HPC / batch / Slurm / headless workflow

| 标题 | URL | 来源类型 | 适合学习的内容 | 适合进入工程手册 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| Getting Started with lumslurm - Python API | https://optics.ansys.com/hc/en-us/articles/20990924220691-Getting-Started-with-lumslurm-Python-API | 官方文档 | Slurm 提交、run_solve/run_batch/run_sweep、license estimation | Yes | P0 |
| Running Lumerical simulations | https://optics.ansys.com/hc/en-us/sections/360004588574-Running-Lumerical-simulations | 官方文档 | Windows/Linux/MPI/GPU/headless/batch 入口 | Yes | P1 |
| Running simulations using terminal on Linux | https://optics.ansys.com/hc/en-us/articles/360024974033-Running-simulations-using-terminal-on-Linux | 官方文档 | CLI 参数、`-nw`、`-run`、`-trust-script` | Yes | P1 |
| runjobs - Script command | https://optics.ansys.com/hc/en-us/articles/360034931373-runjobs-Script-command | 官方文档 | job queue 批处理 | Yes | P1 |
| AWS Use Case: Auto-Scaling Clusters with Slurm Job Scheduler on AWS ParallelCluster UI | https://optics.ansys.com/hc/en-us/articles/31115392717203-AWS-Use-Case-Auto-Scaling-Clusters-with-Slurm-Job-Scheduler-on-AWS-ParallelCluster-UI | 官方示例 | lumslurm 与云端 Slurm 案例 | Partial | P2 |

## Examples / templates

| 标题 | URL | 来源类型 | 适合学习的内容 | 适合进入工程手册 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| Using the Python API in the nanowire application example | https://optics.ansys.com/hc/en-us/articles/360034416574-Using-the-Python-API-in-the-nanowire-application-example | 官方示例 | Python API 控制 FDTD、setnamed、run、getresult 和 Python 绘图的应用示例 | Partial | P1 |
| Structural Color Filters | https://optics.ansys.com/hc/en-us/articles/34870401324563-Structural-Color-Filters | 官方示例 | metasurface/period/angle/polarization sweep 与 Python 后处理 | Partial | P1 |
| Inverse design of y-branch | https://optics.ansys.com/hc/en-us/articles/360042305274-Inverse-design-of-y-branch | 官方示例 | lumopt 参数化优化模板 | Yes | P1 |
| Basic FDTD Simulation - Lumerical style commands | https://lumerical.docs.pyansys.com/version/stable/examples/Sessions_and_Objects/fdtd_example1_lsf.html | 官方/Ansys PyAnsys 示例 | PyLumerical 控制 FDTD 的最小示例 | Partial | P1 |

## 非官方补充资料

| 标题 | URL | 来源类型 | 可信度 | 可用内容 | 适合进入工程手册 | 优先级 |
| --- | --- | --- | --- | --- | --- | --- |
| How to Run a Lumerical Script | https://simutechgroup.com/how-to-run-a-lumerical-script/ | 非官方 | 中；Ansys 渠道伙伴/培训商，但不是官方源 | run 命令解释可作为备查，不作为 API 真源 | No | P2 |
| LEAP Lumerical Scripting Tutorial PDF | https://public-leapaust.s3.ap-southeast-2.amazonaws.com/resources/LEAP_Lumerical_Scripting_Tutorial.pdf | 非官方 | 中；培训材料 | 入门教学，不作为命令权威 | No | P2 |

## 进入手册的抽取规则

1. P0 官方资料用于建立 Agent 操作规范、命令索引和代码模板。
2. P1 官方资料用于补充对象设置、HPC、analysis group、示例 workflow。
3. P2 或非官方资料只作为背景，不作为命令语义来源。
4. 未在真实 Lumerical 环境运行过的代码统一标注“待验证”。
5. 如果官方页面有新旧命令并存，优先采用当前文档推荐命令。例如 frequency-domain monitor 优先 `adddftmonitor`，把 `addpower`/`addprofile` 标注为 deprecated。
