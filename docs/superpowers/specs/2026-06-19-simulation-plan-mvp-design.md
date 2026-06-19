# SimulationPlan MVP 设计

## 决策

Phase 5 新增一个位于自然语言 Agent 与现有 `/jobs/*` 执行系统之间的独立薄编译层：

```text
用户自然语言
  -> Claude Code / Codex 生成 SimulationPlan 草案
  -> 默认值填充、规范化和严格校验
  -> 生成规范化 SimulationPlan 与 SHA-256 指纹
  -> 用户审批默认值和假设
  -> 编译为现有 metasurface-sweep 请求
  -> plan / mock / real 持久 job
```

Python 不负责自然语言解析。首版只支持 metasurface unit-cell sweep，不修改已经通过真实 2×2 验证的 `JobStore`、`NativeSweepRunner` 和 `/jobs/*` 核心行为。

Phase 5 不启动真实 FDTD。实现完成后只做离线测试和端到端 mock 验证。

## 背景

项目当前已经具备：

- Windows RPC API v1，默认端口 `5000`。
- 持久 `/jobs/plan`、`/jobs/start`、`/jobs/<job_id>`、`/jobs/<job_id>/tasks` 和 `/jobs/<job_id>/resume`。
- 原生 `metasurface-sweep` Phase 1-4。
- 真实 2×2 CPU sweep 验证，4/4 task 成功，quality `pass`。
- quality report、evidence index 和逐 task 结果。
- Mac MCP `/jobs/*` 工具和 metasurface 便捷工具。

当前主要缺口不是执行能力，而是自然语言需求与已验证执行契约之间没有可检查的结构化计划层。Agent 可以直接拼装 `/jobs/*` 请求，但无法统一披露默认值、记录假设、绑定审批对象或阻止审批后参数被替换。

另一个已知安全缺口是：real sweep 会在 manifest 中记录模板 SHA-256，但当前 `resume` 尚未在恢复前重新计算模板指纹并拒绝变化后的模板。

## 目标

1. 定义最小、确定性的 `SimulationPlan v0.1`。
2. 让 Agent 把自然语言转成 Plan JSON，由代码负责默认值、规范化、校验和编译。
3. 所有自动填入的默认值和假设都必须向用户披露。
4. mock 前要求用户批准规范化 Plan。
5. real 前额外要求独立的真实运行审批。
6. 两层审批都绑定规范化 Plan 的 SHA-256 指纹。
7. 将已批准 Plan 编译为当前已验证的 `metasurface-sweep` `/jobs/*` 请求。
8. 模板 SHA-256 变化时拒绝 resume。

## 非目标

- 不在 Python 中开发关键词、正则或其他自然语言解析器。
- 不支持 waveguide、MMI、ring、grating coupler 或其他器件 recipe。
- 不建立通用 recipe registry 或插件框架。
- 不开放 GPU；首版固定 CPU 与 `EXPRESS_MODE=0`。
- 不实现优化算法、自动扩大扫描或自动重规划。
- 不修改模板内材料、光源、监视器、边界或网格。
- 不启动真实 FDTD，也不重启 Windows 服务。
- 不新增数据库、审批服务或用户账户系统。

## 架构

### 组件

#### `src/simulation_plan.py`

负责：

- 接收 Agent 生成的 Plan 草案。
- 填充首版安全默认值。
- 统一单位和数据形态。
- 校验器件类型、扫描参数、资源和预算。
- 生成默认值、假设、警告和错误。
- 生成规范化 Plan 的稳定 SHA-256 指纹。
- 生成面向用户的审批摘要。
- 校验审批对象与当前计划指纹一致。

该模块必须是纯 Python，不依赖 MCP、Flask、Windows 或 `lumapi`。

#### `src/plan_compilers/metasurface.py`

负责：

- 接收已经规范化且审批通过的 Plan。
- 编译为现有 `metasurface-sweep` `/jobs/*` 请求。
- 保持 Plan 字段与现有 `sweep.config` 字段的单一、显式映射。

该模块不得调用 RPC，也不得执行 FDTD。

#### `src/tools/plans.py`

负责注册 MCP 工具：

- `fdtd_simulation_plan_validate`
- `fdtd_simulation_plan_approve`
- `fdtd_simulation_plan_start`

工具使用现有 `RpcClient.jobs_plan()` 或 `RpcClient.jobs_start()`，不新增 HTTP 路由。

#### 现有执行层

以下组件保持既有职责：

- `src/job_store.py`
- `src/native_sweep.py`
- `rpc_server.py`
- `/jobs/*`

Phase 5 仅对 `resume` 增加模板指纹冲突保护，不重构 job 状态机。

## SimulationPlan v0.1

### 规范化结构

```json
{
  "schema_version": "0.1",
  "intent": {
    "summary": "Sweep metasurface unit-cell ratio and period on CPU."
  },
  "device": {
    "type": "metasurface_unit_cell"
  },
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
  "outputs": {
    "include_models": false
  },
  "acceptance": {
    "required_quality": "pass",
    "required_task_success_rate": 1.0
  }
}
```

### 首版字段语义

- `schema_version`：固定为 `"0.1"`。
- `intent.summary`：保留用户意图摘要，仅用于审计，不参与执行参数映射。
- `device.type`：首版只接受 `metasurface_unit_cell`。
- `physics.*.strategy`：首版固定为 `template_inherited`。
- `physics.requirements`：可选的用户物理要求，仅用于模板契约核验，不直接修改 `.fsp`。
- `sweep.axis`：接受 `period` 或 `height`。
- `sweep.ratio_values`：无量纲直径/周期比例列表。
- `sweep.period_values_m`：`axis=period` 时必需或由默认值填充。
- `sweep.height_values_m`：`axis=height` 时必需或由默认值填充。
- `sweep.fixed_height_m`：`axis=period` 时使用。
- `sweep.fixed_period_m`：`axis=height` 时使用。
- `execution.resource`：首版固定为 `CPU`。
- `execution.express_mode`：首版固定为 `0`。
- `execution.processes`、`capacity`：正整数，首版默认均为 `1`。
- `execution.hide`：默认 `true`。
- `execution.template`：默认受控 metasurface 模板路径。
- `outputs.include_models`：默认 `false`，保持 evidence-first 回传。
- `acceptance.required_quality`：首版默认 `pass`。
- `acceptance.required_task_success_rate`：首版默认 `1.0`。

### 默认值

首版默认值与当前已验证 2×2 CPU sweep 保持一致：

| 字段 | 默认值 |
| --- | --- |
| `schema_version` | `"0.1"` |
| `device.type` | `metasurface_unit_cell` |
| `physics.*.strategy` | `template_inherited` |
| `sweep.axis` | `period` |
| `sweep.ratio_values` | `[0.2, 0.8]` |
| `sweep.period_values_m` | `[390e-9, 540e-9]` |
| `sweep.fixed_height_m` | `700e-9` |
| `execution.resource` | `CPU` |
| `execution.express_mode` | `0` |
| `execution.processes` | `1` |
| `execution.capacity` | `1` |
| `execution.hide` | `true` |
| `execution.template` | `templates/metasurface/base_model.fsp` |
| `outputs.include_models` | `false` |
| `acceptance.required_quality` | `pass` |
| `acceptance.required_task_success_rate` | `1.0` |

每个自动填入字段都必须出现在 `defaults_applied` 中，至少包含字段路径、填充值和原因。不得静默填充后直接执行。

### 模板继承边界

当前原生 sweep 只会显式修改：

- ratio
- period 或 height
- CPU process/capacity
- `EXPRESS_MODE`
- GUI/headless
- 输出归档策略

材料、光源、监视器、边界和网格均来自 `.fsp` 模板。Plan 必须明确记录 `template_inherited`，不能声称执行器修改了这些物理设置。

如果用户提出波长、材料、光源、监视器、边界或网格要求：

- 将可结构化的要求保留在 `physics.requirements`。
- validate 返回醒目 warning，说明这些要求不会由当前编译器修改，只能由模板满足。
- mock 可在用户批准该 warning 后运行，用于验证软件链。
- real 必须由模板契约逐项声明并匹配这些要求；缺失或不一致时拒绝。

如果草案要求 `strategy` 不是 `template_inherited`，或要求当前编译器直接修改这些物理对象，则返回 `unsupported_plan_feature`。

mock 可以验证受支持计划的软件链，但 mock 输出始终是合成数据，不是物理证据。

### 规范化

- 所有长度在规范化 Plan 中使用米。
- Agent 可以直接生成米制数值；首版代码不解析 `"470 nm"` 之类的自由文本单位。
- 数组保留用户给定顺序，以保证 task 顺序可预测。
- 重复扫描值属于输入错误，不自动去重。
- 指纹输入使用稳定 JSON：键排序、紧凑分隔符、UTF-8、禁止把审批对象放入 Plan。

### 校验

至少校验：

- 输入必须是 JSON object。
- `schema_version` 只能是 `0.1`。
- `device.type` 只能是 `metasurface_unit_cell`。
- `sweep.axis` 只能是 `period` 或 `height`。
- ratio 列表非空、无重复，且每个值满足 `0 < ratio < 1`。
- period/height 列表非空、无重复，且每个值为正有限数。
- fixed period/height 为正有限数。
- `resource=CPU` 且 `express_mode=0`。
- processes 和 capacity 为正整数。
- template 是非空路径字符串。
- `required_quality` 首版只接受 `pass`、`warning` 或 `fail`。
- success rate 位于 `[0, 1]`。
- 总任务数等于 `len(ratio_values) × len(period_values_m|height_values_m)`。
- 总任务数不超过首版安全上限。

首版安全上限固定为 100 个 task。超过时返回 `task_budget_exceeded`，不允许通过审批绕过；扩大上限属于后续独立变更。

## 校验结果

validate 成功时返回：

```json
{
  "ok": true,
  "normalized_plan": {},
  "plan_fingerprint": "<sha256>",
  "task_count": 4,
  "defaults_applied": [],
  "assumptions": [],
  "warnings": [],
  "errors": [],
  "approval_summary": {}
}
```

`approval_summary` 至少包含：

- 用户意图摘要。
- 器件类型。
- 模板路径。
- 模板继承项。
- 扫描轴和参数列表。
- 总任务数。
- CPU、Express Mode、processes、capacity。
- GUI/headless。
- 输出是否包含逐点模型。
- 质量验收要求。
- 所有默认值、假设和警告。
- 当前 `plan_fingerprint`。

validate 失败时：

- `ok=false`。
- 返回结构化 `error.type`、`message` 和 `details`。
- 不生成可使用的审批凭据。

## 指纹与审批

### Plan 指纹

`plan_fingerprint` 是完整规范化 Plan 的 SHA-256：

```text
sha256(stable_json(normalized_plan))
```

审批对象、时间戳和运行状态不进入指纹。任何规范化字段变化都会产生新指纹。

### Plan 审批

`fdtd_simulation_plan_approve` 接收：

- Plan 草案或规范化 Plan。
- 调用者提交的 `plan_fingerprint`。

工具重新规范化并重新计算指纹。只有完全一致时才返回：

```json
{
  "approved": true,
  "approved_for": "simulation_plan",
  "schema_version": "0.1",
  "plan_fingerprint": "<sha256>"
}
```

这是无服务器审批凭据，不保存用户身份，也不试图证明是谁点击了批准。对话 Agent 负责取得明确用户确认；代码负责保证之后执行的 Plan 与用户确认的对象一致。

### Mock 执行门

mock 必须携带匹配的 `simulation_plan` 审批凭据。缺少审批或指纹不一致时不得调用 RPC。

### Real 执行门

real 必须同时具备：

1. 匹配的 `simulation_plan` 审批凭据。
2. 匹配同一 Plan 指纹的 `real_run` 审批凭据。
3. 模板契约信息，包括真实模板 SHA-256。

Phase 5 不执行 real，但必须实现并测试本地拒绝逻辑，确保未来接入真实运行时不会绕过双层审批。

`real_run` 审批摘要必须包含：

- Plan 指纹。
- 模板路径和 SHA-256。
- task 总数。
- CPU 与 `EXPRESS_MODE=0`。
- processes 与 capacity。
- GUI/headless。
- 输出目录和覆盖风险。
- 默认值、假设和警告。

模板指纹变化、Plan 变化或审批类型不匹配时，原审批立即失效。

## 编译到 `/jobs/*`

### period sweep

```text
SimulationPlan                      /jobs/* request
----------------------------------------------------------------
sweep.axis=period                -> SWEEP_Y_AXIS=period
sweep.ratio_values              -> RATIO_LIST
sweep.period_values_m           -> PERIOD_LIST
sweep.fixed_height_m            -> BASE_HEIGHT
execution.processes             -> FDTD_PROCESSES
execution.capacity              -> FDTD_CAPACITY
execution.express_mode          -> EXPRESS_MODE
execution.hide                  -> sweep.hide
execution.template              -> sweep.template
outputs.include_models          -> sweep.include_models
```

### height sweep

```text
SimulationPlan                      /jobs/* request
----------------------------------------------------------------
sweep.axis=height                -> SWEEP_Y_AXIS=height
sweep.ratio_values              -> RATIO_LIST
sweep.height_values_m           -> HEIGHT_LIST
sweep.fixed_period_m            -> BASE_PERIOD
execution.processes             -> FDTD_PROCESSES
execution.capacity              -> FDTD_CAPACITY
execution.express_mode          -> EXPRESS_MODE
execution.hide                  -> sweep.hide
execution.template              -> sweep.template
outputs.include_models          -> sweep.include_models
```

编译结果：

```json
{
  "mode": "mock",
  "job_type": "metasurface-sweep",
  "idempotency_key": "simulation-plan:<plan_fingerprint>:mock",
  "sweep": {
    "template": "templates/metasurface/base_model.fsp",
    "phases": [1, 2, 3, 4],
    "hide": true,
    "include_models": false,
    "config": {}
  }
}
```

mock 不向现有 JobStore 伪造 `real_run` approval。real 编译时继续使用现有：

```json
{
  "approval": {
    "approved": true,
    "approved_for": "real_run"
  }
}
```

Plan 审批由 MCP 薄编译层在调用 RPC 前验证；现有 RPC real 审批继续作为服务端最终防线。

## MCP 工具

### `fdtd_simulation_plan_validate(plan: dict) -> dict`

- 默认值填充、规范化、校验和指纹计算。
- 不调用 RPC。
- 不创建 job。

### `fdtd_simulation_plan_approve(plan: dict, plan_fingerprint: str) -> dict`

- 重新规范化 Plan。
- 验证用户确认的指纹与当前 Plan 一致。
- 返回 `simulation_plan` 审批凭据。
- 不调用 RPC。

### `fdtd_simulation_plan_start(...) -> dict`

建议参数：

- `plan`
- `plan_approval`
- `mode="mock"`
- `real_run_approval=None`
- `template_contract=None`

行为：

1. 重新规范化并校验 Plan。
2. 校验 `plan_approval`。
3. `mode=mock` 时编译并调用 `RpcClient.jobs_start()`。
4. `mode=real` 时额外校验 `real_run_approval` 和模板契约。
5. Phase 5 测试中只执行 mock；real 只验证本地拒绝与编译逻辑。

现有 `fdtd_metasurface_sweep_*` 工具继续保留，但文档标注为低层便捷工具。自然语言工作流应优先使用 `fdtd_simulation_plan_*`。

## Template Contract

真实运行需要一个可审计的模板契约，至少包含：

```json
{
  "path": "templates/metasurface/base_model.fsp",
  "sha256": "<sha256>",
  "resource": "CPU",
  "express_mode": 0,
  "physics_strategy": "template_inherited",
  "declared_physics": {}
}
```

Phase 5 不尝试从二进制 `.fsp` 离线提取材料、光源、监视器、边界或网格详情。用户审批的是“使用这个明确 SHA-256 的已知模板，并继承其物理设置”。

如果 Plan 的 `physics.requirements` 非空，real 启动前要求模板契约的 `declared_physics` 包含并精确匹配这些字段。该声明必须来自受控的模板安装或检查流程，不能由 Agent 根据用户要求自行伪造。

后续如果需要自动提取和验证模板物理内容，应新增独立的 Windows 模板检查流程，不在本阶段猜测。

## Resume 模板指纹保护

当前 runner 在 real sweep 开始时把模板指纹写入 job manifest。恢复前必须：

1. 读取原 job 的 `manifest.template`。
2. 读取原 `inputs/request.json` 中的模板路径。
3. 确认模板文件仍存在。
4. 重新计算 SHA-256。
5. 与 manifest 中的原 SHA-256 比较。
6. 不一致时返回 HTTP 409，`error.type=resume_conflict`。
7. 一致时才选择 pending/failed task。

如果旧 job 没有模板指纹，real metasurface resume 必须拒绝并要求创建新 job；mock 和非 metasurface job 不受该检查影响。

## 错误语义

| 错误类型 | 含义 |
| --- | --- |
| `plan_validation_error` | Plan 字段、单位或范围非法 |
| `unsupported_plan_feature` | 器件、物理策略或直接模板修改不受首版支持 |
| `task_budget_exceeded` | task 数超过 100 |
| `plan_approval_required` | mock/real 缺少 Plan 审批 |
| `plan_fingerprint_mismatch` | 审批指纹与当前规范化 Plan 不一致 |
| `real_run_approval_required` | real 缺少第二层审批 |
| `template_contract_required` | real 缺少模板 SHA-256 契约 |
| `resume_conflict` | 模板缺失、未记录指纹或 SHA-256 变化 |

MCP 本地校验错误使用统一 `{"ok": false, "error": ...}` 结构，不发送 RPC 请求。

## 数据流

### Plan 与 mock

```text
用户自然语言
  -> Agent 生成 Plan 草案
  -> fdtd_simulation_plan_validate
  -> 展示 defaults / assumptions / warnings / fingerprint
  -> 用户明确批准
  -> fdtd_simulation_plan_approve
  -> fdtd_simulation_plan_start(mode="mock")
  -> compile_metasurface_plan
  -> RpcClient.jobs_start
  -> Windows /jobs/start
  -> 持久 mock job / tasks / quality / evidence
```

### Real 的未来入口

```text
已批准 Plan
  -> 取得模板契约和 real 审批摘要
  -> 用户明确批准真实运行
  -> 校验 Plan 指纹和模板 SHA-256
  -> 编译为 real /jobs/start 请求
  -> 服务端再次校验 real_run approval
```

## 测试策略

使用 TDD，离线测试为主。

### Plan 规范化

- 空草案填充当前 2×2 CPU 默认值。
- 每个默认值出现在 `defaults_applied`。
- period sweep 和 height sweep 规范化正确。
- 相同语义输入生成稳定相同指纹。
- 任一规范化字段变化会改变指纹。

### Plan 校验

- 非 object 输入失败。
- 非 metasurface 器件失败。
- 非法 ratio、负长度、NaN/Infinity、空列表和重复值失败。
- CPU 与非零 Express Mode 冲突失败。
- GPU 失败。
- task 数超过 100 失败。
- 非 `template_inherited` 策略或要求编译器直接修改模板物理对象时失败。
- `physics.requirements` 在 mock 中生成警告，在 real 中必须匹配模板契约。

### 审批

- validate 本身不生成可执行审批。
- 正确指纹可生成 Plan 审批。
- 计划变化后旧审批失效。
- 无 Plan 审批不能 mock。
- real 缺少第二层审批时失败。
- real 缺少模板契约时失败。
- real 模板指纹或 Plan 指纹不一致时失败。
- real 模板契约未满足 `physics.requirements` 时失败。

### 编译

- period Plan 精确映射为现有 sweep 字段。
- height Plan 精确映射为现有 sweep 字段。
- 编译任务数与 Plan 任务数一致。
- mock 请求不包含伪造的 real approval。
- real 请求只在双层审批通过后包含现有 `real_run` approval。
- idempotency key 包含 Plan 指纹和 mode。

### MCP

- 注册三个新工具。
- validate/approve 不调用 RPC。
- mock start 只调用一次 `jobs_start`。
- 本地拒绝时不调用 RPC。
- fake RPC 返回持久 job_id、4 个 task、quality 和 evidence 路径。

### Resume

- 模板指纹未变化时允许选择 pending/failed task。
- 模板 SHA-256 变化时返回 `resume_conflict`。
- 模板文件缺失时返回 `resume_conflict`。
- 旧 real metasurface job 缺少指纹时拒绝 resume。
- mock 和 geometry job 保持现有 resume 行为。

### 全量验证

```bash
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
.venv/bin/python -m pytest -q
```

不得在 Phase 5 验证中启动 Windows 服务或真实 FDTD。

## 验收场景

用户提出：

> 用 CPU 扫描超表面单元的直径比例和周期。

Agent 生成最小草案后，系统：

1. 补齐受控模板、2×2 默认扫描值、固定高度、CPU、`EXPRESS_MODE=0`、headless、输出和质量要求。
2. 明确展示所有默认值、模板继承项、任务数和 Plan 指纹。
3. 在用户批准前不执行 mock。
4. 用户批准后创建持久 mock job。
5. 返回 4 个 task、质量报告和 evidence index。
6. mock 输出明确标记为 synthetic，不能作为物理证据。
7. Plan 任一参数变化后，旧审批不能继续使用。

## 后续阶段

Phase 5 完成后，Phase 6 以直波导透射或模式验证作为第二个 recipe，检验 `SimulationPlan` 的公共字段是否真的可复用。只有得到第二种器件的实际需求后，才考虑 recipe registry 或更通用的 solver schema。
