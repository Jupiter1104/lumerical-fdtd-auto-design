# FDTD Operations V1 — 通用 20 步操作闭环

本文档描述通过 FDTD MCP v0.1.0 完成一次完整 FDTD 仿真的 20 步操作流程。

## 20 步操作清单

| 步骤 | 操作 | MCP 工具 | 说明 |
|------|------|----------|------|
| 1 | 健康检查 | `fdtd_health` | 确认 RPC 连通性 |
| 2 | 启动会话 | `fdtd_session_start` | 启动 FDTD GUI/headless |
| 3 | 新建项目 | `fdtd_project_new` | 创建 .fsp 项目 |
| 4 | 添加材料 | `fdtd_material_create` | 定义材料光学属性 |
| 5 | 设置仿真区域 | `fdtd_object_create` (fdtd_region) | 定义 FDTD 求解域 |
| 6 | 创建结构 | `fdtd_object_create` (rectangle/circle/ring) | 添加几何结构 |
| 7 | 列出对象 | `fdtd_object_list` | 检查对象树 |
| 8 | 读取对象属性 | `fdtd_object_get` | 检查单个对象参数 |
| 9 | 修改对象 | `fdtd_object_update` | 调整结构参数 |
| 10 | 复制对象 | `fdtd_object_copy` | 复制并变换结构 |
| 11 | 重命名对象 | `fdtd_object_rename` | 调整对象命名 |
| 12 | 分配材料 | `fdtd_material_assign` | 将材料分配给对象 |
| 13 | 设置边界条件 | `fdtd_solver_update` | 配置 PML/周期边界 |
| 14 | 配置网格 | `fdtd_mesh_diagnose` | 检查网格精度 |
| 15 | 添加光源 | `fdtd_source_create` | 添加 plane/gaussian/mode source |
| 16 | 添加监视器 | `fdtd_monitor_create` | 添加 DFT/index/time monitor |
| 17 | 添加分析组 | `fdtd_analysis_group_create` | 添加 S 参数分析组 |
| 18 | 运行仿真 | `fdtd_simulation_run` | 启动求解 |
| 19 | 读取结果 | `fdtd_result_read` | 提取 S 参数/场数据 |
| 20 | 保存/导出 | `fdtd_project_save` / `fdtd_results_download` | 保存 .fsp 和结果文件 |

## Dry-Run 支持

所有变更操作支持 `dry_run=true` 参数，返回编译后的 Lumerical 脚本而不执行：

```json
{
  "object_type": "rectangle",
  "name": "wg",
  "properties": {"x span": 5e-7, "material": "Si"},
  "dry_run": true
}
```

返回：
```json
{
  "ok": true,
  "script": "addrect;\nset(\"name\",\"wg\");\nset(\"material\",\"Si\");\nset(\"x span\",5e-07);\n",
  "script_sha256": "sha256:..."
}
```

## 对象类型路由

通用 `fdtd_object_create` 接受以下类型：
- `fdtd_region`, `rectangle`, `circle`, `ring`, `polygon`, `structure_group`, `mesh_override`

以下类型有专用工具，使用通用接口会被拒绝并引导至正确工具：
- 光源类型 → `fdtd_source_create`
- 监视器类型 → `fdtd_monitor_create`
- 分析组 → `fdtd_analysis_group_create`
