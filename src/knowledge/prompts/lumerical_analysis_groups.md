# Lumerical Analysis Groups / Object Library Notes

本页记录 Lumerical 官方 Analysis Groups 与 Object Library 的自动化规则。

## 两种创建路径

### 空白/自定义 analysis group

使用 `addanalysisgroup` 创建空白 analysis group，然后自行添加 monitor、user properties、setup script 和 analysis script。

```lsf
addanalysisgroup;
set("name", "analysis_T");
addtime;
addtogroup("analysis_T");
```

适合：

- 项目自定义后处理。
- 官方 Object Library 没有对应对象。
- 需要完全可控、可审计的最小 analysis script。

### 官方 Object Library 预定义对象

使用 `addobject("script_ID")` 插入 Object Library 中的预定义对象或 analysis group。

```lsf
addobject("script_ID");
set("name", "analysis_builtin");
```

使用 `addobject;` 可以让当前 Lumerical 版本返回 Object Library 中可用对象名称列表。

```lsf
A = addobject;
L = length(A);
for (i = 1:L) {
  ?A{i};
}
```

工程规则：

- 若用户请求“官方自带分析组优先”，Agent/MCP 应优先尝试 `addobject("script_ID")`。
- `script_ID` 不要凭空猜测；应来自当前 Windows v242 的 `addobject;` 运行时枚举或官方页面明确给出的 ID。
- 找不到可确认的 `script_ID` 时，回退到 `addanalysisgroup` 自定义路径，除非用户明确要求 `require_builtin=true`。
- Object Library 官方说明为不可由用户修改；自定义对象复用应通过复制/粘贴或项目模板，不应伪装成官方库项。

## 官网列出的 Object Library analysis/related-analysis 条目

官方 “Object library objects and related analysis” 页面列出了以下对象库相关分析主题。它们证明这些方向存在官方示例/库对象或相关分析流程，但不等价于可直接传给 `addobject("...")` 的 `script_ID`；实际 ID 仍需运行时枚举确认。

| 官方主题 | 建议归类 | 自动化备注 |
| --- | --- | --- |
| Absorption per unit volume | optical_power / absorption | 吸收功率密度分析，常需 field monitor + index monitor。 |
| Calculating absorbed optical power - from divergence of Poynting vector | optical_power / absorption | 官方也提示该方法对数值问题敏感；非首选。 |
| Calculating absorbed optical power - Higher accuracy method with multiple materials | optical_power / absorption | 多材料高精度吸收分析。 |
| Calculating absorbed optical power - Simple method | optical_power / absorption | 标准吸收分析方法。 |
| Calculating the effective mode area of a waveguide mode | mode / waveguide | 波导模式有效面积。 |
| Calculating the far field polarization ellipse | far_field | 远场偏振椭圆。 |
| Calculating the modal volume of a cavity mode | cavity / modal_volume | 腔模式体积。 |
| Calculating the net power flow with a Power transmission box | optical_power / transmission_box | 盒状 monitors 净功率流；结果常为 `T`。 |
| Changing the far field refractive index analysis object | far_field | 调整远场折射率相关 analysis object。 |
| Creating curved and angled monitors | monitor_geometry | 曲面/倾斜 monitor 构造。 |
| Determining the direction of power flow | optical_power | 功率流方向判定。 |
| Far field directivity calculations of an antenna | far_field / antenna | 天线远场指向性。 |
| Far field projections from a box of monitors | far_field / monitor_box | 盒状 monitors 远场投影。 |
| Making a CW movie from a frequency monitor | visualization / movie | 从频域 monitor 生成连续波 movie。 |
| Tip for adding structure outlines to field plots | visualization / field_plot | 场图中叠加结构轮廓。 |

## MCP/Agent 设计含义

当前已实现完整的自主 Object Library 工作流，不需要内置未经验证的 script ID：

1. **enumerate**：`/session/start` 在首次 session 自动运行 `addobject;` 枚举，保存 Object Library 名称列表到 `runtime/object_library_catalog.json`，并返回 `object_library.script_id_count`。
2. **shortlist**：`analysis_intent` + `recipe_context` 从 catalog 产生确定性短列表，每项带 `score` 和 `match_reasons`。
3. **probe**：高置信度候选通过只读 inspector 获取 `setup_properties`、`analysis_properties`、`analysis_results`、`settable_properties`；探针后 `restore_verified` 确认模型已恢复原状。
4. **configure**：`parameter_overrides` 按安全优先级合并：`parameter_overrides` > `recipe_context` > 探针默认值；冲突报 `parameter_conflict`，未知参数报 `unknown_analysis_parameter`。
5. **runsetup**：执行 analysis group setup script；失败且 `require_builtin=true` 时报 `analysis_setup_failed` 并从模型中删除对象。
6. **readback**：逐参数 `getnamed` 读回实际值并与期望值比对；任一不匹配报 `analysis_parameter_verification_failed`（409）。

MCP/RPC 决策报告包含：
- `source=builtin|custom`
- `script_id`
- `match_confidence`、`match_reasons`
- `probe.restore_verified`、`setup_verified`
- `candidates`、`fallback_used`、`fallback_reason`
- `catalog_identity`、`catalog_status`
- `physical_conclusion=false`

`prefer_builtin=true` 低置信度自动回退 `addanalysisgroup`；`require_builtin=true` 无匹配直接报错。

## 官方来源

- Analysis Groups - Simulation object: https://optics.ansys.com/hc/en-us/articles/360034382454-Analysis-Groups-Simulation-object
- Object Library in FDTD and MODE: https://optics.ansys.com/hc/en-us/articles/360034394494-Object-Library-in-FDTD-and-MODE
- Object library objects and related analysis: https://optics.ansys.com/hc/en-us/sections/360006692153-Object-library-objects-and-related-analysis
- addanalysisgroup - Script command: https://optics.ansys.com/hc/en-us/articles/360034404074-addanalysisgroup-Script-command
- addobject - Script command: https://optics.ansys.com/hc/en-us/articles/360034404094-addobject-Script-command
