# Windows Template Contract 与 SimulationPlan Real 验证设计

## 决策

下一阶段分为两个安全阶段：

1. 在 Windows 上用 Lumerical v242 Python 只读检查 `base_model.fsp`，生成可审计、可验证、绑定模板与检查 profile 的 template contract。
2. contract 通过用户审核后，再对固定的 2×2 CPU `SimulationPlan` 生成独立真实运行审批，并执行一次真实端到端验证。

Template contract 采用 fail-closed 策略：任何关键对象、属性或指纹无法可靠验证，都生成 `status="unverified"`，并阻止真实运行。检查器可以短暂启动 FDTD 和占用许可证，但不得运行求解、修改或保存模板。

真正启动 2×2 real 前必须再次向用户展示完整审批摘要并取得针对该次运行的明确批准。

## 背景

项目当前已经完成：

- Windows RPC API v1 与默认端口 `5000`。
- 持久 `/jobs/*` 状态机、幂等、审批和 resume。
- 原生 `metasurface-sweep` Phase 1-4。
- 真实 2×2 CPU sweep，4/4 task 成功，quality `pass`。
- quality report、evidence index、CSV 和 SVG。
- MCP jobs 工具。
- `SimulationPlan v0.1` 的严格输入校验、默认值披露、任务预算、稳定 SHA-256、Plan 审批和 mock 端到端流程。
- real 的双层审批接口与 template contract 参数。
- real metasurface resume 的模板 SHA-256 保护。

当前 contract 只是一个接口约定，尚无可信生成流程。现有模板安装脚本只复制 `.fsp` 并打印文件 SHA-256、大小和路径，无法证明模板中的材料、光源、监视器、边界、网格、资源设置和分析组满足 Plan 要求。

因此，直接将手工 JSON 作为 contract 传入 real 审批不够安全。需要建立：

```text
模板文件
  -> Windows 只读检查
  -> contract
  -> 用户审核
  -> real approval
  -> Windows 运行时二次校验
  -> 持久 real job
```

## 目标

1. 建立独立 Windows 只读模板检查器。
2. 先生成 inventory，发现真实对象路径和可读属性。
3. 用 Git 管理的 inspection profile 固化期望对象、属性和结果接口。
4. 生成版本化、带检查证据的 template contract。
5. 让 contract 绑定：
   - 模板 SHA-256
   - inspection profile SHA-256
   - contract fingerprint
   - 代码 commit
   - Lumerical 版本和检查环境
6. 让 Windows `/jobs/start` 在真实 job 创建前重新读取本地 contract、profile 和模板，完成 fail-closed 二次校验。
7. 让 real job manifest 记录 Plan、contract、profile 和模板四类指纹。
8. 通过单独审批执行固定的真实 2×2 `SimulationPlan`。

## 非目标

- 不修改 `.fsp` 模板。
- 不在检查器中运行 `run()`、`runjobs()`、`runanalysis()` 或任何求解。
- 不调用 `save()`、`set()`、`setnamed()` 或其他写操作。
- 不自动修复模板。
- 不猜测无法读取的物理属性。
- 不支持 GPU。
- 不扩大首次真实扫描范围。
- 不新增第二种器件 recipe。
- 不把 inventory 当作 verified contract。
- 不允许 Mac 传入任意 contract 路径让 Windows 信任。
- 不删除或覆盖历史 job。

## 总体架构

```text
templates/metasurface/base_model.fsp
             |
             v
Windows Lumerical Python
scripts/inspect_metasurface_template.py
             |
       +-----+------+
       |            |
   --inventory   --contract
       |            |
       v            v
inventory JSON   profile-driven checks
                    |
                    v
templates/metasurface/base_model.contract.json
                    |
                    v
用户审核 contract 摘要
                    |
                    v
Plan approval + real_run approval
                    |
                    v
Windows /jobs/start 二次校验
 contract/profile/template/Plan fingerprints
                    |
                    v
异步 real 2×2 job
```

## 组件

### `src/template_contract.py`

纯 Python、跨平台的 contract 公共模块，负责：

- profile schema 校验。
- contract schema 校验。
- stable JSON。
- 文件 SHA-256。
- profile SHA-256。
- contract fingerprint 的生成与复算。
- `verified` 状态与 critical check 一致性校验。
- contract 与 Plan requirements 的字段匹配。

Windows 检查器、Mac MCP 审批校验和 Windows RPC preflight 必须复用这一模块，不能各自实现一套指纹或 schema 逻辑。

### `scripts/inspect_metasurface_template.py`

职责：

- 只在 Windows Lumerical v242 Python 中运行。
- 延迟导入 raw `lumapi`。
- 以 `hide=True` 启动 FDTD。
- 加载指定模板。
- 执行 inventory 或严格 contract 检查。
- 写入 JSON。
- 输出短摘要。
- 关闭 FDTD；关闭异常不得把已完成检查误判为失败，但必须记录 cleanup 状态。

禁止调用：

- `run`
- `runjobs`
- `runanalysis`
- `save`
- `set`
- `setnamed`
- `add*`
- `delete`

检查器内部应把所有 Lumerical 调用集中在一个只读 adapter 中，使 fake-lumapi 测试可以记录并断言调用白名单。

### `scripts/windows/inspect_metasurface_template.bat`

职责：

- 切换到项目根目录。
- 使用固定路径：
  `F:\Program Files\Lumerical\v242\python\python.exe`
- 默认检查：
  `templates\metasurface\base_model.fsp`
- 透传 `--inventory` 或 `--contract`。
- 保留错误码。
- 失败时暂停窗口，成功时正常返回。

### Inspection profile

Profile 分为两个明确阶段，避免提交猜测路径。

#### Inventory profile

实现 inventory 能力时创建并提交：

`templates/metasurface/template-inventory-profile.json`

它只包含当前已经由 runner 和模板文档确认的对象：

```json
{
  "profile_version": "0.1",
  "mode": "inventory",
  "template_logical_path": "templates/metasurface/base_model.fsp",
  "known_objects": {
    "fdtd": "FDTD",
    "model": "::model",
    "analysis_group": "::model::s_params"
  },
  "roles_to_discover": ["pillar", "substrate", "source", "monitors"]
}
```

#### Strict contract profile

Windows inventory 完成后，人工根据 inventory JSON 填写并提交：

`templates/metasurface/template-inspection-profile.json`

该文件必须包含 inventory 中真实存在的完整对象路径。提交前不得存在空字符串、占位标记或未绑定 role。

严格 profile 的公共部分至少包含：

```json
{
  "profile_version": "0.1",
  "mode": "contract",
  "template_logical_path": "templates/metasurface/base_model.fsp",
  "objects": {
    "fdtd": "FDTD",
    "model": "::model",
    "analysis_group": "::model::s_params"
  },
  "model_parameters": ["ratio", "height", "period"],
  "results": {
    "transmission": "T",
    "s_parameter": "S21_Gn"
  },
  "expected": {
    "resource": "CPU",
    "express_mode": 0,
    "dimension": "3D"
  },
  "properties": {
    "fdtd": [
      "dimension",
      "express mode",
      "mesh accuracy",
      "x min bc",
      "x max bc",
      "y min bc",
      "y max bc",
      "z min bc",
      "z max bc"
    ],
    "source": [
      "type",
      "wavelength start",
      "wavelength stop",
      "injection axis",
      "direction"
    ],
    "pillar": ["material"],
    "substrate": ["material"]
  }
}
```

Windows inventory 后，`objects` 还必须增加 `pillar`、`substrate`、`source` 和 `monitors`。前三项是 inventory JSON 中复制出的单一完整路径；`monitors` 是一个或多个完整路径组成的非空列表。Profile 校验器必须拒绝空字符串、尖括号、缺失 role、非完整路径或 inventory 中不存在的路径。

如果 v242 对某个属性使用不同名称，应根据 inventory 和真实只读探针修改 profile，并提交该事实；不能在检查器里静默尝试大量别名后选择一个“看起来合理”的值。

### Runtime artifacts

以下文件位于 `templates/metasurface/`，由 Windows 生成，不提交 Git：

- `base_model.inventory.json`
- `base_model.contract.json`

`.gitignore` 必须明确忽略这些运行时产物，同时保留两个 profile JSON 可提交。

### Windows RPC real guard

真实 `metasurface-sweep` 的 `/jobs/start` 在 enqueue 前：

1. 只接受仓库内固定模板逻辑路径。
2. 只读取模板旁固定 contract：
   `templates/metasurface/base_model.contract.json`
3. 只读取仓库内固定 profile：
   `templates/metasurface/template-inspection-profile.json`
4. 验证 contract schema、状态和指纹。
5. 重新计算 profile SHA-256。
6. 重新计算模板 SHA-256。
7. 校验请求中的：
   - `plan_fingerprint`
   - `expected_contract_fingerprint`
   - `expected_profile_sha256`
   - `expected_template_sha256`
8. 全部一致才允许 `JobStore.enqueue()`。

Windows 服务不信任 Mac 传入的 `declared_physics`。物理声明必须来自本地固定 contract。

## Inventory 阶段

### 目的

仓库当前只知道：

- `FDTD`
- `::model`
- `::model::s_params`
- model 参数 `ratio`、`height`、`period`

尚不知道 pillar、substrate、source 和 monitor 的稳定完整路径，也没有在 v242 上验证所有属性名。因此必须先 inventory。

### Inventory 内容

Inventory 输出至少包含：

- 模板路径、SHA-256、大小、mtime。
- 检查时间、主机名、Python executable、Lumerical 版本。
- 对象树：
  - 完整路径
  - 对象类型
  - 重名计数
- 每个候选对象可读取的属性名。
- `::model` 可读取的用户属性名和值。
- 分析组存在性和可读取属性。
- cleanup 状态。
- `inventory_only=true`。

Inventory 不包含 `status=verified`，不能用于审批。

### Inventory 安全规则

- 只读打开模板。
- 不运行 analysis。
- 不读取依赖求解结果的数据。
- 不写回 `.fsp`。
- JSON 写入临时文件后原子替换。
- 打开失败仍输出失败诊断文件。

## Contract 阶段

### Contract schema

```json
{
  "contract_version": "0.1",
  "status": "verified",
  "contract_fingerprint": "<sha256>",
  "template": {
    "logical_path": "templates/metasurface/base_model.fsp",
    "absolute_path": "F:\\...\\base_model.fsp",
    "sha256": "<sha256>",
    "size_bytes": 123,
    "modified_at": "2026-06-19T..."
  },
  "profile": {
    "path": "templates/metasurface/template-inspection-profile.json",
    "sha256": "<sha256>",
    "version": "0.1"
  },
  "inspector": {
    "checked_at": "2026-06-19T...",
    "hostname": "...",
    "python_executable": "F:\\Program Files\\Lumerical\\v242\\python\\python.exe",
    "lumerical_version": "v242",
    "code_commit": "<git-sha>",
    "hide": true,
    "cleanup_state": "closed"
  },
  "resource": "CPU",
  "express_mode": 0,
  "physics_strategy": "template_inherited",
  "declared_physics": {
    "dimension": "3D",
    "wavelength_start_m": 8e-7,
    "wavelength_stop_m": 8.2e-7,
    "pillar_material": "...",
    "substrate_material": "...",
    "mesh_accuracy": 6,
    "x_min_bc": "Periodic",
    "x_max_bc": "Periodic",
    "y_min_bc": "Periodic",
    "y_max_bc": "Periodic",
    "z_min_bc": "PML",
    "z_max_bc": "PML",
    "source_type": "...",
    "source_injection_axis": "z",
    "source_direction": "backward"
  },
  "objects": {},
  "results": {
    "transmission": "T",
    "s_parameter": "S21_Gn"
  },
  "checks": [],
  "warnings": [],
  "errors": []
}
```

`resource="CPU"` 不是从不存在的通用“resource type”模板属性中猜测。检查器先读取并验证 `FDTD.express mode=0`，再依据本项目已确认规则“CPU 对应 0、GPU 对应 1”生成 resource classification，并在 checks 中记录推导依据。无法读取 Express Mode 时，resource 也必须为 unverified。

### Contract fingerprint

Contract fingerprint 使用稳定 JSON 的 SHA-256。计算时排除：

- `contract_fingerprint` 自身。
- 纯显示性的绝对路径。

检查时间、主机、Lumerical 版本、代码 commit、模板 SHA、profile SHA、检查结果和 declared physics 都进入指纹。

任何检查证据或环境变化都会生成新 contract fingerprint，并要求重新审批。

### Check records

每个检查项至少包含：

```json
{
  "name": "fdtd.express_mode",
  "critical": true,
  "status": "pass",
  "expected": 0,
  "actual": 0,
  "object_path": "FDTD",
  "property": "express mode",
  "message": "CPU template uses EXPRESS_MODE=0."
}
```

状态只接受：

- `pass`
- `warning`
- `fail`
- `unverified`

首版所有 profile 中声明的检查均为 critical。任何 critical 项不是 `pass`，contract 总状态必须为 `unverified`。

### Fail-closed

以下情况必须 `status="unverified"`：

- 模板不存在或打不开。
- Lumerical 版本无法读取。
- profile 不合法。
- profile 中对象不存在或重名。
- model 参数不存在或不可读。
- 任一关键属性不可读。
- FDTD 不是 3D。
- resource 不是 CPU。
- `express mode != 0`。
- 必要 source、monitor 或 analysis group 不存在。
- 材料名不可读。
- wavelength 不可读。
- 边界或 mesh accuracy 不可读。
- 结果接口声明缺失。
- contract 写入前内部异常。

检查器不得用人工默认值替代 `actual`。

即使失败，也尽量输出 `unverified` contract 和错误列表，以便诊断。

## Read-only API adapter

检查器对 lumapi 的使用必须经过只读 adapter。允许方法集合由实现测试锁定，至少包括：

- 构造 `FDTD(hide=True)`
- `load`
- `getversion` 或等价只读版本读取
- `getnamed`
- `getnamednumber`
- 必要的只读 `eval/getv`，仅用于枚举对象或用户属性
- `close`

禁止集合至少包括：

- `run`
- `runjobs`
- `runanalysis`
- `save`
- `set`
- `setnamed`
- `add*`
- `delete`

如果 inventory 所需对象树枚举只能通过 Lumerical script 完成，脚本文本必须是固定只读脚本，不接受用户自由输入，并在测试中扫描禁止命令。

## Profile 固化流程

1. 实现检查器和 fake-lumapi 测试。
2. 提交只含已知路径和待发现 role 的 inventory profile。
3. Windows `git pull --ff-only`。
4. 使用 `.bat --inventory` 只读打开模板。
5. 读取 `base_model.inventory.json`。
6. 根据真实对象路径和属性名填写 strict contract profile；删除所有示例命名。
7. 提交 profile 与相关契约测试。
8. Windows 再次同步。
9. 使用 `.bat --contract`。
10. contract 只有 `verified` 才进入真实审批。

如果 inventory 显示模板结构与现有 runner 假设不一致，停止并修订设计或模板；不能在检查器中绕过。

## SimulationPlan real 信任链

### Plan

首次真实 Plan 固定为：

```json
{
  "schema_version": "0.1",
  "device": {"type": "metasurface_unit_cell"},
  "physics": {
    "materials": {"strategy": "template_inherited"},
    "source": {"strategy": "template_inherited"},
    "monitors": {"strategy": "template_inherited"},
    "boundaries": {"strategy": "template_inherited"},
    "mesh": {"strategy": "template_inherited"},
    "requirements": {}
  },
  "sweep": {
    "axis": "period",
    "ratio_values": [0.2, 0.8],
    "period_values_m": [3.9e-7, 5.4e-7],
    "fixed_height_m": 7e-7
  },
  "execution": {
    "resource": "CPU",
    "express_mode": 0,
    "processes": 1,
    "capacity": 1,
    "hide": true,
    "template": "templates/metasurface/base_model.fsp"
  },
  "outputs": {"include_models": false},
  "acceptance": {
    "required_quality": "pass",
    "required_task_success_rate": 1.0
  }
}
```

Plan 仍通过 `fdtd_simulation_plan_validate` 和 `fdtd_simulation_plan_approve`。

### Real approval

真实运行审批对象至少包含：

```json
{
  "approved": true,
  "approved_for": "real_run",
  "plan_fingerprint": "<plan-sha>",
  "template_sha256": "<template-sha>",
  "contract_fingerprint": "<contract-sha>",
  "profile_sha256": "<profile-sha>"
}
```

MCP 本地校验必须确认：

- Plan approval 匹配 Plan。
- real approval 匹配 Plan。
- contract `status=verified`。
- contract/template/profile 指纹匹配 real approval。
- contract logical path 匹配 Plan template。
- contract CPU/Express Mode 匹配 Plan。
- contract `declared_physics` 满足 `physics.requirements`。

### Compiled real request

编译后的 `/jobs/start` 请求在现有字段之外增加：

```json
{
  "plan_fingerprint": "<plan-sha>",
  "template_contract": {
    "expected_contract_fingerprint": "<contract-sha>",
    "expected_profile_sha256": "<profile-sha>",
    "expected_template_sha256": "<template-sha>"
  }
}
```

请求不携带可被服务端信任的 `declared_physics`。

### Windows preflight

`/jobs/start` 对 real metasurface request 执行：

1. 现有 real approval 校验。
2. 现有模板存在性校验。
3. `plan_fingerprint` 必须为 64 位十六进制 SHA-256。
4. 请求必须包含三个 expected fingerprint。
5. 读取固定本地 contract 和 profile。
6. 重新计算 contract fingerprint。
7. 重新计算 profile SHA。
8. 重新计算模板 SHA。
9. 验证 contract `status=verified`。
10. 验证 contract 内 template/profile SHA 与重新计算值一致。
11. 验证 expected fingerprint 与实际值一致。
12. 验证 contract logical path 与受控模板路径一致。
13. 全部通过后才 enqueue。

错误时不创建 job 目录。

## Job manifest 审计

真实 job manifest 增加：

```json
{
  "plan_fingerprint": "<plan-sha>",
  "template_contract": {
    "contract_fingerprint": "<contract-sha>",
    "profile_sha256": "<profile-sha>",
    "template_sha256": "<template-sha>",
    "contract_path": "templates/metasurface/base_model.contract.json",
    "profile_path": "templates/metasurface/template-inspection-profile.json"
  }
}
```

Runner 开始时已有模板 SHA 记录。若 runner 实际 SHA 与 preflight 记录不一致，job 必须在求解前失败，不得继续。

## 首次真实 2×2 验证

### 固定配置

- ratio：`[0.2, 0.8]`
- period：`[390e-9, 540e-9]`
- fixed height：`700e-9`
- task：4
- resource：CPU
- `EXPRESS_MODE=0`
- processes：1
- capacity：1
- `hide=True`
- phases：1、2、3、4
- include models：false
- 新建 job，不覆盖历史目录
- evidence-first

### 真实运行审批摘要

启动前必须展示：

- Plan 指纹。
- contract 指纹。
- profile SHA-256。
- template SHA-256。
- 模板和 contract 逻辑路径。
- 4 个 task 及参数矩阵。
- CPU、`EXPRESS_MODE=0`、processes=1、capacity=1。
- `hide=True`。
- 模板继承的材料、source、monitor、boundary、mesh 摘要。
- 输出目录策略。
- 不覆盖历史结果。
- 许可证占用和预计运行性质。

用户必须针对这份摘要明确批准。此前对只读检查器的批准不能复用为 real 运行批准。

### 完成验收

必须检查：

- HTTP start 返回 `202 + job_id`。
- 4 个 task 最终全部 `succeeded`。
- job 状态 `succeeded`。
- `quality_report.json` conclusion 为 `pass`。
- `results/sweep_results.csv` 存在。
- `results/sweep_summary.json` 存在。
- `evidence/index.json` 存在。
- transmission 与 phase SVG 存在。
- summary 标记真实数据，不是 synthetic。
- manifest 中四类指纹与审批摘要一致。
- 默认回传不包含逐点 `.fsp`。
- 人工审核关键物理结果。

只有人工完成物理合理性审核后，才能记录“SimulationPlan real 验证完成”。

## 错误语义

| 错误类型 | 含义 |
| --- | --- |
| `template_not_found` | 模板文件不存在 |
| `template_open_failed` | Lumerical 无法只读加载模板 |
| `object_missing` | profile 声明对象不存在 |
| `object_not_unique` | 对象路径匹配多个对象 |
| `property_unreadable` | 关键属性无法读取 |
| `property_mismatch` | actual 与 profile expected 不符 |
| `profile_validation_error` | profile schema 或路径非法 |
| `profile_fingerprint_mismatch` | profile 当前 SHA 与 contract/request 不一致 |
| `contract_unverified` | contract 状态不是 verified |
| `contract_fingerprint_mismatch` | contract 内容与其指纹或 request 不一致 |
| `template_fingerprint_mismatch` | 当前模板 SHA 与 contract/request 不一致 |
| `plan_fingerprint_mismatch` | real request 与审批 Plan 不一致 |

所有 Windows preflight 错误返回 HTTP 409 或 400 的结构化 v1 error；不得创建 job。

## 测试策略

### Offline

- fake lumapi verified 模板生成 verified contract。
- fake lumapi 缺对象、重名、属性读取失败生成 unverified。
- 检查器调用记录不包含禁止方法。
- 固定 inventory script 不包含写入或求解命令。
- profile schema 和路径校验。
- stable JSON 与 contract fingerprint。
- 修改 contract 任一检查证据会改变 fingerprint。
- 修改 profile 字节会改变 profile SHA。
- 修改 template 字节会改变 template SHA。
- MCP real approval 校验四类指纹。
- 编译请求只携带 expected fingerprints，不携带 declared physics。
- RPC preflight 对缺失、unverified、篡改和 TOCTOU 全部拒绝。
- 拒绝时 jobs 目录不新增。
- mock 不受 contract guard 影响。
- manifest 记录四类指纹。

### Windows inventory

- 使用 Lumerical v242 Python。
- `hide=True`。
- 只读加载模板。
- 生成 inventory JSON。
- 人工确认没有求解、修改或保存。
- 根据 inventory 固化 profile。

### Windows contract

- 严格 profile 检查。
- contract `status=verified`。
- errors 为空。
- 所有 critical checks 为 pass。
- template/profile/contract 指纹可重复计算。

### Real

- 在用户单独批准后启动。
- 轮询状态，不用长 HTTP 请求等待。
- 完成后核验 quality/evidence/manifest。

## 文档与 SOP

需要更新：

- `README.md`
- `TECH_STACK.md`
- `DEV_LOG.md`
- `PITFALLS.md`
- `SOP.md`
- `docs/RPC_API_V1.md`
- `docs/WINDOWS_RUNBOOK.md`
- `templates/metasurface/README.md`

SOP 必须明确：

```text
install
-> inventory
-> commit profile
-> contract
-> user reviews contract
-> validate/approve Plan
-> present real summary
-> explicit real approval
-> start/poll/collect
-> human physics review
```

## 阶段门

### Gate 1：实现完成

- 离线测试通过。
- 不启动 FDTD。

### Gate 2：Inventory 批准

- 用户已批准只读打开模板。
- Windows inventory 成功。
- profile 根据真实输出提交。

### Gate 3：Contract verified

- Windows contract `verified`。
- 用户审核 contract 摘要。

### Gate 4：Real approval

- 展示固定 2×2 完整审批摘要。
- 用户明确批准该次真实运行。

### Gate 5：Physics review

- 自动质量报告通过。
- 用户审核关键物理结果。
- 才能宣布真实端到端验证完成。
