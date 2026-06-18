# RPC API v1 契约与离线测试设计

## 1. 目标

本轮只解决 Windows RPC Server、Mac `RpcClient` 与 MCP 包装之间的契约漂移，并建立不依赖 Windows、Lumerical 或许可证的自动化测试。

完成后应满足：

- Server、Client 和 MCP 使用同一套路由、成功标记和错误结构。
- Mac 上可以通过 fake backend 和 fake HTTP server 验证契约。
- 现有旧路由在迁移期仍可调用，但新代码不再依赖它们。
- 不实现持久 job/task、`SimulationPlan`、真实运行审批或质量报告。
- 不运行真实 FDTD。

## 2. 方案选择

采用“单一 v1 契约 + 服务端临时兼容别名”。

不选择直接删除旧路由，因为 Windows 当前部署版本仍可能被旧脚本调用；也不选择长期维护两套 API，因为这会继续放大 Server、Client 和 MCP 的漂移。

兼容层只转发到 v1 的同一处理函数，不复制业务逻辑。`RpcClient`、MCP 工具和新测试只能使用 v1 路由。

## 3. 响应与 HTTP 语义

成功响应：

```json
{
  "ok": true,
  "version": "2024 R2"
}
```

失败响应：

```json
{
  "ok": false,
  "error": {
    "type": "validation_error",
    "message": "file_path is required.",
    "details": {}
  }
}
```

约束：

- 成功只使用 `ok: true`，不再产生 `success: true`。
- 错误对象固定包含 `type` 和 `message`；`details` 默认为空对象。
- 参数错误返回 HTTP 400。
- 无活动 FDTD 会话返回 HTTP 409。
- 文件不存在返回 HTTP 404。
- 未处理的后端异常返回 HTTP 500。
- HTTP 客户端超时只表示请求结果未知，不得描述为远端仿真失败。
- 兼容旧路由时，响应增加 `meta.deprecated_route` 和 `meta.use_instead`。

## 4. v1 路由

### 基础与会话

| 方法 | 路由 | 用途 |
| --- | --- | --- |
| GET | `/health` | RPC 进程健康和会话摘要 |
| GET | `/status` | 当前 FDTD 会话与模型状态 |
| POST | `/session/start` | 启动唯一 FDTD 会话 |
| POST | `/session/close` | 关闭会话并释放许可证 |

重复调用 `/session/start` 不静默关闭已有会话，而是返回 HTTP 409，避免误杀正在运行的工作。

### 模型与调试

| 方法 | 路由 | 用途 |
| --- | --- | --- |
| POST | `/model/save` | 保存当前 `.fsp` |
| POST | `/model/load` | 加载 `.fsp` |
| POST | `/debug/eval` | 受审计的原始 lumapi 调试入口 |
| POST | `/debug/getv` | 读取变量 |
| POST | `/debug/setv` | 写入变量 |

`/debug/eval` 不是默认自然语言建模入口。本轮保留它用于联调和补齐 typed API 前的诊断。

### 仿真与几何

| 方法 | 路由 | 用途 |
| --- | --- | --- |
| POST | `/simulation/run` | 当前模型同步运行；仅用于短 smoke |
| POST | `/simulation/result` | 获取监视器结果 |
| POST | `/simulation/electric` | 获取电场结果 |
| POST | `/geometry/fdtd-region` | 添加 FDTD 区域 |
| POST | `/geometry/rectangle` | 添加矩形结构 |
| POST | `/geometry/circle` | 添加圆形结构 |

`/simulation/run` 暂时保持同步，但文档明确限制为短 smoke；长任务将在下一阶段迁移到持久 job/task。

### 已部署 sweep 扩展

以下现有端点继续保留，并改用同一响应和错误结构：

- `GET/POST /sweep/config`
- `POST /sweep/run`
- `GET /sweep/status`
- `GET /results`
- `GET /results/<path>`

本轮不重写 sweep 引擎。若仓库内通用 Server 没有对应实现，Client 契约测试使用 fake HTTP server 验证这些调用，真实 Windows 部署验证留在本地重启步骤。

## 5. 旧路由兼容表

| 旧路由 | v1 路由 |
| --- | --- |
| `/session/stop` | `/session/close` |
| `/file/save` | `/model/save` |
| `/file/load` | `/model/load` |
| `/eval` | `/debug/eval` |
| `/getv` | `/debug/getv` |
| `/setv` | `/debug/setv` |
| `/sim/run` | `/simulation/run` |
| `/sim/getresult` | `/simulation/result` |
| `/sim/getelectric` | `/simulation/electric` |
| `/geom/addfdtd` | `/geometry/fdtd-region` |
| `/geom/addrect` | `/geometry/rectangle` |
| `/geom/addcircle` | `/geometry/circle` |

兼容别名只存在于 Server。Client 与 MCP 中不提供对应旧方法。

## 6. 代码边界

### `rpc_server.py`

- 将 Lumerical 导入延迟到真正启动会话时，避免 Mac 测试环境导入模块即失败。
- 提供可注入 `SessionManager` 的 `create_app()`。
- 使用统一的成功、错误和兼容响应辅助函数。
- v1 和旧别名调用相同处理逻辑。
- 保留现有单例会话和 Flask 部署方式，不做无关框架迁移。

### `src/rpc_client/client.py`

- 低层 HTTP 方法统一解析 v1 envelope。
- 区分连接失败、超时、非 JSON 响应和 HTTP 错误。
- 增加 model、debug、simulation、geometry 方法。
- 保留现有 sweep/results 方法，但让它们遵守 v1 错误结构。
- 下载方法继续返回本地保存路径，路径写入失败也使用统一错误结构。

### MCP 工具

- session 工具改用 v1 Client。
- model、geometry、export 模块在契约测试通过后注册。
- 现有 sweep/results 工具保留。
- 删除或修正读取 `success` 字段的代码。
- 不新增阻塞式长任务行为；已有 monitor 工具只做兼容保留，本轮不作为推荐入口。

## 7. 离线测试

使用 `pytest`，分两层：

### Server 契约测试

通过 Flask `test_client()` 和 fake `SessionManager` 验证：

- v1 成功响应。
- 必填参数缺失。
- 无活动会话。
- 文件不存在。
- 后端异常。
- 重复启动会话。
- 每个旧路由与目标 v1 路由行为一致，并包含弃用元数据。
- 测试期间不导入或启动 Lumerical。

### Client 契约测试

启动本机临时 fake HTTP server，验证：

- 每个 Client 方法使用正确 HTTP 方法、路由和 JSON body。
- 成功响应按原样返回。
- HTTP 400/409/500 的结构化错误得到保留。
- 连接失败返回 `connection_error`。
- 超时返回 `timeout`，并明确远端状态未知。
- 非 JSON 响应返回 `invalid_response`。
- 结果文件可下载，404 和本地写入错误可识别。

MCP 本轮只做注册/import smoke，核心契约放在 Server 和 Client，避免重复测试薄包装。

## 8. 验证标准

交付前运行：

```bash
python3 -m compileall -q rpc_server.py src scripts tests
python3 -m pytest -q
```

在 Mac 上两条命令必须通过，且不得需要 `lumapi`、Windows、FDTD GUI 或许可证。

真实 Windows 验证不属于本轮自动化测试，但实现完成后应给出最小清单：

1. Windows 本地 `.bat` 重启 RPC Server。
2. 调用 `/health`、`/session/start`、一个 geometry 端点和 `/session/close`。
3. 确认旧 `/session/stop` 仍可用并返回弃用元数据。

## 9. 非目标

- 不增加 `/v1` URL 前缀；版本先由契约和服务元数据表达，避免当前部署迁移成本。
- 不实现认证、公网暴露或多用户并发。
- 不实现长任务队列、持久 job/task、幂等键和 resume。
- 不改变 FDTD 物理设置、sweep 算法或 MATLAB 后处理。
- 不引入 CLI-Anything 或新的命令行产品层。
