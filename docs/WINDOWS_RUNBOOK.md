# Windows 本地运维手册

## 机器与路径

- Windows 项目路径：`F:\lumerical-fdtd-auto-design\fdtd-auto-design`
- Lumerical Python：`F:\Program Files\Lumerical\v242\python\python.exe`
- v1 RPC 端口：`127.0.0.1:5004`
- 旧 sweep 端口：`5003`，不要由 v1 脚本管理
- 日志：`logs\rpc_server.err.log`、`logs\rpc_server.out.log`
- PID：`runtime\rpc_server.pid`

## 更新代码

在 Windows 本地 CMD：

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git pull --ff-only
```

如果 GitHub 代理正常且工作树干净，也可以运行：

```cmd
scripts\windows\update_and_restart.bat
```

注意：

- 发现工作树有本地修改时，脚本会拒绝更新。
- 不要用 Mac SSH 远程编辑 Windows 文件。

## 启动、停止和状态

```cmd
scripts\windows\restart_rpc.bat
scripts\windows\status_rpc.bat
scripts\windows\stop_rpc.bat
```

实现细节：

- `.bat` 只是入口，实际逻辑在 `scripts\windows\manage_rpc.ps1`。
- 后台服务优先使用 `pythonw.exe`，避免批处理窗口关闭时终止 RPC 进程。
- 停止脚本只会停止 PID 文件记录且命令行匹配本项目的进程。

## v1 Smoke

不运行求解，只验证 GUI 会话、最小几何、保存和旧路由兼容：

```cmd
"F:\Program Files\Lumerical\v242\python\python.exe" scripts\v1_smoke_test.py
```

成功标准：

- health 返回 `api_version=v1`。
- `/session/start` 成功并打开 FDTD GUI。
- 添加 FDTD region 和 silicon rectangle 成功。
- `smoke-output\*.fsp` 生成。
- 旧 `/session/stop` 返回弃用元数据。
- 最终 health 显示 `connected=false`。

## 当前已知状态（2026-06-18）

- Windows clone 已同步并加载 close detach/timeout 修复。
- `5004` 服务健康，真实 v1 smoke 全流程通过：GUI 启动、最小几何、`.fsp` 保存、旧 `/session/stop` 兼容和 final health。
- 最新 smoke 产物：`smoke-output\rpc_v1_smoke_20260618_181844.fsp`。

## 故障排查

### `5004` 连不上

```cmd
scripts\windows\status_rpc.bat
type logs\rpc_server.err.log
```

若 PID 文件存在但进程已退出，`restart_rpc.bat` 会自动清理陈旧 PID。

### 批处理窗口关闭后服务退出

确认已同步到 `ca4cf6a` 或之后版本。管理脚本应使用 `pythonw.exe` 启动后台服务。

### `git pull` 失败并提到 `127.0.0.1:17891`

Windows Git 全局代理指向本机端口。确认代理程序正在运行，或临时绕过：

```cmd
git -c http.proxy= -c https.proxy= pull --ff-only
```

### `/session/start` 报 `getversion`

确认 Windows clone 至少为：

```cmd
git rev-parse --short HEAD
```

应为 `0cdf639` 或之后版本。然后运行 `restart_rpc.bat` 让服务进程加载新代码。

### `/session/stop` 或 `/session/close` 超时

确认已同步到包含 close detach/timeout 修复的提交。修复版会先把 RPC 状态标记为断开，再后台请求 raw lumapi 关闭；如果 `fdtd.close()` 不返回，响应仍会包含 `close_state=timed_out`，服务不会被永久占住。
