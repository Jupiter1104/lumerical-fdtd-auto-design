# Device Recipe V1

DeviceRecipe 是可编译为 Lumerical 脚本的结构化器件描述格式。

## Schema Version

`1.0`

## 结构

```json
{
    "schema_version": "1.0",
    "parameters": {...},
    "assumptions": [...],
    "materials": [...],
    "geometry": [...],
    "sources": [...],
    "monitors": [...],
    "analysis_groups": [...],
    "pre_run": "...",
    "post_run": "..."
}
```

## Parameters

参数定义支持：
- `type`: `"float"` 或 `"int"`
- `default`: 默认值（可选）
- `min`/`max`: 值域限制（可选）
- `unit`: 单位，如 `"m"`（可选）
- `source_ref.locator`: 数据来源追踪（可选，无 default 时必需）

## Source References

每个参数的来源必须可追溯：
- 有 `default` 的参数必须有对应的 `assumption` 条目（含 `reason`）
- 无 `default` 的参数必须有 `source_ref.locator`

## Assumptions（假设声明）

```json
{
    "parameter": "pillar_radius",
    "value": 1.88e-7,
    "reason": "From Stage B0.1 probe measurement"
}
```

所有使用默认值的参数必须声明假设及理由。

## Expressions（表达式）

Geometry 属性支持受限表达式：
- 数值常量
- 参数引用：`${parameter_name}`
- 四则运算：`+ - * /`
- 括号分组
- 一元正负号

示例：`${pillar_radius} * 2`

不支持：Python 代码、函数调用、属性访问、import。

## Raw Hooks

`pre_run` 和 `post_run` 可包含原始 Lumerical 脚本：
- **build-only** 模式：hooks 内容被注释，不执行
- **run** 模式：hooks 正常执行
- hooks 的 SHA-256 指纹记录在 `raw_hook_hashes` 中

## Analysis Groups

`analysis_groups[]` 支持两种创建路径：

```json
{
  "type": "analysis_group",
  "name": "analysis_builtin",
  "prefer_builtin": true,
  "require_builtin": false,
  "script_id": "power_transmission_box",
  "properties": {}
}
```

- 默认：使用 `addanalysisgroup` 创建自定义空白 analysis group。
- `prefer_builtin=true` 且提供 `script_id`：使用官方 Object Library `addobject("script_id")`。
- `prefer_builtin=true` 但没有 `script_id`：系统自动 enumerate → shortlist → probe → configure → runsetup → readback。
- `require_builtin=true`：调用 RPC/MCP 创建时必须提供已验证 `script_id` 或由系统自动匹配；不要由 Agent 猜测 ID。

`script_id` 应来自 Ansys 官方文档或目标 Windows v242 中 `addobject;` 的运行时枚举。

### Runtime Instructions

编译后的 recipe 可携带 `runtime_instructions`，在 build 阶段注入 analysis group 创建行为：

```json
{
  "type": "analysis_group",
  "runtime_instructions": {
    "prefer_builtin": true,
    "require_builtin": true,
    "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
    "recipe_context": {
      "solver": {"x span": 1.2e-6, "y span": 1.2e-6, "z span": 1.0e-6},
      "monitors": [{"type": "power_monitor", "name": "mon"}],
      "outputs": ["T"],
      "fom": {"result": "T"}
    },
    "parameter_overrides": {}
  }
}
```

构建时 RPC server 按 `runtime_instructions` 自主匹配和配置 official analysis group，并将决策报告写回编译输出。

### Execution Fingerprint

每次 build 生成 `execution_fingerprint`：`SHA-256(recipe_fingerprint + analysis_group.decision_report)`。同一 recipe 对同一 catalog 产生确定性指纹；catalog 版本或探针证据变化会导致指纹变化，防止跨版本篡改决策。

## Compiler Pipeline

```
pre_geometry (raw hook)
→ materials
→ geometry
→ post_geometry (raw hook)
→ simulation region
→ boundaries
→ mesh
→ sources
→ monitors
→ analysis groups
→ save model
```

## Fingerprints

- `recipe_fingerprint`: 规范化 recipe 的 SHA-256
- `compile_fingerprint`: 编译报告的 SHA-256
- `script_sha256`: 生成脚本的 SHA-256

Build 操作通过校验 `compile_fingerprint` 防止篡改。

## MCP 工具

- `fdtd_device_recipe_validate`: 验证 recipe 结构和假设完整性
- `fdtd_device_recipe_compile`: 编译为 Lumerical 脚本
- `fdtd_device_recipe_build`: 通过 RPC 构建 .fsp 文件（需指纹 + 审批）
