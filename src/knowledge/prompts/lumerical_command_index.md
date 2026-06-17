# Lumerical Script / Python API 命令索引

说明：
- `什么时候用` 是工程用法。
- `不要什么时候用` 是 Agent 安全边界。
- `返回值` 依据官方页面；如命令页面说明不返回数据，则写 None。
- Python API 中“大多数 script commands 可作为 session 方法调用”来自官方 Script Commands as Methods 文档： https://optics.ansys.com/hc/en-us/articles/360041579954-Script-commands-as-methods-Python-API
- 未在本机真实 Lumerical 环境运行，示例代码均为待验证。

## addfdtd

- 功能：添加 FDTD solver region。
- 什么时候用：新建仿真或从空项目脚本化搭建 solver region。
- 不要什么时候用：已有模板包含 FDTD region 时，不要重复添加；优先修改现有对象。
- 常见参数：`addfdtd;` 或 `addfdtd(struct_data);`
- 返回值：None。
- 示例：

```lsf
addfdtd;
set("x span", 2e-6);
set("y span", 2e-6);
set("z span", 1e-6);
```

- 常见坑：运行后进入 analysis mode 时不能添加/修改对象，需 `switchtolayout`。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034924173-addfdtd-Script-command

## newproject

- 功能：创建新的 simulation project file。
- 什么时候用：从零脚本化生成一个最小模型，或明确要抛弃当前未保存项目状态。
- 不要什么时候用：已打开模板或历史结果文件且尚未保存时不要调用；官方说明旧项目不会自动保存。
- 常见参数：`newproject;`；FDTD 还支持选项如 `'default'`, `'RF'`, `'current'`, `'existing'`。
- 返回值：None。
- 示例：

```lsf
newproject;
addfdtd;
```

- 常见坑：会创建新 layout 环境，当前 GUI 中旧文件不自动保存。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034931473-newproject-Script-command

## addmesh

- 功能：添加 mesh override region。
- 什么时候用：局部细化关键纳米结构、金属边界、小 gap。
- 不要什么时候用：不要在未做收敛验证时把细网格当作“修复所有问题”的默认动作。
- 常见参数：`addmesh;` 或 `addmesh(struct_data);`
- 返回值：None。
- 示例：

```lsf
addmesh;
set("name", "mesh_device");
set("override x mesh", 1);
set("set maximum mesh step", 1);
set("dx", 5e-9);
```

- 常见坑：全局 `min mesh step` 会覆盖其他 mesh size 设置。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034924253-addmesh

## addrect

- 功能：添加矩形 primitive。
- 什么时候用：创建 substrate、pillar、waveguide、box-like geometry。
- 不要什么时候用：复杂多边形或连续曲线优化不要硬拼大量 rectangle，除非这是明确离散设计。
- 常见参数：`addrect;` 或 `addrect(struct_data);`
- 返回值：None。
- 示例：

```lsf
addrect;
set("name", "pillar");
set("x span", 120e-9);
set("y span", 120e-9);
set("z span", 600e-9);
set("material", "Si (Silicon) - Palik");
```

- 常见坑：对象重名会让 `setnamed` 行为不可靠。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034404214-addrect-Script-command

## addcircle

- 功能：添加圆/椭圆 primitive；3D 中对应柱体。
- 什么时候用：圆柱 nanopillar、圆形孔、disk resonator。
- 不要什么时候用：需要非圆任意轮廓时用 polygon 或 lumopt geometry。
- 常见参数：`addcircle;` 或 `addcircle(struct_data);`
- 返回值：None。
- 示例：

```lsf
addcircle;
set("name", "cylinder");
set("radius", 80e-9);
set("z span", 600e-9);
```

- 常见坑：半径/diameter 属性不要混淆；用 `get` 查对象属性。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034404114-addcircle-Script-command

## addplane

- 功能：添加 plane wave source。
- 什么时候用：平面波照明、周期单元、透射/反射谱。
- 不要什么时候用：波导端口激励、局域偶极发光、TFSF 散射问题各有专用 source。
- 常见参数：`addplane;` 或 `addplane(struct_data);`
- 返回值：None。
- 示例：

```lsf
addplane;
set("injection axis", "z");
set("direction", "backward");
set("wavelength start", 0.8e-6);
set("wavelength stop", 0.82e-6);
```

- 常见坑：周期结构斜入射需要配合 Bloch/BFAST 等边界策略。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034924413-addplane

## adddipole

- 功能：添加 dipole source。
- 什么时候用：发射体、局域源、Purcell/辐射问题。
- 不要什么时候用：宏观平面波照明或波导端口注入。
- 常见参数：`adddipole;` 或 `adddipole(struct_data);`
- 返回值：None。
- 示例：

```lsf
adddipole;
set("x", 0);
set("y", 0);
set("z", 100e-9);
```

- 常见坑：偶极方向、源功率归一化和 monitor 设置必须一起定义。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034924393-adddipole

## adddftmonitor

- 功能：添加 frequency-domain field profile monitor。
- 什么时候用：读取 E/H/T 等频域结果；新脚本优先用它。
- 不要什么时候用：不要优先使用已 deprecated 的 `addpower`/`addprofile`，除非旧模板兼容需要。
- 常见参数：`adddftmonitor;` 或 `adddftmonitor(struct_data);`
- 返回值：None。
- 示例：

```lsf
adddftmonitor;
set("name", "T");
set("monitor type", 7);
set("x span", 2e-6);
set("y span", 2e-6);
set("z", -0.7e-6);
```

- 常见坑：monitor type 的数字/字符串映射需在目标版本中查询确认。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/36957320687763-adddftmonitor-Script-command

## addpower

- 功能：添加旧 field and power monitor。
- 什么时候用：维护旧脚本或旧模板。
- 不要什么时候用：新建工程默认不用；官方标注 deprecated，推荐 `adddftmonitor`。
- 常见参数：`addpower;`
- 返回值：None。
- 示例：

```lsf
addpower;
set("name", "field_profile");
set("monitor type", 7);
```

- 常见坑：未来版本可能移除。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034404534-addpower-Script-command

## addtime

- 功能：添加 time-domain monitor。
- 什么时候用：需要时间波形、谐振衰减、Q factor、时域诊断。
- 不要什么时候用：只需稳态频域透射时不要添加大面积 time monitor。
- 常见参数：`addtime;` 或 `addtime(struct_data);`
- 返回值：None。
- 示例：

```lsf
addtime;
set("name", "time_1");
set("monitor type", 1);
set("x", 0); set("y", 0); set("z", 0);
```

- 常见坑：大空间范围 time monitor 会消耗大量内存。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034404494-addtime

## addanalysisgroup

- 功能：添加 analysis group。
- 什么时候用：封装 monitors 与 analysis script。
- 不要什么时候用：不要把全局优化决策写进 analysis group；Agent 决策应在 Python 层留日志。
- 常见参数：`addanalysisgroup;` 或 `addanalysisgroup(struct_data);`
- 返回值：None。
- 示例：

```lsf
addanalysisgroup;
set("name", "analysis_T");
```

- 常见坑：已有数据的 analysis script 不会自动重复运行，重跑前用 `clearanalysis`。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034404074-addanalysisgroup-Script-command

## set

- 功能：设置选中对象属性。
- 什么时候用：刚创建对象后立即设置属性，或明确选中了对象。
- 不要什么时候用：对象不明确或可能重名时不要依赖当前选择。
- 常见参数：`set("property", value);`，也可用 struct。
- 返回值：None。
- 示例：

```lsf
addrect;
set("name", "pillar");
set("x span", 120e-9);
```

- 常见坑：属性名与 GUI 属性名一致；单位用 SI 标准数值。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034928773-set-Script-command

## setnamed

- 功能：按对象名设置属性。
- 什么时候用：自动化修改模板中已有对象。
- 不要什么时候用：对象名不唯一时不要省略索引或完整路径。
- 常见参数：`setnamed("name", "property", value);`，`setnamed("group::name", ...)`，`setnamed("name", struct);`
- 返回值：None；`?setnamed("name")` 可列属性。
- 示例：

```lsf
setnamed("pillar", "x span", 140e-9);
```

- 常见坑：analysis mode 下会报错；先 `layoutmode` / `switchtolayout`。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034928793-setnamed-Script-command

## get

- 功能：读取选中对象属性。
- 什么时候用：检查属性值、导出模板属性清单。
- 不要什么时候用：不要在多个对象同时选中且未指定索引时做关键判断。
- 常见参数：`get("property");`，`get({"x","y","z"});`
- 返回值：矩阵、字符串或 struct。
- 示例：

```lsf
select("pillar");
xspan = get("x span");
```

- 常见坑：group 内对象读取需要用 `getnamed` 或完整路径。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034928873-get-Script-command

## layoutmode

- 功能：判断当前是否 layout/design mode。
- 什么时候用：任何修改对象前。
- 不要什么时候用：不要把返回 1 当成结果仍有效；它只是模式状态。
- 常见参数：`layoutmode;`
- 返回值：1 表示 layout mode，0 表示 analysis mode。
- 示例：

```lsf
if (layoutmode == 0) {
  switchtolayout;
}
```

- 常见坑：`switchtolayout` 会丢失已有结果。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034924033-layoutmode

## switchtolayout

- 功能：切换到 layout mode。
- 什么时候用：已运行仿真后需要修改对象。
- 不要什么时候用：不要在尚未保存/提取结果前随手调用；结果会丢失。
- 常见参数：`switchtolayout;`
- 返回值：None。
- 示例：

```lsf
run;
switchtolayout;
setnamed("FDTD", "simulation temperature", 400);
```

- 常见坑：会清除可用结果，必须先保存结果。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034923993-switchtolayout

## run

- 功能：运行当前仿真。
- 什么时候用：单个项目已经完成建模和保存后。
- 不要什么时候用：不要在真实 FDTD 未审批时运行；不要对未保存/未记录 config 的模型运行。
- 常见参数：`run;`，FDTD/RCWA 可用 `run("FDTD","CPU")` 或 `run("FDTD","GPU")` 等官方形式。
- 返回值：None。
- 示例：

```lsf
save("sample_0001.fsp");
run;
```

- 常见坑：运行完成后进入 analysis mode；修改前需切回 layout。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034931333-run-Script-command

## runjobs

- 功能：运行 job manager queue 中的所有仿真。
- 什么时候用：多个已保存仿真文件批量运行。
- 不要什么时候用：不要替代带失败记录的 Python scheduler，除非已接受 runjobs 错误模型。
- 常见参数：`runjobs;`，`runjobs("FDTD","CPU");`
- 返回值：None；错误时抛出错误。
- 示例：

```lsf
addjob("sample_0001.fsp");
addjob("sample_0002.fsp");
runjobs;
```

- 常见坑：并发错误时只显示最新错误；需要外部日志补足。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034931373-runjobs-Script-command

## load

- 功能：加载 simulation project file。
- 什么时候用：打开 copied `.fsp` 或历史结果文件。
- 不要什么时候用：不要加载原始模板后直接保存覆盖。
- 常见参数：`load(filename);`
- 返回值：None。
- 示例：

```lsf
load("sample_0001.fsp");
```

- 常见坑：路径转义；Windows 路径建议由 Python 规范化传入。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034410834-load-Script-command

## save

- 功能：保存 project file；已运行时可包含结果。
- 什么时候用：运行前保存 point `.fsp`，运行后保存结果态。
- 不要什么时候用：不要保存到 template 路径。
- 常见参数：`save(filename);`
- 返回值：None。
- 示例：

```lsf
save("runs/run_001/simulations/sample_0001/model.fsp");
```

- 常见坑：相对路径依赖 cwd；Agent 应使用绝对路径。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034410814-save-Script-command

## getresult

- 功能：从 simulation object 获取 dataset 结果。
- 什么时候用：读取 E field、T、status、analysis group 结果。
- 不要什么时候用：只需要单个 raw field array 时可用 `getdata`。
- 常见参数：`getresult("monitor","E");`，`?getresult("monitor");`
- 返回值：dataset。
- 示例：

```lsf
E = getresult("field", "E");
T = getresult("T", "T");
```

- 常见坑：读取前仿真必须已运行；dataset 字段用 `.` 访问。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034409854-getresult

## getdata

- 功能：从 monitor 获取 raw data。
- 什么时候用：读取 `Ex`, `f`, `x`, `y`, `z` 等单独数组。
- 不要什么时候用：需要完整带坐标/属性的结果时优先 `getresult`。
- 常见参数：`getdata("monitor","Ex");`，可选 unfold option。
- 返回值：矩阵/向量/raw data。
- 示例：

```lsf
f = getdata("field", "f");
Ex = getdata("field", "Ex");
```

- 常见坑：官方建议多数情况下 `getresult` 更方便。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034409834-getdata

## haveresult

- 功能：检查对象是否有 dataset result。
- 什么时候用：`getresult` 前。
- 不要什么时候用：不要用它检查 raw data；raw data 用 `havedata`。
- 常见参数：`haveresult("T","T");`
- 返回值：1 或 0。
- 示例：

```lsf
if (haveresult("T", "T")) {
  T = getresult("T", "T");
}
```

- 常见坑：monitor 名称错时返回 0 或报错，需记录可用 result 列表。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034409894-haveresult-Script-command

## havedata

- 功能：检查对象是否有 raw data。
- 什么时候用：`getdata` 前。
- 不要什么时候用：不要用它判断 dataset result；dataset 用 `haveresult`。
- 常见参数：`havedata("field","Ex");`
- 返回值：1 或 0。
- 示例：

```lsf
if (havedata("field", "Ex")) {
  Ex = getdata("field", "Ex");
}
```

- 常见坑：analysis group 可能需先 `runanalysis`。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034930213-havedata-Script-command

## transmission

- 功能：返回 power/profile monitor 的归一化透射。
- 什么时候用：透射率 FOM、约束判断。
- 不要什么时候用：monitor 法向不明确或需要指定衍射级次时，先确认 monitor 类型或用 grating 相关命令。
- 常见参数：`transmission("mname");`
- 返回值：频率相关透射数组。
- 示例：

```lsf
T = transmission("T");
```

- 常见坑：负值表示功率沿负方向流动；归一化状态不影响该函数结果。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034405354-transmission-Script-command

## runanalysis

- 功能：运行 analysis object 脚本。
- 什么时候用：analysis group 中有后处理脚本时。
- 不要什么时候用：不要指望它重算已有数据；要重算先 `clearanalysis`。
- 常见参数：`runanalysis;`，`runanalysis("group name");`
- 返回值：None。
- 示例：

```lsf
runanalysis("analysis_T");
```

- 常见坑：已有数据不会重跑。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034409874-runanalysis-Script-command

## clearanalysis

- 功能：清除 analysis object 结果。
- 什么时候用：需要强制重跑 analysis script。
- 不要什么时候用：不要在未导出结果前清除。
- 常见参数：`clearanalysis;`，`clearanalysis("name");`
- 返回值：None。
- 示例：

```lsf
clearanalysis("analysis_T");
runanalysis("analysis_T");
```

- 常见坑：切换到 layout mode 也会清除 analysis data。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034930253-clearanalysis-Script-command

## savedata

- 功能：保存 workspace variables 到 `.ldf`。
- 什么时候用：Lumerical 内部保存中间变量或 monitor 提取数据。
- 不要什么时候用：Agent 需要跨工具消费的表格结果优先 Python JSON/CSV。
- 常见参数：`savedata("filename", var1, var2);`
- 返回值：None。
- 示例：

```lsf
x = getdata("field", "x");
Ex = getdata("field", "Ex");
savedata("field_raw", x, Ex);
```

- 常见坑：复杂 sweep 文件名要唯一。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034411174-savedata-Script-command

## write

- 功能：写字符串到文本文件或 Linux stdout。
- 什么时候用：简单 CSV/text 导出。
- 不要什么时候用：safe mode 下不能用；大矩阵建议 Python 保存。
- 常见参数：`write("file.txt", my_string, "overwrite");`
- 返回值：None。
- 示例：

```lsf
write("metrics.csv", "sample_id,T", "overwrite");
```

- 常见坑：默认 append；需要覆盖时明确 `"overwrite"`。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034411134-write-Script-command

## struct

- 功能：创建键值结构，用于批量属性设置或 sweep 参数/结果定义。
- 什么时候用：`setnamed(..., struct)`、`addsweepparameter`、`addsweepresult`。
- 不要什么时候用：单个属性设置不必引入 struct。
- 常见参数：`s = struct; s.Name = "...";`
- 返回值：struct。
- 示例：

```lsf
para = struct;
para.Name = "radius";
para.Parameter = "::model::pillar::radius";
para.Type = "Length";
para.Start = 50e-9;
para.Stop = 150e-9;
```

- 常见坑：字段名大小写来自具体命令示例；新版本需验证。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034409574-struct-Script-command

## addsweep

- 功能：添加 sweep/optimization/Monte Carlo/S-parameter sweep。
- 什么时候用：使用 Lumerical 内置 sweep/optimization。
- 不要什么时候用：需要复杂失败恢复、数据库、外部优化器时优先 Python 外循环。
- 常见参数：`addsweep(0)` 参数扫描，`addsweep(1)` optimization，`addsweep(2)` Monte Carlo，`addsweep(3)` S-parameter sweep。
- 返回值：官方页面未说明返回数据；按 None 使用。
- 示例：

```lsf
addsweep(0);
setsweep("sweep", "name", "radius_sweep");
```

- 常见坑：创建后默认名称需立即改名，避免多个 sweep 混淆。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034930413-addsweep-Script-command

## setsweep

- 功能：设置 sweep/optimization 属性。
- 什么时候用：设置 sweep 名称、类型、点数、optimization 参数。
- 不要什么时候用：不要用于修改普通 simulation object 属性。
- 常见参数：`setsweep("name","property",value);`
- 返回值：查询形式可返回属性列表；设置形式按 None 使用。
- 示例：

```lsf
setsweep("radius_sweep", "type", "Ranges");
setsweep("radius_sweep", "number of points", 9);
```

- 常见坑：不同 sweep type 属性不同，先 `?setsweep("name")` 查询。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034930473-setsweep-Script-command

## addsweepparameter

- 功能：向 sweep/optimization 添加参数。
- 什么时候用：定义被扫描或优化的对象属性路径。
- 不要什么时候用：不要用于 Python 外循环样本表；外循环直接 `setnamed`。
- 常见参数：`addsweepparameter("sweep_name", para_struct);`
- 返回值：参数名。
- 示例：

```lsf
para = struct;
para.Name = "radius";
para.Parameter = "::model::pillar::radius";
para.Type = "Length";
para.Start = 50e-9;
para.Stop = 150e-9;
addsweepparameter("radius_sweep", para);
```

- 常见坑：`Parameter` 必须是正确对象路径和属性；路径错会导致 sweep 无效。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034930493-addsweepparameter-Script-command

## addsweepresult

- 功能：向 sweep/optimization 添加结果。
- 什么时候用：定义 sweep 完成后要收集的 monitor/analysis result。
- 不要什么时候用：Python 外循环中不需要内置 sweep result，直接读取 monitor。
- 常见参数：`addsweepresult("sweep_name", result_struct);`
- 返回值：result name。
- 示例：

```lsf
result = struct;
result.Name = "T";
result.Result = "::model::T::T";
addsweepresult("radius_sweep", result);
```

- 常见坑：result path 要与对象树一致。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034410034-addsweepresult-Script-command

## runsweep

- 功能：运行 sweep/optimization。
- 什么时候用：已配置内置 sweep/optimization 后执行。
- 不要什么时候用：未审批的真实大任务不要运行；先预览 task count 和资源。
- 常见参数：`runsweep;`，`runsweep("taskname");`，FDTD 可指定 `"CPU"`/`"GPU"`。
- 返回值：None。
- 示例：

```lsf
runsweep("radius_sweep");
```

- 常见坑：FDTD 默认 CPU；GPU/resource 行为需按版本和资源配置验证。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034931413-runsweep-Script-command

## getsweepresult

- 功能：获取 sweep/optimization/Monte Carlo/S-parameter sweep 结果。
- 什么时候用：读取 sweep result、optimization best FOM/best parameters。
- 不要什么时候用：单次 monitor 结果用 `getresult`。
- 常见参数：`getsweepresult("sweep_name","result");`
- 返回值：dataset、matrix 或 scalar，取决于 result。
- 示例：

```lsf
best_fom = getsweepresult("thickness_optimization", "best fom");
T = getsweepresult("radius_sweep", "T");
```

- 常见坑：optimization 可用结果名与 parameter sweep 不同，先 `?getsweepresult("name")`。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034409814-getsweepresult-Script-command

## havesweepresult

- 功能：检查 sweep/optimization 是否有结果。
- 什么时候用：`getsweepresult` 前。
- 不要什么时候用：不要替代单 monitor 的 `haveresult`。
- 常见参数：`havesweepresult("name","data");`
- 返回值：1 或 0。
- 示例：

```lsf
if (havesweepresult("radius_sweep", "T")) {
  T = getsweepresult("radius_sweep", "T");
}
```

- 常见坑：`havesweepdata` 与 `havesweepresult` 语义不同。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034409954-havesweepresult-Script-command

## savesweep

- 功能：把 sweep 的仿真文件保存到工作目录文件夹。
- 什么时候用：需要检查或分发每个 sweep 点的 `.fsp`。
- 不要什么时候用：不要把它当作结果数据库；仍需独立保存 metrics。
- 常见参数：`savesweep;`，`savesweep("name");`
- 返回值：None。
- 示例：

```lsf
savesweep("radius_sweep");
```

- 常见坑：输出位置依赖当前工作目录。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360034410014-savesweep-Script-command

## lumapi.FDTD

- 功能：Python 中启动/连接 FDTD session。
- 什么时候用：Agent 默认控制入口。
- 不要什么时候用：没有 license 或真实 run 未审批时不要启动真实 solve。
- 常见参数：`filename`, `hide`, `serverArgs`, `remoteArgs`。
- 返回值：FDTD session object。
- 示例：

```python
with lumapi.FDTD(filename="model.fsp", hide=True) as fdtd:
    fdtd.run()
```

- 常见坑：外部 Python 需要正确导入 lumapi；Linux remote API 需要 interop server。
- 官方来源 URL：
  - https://optics.ansys.com/hc/en-us/articles/360041873053-Session-Management-Python-API
  - https://optics.ansys.com/hc/en-us/articles/38660003331859-Lumerical-Python-API-Reference

## lumapi.eval

- 功能：Python 中执行 Lumerical Script Language 字符串。
- 什么时候用：执行 .lsf 文件或减少循环内大量 API calls。
- 不要什么时候用：不要把未审查的用户输入直接拼接执行。
- 常见参数：`fdtd.eval(code: str)`。
- 返回值：None。
- 示例：

```python
fdtd.eval("addrect; set('name','pillar');")
```

- 常见坑：字符串转义和路径转义；复杂脚本建议存为 `.lsf` 并随 run 归档。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/360043166434-lumapi-Lumerical-eval-Python-API-Method

## lumapi.getv / putv

- 功能：Python 和 Lumerical workspace 之间传变量。
- 什么时候用：需要把 Python 数组传入 LSF 或取回 LSF workspace 变量。
- 不要什么时候用：常规 monitor result 读取优先 `getresult`/`getdata`。
- 常见参数：`fdtd.putv("name", value)`, `fdtd.getv("name")`。
- 返回值：按类型转换为 Python `str/float/np.array/list/dict` 等。
- 示例：

```python
fdtd.putv("radius", 120e-9)
radius_back = fdtd.getv("radius")
```

- 常见坑：传大数据有拷贝成本；官方建议大量循环可用 `eval` 合并操作。
- 官方来源 URL：
  - https://optics.ansys.com/hc/en-us/articles/39748719848211-lumapi-Lumerical-getv-Python-API-method
  - https://optics.ansys.com/hc/en-us/articles/360041401434-Passing-Data-Python-API

## lumapi.close

- 功能：关闭 session。
- 什么时候用：非 context manager 场景或异常清理。
- 不要什么时候用：`with` 块中通常不需要手动调用。
- 常见参数：None。
- 返回值：None。
- 示例：

```python
fdtd = lumapi.FDTD(hide=True)
try:
    fdtd.run()
finally:
    fdtd.close()
```

- 常见坑：未关闭 session 会占用 GUI/API/solve 资源。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/39746549400723-lumapi-Lumerical-close-Python-API-Method

## lumslurm.run_solve / run_batch / run_sweep

- 功能：通过 Slurm 提交 FDTD solve、batch、sweep 工作流。
- 什么时候用：HPC/云集群、大规模 sweep、solve/postprocess/collect 分离。
- 不要什么时候用：非 Slurm scheduler；官方说明其他 scheduler 当前不支持 lumslurm。
- 常见参数：`fsp_file`, `partition`, `nodes`, `processes_per_node`, `threads_per_process`, `block`；sweep 额外有 `sweep_name`。
- 返回值：Slurm job ID 字符串。
- 示例：

```python
import lumslurm
lumslurm.run_sweep("model.fsp", "radius_sweep", solve_partition="auto", block=True)
```

- 常见坑：license sharing、partition、MPI 路径、Python path 需要集群配置；必须先小任务验证。
- 官方来源 URL：https://optics.ansys.com/hc/en-us/articles/20990924220691-Getting-Started-with-lumslurm-Python-API
