# RPC API v1 速查

## 状态

- 代码状态：本提交包含 raw lumapi `close()` detach/timeout 修复，待同步 Windows clone。
- 离线验证：Mac 上 `65 passed`，不依赖 Lumerical。
- Windows 状态：`127.0.0.1:5004` 已用 `0cdf639` 完成 GUI 启动、建模和保存 `.fsp`；旧 `/session/stop` 在 raw lumapi `close()` 处超时，需同步本提交后复测完整 smoke。
- 过渡期：旧 `5003` Autosweep 服务与新 `5004` v1 服务并行；本文件只描述 `5004` v1。

## Envelope

成功：

```json
{"ok": true}
```

失败：

```json
{
  "ok": false,
  "error": {
    "type": "validation_error",
    "message": "cmd is required.",
    "details": {}
  }
}
```

约定：

- 参数错误：HTTP 400。
- 无会话或重复启动：HTTP 409。
- 文件不存在：HTTP 404。
- 未处理后端异常：HTTP 500。
- Client 超时返回 `error.type=timeout`，`details.remote_state=unknown`。
- `/session/close` 成功响应可带 `close_state`：`closed`、`timed_out` 或 `error`。

## 已实现路由

| 方法 | 路由 | 说明 |
|---|---|---|
| GET | `/health` | RPC 进程健康、API 版本和会话摘要 |
| GET | `/status` | 当前 FDTD 会话、版本和模型路径 |
| POST | `/session/start` | 启动唯一 FDTD 会话，body: `{"hide": false}` |
| POST | `/session/close` | 摘除 RPC 会话并请求 FDTD 关闭；raw lumapi 关闭不返回时返回 `close_state=timed_out` 以保持服务可用 |
| POST | `/model/save` | 保存当前 `.fsp`，body: `{"file_path": "..."}` |
| POST | `/model/load` | 加载 `.fsp` |
| POST | `/debug/eval` | 受审计的 raw lumapi 调试入口 |
| POST | `/debug/getv` | 读取变量 |
| POST | `/debug/setv` | 写入变量 |
| POST | `/simulation/run` | 同步运行当前模型，仅用于短 smoke |
| POST | `/simulation/result` | 读取 monitor result |
| POST | `/simulation/electric` | 读取电场 |
| POST | `/geometry/fdtd-region` | 添加 FDTD 区域 |
| POST | `/geometry/rectangle` | 添加矩形 |
| POST | `/geometry/circle` | 添加圆形 |

## 兼容旧路由

这些别名只保留在 Server 端，新 Client/MCP 不调用：

| 旧路由 | v1 路由 |
|---|---|
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

兼容响应会带：

```json
{
  "meta": {
    "deprecated_route": "/session/stop",
    "use_instead": "/session/close"
  }
}
```

## 已知限制

- `/debug/eval` 仅用于诊断，不是自然语言建模入口。
- 文件路径越界限制将在持久 job 层实现；当前 v1 服务仅在受控本地/隧道环境使用。
- `/jobs/*`、审批、恢复和质量报告尚未实现。
- 旧 sweep API `/sweep/*`、`/results/*` 属于已部署 Autosweep 扩展；仓库通用 v1 Server 当前不承载完整 sweep 引擎。
