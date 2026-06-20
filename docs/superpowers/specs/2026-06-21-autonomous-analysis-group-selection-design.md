# 官方 Analysis Group 自主选择闭环设计

## 决策

扩展现有 FDTD MCP，使其在实际建模过程中能够根据分析意图优先选择 Lumerical FDTD v242 Object Library 中的官方 analysis group，并在安全边界内自动探测、配置和验证参数。

本功能不增加 MCP 工具数量。现有 69-tool 注册表保持不变，主要扩展：

- `fdtd_session_start` / `fdtd_session_status`：披露 Object Library catalog 状态。
- `fdtd_analysis_group_create`：支持意图解析、候选匹配、按需探测、参数配置和决策报告。
- `fdtd_device_recipe_validate/compile/build`：保留并执行结构化 `analysis_intent`。

核心原则：

- Windows v242 是 Object Library 事实来源，Agent 不猜 `script_id`。
- 高置信度才自动使用官方分析组。
- 只填写可由结构化输入或当前模型明确推导的参数。
- 探测不得破坏当前工程或干扰正在运行的仿真。
- 任一步骤不满足安全条件时，优先回退自定义 analysis group；`require_builtin=true` 时结构化报错。

## 目标

1. Windows RPC 首次连接 FDTD 时枚举当前安装版本的 Object Library ID，并按安装身份缓存。
2. Lumerical 版本或安装身份变化时自动失效并重建 catalog。
3. 优先读取 Recipe 显式 `analysis_intent`；缺失时从 outputs、FOM 和 monitors 推导意图。
4. 根据意图对当前 catalog 候选进行确定性评分。
5. 高置信度候选在同一空闲 FDTD 会话的隔离临时工程中按需插入和探测。
6. 获取 Setup user properties、Analysis input properties、声明结果、可修改对象属性和可读取的官方默认值。
7. 正式创建时只覆盖可证明的参数，保留其余官方默认值。
8. 执行 `runsetup`，回读已写参数并验证；失败时清理并回退或报错。
9. 每次选择返回完整、可审计的匹配、参数和回退报告。

## 非目标

- 不在首次连接时逐个插入并探测 Object Library 全部对象。
- 不通过网页标题或自然语言猜测 Object Library `script_id`。
- 不让大模型自行生成没有来源的参数数值、推荐范围或物理约束。
- 不保证 Object Library 中每个对象都是 analysis group；非 analysis group 候选在探测后淘汰。
- 不在仿真运行、持久 real job 运行或无法保存恢复工程时执行候选探测。
- 不为了探测启动第二个 FDTD 会话或占用第二份 license。
- 不把成功插入和运行 setup 等同于物理结果正确。
- 不在本功能中增加 MCP tool、修改真实 sweep 审批门或启动 C4/C5。

## 总体流程

```text
FDTD session start
  → 读取 solver version / installation identity
  → 命中同身份 catalog：加载
  → 未命中或身份变化：运行 addobject; 枚举 ID 并缓存

DeviceRecipe / analysis_group_create
  → 解析 analysis_intent
  → catalog 初筛候选
  → 有相关候选且会话可安全探测？
      ├─ 否：回退 custom 或 require_builtin 报错
      └─ 是：依次探测最多 3 个 shortlist 候选
             → 每个候选均保存/恢复当前工程快照
             → addobject(candidate)
             → 探测参数、默认值、结果并缓存
             → 使用探测证据重新评分
             → 通过高置信度门？
                 ├─ 否：回退 custom 或 require_builtin 报错
                 └─ 是：选择最高分候选
             → 正式 addobject
             → 确定性参数映射
             → runsetup
             → 回读验证
             → 成功返回 builtin 决策报告
             → 失败则删除并回退/报错
```

## 组件边界

### `ObjectLibraryCatalog`

位于 Windows RPC 侧，负责：

- 获取当前 FDTD 版本。
- 运行 `addobject;` 枚举当前版本 Object Library ID。
- 维护 catalog 元数据和已探测对象记录。
- 判断缓存是否与当前安装身份一致。
- 使用原子写入保存 catalog，避免服务中断留下半文件。

它不负责语义匹配，也不负责修改用户工程。

### `AnalysisIntentResolver`

纯 Python 组件，负责将结构化输入归一化为一个分析意图。

意图来源优先级：

1. `analysis_groups[].analysis_intent`。
2. Recipe 声明的目标 outputs。
3. FOM 中引用的结果。
4. monitors 的类型、名称和结果字段。

无法唯一推导时返回 `kind=unknown`，不得用自由文本猜测成高置信度意图。

### `AnalysisGroupMatcher`

纯 Python 组件，使用 catalog 中的真实 ID 和已探测元数据评分。

它只输出候选、评分和匹配依据，不调用 lumapi。

### `AnalysisGroupInspector`

Windows RPC 侧组件，负责在安全条件满足时：

- 保存当前工程快照。
- 新建隔离临时工程。
- 插入一个候选 Object Library 对象。
- 确认候选可按 analysis group 查询。
- 探测 Setup、Analysis、结果和通用属性。
- 无论成功或失败都恢复原工程。

### `AnalysisParameterResolver`

纯 Python 组件，只从明确数据源生成参数赋值。

参数来源优先级：

```text
parameter_overrides
→ Recipe 明确值
→ 当前模型可证明推导值
→ 官方默认值
```

### `AnalysisGroupBuilder`

复用现有 `WindowsFdtdAdapter.analysis_group_create` 路径，负责：

- 插入最终官方对象或自定义 group。
- 应用确定参数。
- 执行 setup。
- 回读验证。
- 清理失败对象。
- 生成决策报告。

## Catalog 生命周期

### 缓存位置

Windows runtime 状态继续使用：

```text
%LOCALAPPDATA%\fdtd-mcp\object-library\
```

每个安装身份对应一个 JSON catalog：

```text
catalog-<identity_sha256>.json
```

不得写入 Git 仓库。

### 安装身份

identity payload 至少包含：

```json
{
  "product": "FDTD",
  "solver_version": "2024 R2.4",
  "path_version_tag": "v242",
  "lumapi_sha256": "sha256:..."
}
```

`solver_version` 可读时必须使用；若返回 `unknown`，必须同时获得 `path_version_tag` 和 `lumapi_sha256` 才允许复用缓存。身份信息不足时，本次会话可内存枚举，但不得跨会话复用 catalog。

### 首次连接

`POST /session/start` 成功建立 lumapi 会话后：

1. 计算安装身份。
2. 读取匹配 catalog。
3. 未命中时运行一次 `addobject;`。
4. 保存 ID 列表和生成时间。
5. 在 session response 中返回 catalog 摘要。

枚举失败不应关闭已经成功建立的 FDTD 会话。返回：

```json
{
  "object_library": {
    "status": "unavailable",
    "catalog_cached": false,
    "enumeration_error": {
      "type": "object_library_enumeration_failed",
      "message": "..."
    }
  }
}
```

此时 builtin 自动选择不可用，但 custom analysis group 仍可使用。

### Catalog schema

```json
{
  "schema_version": "1.0",
  "installation_identity": {},
  "generated_at": "2026-06-21T00:00:00Z",
  "script_ids": ["..."],
  "probes": {
    "verified-script-id": {
      "status": "verified_analysis_group",
      "probed_at": "2026-06-21T00:00:00Z",
      "setup_properties": [],
      "analysis_properties": [],
      "analysis_results": [],
      "settable_properties": [],
      "probe_evidence": {}
    }
  }
}
```

探测失败也要缓存，记录 `status=not_analysis_group | probe_failed` 和结构化错误，避免同一会话反复破坏性试错。服务重启后允许对 `probe_failed` 重试一次；已确认 `not_analysis_group` 在安装身份不变时不重试。

## Analysis Intent 契约

DeviceRecipe analysis group：

```json
{
  "type": "analysis_group",
  "name": "power_analysis",
  "analysis_intent": {
    "kind": "net_power_flow",
    "outputs": ["T"],
    "region_role": "device",
    "direction": "forward"
  },
  "prefer_builtin": true,
  "require_builtin": false,
  "script_id": "",
  "parameter_overrides": {}
}
```

首版支持的规范化 `kind`：

- `transmission`
- `net_power_flow`
- `absorption`
- `far_field`
- `polarization`
- `mode_area`
- `modal_volume`
- `movie`
- `unknown`

未知字符串保留在报告中，但归一化为 `unknown`，不能触发 builtin 自动创建。

### 显式 `script_id`

- 显式 `script_id` 优先于自动匹配。
- ID 必须存在于当前安装身份的 catalog。
- 不存在时：
  - `require_builtin=true`：返回 `object_library_script_id_not_found`。
  - 其他情况：回退 custom，并披露原因。
- 即使 ID 存在，也必须按需探测并确认它是可用 analysis group。

## 候选匹配

### 评分输入

匹配只使用：

- 真实 `script_id` 的规范化 token。
- 已探测的参数名和结果名。
- 规范化 intent kind。
- intent outputs。
- Recipe FOM 引用。
- monitor 类型和结果字段。

不调用外部网页，不由 LLM 在运行时自由打分。

### 首版确定性评分

总分限制在 `[0, 1]`：

- script ID token 与 intent kind 的核心词命中：`+0.45`
- 已探测结果名与 requested output 精确命中：`+0.25`
- 已探测参数名与 intent 特征命中：`+0.15`
- monitor 类型与候选用途兼容：`+0.10`
- FOM 引用与候选结果匹配：`+0.05`

互斥用途或探测证明不是 analysis group：候选淘汰。

### 两阶段选择

未探测对象没有参数和结果证据，不能直接套用最终 `0.85` 门槛。选择必须分两阶段：

1. **Shortlist 初筛**：
   - 只使用真实 script ID token、intent、monitor 和 FOM 上下文。
   - 核心词得分 `>= 0.35` 才进入 shortlist。
   - 最多保留 3 个候选；同分按规范化 script ID 字典序排序，保证确定性。
2. **Probe 后复评**：
   - 对 shortlist 中尚未探测的候选按顺序执行安全探测。
   - 加入参数名、结果名和对象类型证据后重新计算完整分数。
   - 只有复评后通过高置信度门的候选才能正式插入。

若一个已缓存探测候选直接达到高置信度门，不重复执行 probe。

### 自动选择门

只有同时满足以下条件才自动选择：

- 第一名评分 `>= 0.85`。
- 第一名与第二名分差 `>= 0.15`；只有一个候选时不检查分差。
- 候选已成功探测或当前会话可立即安全探测。
- 没有兼容性错误。

否则返回低置信度报告并回退 custom；`require_builtin=true` 时返回 `builtin_analysis_group_no_high_confidence_match`。

## 安全探测与工程恢复

### 允许探测的条件

必须同时满足：

- lumapi session active。
- 当前没有 simulation run。
- 当前没有 real sweep/job 占用会话。
- solver 处于可编辑状态，或能安全切回 layout 且不会丢失未归档结果。
- RPC 能创建本地临时目录。
- 当前工程能成功保存为恢复快照。

任一条件不满足时，不执行探测。

### 隔离流程

1. 在 `%LOCALAPPDATA%\fdtd-mcp\object-library\probe-work\` 创建唯一目录。
2. 将当前工程保存为 `restore.fsp`。
3. 记录当前工程标识；若原工程已有稳定路径，只记录路径，不自动覆盖原文件。
4. `newproject` 创建临时空工程。
5. `addobject(candidate_id)`。
6. 给对象设置唯一探测名称。
7. 执行属性查询。
8. 关闭临时工程并加载 `restore.fsp`。
9. 验证恢复后关键对象清单指纹与保存前一致。
10. 删除临时目录；若清理失败，记录路径但不得影响恢复结果。

恢复失败是严重错误：

- 禁止继续正式创建 analysis group。
- 返回 `analysis_probe_restore_failed`。
- 不自动创建 custom group，避免在未知工程状态上继续写入。

### 探测查询

使用 FDTD v242 官方接口：

- `queryuserprop(group)`：Setup user property 名称和类型。
- `queryanalysisprop(group)`：Analysis input property 名称和类型。
- `queryanalysisresult(group)`：声明结果名称和类型。
- `getnamed` / `get`：读取可访问的当前值。
- `setnamed` / `set` 的属性列表查询：获取通用可修改属性。

无法读取默认值时保留名称和类型，并标记 `default_readable=false`，不得制造默认值。

## 参数自动配置

### 类型

Lumerical property type 代码按官方接口原样保存，同时提供规范化类型：

- number
- string/text
- length
- time
- frequency
- material
- matrix
- unknown

Analysis property 出现额外官方 type code 时原样保存，不强制错误映射。

### 可证明推导

首版允许的模型推导来源：

- FDTD region 的 `x/y/z`、`x/y/z span`。
- 与 intent 明确关联的 monitor 的位置、span、orientation 和频率/波长范围。
- source 的传播方向、偏振和频率/波长范围。
- DeviceRecipe 明确命名的 region role。
- 参数表达式经 DeviceRecipe 编译器确定性求值后的值。

参数名需通过规范化别名表精确匹配，例如：

```text
x span ↔ x_span
y span ↔ y_span
z span ↔ z_span
wavelength start ↔ wavelength_start
wavelength stop ↔ wavelength_stop
```

不存在唯一来源、单位不兼容或多个对象冲突时，标记 unresolved 并保留官方默认值。

### 覆盖规则

`parameter_overrides` 允许用户显式覆盖已探测到的参数。每个 override 必须：

- 参数名存在于探测 schema。
- 值与参数类型兼容。
- DeviceRecipe 表达式可确定性求值。

未知参数返回验证错误，不静默传给 `set`。

### Setup 与回读

正式插入官方 analysis group 后：

1. 应用已确定参数。
2. 执行 `runsetup`。
3. 回读所有已应用参数。
4. 对数值使用类型相关的稳定容差比较；字符串要求精确相等。
5. 记录保留默认值和 unresolved 参数。

任何写入、setup 或回读失败：

- 删除本次插入对象。
- `prefer_builtin=true`：创建自定义 group，并返回 builtin 失败证据。
- `require_builtin=true`：返回结构化错误，不创建 custom group。

## RPC 与 MCP 契约

### `POST /analysis-groups`

扩展 request：

```json
{
  "name": "power_analysis",
  "properties": {},
  "analysis_intent": {},
  "recipe_context": {
    "solver": {},
    "sources": [],
    "monitors": [],
    "outputs": [],
    "fom": {}
  },
  "parameter_overrides": {},
  "prefer_builtin": true,
  "require_builtin": false,
  "script_id": "",
  "dry_run": false
}
```

直接 MCP 调用可提供 `recipe_context`。DeviceRecipe build 由编译/build 管线生成同一上下文，不要求用户重复填写。

### Dry run

`dry_run=true` 不启动候选插入探测，也不声称候选已验证：

- 使用已有 catalog 和已缓存 probe 评分。
- 未探测候选返回 `probe_required=true`。
- 若不能达到高置信度，返回计划中的 fallback。
- 不生成假定成功的 `addobject` 最终脚本。

### 决策报告

成功或回退响应包含：

```json
{
  "name": "power_analysis",
  "source": "builtin",
  "script_id": "verified-id",
  "catalog_identity": "sha256:...",
  "catalog_status": "ready",
  "intent": {
    "kind": "net_power_flow",
    "source": "explicit",
    "evidence": []
  },
  "match_confidence": 0.95,
  "match_reasons": [],
  "candidates": [],
  "probe": {
    "status": "cached|executed|not_required|deferred",
    "restore_verified": true
  },
  "parameters": {
    "applied": {},
    "defaults_preserved": {},
    "unresolved": [],
    "verification": {}
  },
  "setup_verified": true,
  "fallback_used": false,
  "fallback_reason": null,
  "physical_conclusion": false
}
```

候选列表默认最多返回 5 项，只包含 ID、评分、匹配依据和 probe 状态，不回传 setup/analysis script 全文。

### Session 状态

`fdtd_session_start` 和 `fdtd_session_status` 增加：

```json
{
  "object_library": {
    "status": "ready|unavailable|identity_unstable",
    "identity": "sha256:...",
    "script_id_count": 0,
    "verified_analysis_group_count": 0,
    "generated_at": "...",
    "catalog_path": "..."
  }
}
```

不得在响应中泄露本机无关路径；`catalog_path` 只返回 `%LOCALAPPDATA%` 下的规范化路径。

## DeviceRecipe 编译与 Build

### Validate

`fdtd_device_recipe_validate`：

- 保留并校验 `analysis_intent`、`parameter_overrides`。
- 允许 `script_id` 为空。
- 不要求 Windows 在线。
- 对未知 intent 给 warning，不在 validate 阶段宣称 fallback 已发生。

### Compile

离线 compile 不能访问 Windows catalog，因此输出的是 analysis group resolution instruction，而不是提前锁定未知官方 ID。

编译报告中每个 analysis group 包含：

```json
{
  "resolution": "explicit_script_id|runtime_match|custom",
  "analysis_intent": {},
  "prefer_builtin": true,
  "require_builtin": false,
  "script_id": "",
  "parameter_overrides": {}
}
```

编译产物拆成：

- `base_script`：材料、几何、solver、source 和 monitor 等可离线确定的 LSF。
- `analysis_group_instructions`：需要 Windows catalog 参与的结构化指令。
- 明确为 custom 且不要求 builtin 的 analysis group 可继续编入 `base_script`。

只要 `prefer_builtin=true`、`require_builtin=true` 或提供了显式 `script_id`，compile 就不得把最终 `addobject` 直接写入可执行 `base_script`。即使有显式 ID，也必须由 Windows build 阶段复核当前 catalog 和 probe 状态。

### Build

`fdtd_device_recipe_build` 的执行顺序固定为：

1. 校验已批准的 Recipe compile fingerprint。
2. 执行 `base_script`，但暂不保存最终 `.fsp`。
3. 对 `analysis_group_instructions` 逐项运行 matcher、inspector、parameter resolver 和 builder。
4. 所有 analysis group 成功创建或按策略回退后保存 `.fsp`。
5. 写 build report 和结构化 manifest。

Compile fingerprint 必须包含 analysis intent、参数覆盖和匹配策略版本。用户批准的是这套确定性运行时选择策略，不要求离线 compile 预先知道具体 Object Library ID。

Build 另生成 `execution_fingerprint`，包含：

- compile fingerprint
- catalog identity
- 最终 script ID 或 custom fallback
- probe schema fingerprint
- 参数 resolution

同一次 build 可以在批准的策略下自主完成选择。后续 replay、resume 或覆盖同一产物时必须匹配原 `execution_fingerprint`；catalog 或 resolution 变化时拒绝静默复用，并要求创建新的 build revision。

## 错误语义

新增结构化错误类型：

- `object_library_enumeration_failed`
- `object_library_identity_unstable`
- `object_library_script_id_not_found`
- `analysis_probe_unavailable`
- `analysis_probe_failed`
- `analysis_probe_restore_failed`
- `builtin_analysis_group_no_high_confidence_match`
- `analysis_parameter_unknown`
- `analysis_parameter_type_mismatch`
- `analysis_setup_failed`
- `analysis_parameter_verification_failed`

所有错误继续使用 API v1 envelope。错误 details 不包含 setup/analysis script 全文或非项目敏感路径。

## 并发与状态

- Catalog 文件写入使用进程内锁和原子 replace。
- 同一时间只允许一个 Object Library probe。
- probe 与 simulation run、real sweep、recipe build 写操作互斥。
- 等待锁不超过 5 秒；超时后按 `analysis_probe_unavailable` 处理，不长时间阻塞 MCP。
- 长时间 solver run 不得被 catalog refresh 或 probe 中断。
- Agent 提交长任务后不因 catalog 状态主动轮询。

## 测试与验收

### 离线单元测试

覆盖：

- 安装身份相同复用 catalog。
- solver version 或 lumapi hash 变化使缓存失效。
- `unknown` version 且身份不足时不跨会话复用。
- intent 显式优先和 outputs/FOM/monitor 推导。
- 确定性评分、`0.85` 门槛和 `0.15` 分差。
- 低置信度回退及 `require_builtin` 错误。
- 显式 ID 不在 catalog 时拒绝。
- 参数优先级、类型校验、默认值保留和 unresolved 披露。
- dry-run 不执行 probe。
- 69-tool 注册表保持不变。

### Fake lumapi 集成测试

Fake backend 需支持：

- `addobject;` 枚举。
- `addobject("id")` 插入。
- `queryuserprop`。
- `queryanalysisprop`。
- `queryanalysisresult`。
- 默认值读取、参数写入、`runsetup` 和回读。
- project snapshot/new/load 恢复。

测试成功、probe 失败、setup 失败、回读不一致和恢复失败路径。

### Windows v242 manual smoke

新增一个不求解的 Object Library smoke：

1. 启动 session。
2. 验证 catalog 使用真实 v242 identity。
3. 选择一个从 `addobject;` 枚举得到的、用途明确的 analysis group。
4. 在空工程中按需探测。
5. 验证 Setup/Analysis/Result 至少有一类 schema 可读。
6. 正式插入并应用一个可安全回读的参数；若该对象没有适合覆盖的参数，则验证全部默认值被保留。
7. 执行 `runsetup`。
8. 保存 `.fsp` 和 JSON 报告。

报告必须包含：

```json
{
  "technical_smoke": true,
  "physical_conclusion": false,
  "catalog_enumerated": true,
  "probe_restore_verified": true,
  "setup_verified": true
}
```

该 smoke 不运行 FDTD solve，不判断分析结果物理正确性。

### 完成定义

本功能完成需同时满足：

1. Windows v242 catalog 能首次枚举、复用和按身份失效。
2. DeviceRecipe 可携带或推导 analysis intent。
3. 高置信度候选能按需安全探测。
4. Agent 能读取官方组声明的可填参数、类型和可访问默认值。
5. 只覆盖确定值，其余官方默认值明确披露。
6. `runsetup` 和回读验证成功。
7. 低置信度、不安全或候选失败时按策略回退/报错。
8. 决策报告包含来源、候选、评分、参数来源、默认值和 fallback 原因。
9. 现有 69-tool 注册表和原有显式 `script_id` 行为兼容。
10. 离线完整测试通过，Windows v242 manual smoke 通过。

## 文档更新

实现完成后同步更新：

- `README.md`
- `AGENTS.md`
- `TECH_STACK.md`
- `docs/MCP_USER_GUIDE.md`
- `docs/FDTD_OPERATIONS_V1.md`
- `docs/DEVICE_RECIPE_V1.md`
- `docs/RPC_API_V1.md`
- `docs/WINDOWS_RUNBOOK.md`
- `src/knowledge/prompts/lumerical_analysis_groups.md`
- `DEV_LOG.md`
- `PITFALLS.md`
- `RETROSPECTIVE.md`

## 官方依据

- Analysis Groups - Simulation object: https://optics.ansys.com/hc/en-us/articles/360034382454-Analysis-Groups-Simulation-object
- Object Library in FDTD and MODE: https://optics.ansys.com/hc/en-us/articles/360034394494-Object-Library-in-FDTD-and-MODE
- addobject - Script command: https://optics.ansys.com/hc/en-us/articles/360034404094-addobject-Script-command
- queryuserprop - Script command: https://optics.ansys.com/hc/en-us/articles/360042665193-queryuserprop-Script-command
- queryanalysisprop - Script command: https://optics.ansys.com/hc/en-us/articles/360042187894-queryanalysisprop-Script-command
- set - Script command: https://optics.ansys.com/hc/en-us/articles/360034928773-set-Script-command
- get - Script command: https://optics.ansys.com/hc/en-us/articles/360034928873-get-Script-command
