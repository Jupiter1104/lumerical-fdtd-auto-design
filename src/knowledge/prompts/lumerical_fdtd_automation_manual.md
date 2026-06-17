# Lumerical FDTD 自动化工程手册

版本：2026-06-01  
定位：服务于 MCP / Skill / Codex Agent 自动控制 Ansys Lumerical FDTD，不是人类入门教材。  
验证状态：所有 Python/LSF 模板均为官方 API 摘要后的工程模板，未在本机真实 Lumerical 环境运行，标注为“待验证”。

## 0. 手册目标

本手册定义一个 AI Agent 如何通过 Python API / lumapi / Lumerical Script Language 自动控制 FDTD：自动建模、参数扫描、仿真运行、结果提取、FOM 计算、优化选择、批处理执行和归档复现。

内容类型标记：
- 官方明确说明：来自 Ansys Optics、Ansys Developer Portal、PyAnsys/PyLumerical 文档。
- 工程经验总结：从官方能力组合出的 Agent 操作规范。
- 待验证假设：需要在真实 Lumerical 版本、license、OS、模板文件上运行确认。

核心官方入口：
- Python API overview: https://optics.ansys.com/hc/en-us/articles/360037824513-Python-API-overview
- Python API - Lumapi: https://developer.ansys.com/docs/lumerical/python-lumapi
- Lumerical scripting language - By category: https://optics.ansys.com/hc/en-us/articles/360037228834-Lumerical-scripting-language-By-category
- Lumerical Python API Reference: https://optics.ansys.com/hc/en-us/articles/38660003331859-Lumerical-Python-API-Reference

## 1. Lumerical FDTD 自动化总体架构

官方明确说明：Lumerical Automation API 支持通过 Lumerical Script、Python API、MATLAB 创建/修改/运行仿真、访问结果、做 sweep/optimization/inverse design。Python API 中 lumapi 负责产品自动化，lumopt 负责 inverse design，lumslurm 负责 Slurm/HPC 工作流。

工程架构图：

```text
Human requirement
  |
  v
Agent planning layer
  - translate design goal to config schema
  - choose source/monitor/mesh/boundary strategy
  - define FOM, constraints, sweep/optimization policy
  |
  v
Python control layer
  - import lumapi
  - open/copy .fsp
  - use script commands as methods or eval(.lsf)
  - write config.json / run manifest
  |
  v
Lumerical FDTD execution layer
  - FDTD solver region
  - geometry/material/source/monitor/mesh/boundary
  - run / runsweep / runjobs / lumslurm
  |
  v
Result parsing layer
  - getresult/getdata/transmission/grating
  - convert dataset to NumPy/CSV/JSON
  - record status/autoshutoff/benchmark
  |
  v
Optimization decision layer
  - compute FOM
  - check constraints and failures
  - select next sample or best design
  |
  v
Logging and reproducibility layer
  - immutable run_id directory
  - copied .fsp/.lsf/.py/config
  - results.json/results.csv/error.log/manifest.json
```

Agent 分层职责：
- 人类需求层：只描述目标，例如“810 nm 下最大化 0 阶透射，相位覆盖 0-2pi，T > 0.8”。
- Agent 规划层：把目标转成参数空间、FOM、约束、停止条件和资源预算。
- Python 控制层：唯一默认自动化入口。优先用 `lumapi.FDTD(hide=True)`、`load`/`save`、`setnamed`、`run`、`getresult`。
- Lumerical FDTD 执行层：只执行可追溯输入，不承担结果筛选逻辑。
- 结果解析层：把 monitor/sweep 结果转成机器可读文件。
- 优化决策层：Python 侧计算 FOM 并决定下一组参数；除非明确使用内置 `addsweep(1)` 或 lumopt。
- 日志与复现实验层：每次运行必须能由 run directory 复现。

## 2. FDTD 工程对象速查

### simulation region

- 用途：定义 FDTD 求解体积/面积、仿真维度、背景折射率、仿真时间、mesh、boundary、autoshutoff 和并行设置。
- 常用属性：`dimension`, `x/y/z`, `x span/y span/z span`, `background index`, `simulation time`, `mesh accuracy`, boundary 条件，`auto shutoff min`。
- 设置原则：先用 mesh accuracy 1-2 做快速初扫，再做 mesh convergence；仿真区域要覆盖 source、结构、monitor 和必要 padding；PML 边界处结构应按官方建议延伸穿过 PML。
- 自动化注意：修改对象前检查 `layoutmode`；若已运行进入 analysis mode，先 `switchtolayout`，并意识到已有结果会丢失。
- 相关命令：`addfdtd`, `set`, `setnamed`, `layoutmode`, `switchtolayout`, `run`, `getresult("FDTD","status")`。
- 最小示例：

```lsf
addfdtd;
set("dimension", 2); # 1 = 2D, 2 = 3D, 按官方 addfdtd 页面示例
set("x", 0); set("x span", 2e-6);
set("y", 0); set("y span", 2e-6);
set("z", 0); set("z span", 1e-6);
set("mesh accuracy", 2);
```

来源：
- https://optics.ansys.com/hc/en-us/articles/360034382534-FDTD-solver-Simulation-Object
- https://optics.ansys.com/hc/en-us/articles/360034924173-addfdtd-Script-command

### mesh

- 用途：控制空间离散化；mesh override 用于局部细化关键结构。
- 常用属性：global `mesh accuracy`, `min mesh step`; mesh override 的 `override x/y/z mesh`, `set maximum mesh step`, `dx/dy/dz`, span。
- 设置原则：初扫粗网格，候选最优点必须做 mesh convergence；高折射率材料有效波长更短，需要更细网格。
- 自动化注意：不要把 mesh override 作为所有失败的默认补丁；记录每次 mesh 参数，否则 FOM 不可比。
- 相关命令：`addmesh`, `set`, `setnamed`。
- 最小示例：

```lsf
addmesh;
set("name", "mesh_device");
set("x", 0); set("x span", 1e-6);
set("y", 0); set("y span", 1e-6);
set("z", 0); set("z span", 0.8e-6);
set("override x mesh", 1);
set("set maximum mesh step", 1);
set("dx", 5e-9);
```

来源：
- https://optics.ansys.com/hc/en-us/articles/360034924253-addmesh
- https://optics.ansys.com/hc/en-us/articles/360034382534-FDTD-solver-Simulation-Object

### material

- 用途：为几何体指定光学材料或折射率模型。
- 常用属性：`material`, `index`, material database entry name，mesh order。
- 设置原则：优先使用项目模板中已验证材料名；默认材料库不可直接编辑，需复制后修改。
- 自动化注意：Agent 必须记录材料名、来源、版本；不要假设不同版本材料库名称完全一致。
- 相关命令：`set("material", "...")`, `get`, material database GUI/API 命令待进一步系统验证。
- 最小示例：

```lsf
addrect;
set("name", "pillar");
set("material", "Si (Silicon) - Palik");
```

来源：
- https://optics.ansys.com/hc/en-us/articles/360034394614-Material-Database-in-FDTD-and-MODE
- https://optics.ansys.com/hc/en-us/articles/360034404214-addrect-Script-command

### geometry

- 用途：定义结构形状，例如 rectangle、circle、polygon、structure group。
- 常用属性：`name`, `x/y/z`, span, radius, vertices, material。
- 设置原则：参数化对象必须有唯一名称；优化中固定命名路径，避免 `setnamed` 修改到错误对象。
- 自动化注意：官方 Python 文档指出 duplicate object names 会造成未定义行为；Agent 应在创建前确保唯一命名。
- 相关命令：`addrect`, `addcircle`, `addpoly`, `select`, `set`, `setnamed`, `getnamednumber`。
- 最小示例：

```lsf
addrect;
set("name", "unit_cell::pillar"); # 若在 group 内，按实际 groupscope 使用
set("x span", 120e-9);
set("y span", 120e-9);
set("z span", 600e-9);
```

来源：
- https://optics.ansys.com/hc/en-us/articles/360034404214-addrect-Script-command
- https://optics.ansys.com/hc/en-us/articles/39744946400659-Working-with-Simulation-Objects-Python-API

### source

- 用途：注入电磁场。常见类型包括 plane wave、Gaussian、dipole、TFSF、mode source、imported source。
- 常用属性：`injection axis`, `direction`, `x/y/z span`, `wavelength start/stop`, angle/polarization 相关属性。
- 设置原则：周期结构正入射通常配 periodic；周期结构斜入射通常考虑 Bloch 或 BFAST；非周期开放方向用 PML。
- 自动化注意：source bandwidth 会影响 mesh/material fit/monitor frequency range；修改 source 后需要重新运行。
- 相关命令：`addplane`, `adddipole`, `addgaussian`, `addtfsf`, `setglobalsource`。
- 最小示例：

```lsf
addplane;
set("injection axis", "z");
set("direction", "backward");
set("x span", 2e-6);
set("y span", 2e-6);
set("z", 0.8e-6);
set("wavelength start", 0.8e-6);
set("wavelength stop", 0.82e-6);
```

来源：
- https://optics.ansys.com/hc/en-us/articles/360034914633-FDTD-solver
- https://optics.ansys.com/hc/en-us/articles/360034924413-addplane
- https://optics.ansys.com/hc/en-us/articles/360034382854-Sources-Plane-wave-and-Beam

### monitor

- 用途：记录频域或时域场、功率、谱、mode expansion 等结果。
- 常用属性：`monitor type`, `x/y/z`, span, `frequency points`, `override global monitor settings`。
- 设置原则：频域结果优先使用 `adddftmonitor`; `addpower`/`addprofile` 官方已标注 deprecated；time monitor 控制空间/时间 down sampling 以免内存过大。
- 自动化注意：读取前先 `haveresult` 或 `havedata`；monitor 名称应稳定且唯一，例如 `T`, `R`, `field_xy`。
- 相关命令：`adddftmonitor`, `addtime`, `addmodeexpansion`, `getresult`, `getdata`, `haveresult`, `havedata`, `transmission`。
- 最小示例：

```lsf
adddftmonitor;
set("name", "T");
set("monitor type", 7); # 2D z-normal；字符串形式需在版本中验证
set("x", 0); set("x span", 2e-6);
set("y", 0); set("y span", 2e-6);
set("z", -0.7e-6);
```

来源：
- https://optics.ansys.com/hc/en-us/articles/36957320687763-adddftmonitor-Script-command
- https://optics.ansys.com/hc/en-us/articles/360034404534-addpower-Script-command
- https://optics.ansys.com/hc/en-us/articles/360034902353-Monitors-Field-time

### boundary condition

- 用途：定义仿真区域边界的场延拓或吸收方式。
- 常用类型：PML、Periodic、Bloch、Symmetric、Anti-symmetric、Metal/PEC 等。
- 设置原则：开放边界用 PML；周期结构用 periodic；周期结构斜入射用 Bloch 或 BFAST；PML 附近结构按官方建议穿过边界区域。
- 自动化注意：边界条件与 source 类型、入射角、结构周期耦合，不应由 Agent 独立更改而不记录。
- 相关命令：通常通过 `setnamed("FDTD", "x min bc", "...")` 等属性设置，具体属性名需用 `?setnamed("FDTD")` 或版本帮助确认。
- 最小示例：

```lsf
# 属性名在目标版本中待验证；先用 ?setnamed("FDTD") 查询
setnamed("FDTD", "x min bc", "Periodic");
setnamed("FDTD", "x max bc", "Periodic");
setnamed("FDTD", "z min bc", "PML");
setnamed("FDTD", "z max bc", "PML");
```

来源：
- https://optics.ansys.com/hc/en-us/articles/360034382534-FDTD-solver-Simulation-Object
- https://optics.ansys.com/hc/en-us/articles/360034382714-Bloch-boundary-conditions-in-FDTD-and-MODE
- https://optics.ansys.com/hc/en-us/articles/360034382734-Periodic-boundary-conditions-in-FDTD-and-MODE

### analysis group

- 用途：把 monitors 和 analysis script 封装为可复用分析对象。
- 常用属性：`setup script`, analysis script, user properties, analysis results。
- 设置原则：只把稳定后处理封装进 group；复杂优化决策留在 Python 层，便于日志和异常处理。
- 自动化注意：`runanalysis` 不会重复运行已有数据的 analysis script，重跑前用 `clearanalysis`。
- 相关命令：`addanalysisgroup`, `adduserprop`, `runanalysis`, `clearanalysis`, `getresult`。
- 最小示例：

```lsf
addanalysisgroup;
set("name", "analysis_T");
addtime;
addtogroup("analysis_T");
```

来源：
- https://optics.ansys.com/hc/en-us/articles/360034382454-Analysis-Groups-Simulation-object
- https://optics.ansys.com/hc/en-us/articles/360034404074-addanalysisgroup-Script-command
- https://optics.ansys.com/hc/en-us/articles/360034409874-runanalysis-Script-command

### parameter sweep

- 用途：按参数表批量运行仿真，获取每个点的结果。
- 常用属性：sweep type、number of points、parameter path、start/stop 或 values、result path。
- 设置原则：小规模设计空间可用内置 sweep；复杂失败处理和数据库记录建议 Python 外循环。
- 自动化注意：内置 sweep 会修改/保存项目；大 sweep 必须先预览任务数和资源。
- 相关命令：`addsweep(0)`, `setsweep`, `addsweepparameter`, `addsweepresult`, `runsweep`, `getsweepresult`, `savesweep`。
- 最小示例：

```lsf
addsweep(0);
setsweep("sweep", "name", "radius_sweep");
setsweep("radius_sweep", "type", "Ranges");
setsweep("radius_sweep", "number of points", 5);
para = struct;
para.Name = "radius";
para.Parameter = "::model::pillar::radius";
para.Type = "Length";
para.Start = 50e-9;
para.Stop = 150e-9;
addsweepparameter("radius_sweep", para);
```

来源：
- https://optics.ansys.com/hc/en-us/articles/360034922853-Parameter-sweeps-Optimization-and-Monte-Carlo-analysis-overview
- https://optics.ansys.com/hc/en-us/articles/360034930413-addsweep-Script-command
- https://optics.ansys.com/hc/en-us/articles/360034930493-addsweepparameter-Script-command

### optimization

- 用途：使用优化算法寻找更优参数，或用 lumopt 做 adjoint inverse design。
- 常用属性：FOM script、parameter bounds、algorithm、generation size、maximum generations；lumopt 中 geometry、FOM、optimizer、wavelengths。
- 设置原则：低维几何参数优先 Python 外循环或内置 optimization；高维连续结构考虑 lumopt，但需要更严格的几何/FOM/许可验证。
- 自动化注意：Agent 必须区分“内置 sweep/optimization”和“外部 Python optimizer”；不要把 mock 或未收敛结果作为最优结构。
- 相关命令/API：`addsweep(1)`, `setsweep`, `getsweepresult("...","best fom")`, lumopt `ModeMatch`, `FunctionDefinedPolygon`, `ParameterizedGeometry` 等。
- 最小示例：见 `templates/parameter_sweep_template.py` 和 lumopt 官方示例。

来源：
- https://optics.ansys.com/hc/en-us/articles/360049853854-Photonic-Inverse-Design-Overview-Python-API
- https://optics.ansys.com/hc/en-us/articles/360052044913-Optimizable-Geometry-Python-API
- https://optics.ansys.com/hc/en-us/articles/360042305274-Inverse-design-of-y-branch

## 3. Lumerical Script Language 工程用法

### 创建对象

使用 `add...` 命令创建 solver、geometry、source、monitor、group。对象创建后通常成为选中对象，后续 `set` 作用于它。工程上优先立即设置唯一 `name`。

```lsf
addrect;
set("name", "pillar_r120_h600");
set("x span", 120e-9);
set("y span", 120e-9);
set("z span", 600e-9);
```

### 设置属性

- `set("property", value)`：设置当前选中对象。
- `setnamed("name", "property", value)`：设置指定名称对象。
- `setnamed("group::name", ...)`：设置 group 内对象。
- 修改已运行文件前检查 `layoutmode`，必要时 `switchtolayout`。

```lsf
if (layoutmode == 0) {
  switchtolayout;
}
setnamed("pillar", "x span", 140e-9);
```

### 运行仿真

- `run`：运行当前仿真。
- `run("FDTD", "CPU")` 或 `run("FDTD", "GPU")`：官方 run 文档给出 FDTD/RCWA resource type 形式。
- `runjobs`：运行 job manager queue。
- `runsweep`：运行 sweep/optimization。

### 读取 monitor 数据

- `getresult(monitor, result)` 返回 dataset，适合结构化结果。
- `getdata(monitor, dataname)` 返回 raw data，适合精细字段。
- `transmission(monitor)` 返回归一化透射。
- 读取前用 `haveresult`/`havedata` 防止空结果。

### 导出数据

- `savedata(filename, var1, ...)`：保存 workspace 到 Lumerical `.ldf`。
- `write(filename, string, option)`：文本/CSV 输出，官方说明 safe mode 下不可用。
- Python 自动化更推荐 Python 侧写 JSON/CSV，便于 Agent 统一处理。

### 保存文件

- `save(filename)` 保存项目；如果已运行，项目文件可包含结果。
- `load(filename)` 加载项目。
- Agent 不得直接覆盖原始模板，应复制到 run directory 后再保存。

### 参数扫描

内置 sweep 工作流：

```text
addsweep -> setsweep -> addsweepparameter -> addsweepresult -> runsweep -> getsweepresult
```

Python 外循环工作流：

```text
copy template -> set parameters -> save point .fsp -> run -> get results -> write row -> select next
```

工程建议：需要强失败处理、重试、数据库、断点续跑时，用 Python 外循环；需要复用 GUI sweep 结果或官方 sweep 功能时，用内置 sweep。

### analysis script

analysis group 可封装监视器和后处理。`runanalysis` 会运行 analysis object 脚本；已有结果不会重复运行，需先 `clearanalysis`。

### 常见命令清单

完整命令索引见 `lumerical_command_index.md`。本手册只保留工作流语义。

## 4. Python API / lumapi 工程用法

### 启动 FDTD session

官方明确说明：用产品类创建 session，例如 `lumapi.FDTD()`；支持 `hide=True` 隐藏窗口，支持 `with` context 自动关闭，支持 `serverArgs` 和 Linux interop `remoteArgs`。

```python
import lumapi

with lumapi.FDTD(hide=True) as fdtd:
    fdtd.addfdtd()
```

待验证：在本项目 Windows real-run 环境中，lumapi 导入路径应使用 Lumerical v242 bundled Python 或显式从安装路径导入。

### 加载 .fsp

```python
with lumapi.FDTD(filename=str(run_fsp), hide=True) as fdtd:
    ...
```

或：

```python
fdtd = lumapi.FDTD(hide=True)
fdtd.load(str(run_fsp))
```

### 执行 .lsf

官方 `eval` 可执行 Lumerical script 字符串，适合减少多次 API call。

```python
code = Path("setup.lsf").read_text()
fdtd.eval(code)
```

### set / get 参数

两种等价风格：

```python
fdtd.setnamed("pillar", "x span", 120e-9)
value = fdtd.getnamed("pillar", "x span")
```

或使用创建对象返回的 SimObject：

```python
rect = fdtd.addrect(name="pillar", x_span=120e-9)
rect["y span"] = 120e-9
```

工程规则：Agent 默认使用 `setnamed` + 稳定对象路径，减少 Python 变量与 CAD 对象生命周期耦合。

### run

```python
fdtd.save(str(run_fsp))
fdtd.run()
```

资源指定示例待版本验证：

```python
fdtd.run("FDTD", "CPU")
```

来源：官方 run script command 支持 FDTD solver/resource_type；Python API 支持 script commands as methods。

### getresult / getdata

```python
if fdtd.haveresult("T", "T"):
    t_dataset = fdtd.getresult("T", "T")

if fdtd.havedata("field", "Ex"):
    ex = fdtd.getdata("field", "Ex")
```

官方 Python 结果文档说明 dataset 到 Python 后是 dict，包含属性/参数键；raw data 通常映射为 NumPy 数组。

### 保存结果

Python 侧统一保存：
- `config.json`：本次输入参数。
- `results.json`：标量 FOM、约束、status、源文件路径。
- `results.csv`：参数扫描表。
- `raw/*.npz`：大矩阵或频谱。
- `logs/error.log`：异常堆栈。

### 关闭 session

优先使用：

```python
with lumapi.FDTD(hide=True) as fdtd:
    ...
```

需要显式关闭时用：

```python
fdtd.close()
```

### batch sweep

工程默认使用 Python 外循环：

```text
for sample in parameter_space:
  create run point directory
  copy template.fsp
  open session
  switch to layout if needed
  set parameters
  save point file
  run
  collect monitor results
  compute FOM
  append CSV
  close session
```

在 Slurm 中，官方 `lumslurm.run_batch` 和 `lumslurm.run_sweep` 可把 solve/postprocess/collect 拆为依赖作业。

### 转 CSV / JSON / NumPy

原则：
- 标量：JSON。
- 每个样本一行：CSV。
- 大数组：NumPy `.npz`，JSON 只写路径和 shape。
- Lumerical dataset dict 不直接 JSON dump；先抽取 scalars/list，数组转 `.npz`。

### 最小 Python 自动化模板

见 `templates/single_run_template.py`。该模板包含输入、输出目录、失败处理和结果持久化。

## 5. 参数扫描与优化工作流

### grid sweep

适用：低维、离散、可全量枚举参数。参数从 YAML/JSON config 来；每个组合一个 point directory；结果按 sample_id 命名。

### random search

适用：中维参数、早期探索。必须固定 random seed 并保存 sample table。

### Bayesian optimization

适用：真实仿真昂贵、FOM 有噪声但相对平滑。官方 Lumerical 文档不直接规定 Python 外部 BO API；这是工程经验总结。Agent 可用 scikit-optimize/Optuna 等外部库，但必须标注依赖和版本。

### 自定义 FOM

FOM 来源：
- `transmission("T")` 或 `getresult("T","T")`：透射/反射谱。
- mode expansion 结果：耦合效率。
- grating order：衍射级次效率。
- phase：从复场或 S 参数提取，具体字段需按 monitor/analysis 输出验证。

FOM 计算规则：
- 每个 FOM 必须写清公式、输入 monitor、频率/波长索引、方向、归一化。
- 不允许只保存“best=true”；必须保存原始指标和约束判断。

### 约束条件

常见约束：
- transmission >= threshold
- phase coverage / phase error <= threshold
- min feature size >= fabrication limit
- autoshutoff status acceptable
- peak memory <= resource limit
- no divergence

### 失败仿真处理

失败类型：
- session 启动失败：记录 error，sample 标记 `failed_session`。
- run 异常：记录 error，sample 标记 `failed_run`。
- monitor 无结果：记录 available results，sample 标记 `missing_result`。
- diverged/autoshutoff 异常：记录 FDTD status，sample 标记 `bad_status`。

默认重试策略：
- 同一 sample 最多 1 次重试。
- 重试只能解决临时 session/IO 错误，不自动改变物理参数。
- mesh、boundary、simulation time 改动属于新 sample，不能覆盖原 sample。

### 数据库记录

最小记录字段：

```json
{
  "run_id": "20260601T120000Z_demo",
  "sample_id": "sample_0001",
  "template_fsp": "...",
  "run_fsp": "...",
  "parameters": {},
  "metrics": {},
  "constraints": {},
  "status": "ok|failed_*",
  "source_urls": [],
  "software": {"lumerical_version": "待验证"},
  "created_at": "ISO-8601"
}
```

### 最优单元选择

选择规则必须显式：
1. 过滤失败和未满足约束的样本。
2. 按主 FOM 排序。
3. 若 FOM 并列，用次级指标排序，例如相位误差、mesh convergence、runtime。
4. 写入 `best_result.json`，包含 sample_id、run_fsp、参数、FOM、约束、原始结果文件路径。

### 通用 workflow

```text
输入参数空间
  -> 生成样本表 samples.csv
  -> 为每个样本复制仿真文件到 runs/<run_id>/simulations/<sample_id>/
  -> 修改模型参数
  -> 保存 point .fsp
  -> 运行 FDTD
  -> 读取 monitor/sweep 结果
  -> 计算 FOM
  -> 判断约束
  -> 保存记录 results.json/results.csv/raw/*.npz
  -> 选择下一组参数或结束
  -> 保存 best_result.json 与归档 manifest
```

## 6. AI Agent 控制 FDTD 的操作规范

强制规则：
1. 不直接覆盖原始 `.fsp`，只读模板，复制到 run directory。
2. 每次运行生成唯一 `run_id`。
3. 所有输入参数写入 `config.json`。
4. 所有结果写入 `results.json` / `results.csv`。
5. 所有错误写入 `logs/error.log`。
6. 仿真文件、脚本、图表、结果分目录保存。
7. 每次结论必须追溯到具体 `.fsp`、参数、monitor、代码版本和 source URL。
8. 真实 FDTD 是高成本动作；在本仓库遵守 `AGENTS.md` 的 real-run approval workflow。
9. mock/dry 输出不得作为物理证据。
10. 所有 API/属性名首次用于新版本时必须有“查询属性/小样本验证”步骤。

建议目录：

```text
runs/<run_id>/
  config.json
  manifest.json
  scripts/
    setup.lsf
    postprocess.py
  simulations/
    sample_0001/
      model.fsp
      sample_config.json
      results.json
      raw/
      logs/
  tables/
    samples.csv
    results.csv
  figures/
  best_result.json
```

## 7. 可复用模板

模板目录：`templates/`

- `single_run_template.py`：单次仿真模板。
- `parameter_sweep_template.py`：Python 外循环参数扫描模板。
- `monitor_extract_template.py`：monitor 数据提取模板。
- `fom_calculation_template.py`：FOM 计算模板。
- `retry_failed_runs_template.py`：失败重试模板。
- `select_best_result_template.py`：最优结果选择模板。
- `batch_directory_structure.md`：批量任务目录结构模板。
- `setup_minimal_fdtd.lsf`：最小 LSF 建模模板。

## 8. 常见错误与排查

### Python 找不到 lumapi

- 现象：`ModuleNotFoundError: No module named 'lumapi'`。
- 可能原因：未使用 Lumerical bundled Python；未把 `<install>/api/python` 加入路径；PyLumerical 包名与传统 `lumapi.py` 混用。
- 排查步骤：确认 Lumerical 版本；确认 `api/python/lumapi.py`；用官方 Installation 页示例导入；在 Windows real-run 中优先用 Lumerical 自带 Python。
- 修复方案：使用安装目录 Python 或 `importlib.util.spec_from_file_location` 加载 lumapi。
- 预防规则：run manifest 记录 Python executable 和 lumapi path。
- 来源：https://optics.ansys.com/hc/en-us/articles/39744901602707-Installation-and-Getting-Started-Python-API

### FDTD session 启动失败

- 现象：`lumapi.FDTD()` 抛异常或 GUI/engine 无响应。
- 可能原因：license 不足、DISPLAY/offscreen 问题、安装路径错误、serverArgs 不适配。
- 排查步骤：先 GUI 打开；再 `lumapi.FDTD(hide=False)`；Linux headless 尝试官方 `serverArgs` 的 `platform: offscreen`。
- 修复方案：按官方 Session Management 设置 `hide`, `serverArgs`, `remoteArgs`。
- 预防规则：模板中捕获 session 初始化异常并写入 `error.log`。
- 来源：https://optics.ansys.com/hc/en-us/articles/360041873053-Session-Management-Python-API

### license 问题

- 现象：session 或 run 启动时 license checkout 失败。
- 可能原因：GUI/API/solve license 不足；lumslurm enterprise license sharing 行为未确认。
- 排查步骤：记录 license error 原文；确认 GUI license、API license、solve license；HPC 前估算核心数和 license。
- 修复方案：降低并发；改为 dry/mock；请求人工许可确认。
- 预防规则：真实 run 前报告任务数、资源、license 风险。
- 来源：https://optics.ansys.com/hc/en-us/articles/20990924220691-Getting-Started-with-lumslurm-Python-API

### 属性名错误

- 现象：`setnamed` 报 no property 或 no item matching。
- 可能原因：对象名不唯一/不存在；属性名随对象类型或版本不同；Python keyword 下划线映射误用。
- 排查步骤：`?setnamed("object")` 查询属性；`getnamednumber` 查重名；Python 中优先脚本属性名。
- 修复方案：稳定命名；用 object path；必要时版本分支。
- 预防规则：首次接入新模板时导出对象属性清单。
- 来源：https://optics.ansys.com/hc/en-us/articles/360034928793-setnamed-Script-command

### monitor 无数据

- 现象：`getresult`/`getdata` 空或报错。
- 可能原因：未运行仿真；monitor 名错；monitor 未覆盖目标区域；analysis group 未 `runanalysis`。
- 排查步骤：`haveresult`, `havedata`, `?getresult("monitor")`, `?getdata("monitor")`。
- 修复方案：检查 monitor 位置/type/frequency points；运行仿真或 analysis。
- 预防规则：读取前强制存在性检查，失败样本不计算 FOM。
- 来源：
  - https://optics.ansys.com/hc/en-us/articles/360034409854-getresult
  - https://optics.ansys.com/hc/en-us/articles/360034409834-getdata

### 仿真未收敛

- 现象：FDTD status 非预期、autoshutoff 未降到阈值或结果异常。
- 可能原因：simulation time 太短、Q 值高、PML/mesh/source 设置问题。
- 排查步骤：读取 `getresult("FDTD","status")` 和 autoshutoff；查看 time monitor。
- 修复方案：增加 simulation time、调整 PML、重新做 mesh convergence。
- 预防规则：FOM 记录必须包含 status/autoshutoff。
- 来源：https://optics.ansys.com/hc/en-us/articles/360034382534-FDTD-solver-Simulation-Object

### mesh 过粗

- 现象：FOM 随 mesh accuracy/override 显著变化。
- 可能原因：高折射率/小特征/金属结构没有充分离散。
- 排查步骤：对候选点做 mesh sweep；比较 FOM 变化。
- 修复方案：提高 mesh accuracy 或局部 override；记录新 sample。
- 预防规则：最终最佳结构必须有 mesh convergence 附件。
- 来源：https://optics.ansys.com/hc/en-us/articles/360034382534-FDTD-solver-Simulation-Object

### 内存不足

- 现象：run 中断、系统杀进程、monitor 结果巨大。
- 可能原因：3D 高精度 mesh、大面积 time monitor、过多 frequency points。
- 排查步骤：读取 FDTD benchmark peak memory；估算 grid points；减少 monitor 数据。
- 修复方案：缩小仿真区域、降低 monitor 维度/downsample、HPC/lumslurm。
- 预防规则：禁止默认保存全域时域场。
- 来源：
  - https://optics.ansys.com/hc/en-us/articles/360034382534-FDTD-solver-Simulation-Object
  - https://optics.ansys.com/hc/en-us/articles/360034902353-Monitors-Field-time

### 文件路径错误

- 现象：`load`/`save`/`eval` 找不到文件。
- 可能原因：工作目录不一致；Windows 路径反斜杠转义；Mac-to-Windows 远程路径未映射。
- 排查步骤：打印 cwd；使用绝对路径；Windows 传给 lumapi 时优先 forward slash。
- 修复方案：所有路径进 manifest；Python 用 `Path.resolve()`。
- 预防规则：Agent 不使用隐式当前目录保存关键结果。
- 来源：https://optics.ansys.com/hc/en-us/articles/360034410834-load-Script-command

### headless / batch 运行失败

- 现象：Linux 无显示或 CLI run 失败。
- 可能原因：没有 `-nw`/offscreen；safe mode；脚本未 trust；Interop Server 证书/端口问题。
- 排查步骤：对照官方 Linux terminal 和 Interop Server 文档；记录命令行。
- 修复方案：使用 `fdtd-solutions -nw -trust-script -run script.lsf file.fsp` 或 Python `serverArgs`。
- 预防规则：headless 配置独立保存，不与本地 GUI 配置混用。
- 来源：
  - https://optics.ansys.com/hc/en-us/articles/360024974033-Running-simulations-using-terminal-on-Linux
  - https://optics.ansys.com/hc/en-us/articles/15499581457811-Interop-Server-Remote-API

## 9. Agent 可执行检查清单

### 建模前检查

- [ ] 已确认目标波长/频率、偏振、入射方向、边界类型。
- [ ] 已确认 template `.fsp` 只读，不会覆盖。
- [ ] 已确认材料名和对象名来自模板或官方文档。
- [ ] 已定义参数空间、单位、范围、制造约束。
- [ ] 已定义 source/monitor 名称和 FOM 公式。

### 仿真前检查

- [ ] 已生成唯一 `run_id` 和 run directory。
- [ ] 已写入 `config.json`。
- [ ] 已复制 `.fsp` 到 sample directory。
- [ ] 已检查 `layoutmode`，修改前必要时 `switchtolayout`。
- [ ] 已保存 point `.fsp`。
- [ ] 真实 FDTD 前已按本仓库 `AGENTS.md` 完成审批。

### 运行中检查

- [ ] 捕获 session/run 异常。
- [ ] 写入 `logs/error.log`。
- [ ] 记录 runtime、resource type、software version（可获得时）。
- [ ] 不在失败后静默更改物理参数重跑。

### 结果读取检查

- [ ] `haveresult`/`havedata` 通过。
- [ ] 已保存 raw data 路径或压缩数组。
- [ ] 已记录 FDTD status/autoshutoff。
- [ ] 已将标量结果写入 `results.json`。
- [ ] 已追加 `results.csv`。

### 优化选择检查

- [ ] 过滤失败样本。
- [ ] 过滤约束不满足样本。
- [ ] 按 FOM 和 tie-breaker 排序。
- [ ] `best_result.json` 指向原始 sample 和 `.fsp`。
- [ ] 最优结论没有使用 mock/dry 作为物理证据。

### 归档检查

- [ ] `manifest.json` 包含代码版本、source URLs、模板路径、生成脚本。
- [ ] `source_map.md` 或等价引用可追溯。
- [ ] 所有待验证假设列入 `open_questions.md`。
- [ ] 可由另一个 Agent 从 `config.json` 和模板重跑。

## 第四阶段自检

1. 是否每个关键结论都有来源：核心 API、命令、对象、sweep、HPC 规则均引用官方 URL；工程规范标注为工程经验总结。
2. 是否区分官方资料和推断：本手册使用“官方明确说明 / 工程经验总结 / 待验证假设”标记。
3. 是否包含可执行代码模板：见 `templates/`。
4. 是否避免未经验证 API 调用：模板中使用官方命令；版本/属性不确定处标注待验证。
5. 是否所有命令都有官方来源或标注待验证：命令索引逐条列 URL；boundary 属性名示例标注待验证。
6. 是否能指导另一个 Agent 执行自动化仿真：包含 run directory、config、结果、失败处理、FOM、最佳选择和审批规范。
