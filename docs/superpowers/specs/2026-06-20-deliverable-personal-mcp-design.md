# 可交付个人 FDTD MCP 设计

## 决策

将现有项目收敛为一套可重复部署、可切换 Windows 工作站、可被 Codex、Claude Code 和 Hermes 使用的个人 FDTD MCP。

首版交付采用仓库原生双端部署：

- Mac 运行 MCP Server。
- Windows 运行 RPC Server 和 Lumerical FDTD。
- 项目目录可通过 ToDesk 传输，不依赖 Git、PyPI 或容器。
- 一个 MCP 进程只连接一台 Windows；切换电脑时修改 `FDTD_RPC_URL` 并重启 MCP。
- 交付验收只验证安装、协议、工具、参数传递和 mock 持久作业，不要求真实物理仿真。

## 背景

当前项目已经具备 API v1、Mac `RpcClient`、FastMCP 工具、SimulationPlan、审批、持久 job/task、结果下载、质量报告和飞书通知。现阶段缺口不是仿真物理结果，而是把已有能力收敛成一套个人可以在当前 Windows 和实验室 Windows 工作站之间迁移的 MCP 交付物。

用户已经拥有可覆盖 2π 的参数集。该参数集是 MCP 的输入数据，不是本项目要重新发现或验证的物理成果。项目开发不得以 C4/C5 真实 sweep、2π phase library 或器件优化结果作为 MCP 交付前置条件。

## 目标

1. 在 Mac 上通过一个安装命令创建运行环境，并生成 Codex、Claude Code、Hermes 三种 MCP 配置。
2. 在任意满足环境要求的 Windows 工作站上，通过首次配置完成 RPC 部署，此后可双击启动、停止、查询和重启。
3. 支持 SSH 隧道和可信局域网直连，两种模式只通过 `FDTD_RPC_URL` 区分。
4. 默认暴露精简的 API v1 MCP 工具面，并默认开放 raw Lumerical `eval/getv/setv` 高级能力。
5. 使用 MCP stdio、fake-lumapi 契约测试和一个有界 Windows 最小 solver smoke 完成交付验收；smoke 只证明工具链能运行，不作为物理实验或器件结果。
6. 项目目录被 ToDesk 覆盖更新时，Windows 本机配置、日志、PID 和持久 job 不丢失。
7. 允许上层 Agent 将用户自然语言转换为通用 SweepPlan，并由 MCP 确定性校验、展开和创建扫参任务。
8. 允许上层 Agent 从论文中提取参数和引用位置，生成通用 DeviceRecipe；MCP 将 Recipe 确定性编译为可审计的 Lumerical script，经用户确认后创建 `.fsp`。
9. 提供覆盖常规 FDTD 仿真 20 步流程的通用操作闭环，使 Agent 能像用户在 FDTD GUI 中一样搭建、检查、运行和读取任意器件。

## 非目标

- 不在本阶段运行 C4/C5 真实 sweep。
- 不判断用户参数是否真的覆盖 2π，也不验证器件物理正确性。
- 不支持一台 MCP 同时连接多台 Windows。
- 不在 MCP 运行中动态切换 Windows。
- 不支持 Linux、Slurm、集群队列或多机调度。
- 不发布 PyPI 包，不制作 macOS App，不制作 Windows 安装程序。
- 不提供公网暴露、API Key、TLS 或多用户认证。
- 不保证非 Lumerical v242 版本兼容。
- 不开发 Codex、Claude Code 或 Hermes 专属业务逻辑；三者共享同一个 stdio MCP Server。
- MCP 不直接读取、OCR、总结或理解论文 PDF；论文阅读由 Codex、Claude Code 或 Hermes 完成。
- MCP 不自动补造论文中的关键参数，不宣称生成结构与论文物理等价。
- DeviceRecipe 编译完成后不自动连接 Windows、不自动创建模型、不自动运行求解。
- 不以参数扫描、优化或论文器件的真实求解作为交付验收；唯一允许的 solver 验收是固定、单任务、低成本的最小技术 smoke。

## 总体架构

```text
Codex / Claude Code / Hermes
            │ MCP stdio
            ▼
Mac FDTD MCP Server
  ├─ Session / Project / Generic Objects
  ├─ Debug: eval / getv / setv
  ├─ Materials / Solver / Sources / Monitors
  ├─ Analysis / Diagnostics / Results
  ├─ DeviceRecipe validate / compile / build
  ├─ Generic SweepPlan validate / plan / start
  ├─ SimulationPlan / Approval
  ├─ Persistent Job / Results
  └─ Knowledge
            │ HTTP API v1
            ▼
当前 Windows 或实验室 Windows
  ├─ RPC Server
  ├─ Persistent JobStore
  ├─ raw lumapi
  └─ Lumerical FDTD v242
```

### 组件边界

#### Mac MCP Server

- 是 Codex、Claude Code 和 Hermes 的唯一 Agent 入口。
- 通过 stdio 提供 MCP，不开放额外 HTTP MCP 端口。
- 不导入 `lumapi`，不直接读取 Windows 文件系统。
- 启动时只读取一个 `FDTD_RPC_URL`。
- Windows 离线时仍允许 MCP 进程启动和列出工具；具体工具调用返回结构化连接错误。
- DeviceRecipe 校验、script 编译和 SweepPlan 任务展开均为本地纯函数，不要求 Windows 在线。
- 论文到 DeviceRecipe 的语义转换由上层 Agent 完成；MCP 只接受结构化输入。

#### Windows RPC Server

- 是 Lumerical FDTD 的唯一执行入口。
- 使用 Lumerical v242 自带 Python 和 raw `lumapi`。
- 继续提供 HTTP API v1、持久 JobStore、结果文件和飞书通知。
- 新增通用 project/object/material/solver/source/monitor/analysis/result API v1 路由；Mac typed tools 不通过 `/debug/eval` 假装实现结构化能力。
- 新增 `POST /recipes/build`，用于执行已确认的 build-only script 并保存 `.fsp`。
- `/jobs/plan` 和 `/jobs/start` 新增 `job_type=recipe-sweep`，用于通用 Recipe 扫参。
- Server 端可保留 legacy HTTP 别名兼容旧脚本，但这些别名不再通过 MCP 暴露。

#### 连接

- SSH 隧道模式：Windows RPC 只监听 `127.0.0.1`；Mac 的 `FDTD_RPC_URL` 指向本地隧道端口，例如 `http://127.0.0.1:5501`。
- 局域网模式：Windows RPC 监听 `0.0.0.0`；Mac 的 `FDTD_RPC_URL` 指向 Windows 私网地址，例如 `http://192.168.1.20:5000`。
- 局域网模式仅允许 Windows“专用网络”防火墙范围，不配置公网端口映射。
- SSH 隧道断开时只报告连接失败，不自动回退到局域网地址或另一台电脑。

## 实施优先级

实现顺序固定为：

1. 通用 FDTD 操作闭环。
2. DeviceRecipe 编译、确认和 build。
3. Generic SweepPlan 和 `recipe-sweep` 持久 job。
4. 器件 Recipe 与 Skill 沉淀。

DeviceRecipe 和 SweepPlan 必须复用通用操作闭环的编译器和 RPC 能力，不得另造第二套 Lumerical 执行后端。器件 Skill 只描述如何组合 Recipe、SweepPlan 和验收规则，不直接绕过 MCP 调用 Windows。

## 通用 FDTD 操作闭环

### 完成定义

通用闭环必须覆盖：

```text
新建/加载工程
→ 几何与材料
→ FDTD region / 时间 / 背景 / 边界 / PML / 网格
→ source / 方向 / 角度 / 偏振 / 波长或频率范围
→ monitor / analysis group / 采样
→ 材料拟合诊断与内存预估
→ 参数扫描
→ 运行
→ 后处理
→ 列举、读取、拉取和导出结果
→ 保存 .fsp
```

每个阶段至少支持：

- 结构化创建或配置。
- 读取当前配置。
- 编译或执行前审查。
- 结构化错误诊断。
- 保存为 DeviceRecipe 或 Skill 所需的稳定输入。

### `0.1.0` 验收分层

#### 必须端到端验收

图中红色和橙色步骤必须具备 typed tools，并通过真实 API v1 端到端验证：

- 几何和材料。
- FDTD 求解区域。
- 背景材料。
- 边界条件。
- 光源创建和完整光源设置。
- 监视器创建、物理量和采样设置。
- analysis group 创建。
- 参数扫描。
- 运行。
- 查看、读取和下载结果。

#### 必须具备配置、读取和诊断

图中蓝色步骤必须具备 typed 配置、读取和诊断接口，但 `0.1.0` 不要求自动寻找最优值：

- 仿真时间。
- PML 参数。
- 网格。
- Auto shutoff min。
- 材料拟合设置和拟合质量诊断。
- 仿真内存预估。

#### 通过通用高级接口覆盖

图中黑色高级处理通过 analysis group 与默认开启的 raw script 能力覆盖：

- analysis group setup script。
- analysis script。
- 自定义后处理。
- 非标准 Lumerical 命令。

### 20 步能力映射

| 步骤 | 流程 | 结构化 MCP 能力 | `0.1.0` 验收 |
|---|---|---|---|
| 1 | 画几何结构并设置材料 | Generic object create/update；material create/assign | 端到端 |
| 2 | 设置 FDTD 求解范围 | solver create/update/get | 端到端 |
| 3 | 调整仿真时间 | solver timing get/set | 配置、读取、诊断 |
| 4 | 设置背景材料 | solver background get/set | 端到端 |
| 5 | 设置边界条件 | boundary get/set | 端到端 |
| 6 | 优化 PML 参数 | PML get/set/diagnose | 配置、读取、诊断 |
| 7 | 优化网格 | global mesh、mesh override、mesh diagnose | 配置、读取、诊断 |
| 8 | 调整 Auto shutoff min | solver shutoff get/set | 配置、读取、诊断 |
| 9 | 添加光源 | source create/update/get | 端到端 |
| 10 | 设置入射方向、入射角、偏振角 | source typed properties | 端到端 |
| 11 | 设置波长/频率范围 | source spectrum get/set | 端到端 |
| 12 | 添加监视器 | monitor create/update/get | 端到端 |
| 13 | 添加分析组 | analysis group create/update/get | 端到端 |
| 14 | 设置物理量和采样点数 | monitor result fields/frequency points get/set | 端到端 |
| 15 | 优化材料拟合 | material fit get/set/diagnose | 配置、读取、诊断 |
| 16 | 检查所需内存 | simulation resource estimate | 配置、读取、诊断 |
| 17 | 添加参数扫描 | Generic SweepPlan | 端到端 |
| 18 | 运行计算 | synchronous short run；persistent long job | 端到端 |
| 19 | 分析组脚本后处理 | setup/analysis script；raw hooks | 高级接口 |
| 20 | 查看计算结果 | result list/describe/read/download/export | 端到端 |

### 通用对象模型

FDTD 对象操作不按每种器件创建独立工具。统一对象 API 覆盖：

- `fdtd_region`
- `rectangle`
- `circle`
- `ring`
- `polygon`
- `structure_group`
- `mesh_override`
- `plane_source`
- `mode_source`
- `gaussian_source`
- `dipole_source`
- `dft_monitor`
- `power_monitor`
- `time_monitor`
- `index_monitor`
- `analysis_group`

所有对象统一使用：

```text
create
→ list
→ get
→ update
→ copy
→ rename
→ delete
→ add/remove from group
```

对象由稳定唯一 `name` 标识；工具不得依赖 GUI 当前选中对象。更新和读取使用结构化 `properties`，属性名保持 Lumerical v242 canonical naming，并在返回值中给出规范化后的实际属性。

工具职责不重复：

- `fdtd_object_create/update` 直接创建和更新 geometry、group 与 mesh override。
- source、monitor 和 analysis group 的创建/更新必须走各自 typed facade。
- `fdtd_object_list/get/copy/rename/delete` 可作用于所有命名对象。
- 所有 facade 最终复用同一个 Windows object adapter、属性规范化器和错误模型。

### 原子工具设计

为了保持工具面可发现，不为每种对象和每个动作生成独立 MCP tool。交付版使用按领域聚合的 typed tools。

#### 工程和会话

- `fdtd_health`
- `fdtd_session_start`
- `fdtd_session_pause`
- `fdtd_session_close`
- `fdtd_project_new`
- `fdtd_project_load`
- `fdtd_project_save`
- `fdtd_project_status`
- `fdtd_switch_to_layout`

#### 通用对象

- `fdtd_object_create(object_type, name, properties)`
- `fdtd_object_list(scope, object_type)`
- `fdtd_object_get(name, properties)`
- `fdtd_object_update(name, properties)`
- `fdtd_object_copy(name, new_name, transform)`
- `fdtd_object_rename(name, new_name)`
- `fdtd_object_delete(name)`
- `fdtd_group_update(group_name, add, remove)`

typed object tool 必须校验 `object_type`、必填属性、单位、材料引用和稳定名称。未覆盖的特殊属性仍可通过 `properties` 传递，但返回 warning，并在 v242 上执行前先检查属性是否存在。

`fdtd_object_create/update` 的 `object_type` 仅接受 geometry、group 和 mesh override；source、monitor 和 analysis group 输入返回 `use_typed_domain_tool`，并指出应调用的工具。

#### 材料

- `fdtd_material_create`
- `fdtd_material_list`
- `fdtd_material_get`
- `fdtd_material_update`
- `fdtd_material_assign`
- `fdtd_material_fit_diagnose`

#### Solver 和精度

- `fdtd_solver_get`
- `fdtd_solver_update`
- `fdtd_mesh_diagnose`
- `fdtd_resource_estimate`

`fdtd_solver_update` 统一覆盖 region、simulation time、background material、boundaries、PML、global mesh、auto shutoff 和 resource 设置；返回变更前后差异。`fdtd_mesh_diagnose` 和 `fdtd_resource_estimate` 不运行求解。

#### Source

- `fdtd_source_create`
- `fdtd_source_get`
- `fdtd_source_update`

source typed schema 覆盖 source type、位置、span、注入轴、方向、入射角、偏振角、波长/频率范围和 mode selection。

#### Monitor

- `fdtd_monitor_create`
- `fdtd_monitor_get`
- `fdtd_monitor_update`

monitor typed schema 覆盖 monitor type、位置、span、物理量、频率点数、采样方式、down sample 和输出名称。

#### Analysis

- `fdtd_analysis_group_create`
- `fdtd_analysis_group_get`
- `fdtd_analysis_group_update`

analysis group schema 覆盖 properties、setup script、analysis script、结果声明和参数声明。

#### Run 和 result

- `fdtd_simulation_run`
- `fdtd_simulation_status`
- `fdtd_result_list`
- `fdtd_result_describe`
- `fdtd_result_read`
- `fdtd_results_download`
- `fdtd_export_gds`
- `fdtd_export_data`

`fdtd_simulation_run` 只用于明确标记为短任务的当前模型同步运行。预计超过 30 秒、批量任务或 SweepPlan 必须走持久 `/jobs/*`。

`fdtd_result_read` 返回 JSON 可表达的标量、数组和 dataset metadata。大数组超过响应预算时写入 job/results 文件并返回下载路径，不把无限数据塞进 MCP 上下文。

#### Raw capability

- `fdtd_eval`
- `fdtd_getv`
- `fdtd_setv`

raw 工具默认开启，是极特殊命令的逃生口，不替代红色和橙色步骤的 typed tools。

### 编译、预览与执行

所有改变模型的 typed tools支持 `dry_run`：

- `dry_run=true`：返回拟执行的 Lumerical script、目标对象、属性、warnings 和 script SHA-256，不连接或修改 FDTD。
- `dry_run=false`：通过 API v1 执行，并返回执行后读取的实际对象状态。

批量结构创建优先使用 DeviceRecipe 的 compile → confirm → build，不要求 Agent 连续调用几十次对象工具。原子工具用于探索、调试、人工式搭建和 Recipe/Skill 原型化。

新建工程具有额外保护：

- 当前模型存在未保存变更时，`fdtd_project_new` 默认拒绝。
- 只有 `discard_unsaved=true` 才允许清空。
- 返回值明确说明原模型路径、dirty 状态和是否发生清空。

### API v1 路由分组

通用闭环至少增加以下路由组：

```text
/project/new
/project/status
/model/load
/model/save
/model/layout

/objects
/objects/<name>
/objects/<name>/copy
/objects/<name>/rename
/groups/<name>/members

/materials
/materials/<id>
/materials/<id>/fit-diagnostics

/solver
/solver/mesh-diagnostics
/solver/resource-estimate

/sources
/sources/<name>
/monitors
/monitors/<name>
/analysis-groups
/analysis-groups/<name>

/simulation/run
/simulation/status
/results
/results/<object>
/results/<object>/<result>
/results/files/<path>
```

每个变更路由接受 `dry_run`，成功和失败继续使用 API v1 envelope。对象、source、monitor 和 analysis group 路由必须在响应中回读实际状态，而不是只返回“命令已发送”。

### 能力沉淀

```text
原子工具成功搭建一次器件
→ 导出/整理 DeviceRecipe
→ Recipe 加入参数来源、假设和验收
→ Generic SweepPlan 复用参数
→ 高频稳定流程沉淀为 Skill
```

Skill 只固化：

- 何时使用。
- 论文参数如何映射到 Recipe。
- 推荐建模顺序。
- 验证和故障排除。
- 可复用 Recipe/SweepPlan 模板。

Skill 不复制 RPC 或 compiler 实现。

## 论文复现与自然语言职责边界

### 自然语言扫参

用户可以自然语言描述扫参任务，但自然语言不是 MCP 工具的直接输入：

```text
用户自然语言
→ Codex / Claude Code / Hermes 生成 DeviceRecipe + SweepPlan
→ MCP 校验 Recipe 和 SweepPlan
→ MCP 展开确定性任务清单
→ plan / mock / real 持久 job
```

MCP 不内置大语言模型，也不在 Python 中解析自然语言。它负责：

- 校验参数名、单位、表达式和任务预算。
- 将显式列表或线性区间展开为有界笛卡尔积。
- 生成稳定 Recipe、SweepPlan 和 task 指纹。
- 将每个任务编译为完整参数快照和 Lumerical script。
- 在 plan、mock、real 三种模式中保持相同任务语义。

### 论文到器件结构

```text
论文 / PDF / 用户笔记
→ 上层 Agent 提取结构、材料、仿真设置和来源位置
→ DeviceRecipe
→ MCP validate
→ MCP compile
→ script + 编译报告 + 对象清单
→ 用户确认 exact fingerprint
→ MCP build
→ Windows 创建结构并保存 .fsp
```

MCP 不声称“理解论文”。可审计边界是：

- 上层 Agent 对论文内容和参数提取负责。
- DeviceRecipe 对参数值、来源和假设负责。
- MCP 对 schema、表达式、对象依赖、确定性编译和执行顺序负责。
- 用户对编译报告和最终 GUI 结构预览负责。

## DeviceRecipe v1

### 顶层结构

```yaml
schema_version: "1.0"
metadata:
  name: paper_device
  device_type: free_text
  coordinate_system: cartesian
  length_unit: m

references:
  - id: paper
    title: "Paper title"
    doi: "10.xxxx/example"
    year: 2024

parameters:
  pillar_radius:
    value: 180e-9
    required: true
    source_ref:
      reference_id: paper
      locator: "Fig. 2b"
  mesh_dx:
    value: 10e-9
    required: false
    assumption:
      reason: "论文未披露"
      basis: "用户确认的默认值"

materials:
  - id: core
    model: database
    name: "Si3N4 (Silicon Nitride) - Phillip"

geometry:
  - id: pillar
    type: circle
    properties:
      radius: "${pillar_radius}"
      z_span: "${pillar_height}"
      material: core

simulation:
  region: {}
  boundaries: {}
  mesh: []
  sources: []
  monitors: []

postprocess:
  metrics: []

acceptance:
  structural_checks: []
  result_checks: []

raw_hooks:
  pre_geometry: ""
  post_geometry: ""
  pre_run: ""
  post_run: ""
```

器件类型是自由文本标签，不决定 schema 分支。实际结构由通用原语和参数表达式描述。

### 参数和表达式

每个参数包含：

- `value`：默认标量或数组。
- `required`：是否属于关键参数。
- `source_ref`：论文或其他来源的位置。
- `assumption`：非关键缺失参数的显式假设。

规则：

- `required=true` 的参数必须有值和 `source_ref.locator`。
- 关键来源位置使用页码、公式、图号或表号，例如 `p. 4`、`Eq. 7`、`Fig. 2b`、`Table 1`。
- 非关键参数缺失时可以使用默认值，但必须包含 `assumption.reason` 和 `assumption.basis`。
- 禁止静默默认。
- Recipe 不保存大段论文原文。

表达式只允许：

- 参数引用：`${pillar_radius}`。
- 数字常量。
- `+`、`-`、`*`、`/`、括号和一元正负号。

禁止：

- Python、Lumerical script 或函数调用。
- 属性访问、索引、文件读取或环境变量读取。
- 未声明参数。
- 非有限数值和除零。

表达式解析使用专用 AST 或 parser，不使用 Python `eval()`。

### 通用几何原语

首版支持：

- `rectangle`
- `circle`
- `ring`
- `polygon`
- `taper`
- `array`
- `group`

所有对象必须有稳定唯一 `id`。对象引用使用 `id`，不依赖创建后的隐式选择状态。

`array` 引用一个已定义的基础对象或内联对象，并声明确定性的数量与间距。`group` 只组织对象和局部变换，不允许改变子对象的物理参数来源。

### 材料

首版支持：

- `database`：Lumerical 材料数据库名称。
- `constant_index`：固定 `n`，可选 `k`。
- `sampled_data`：相对 Recipe 根或 Windows workspace 的 `n/k` 数据文件。

材料引用必须指向 `materials[].id`。文件路径必须经过 workspace 边界检查。

### 仿真环境

Recipe 完整描述：

- FDTD region。
- Boundary：PML、periodic、Bloch、symmetric、anti-symmetric、metal。
- Global mesh 和 mesh override。
- Source：plane wave、mode、Gaussian、dipole。
- Monitor：DFT field、power、time、index。
- 后处理 metrics。
- structural checks 和 result checks。

每个 source、monitor 和 mesh override 同样必须有唯一 `id`。

### Raw-script escape hatch

只允许四个生命周期钩子：

1. `pre_geometry`
2. `post_geometry`
3. `pre_run`
4. `post_run`

执行顺序固定：

```text
pre_geometry
→ materials
→ geometry
→ post_geometry
→ simulation region / boundaries / mesh / sources / monitors
→ save model
→ pre_run
→ optional run
→ post_run
```

规则：

- raw hook 内容纳入 Recipe 指纹、编译报告和审批。
- hook 变化使旧 fingerprint 和旧批准失效。
- 编译报告明确列出每个非空 hook 的字符数、SHA-256 和生命周期位置。
- raw hook 不允许读取 MCP/Windows 进程环境变量。
- `pre_run` 和 `post_run` 在 build-only 模式下不执行，只写入待执行脚本并在报告中标记。

### 校验输出

`fdtd_device_recipe_validate` 返回：

- 规范化 Recipe。
- errors 和 warnings。
- defaults/assumptions 清单。
- 参数来源覆盖率。
- 对象、材料、source、monitor 和 mesh 清单。
- 未解析引用。
- Recipe fingerprint。

### 编译输出

`fdtd_device_recipe_compile` 为本地纯操作，返回：

- 规范化 Recipe。
- 完整 Lumerical script。
- script SHA-256。
- Recipe fingerprint。
- 编译 fingerprint。
- 按生命周期排序的对象清单。
- 参数值和来源报告。
- assumptions 和 raw hooks 报告。
- 预计创建对象数。
- build-only 与 run-capable 标记。

默认只编译，不连接 Windows。

### 用户确认和建模

`fdtd_device_recipe_build` 必须接收：

- 原始或规范化 Recipe。
- 用户确认的 `compile_fingerprint`。
- Windows 输出 `.fsp` 路径。
- `approved=true`。

工具重新校验和编译 Recipe；fingerprint 不一致时拒绝执行。成功时：

1. 确认 RPC health。
2. 调用 `POST /recipes/build`，提交 build-only script、Recipe fingerprint、compile fingerprint、对象清单和输出路径。
3. Windows 再次校验指纹和输出路径边界。
4. RPC 拒绝覆盖活动 real job 使用的 session；没有活动 real job 时进入 layout，并创建干净的新工程。
5. 执行 build-only script。
6. 保存固定 `.fsp` 路径。
7. 返回对象清单、模型路径和执行日志摘要。

该工具不运行求解，不执行 `pre_run` 或 `post_run`。

## Generic SweepPlan v1

### 数据模型

```yaml
schema_version: "1.0"
recipe: device-recipe.yaml

sweep:
  parameters:
    pillar_radius:
      values: [150e-9, 175e-9, 200e-9]
    pillar_height:
      range:
        start: 500e-9
        stop: 800e-9
        count: 7

execution:
  mode: plan
  max_tasks: 100
  resource: CPU
  processes: 1
  capacity: 1
  hide: true

outputs:
  include_models: false
  metrics: [transmission, phase]
```

`recipe` 可以是 Recipe 文件路径，也可以由 MCP tool 参数直接传入内联 Recipe；两者不得同时提供。

### 采样

每个参数必须使用且只能使用一种形式：

- `values`：显式有序值列表。
- `range`：`start`、`stop`、`count`，采用包含首尾的线性采样。

规则：

- `values` 保持用户声明顺序。
- 拒绝空列表、重复值和非有限数值。
- `range.count` 必须为大于等于 2 的整数。
- `range.start` 和 `range.stop` 必须不同。
- 线性区间的最后一个值强制等于 `stop`，避免累计浮点误差。
- Sweep 参数必须已在 Recipe 顶层 `parameters` 声明。
- 所有参数取笛卡尔积。
- 参数维度顺序按 SweepPlan 中的声明顺序。
- 最后声明的参数变化最快。

### 任务展开

每个任务包含：

- 稳定 `task_id`。
- task index。
- 完整参数快照。
- 规范化 Recipe fingerprint。
- SweepPlan fingerprint。
- 编译 fingerprint。
- 该任务的 Lumerical script SHA-256。
- 预期输出路径。

相同 Recipe 和 SweepPlan 必须生成相同任务顺序、ID 和指纹。

展开后的任务数超过 `execution.max_tasks` 时直接失败，不截断任务。

### 运行模式

#### plan

- 本地校验 Recipe 和 SweepPlan。
- 展开完整任务清单。
- 编译每个任务。
- 返回任务数、输出路径、成本和覆盖风险。
- 不调用 Windows RPC。

#### mock

- 创建持久 job/task。
- 验证脚本编译、状态、summary、metrics 数据形状和结果索引。
- 不启动 FDTD。
- mock 数据明确标记 `synthetic=true`。

#### real

- 要求 exact plan packet 和用户明确批准。
- 任何 Recipe、参数、raw hook、材料文件指纹、模板或执行设置变化都会使批准失效。
- 启动后返回 `job_id`，Agent 停止轮询。

### MCP 工具契约

#### `fdtd_generic_sweep_validate`

输入 Recipe 和 SweepPlan，执行本地 schema、表达式、引用、采样和预算校验。返回规范化输入、完整任务数、Recipe fingerprint、SweepPlan fingerprint、errors 和 warnings；不编译所有 task script，不调用 RPC。

#### `fdtd_generic_sweep_plan`

输入已通过或原始 Recipe 和 SweepPlan，执行本地完整任务展开与 script 编译。返回：

- exact plan packet。
- 完整 task manifest。
- 每个 task 的参数快照和 script SHA-256。
- Recipe、SweepPlan 和 packet fingerprint。
- 输出目录、对象数、预计模型数和覆盖风险。

该工具不调用 RPC，也不创建 Windows job。

#### `fdtd_generic_sweep_start`

输入：

- Recipe。
- SweepPlan。
- `mode`：`mock` 或 `real`。
- 用户确认的 exact `packet_fingerprint`。
- `approved=true`。

工具重新执行 validate 和 plan。fingerprint 不一致或未批准时不调用 RPC。`mock` 调用 `/jobs/start` 创建 synthetic `recipe-sweep`；`real` 还要求 real-run approval，并提交相同的 normalized Recipe、SweepPlan 和 expected fingerprints。

### RPC 请求与落盘

Generic SweepPlan 编译到现有 `/jobs/*` 主路径：

```json
{
  "mode": "plan",
  "job_type": "recipe-sweep",
  "recipe": {},
  "sweep_plan": {},
  "recipe_fingerprint": "sha256",
  "sweep_fingerprint": "sha256",
  "idempotency_key": "recipe-sweep:<recipe-fp>:<sweep-fp>:plan"
}
```

Mac MCP 不把自身编译结果当作 Windows 的盲目信任输入。Windows 使用同一纯 Python compiler：

1. 重新规范化 Recipe 和 SweepPlan。
2. 重新计算 Recipe、SweepPlan、task 和 script 指纹。
3. 对比请求中的 expected fingerprints。
4. 不一致时返回 `compile_fingerprint_mismatch`，不创建或启动任务。

job 目录至少增加：

```text
jobs/<job_id>/
├── inputs/
│   ├── recipe.json
│   └── sweep_plan.json
├── compiled/
│   ├── compile_report.json
│   └── scripts/<task_id>.lsf
└── tasks/<task_id>.json
```

每个 task 记录参数快照、script SHA-256、模型路径、metrics 路径和 synthetic/real 标记。

### 兼容层

现有 metasurface `SimulationPlan v0.1` 和 `fdtd_metasurface_sweep_*` 在首个交付版本保留。其内部适配为：

```text
metasurface SimulationPlan
→ metasurface DeviceRecipe
→ Generic SweepPlan
→ 通用 validate / compile / task expansion
```

兼容层必须保持已有 ratio、period、height、task count、fingerprint approval 和 RPC 请求语义。通用内核不得反向依赖 metasurface 专用 schema。

## MCP 工具面

交付版默认注册 69 个工具。工具按领域聚合；对象类型和属性通过参数表达，不为每种结构复制 CRUD 工具。

### Session and project

- `fdtd_health`
- `fdtd_session_start`
- `fdtd_session_pause`
- `fdtd_session_close`
- `fdtd_project_new`
- `fdtd_project_load`
- `fdtd_project_save`
- `fdtd_project_status`
- `fdtd_switch_to_layout`

### Generic objects

- `fdtd_object_create`
- `fdtd_object_list`
- `fdtd_object_get`
- `fdtd_object_update`
- `fdtd_object_copy`
- `fdtd_object_rename`
- `fdtd_object_delete`
- `fdtd_group_update`

### Materials

- `fdtd_material_create`
- `fdtd_material_list`
- `fdtd_material_get`
- `fdtd_material_update`
- `fdtd_material_assign`
- `fdtd_material_fit_diagnose`

### Solver and precision

- `fdtd_solver_get`
- `fdtd_solver_update`
- `fdtd_mesh_diagnose`
- `fdtd_resource_estimate`

### Sources

- `fdtd_source_create`
- `fdtd_source_get`
- `fdtd_source_update`

### Monitors

- `fdtd_monitor_create`
- `fdtd_monitor_get`
- `fdtd_monitor_update`

### Analysis groups

- `fdtd_analysis_group_create`
- `fdtd_analysis_group_get`
- `fdtd_analysis_group_update`

### Simulation, results, and export

- `fdtd_simulation_run`
- `fdtd_simulation_status`
- `fdtd_result_list`
- `fdtd_result_describe`
- `fdtd_result_read`
- `fdtd_results_download`
- `fdtd_export_gds`
- `fdtd_export_data`

### Raw capability

- `fdtd_eval`
- `fdtd_getv`
- `fdtd_setv`

Debug 工具默认开启。它们用于执行 typed tools 尚未覆盖的 Lumerical 脚本，属于高级能力：

- 不自动创建持久 job。
- 不承诺 resume、飞书通知、审批或质量报告。
- 不得把环境变量、飞书 Webhook 或其他进程秘密写入返回值。
- 长任务和可恢复工作流仍优先使用 Job/SimulationPlan 工具。

### DeviceRecipe

- `fdtd_device_recipe_validate`
- `fdtd_device_recipe_compile`
- `fdtd_device_recipe_build`

### Generic SweepPlan

- `fdtd_generic_sweep_validate`
- `fdtd_generic_sweep_plan`
- `fdtd_generic_sweep_start`

### SimulationPlan

- `fdtd_simulation_plan_validate`
- `fdtd_simulation_plan_approve`
- `fdtd_simulation_plan_start`
- `fdtd_simulation_plan_real_preflight`
- `fdtd_simulation_plan_production_preflight`

### Persistent Jobs

- `fdtd_job_plan`
- `fdtd_job_start`
- `fdtd_job_status`
- `fdtd_job_tasks`
- `fdtd_job_resume`
- `fdtd_metasurface_sweep_plan`
- `fdtd_metasurface_sweep_start`

### Knowledge

- `fdtd_device_template`
- `fdtd_list_devices`
- `fdtd_troubleshoot`
- `fdtd_best_practices`

### 不再注册的工具

以下现有低层、重复或 legacy 工具从交付版 MCP 注册表移除，由上述通用工具替代：

- `fdtd_save`
- `fdtd_load`
- `fdtd_add_fdtd_region`
- `fdtd_add_rect`
- `fdtd_add_circle`
- `fdtd_results_list`
- `fdtd_sweep_config_get`
- `fdtd_sweep_config_set`
- `fdtd_sweep_run`
- `fdtd_sweep_status`
- `fdtd_sweep_monitor`

对应 Python 兼容代码可以保留一轮版本，但不得出现在 `tools/list` 中，也不得出现在新人使用指南的推荐路径中。迁移映射：

- `fdtd_save/load` → `fdtd_project_save/load`
- `fdtd_add_*` → `fdtd_object_create`
- `fdtd_results_list` → `fdtd_result_list`
- `fdtd_sweep_*` → Generic SweepPlan 或 Persistent Jobs

## Mac 部署

### 安装入口

仓库提供：

```zsh
./scripts/macos/install_mcp.sh
```

安装脚本必须：

1. 要求 macOS 和 Python 3.10 或更高版本。
2. 在项目根创建或复用 `.venv`。
3. 从独立运行时依赖文件安装 MCP 所需依赖；测试依赖不属于默认安装。
4. 让用户选择 SSH 隧道或局域网直连。
5. 接受或交互获取最终 `FDTD_RPC_URL`。
6. 调用 `/health`；health 失败时允许生成配置，但必须清楚标记连接尚未验证并返回非零状态。
7. 根据当前项目绝对路径生成三种客户端配置。
8. 修改现有用户配置前创建带时间戳备份。
9. 只新增或替换名为 `fdtd` 的 MCP 条目，不覆盖其他 MCP、模型、权限或环境配置。
10. 可重复执行；重复执行不得产生重复 `fdtd` 条目。
11. 写入前先解析并验证三份目标配置；任一配置无法安全解析时，三份配置均不修改。
12. 三份配置作为一次事务写入；任一写入失败时，从本次备份恢复已经修改的文件。

### 客户端配置目标

#### Codex

修改：

```text
~/.codex/config.toml
```

生成等价配置：

```toml
[mcp_servers.fdtd]
command = "${PROJECT_ROOT}/.venv/bin/python"
args = ["-m", "src.server"]
cwd = "${PROJECT_ROOT}"

[mcp_servers.fdtd.env]
FDTD_RPC_URL = "${SELECTED_FDTD_RPC_URL}"
```

示例中的 `${PROJECT_ROOT}` 和 `${SELECTED_FDTD_RPC_URL}` 表示安装脚本写入的实际绝对值，不作为运行时 shell 展开变量保留。

#### Claude Code

修改项目根：

```text
.mcp.json
```

生成：

```json
{
  "mcpServers": {
    "fdtd": {
      "command": "${PROJECT_ROOT}/.venv/bin/python",
      "args": ["-m", "src.server"],
      "cwd": "${PROJECT_ROOT}",
      "env": {
        "FDTD_RPC_URL": "${SELECTED_FDTD_RPC_URL}"
      }
    }
  }
}
```

安装脚本写入时将 `${PROJECT_ROOT}` 和 `${SELECTED_FDTD_RPC_URL}` 替换为实际字符串。

#### Hermes

修改：

```text
~/.hermes/config.yaml
```

生成等价配置：

```yaml
mcp_servers:
  fdtd:
    command: "${PROJECT_ROOT}/.venv/bin/python"
    args:
      - "-m"
      - "src.server"
    cwd: "${PROJECT_ROOT}"
    env:
      FDTD_RPC_URL: "${SELECTED_FDTD_RPC_URL}"
```

安装脚本写入时将两个变量替换为实际字符串。Hermes 中 `fdtd` 同时作为可启用 toolset：

- 如果 `toolsets` 是显式列表且不含 `fdtd`，追加 `fdtd`。
- 如果 `toolsets` 不存在，保持不存在，让 Hermes 使用默认工具选择逻辑。
- 安装脚本不得删除、排序或重写现有其他 `toolsets`。

### 配置备份

修改前备份到：

```text
原文件名.backup-YYYYMMDD-HHMMSS
```

如果解析失败、目标格式非法或写入中断：

- 三份原文件均恢复为安装前内容。
- 临时文件删除。
- 输出失败文件、错误阶段和备份位置。

## Windows 部署

### 传输

用户通过 ToDesk 将项目目录复制到 Windows。ToDesk 只负责文件传输，不是运行时依赖。

### 首次配置入口

仓库提供：

```cmd
scripts\windows\setup_rpc.bat
```

该入口调用 PowerShell 配置逻辑，并完成：

1. 检查 Windows 版本和项目目录。
2. 检测或要求选择 Lumerical v242 Python：

   ```text
   F:\Program Files\Lumerical\v242\python\python.exe
   ```

3. 验证 `import lumapi`。
4. 安装或验证 Flask 等 Windows RPC 运行依赖。
5. 选择连接模式：`ssh` 或 `lan`。
6. 设置监听地址：
   - `ssh` → `127.0.0.1`
   - `lan` → `0.0.0.0`
7. 设置端口，默认 `5000`。
8. `lan` 模式下创建仅适用于 Windows“专用网络”的入站防火墙规则；`ssh` 模式不创建入站规则。
9. 启动 RPC 并调用 `/health`。
10. 输出配置路径、PID、日志路径和 health 结果。

### Windows 本机状态目录

不可被 ToDesk 覆盖更新的状态统一放在：

```text
%LOCALAPPDATA%\fdtd-mcp\
├── config\rpc.env
├── logs\rpc_server.out.log
├── logs\rpc_server.err.log
├── run\rpc_server.pid
└── jobs\
```

`rpc.env` 至少记录：

```text
FDTD_PYTHON=F:\Program Files\Lumerical\v242\python\python.exe
LUMAPI_PATH=F:\Program Files\Lumerical\v242\api\python
FDTD_RPC_HOST=127.0.0.1
FDTD_RPC_PORT=5000
FDTD_JOB_ROOT=C:\Users\USERNAME\AppData\Local\fdtd-mcp\jobs
```

示例使用 SSH 模式；LAN 模式只把 `FDTD_RPC_HOST` 改为 `0.0.0.0`。配置程序写入当前用户真实的 `%LOCALAPPDATA%` 路径。

Webhook 仍只从 Windows 用户环境变量 `FDTD_FEISHU_WEBHOOK` 读取，不写入 `rpc.env`。

### 日常双击入口

继续提供：

- `scripts\windows\start_rpc.bat`
- `scripts\windows\status_rpc.bat`
- `scripts\windows\stop_rpc.bat`
- `scripts\windows\restart_rpc.bat`

这些入口必须统一读取 `%LOCALAPPDATA%\fdtd-mcp\config\rpc.env`，并显示：

- 当前监听地址和端口。
- PID 是否存在、是否匹配本项目 RPC。
- health 是否可访问。
- stdout/stderr 日志路径。

关闭 `.bat` 窗口不得终止后台 RPC；后台继续使用 `pythonw.exe`。

## 参数集传递

用户已有的 2π 参数集只用于验证 MCP 是否能无损表达和传递参数。

验收参数文件由用户保存在本地，不要求提交 Git。安装后的验证命令接受：

```text
--parameter-file /absolute/path/to/parameters.json
```

验证只检查：

- JSON 可解析。
- 参数数组顺序、长度和数值在 Recipe/SweepPlan validate → normalize → compile 后保持一致。
- task count 与参数组合一致。
- 编译请求不擅自裁剪、扩展或替换用户参数。
- 不调用 `/jobs/start` real 模式。
- 不声明参数覆盖 2π，不生成物理结论。

仓库自动测试使用合成参数 fixture 验证同一数据契约，不复制用户的真实参数。

## 数据流

### 客户端启动

```text
Client
→ 启动项目目录/.venv/bin/python -m src.server
→ MCP initialize
→ tools/list
→ Windows 可以离线
```

### 普通工具调用

```text
tools/call
→ Mac MCP tool
→ RpcClient
→ FDTD_RPC_URL + API v1 route
→ Windows RPC
→ structured v1 envelope
→ MCP result
```

### 持久任务

```text
SimulationPlan / job request
→ plan/approval checks
→ /jobs/start
→ job_id
→ Agent 返回 job_id 后停止轮询
→ Windows 持久状态 + 飞书终态通知
→ 用户要求后读取 status/results
```

### 论文结构编译

```text
论文提取结果
→ DeviceRecipe
→ validate
→ compile
→ script + report + compile_fingerprint
→ 用户确认
→ build
→ Windows .fsp
```

### 通用扫参

```text
DeviceRecipe + SweepPlan
→ validate
→ deterministic Cartesian expansion
→ plan / mock / real
→ persistent tasks
```

## 错误处理

### Mac 安装

- Python 版本不满足：停止，不创建 `.venv` 或客户端配置。
- 依赖安装失败：保留 pip 输出，不写客户端配置。
- health 失败：显示 URL、错误类型、SSH/防火墙建议；不尝试真实任务。
- 客户端配置无法解析：停止并保持原文件，不进行猜测性重写。

### MCP 调用

- 连接失败：返回目标 URL、API 路径和 `connection_error`。
- 超时：返回 `remote_state=unknown`，不得解释为 FDTD 失败。
- 非 JSON 或 envelope 非法：返回 `invalid_response`。
- debug eval 失败：返回 RPC/Lumerical 错误摘要，不自动重试破坏性命令。
- Recipe 表达式或引用无效：本地拒绝，不生成部分 script。
- 关键论文参数缺失：返回缺失参数和 source locator 要求，不使用默认值。
- compile fingerprint 不匹配：拒绝 build，不连接 Windows。
- SweepPlan 超过预算：返回实际 task count 和 `max_tasks`，不截断。

### Windows 管理

- PID 文件陈旧：状态命令明确标记；启动前安全清理陈旧 PID。
- 端口被占用：显示占用端口和 PID，不启动第二个 RPC。
- Lumerical Python/lumapi 不可用：拒绝启动并显示配置文件路径。
- 防火墙配置失败：LAN setup 失败，不以“已可远程连接”状态结束。
- health 失败：显示日志尾部，不自动启动 FDTD real job。

## 交付验收

### 1. 静态验收

- 运行时依赖和测试依赖分离。
- Mac、Windows 安装/管理脚本都支持 `--help` 或等价帮助。
- 配置模板不包含开发机固定绝对路径。
- `tools/list` 精确返回本 spec 的 69 个工具。
- `tools/list` 不包含任何 `fdtd_sweep_*`。
- 20 步能力映射中的每一步都关联至少一个注册工具和至少一个契约测试。

### 2. Mac MCP 协议验收

通过真实子进程 stdio 完成：

1. `initialize`
2. `tools/list`
3. `tools/call(fdtd_health)`
4. `tools/call(fdtd_project_status)`
5. `tools/call(fdtd_object_create)`，`dry_run=true`
6. `tools/call(fdtd_source_create)`，`dry_run=true`
7. `tools/call(fdtd_monitor_create)`，`dry_run=true`
8. `tools/call(fdtd_device_recipe_validate)`
9. `tools/call(fdtd_device_recipe_compile)`
10. `tools/call(fdtd_generic_sweep_plan)`
11. `tools/call(fdtd_generic_sweep_start)`，请求为 mock

协议测试不得通过直接导入 Python 函数代替 stdio。

### 3. 三客户端验收

- Codex 能发现 `fdtd` MCP 和完整目标工具面。
- Claude Code 能发现同一工具面。
- Hermes 能加载 `mcp_servers.fdtd`，并把工具作为 `fdtd` toolset 提供。
- 三个客户端调用同一个 `fdtd_health` 时返回一致 API v1 语义。

### 4. 两种连接验收

- SSH 隧道模式可通过本地 URL 调用 `/health`。
- LAN 模式可从 Mac 通过 Windows 私网 IP 调用 `/health`。
- 切换模式通过修改配置并重启 MCP 完成，不要求代码修改。

### 5. 非物理工作流验收

- 用户参数文件完成 validate/normalize/compile 无损检查。
- 合成论文 Recipe 完成 validate/compile，并生成稳定对象清单和 fingerprint。
- Recipe build 未经 exact fingerprint 确认时被拒绝。
- Generic SweepPlan 的显式列表和线性区间生成稳定笛卡尔积。
- `plan` 或 `mock` job 返回稳定 `job_id`。
- job 的 manifest、status、summary 和 task 文件落盘到 `%LOCALAPPDATA%\fdtd-mcp\jobs`。
- mock 终态可发送飞书通知。
- Recipe/SweepPlan 全流程不启动真实 FDTD 求解，不产生物理结论。

### 6. 通用闭环契约验收

使用注入式 fake lumapi 覆盖完整 20 步：

- 新建工程、创建几何、材料分配。
- solver 范围、时间、背景、boundary、PML、mesh、shutoff。
- source 的方向、角度、偏振和频谱。
- monitor 的物理量、采样和频率点。
- analysis group 及脚本。
- 材料拟合诊断和内存预估。
- SweepPlan task 展开。
- simulation run/status。
- result list/describe/read/download/export。

测试必须验证工具 → RpcClient → API v1 route → adapter → fake lumapi 的真实调用链，不能只断言独立 helper。

### 7. Windows 最小 solver smoke

允许并要求一次固定的低成本技术 smoke，用于证明“运行仿真”和“拉取结果”不是仅存在于 fake backend：

1. 创建新工程。
2. 创建一个固定简单结构及材料。
3. 创建小型 FDTD region，使用固定低成本网格和短仿真时间。
4. 设置背景、边界和 auto shutoff。
5. 添加一个固定 source。
6. 添加一个固定 monitor。
7. 添加一个最小 analysis group。
8. 保存 `.fsp`。
9. 执行单次 `fdtd_simulation_run`。
10. 使用 `fdtd_result_list/describe/read` 读取一个结果。
11. 下载结构化结果文件。
12. 关闭 session。

边界：

- 只有 1 个模型、1 次求解、无参数扫描、无优化。
- 参数固定在仓库 smoke fixture 中。
- 结果只检查字段存在、数组非空和 API 数据流，不设物理性能阈值。
- 报告必须标记 `technical_smoke=true`、`physical_conclusion=false`。

### 8. 可迁移验收

将同一项目目录通过 ToDesk 复制到第二台 Windows 后：

1. 运行 `setup_rpc.bat`。
2. 选择该机器的 Lumerical v242 Python。
3. 完成 health。
4. 在 Mac 修改 `FDTD_RPC_URL` 并重启 MCP。
5. 无代码修改即可使用相同工具面。

## 文档交付

实现完成后，当前入口文档必须面向 MCP 交付重写：

- `README.md`：五分钟安装、两种连接方式、三客户端入口、快速验收。
- `docs/MCP_USER_GUIDE.md`：完整工具目录、20 步通用流程、debug 工具边界、DeviceRecipe、Generic SweepPlan、参数文件验证和客户端配置。
- `docs/FDTD_OPERATIONS_V1.md`：project、object、material、solver、source、monitor、analysis、run 和 result 的 typed schema、属性映射和示例。
- `docs/DEVICE_RECIPE_V1.md`：Recipe schema、原语、来源追踪、表达式、raw hooks 和完整示例。
- `docs/GENERIC_SWEEP_PLAN_V1.md`：SweepPlan schema、采样、任务顺序、预算、审批和完整示例。
- `docs/WINDOWS_RUNBOOK.md`：首次配置、双击管理、状态目录、防火墙和迁移。
- `docs/RPC_API_V1.md`：MCP 实际依赖的 API v1 路由。
- `REQUIREMENTS.md`：把“可交付个人 MCP”设为当前验收目标；物理实验保留为使用场景，不作为开发完成标准。

## 版本与发布边界

- 首个可交付版本标记为 `0.1.0`。
- 版本号必须能通过 Python 包元数据或 `src` 内单一版本常量读取，不能在多个文档中手工维护。
- 发布产物是 Git/ToDesk 可复制的仓库目录，不发布 PyPI。
- `0.1.0` 的完成定义是本 spec 的全部验收项通过，不包含真实 sweep。

## 实现原则

- 复用现有 FastMCP、RpcClient、JobStore 和 Windows 管理脚本。
- 不重写已验证的 API v1 和持久 job 状态机。
- 不引入数据库、队列、容器或额外守护进程。
- 配置生成使用结构化 TOML/JSON/YAML 读写，不用字符串替换破坏用户配置。
- 所有配置写入采用临时文件加原子替换。
- Recipe 和 SweepPlan 编译器是无网络、无 RPC、无文件副作用的纯逻辑；文件材料只做路径与指纹读取。
- DeviceRecipe 与通用 SweepPlan 的 schema 不包含自然语言解析逻辑。
- raw hook 只在固定生命周期位置执行，且必须参与指纹。
- 测试不得访问真实飞书、启动 FDTD 或依赖用户真实参数文件。
