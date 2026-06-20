# Generic SweepPlan V1

Generic SweepPlan 将 DeviceRecipe 的参数空间展开为可执行的 Cartesian 任务网格。

## Schema Version

`1.0`

## 结构

```json
{
    "schema_version": "1.0",
    "recipe_ref": {"recipe": {...}},
    "parameters": [
        {"name": "period", "values": [390e-9, 470e-9, 540e-9]},
        {"name": "ratio", "range": {"start": 0.2, "stop": 0.8, "step": 0.3}}
    ],
    "max_tasks": 100
}
```

## 参数指定方式

### Values（显式列表）

```json
{"name": "period", "values": [390e-9, 470e-9, 540e-9]}
```

保持输入顺序，每个值产生一个 task。

### Range（等差范围）

```json
{"name": "ratio", "range": {"start": 0.2, "stop": 0.8, "step": 0.3}}
```

生成 `[0.2, 0.5, 0.8]`（含终点）。

## Cartesian 展开

多个参数的 Cartesian 积按声明顺序展开，**最后一个参数变化最快**：

```json
{"parameters": [
    {"name": "period", "values": [390e-9, 470e-9]},
    {"name": "ratio", "range": {"start": 0.2, "stop": 0.8, "step": 0.3}}
]}
```

Task 顺序：
1. `period=390e-9, ratio=0.2`
2. `period=390e-9, ratio=0.5`
3. `period=390e-9, ratio=0.8`
4. `period=470e-9, ratio=0.2`
5. `period=470e-9, ratio=0.5`
6. `period=470e-9, ratio=0.8`

## 约束

- 重复参数值 → 错误
- task 数超过 `max_tasks` → 错误（不截断）
- 所有 swept 参数必须在 Recipe 的 `parameters` 中声明
- 同一 Recipe + SweepPlan → 相同 `packet_fingerprint`

## Fingerprints

- `sweep_fingerprint`: SweepPlan 规范化后的 SHA-256
- `packet_fingerprint`: Recipe + SweepPlan + task ID 列表的 SHA-256
- 每个 task 有独立的 `task_id`（从 index + 参数快照派生）

## Mock vs Real

### Mock 模式
- 生成 job 结构
- 写入 `synthetic=true` 合成度量
- 标记 `succeeded`
- 发送飞书通知

### Real 模式
- 要求精确 `packet_fingerprint`
- 要求审批：`{"approved": true, "approved_for": "real_run"}`
- 创建 job + task 文件
- 返回 `202 + job_id`（不等待求解完成）
- 不主动轮询

## MCP 工具

- `fdtd_generic_sweep_validate`: 本地验证（不编译 task）
- `fdtd_generic_sweep_plan`: 完整展开 + 编译
- `fdtd_generic_sweep_start`: 重新规划 + 校验审批 + 调用 RPC
