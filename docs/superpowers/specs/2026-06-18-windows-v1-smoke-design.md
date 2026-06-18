# Windows RPC v1 本地部署与 Smoke 设计

## 目标

在不影响旧 Autosweep 服务的前提下，从新克隆目录启动仓库内 RPC API v1，并验证 Windows Python、lumapi、FDTD GUI、HTTP 路由和旧路由兼容层能够贯通。

Windows 项目路径：

```text
F:\lumerical-fdtd-auto-design\fdtd-auto-design
```

## 隔离策略

- 新 v1 服务仅监听 `127.0.0.1:5004`。
- 不停止、不覆盖、不探测性杀死旧端口 `5003` 的进程。
- 服务 PID、日志和 smoke 产物都写在新项目目录下。
- 停止脚本只能终止 PID 文件中记录的进程；PID 不存在或不匹配时失败并提示人工检查。

## Windows 脚本

新增：

```text
scripts/windows/start_rpc.bat
scripts/windows/stop_rpc.bat
scripts/windows/restart_rpc.bat
scripts/windows/status_rpc.bat
scripts/windows/update_and_restart.bat
scripts/windows/manage_rpc.ps1
```

共同约定：

- 默认 Python：`F:\Program Files\Lumerical\v242\python\python.exe`。
- 默认端口：`5004`。
- 可通过环境变量 `FDTD_PYTHON` 和 `FDTD_RPC_PORT` 覆盖。
- PID：`runtime\rpc_server.pid`。
- 日志：`logs\rpc_server.log`。
- 启动前检查 Python、项目文件和端口。
- 启动后轮询 `/health`；健康检查失败则返回非零退出码并显示日志路径。

`.bat` 文件只作为双击入口，进程管理集中在 `manage_rpc.ps1`。PowerShell 使用 `Start-Process -PassThru` 启动后台进程并记录 PID，避免 CMD 与 PowerShell 混合转义及 SSH 非交互环境中 `start /MIN` 的已知问题。脚本只面向 Windows 本地交互执行。

`update_and_restart.bat` 仅在工作树干净时执行 `git pull --ff-only`，随后调用 restart；发现本地修改时拒绝更新，避免覆盖 Windows 现场文件。

## Smoke Test

新增 `scripts/v1_smoke_test.py`，默认连接 `http://127.0.0.1:5004`。

步骤：

1. `/health` 返回 `api_version=v1`。
2. `/session/start` 以 `hide=false` 打开 GUI。
3. `/status` 返回已连接和 Lumerical 版本。
4. `/geometry/fdtd-region` 添加一个小型 3D 区域。
5. `/geometry/rectangle` 添加一个硅矩形。
6. `/model/save` 保存到项目 `smoke-output/` 下的时间戳 `.fsp`。
7. 调用旧 `/session/stop`，确认成功且包含 `meta.deprecated_route`。
8. 再次检查 `/health`，确认会话已关闭。

测试不调用 `/simulation/run`，因此不会执行真实求解。失败时仍尝试关闭会话，避免占用许可证。

## 验证标准

Mac 离线：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
```

Windows 真实环境：

```bat
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git pull --ff-only
scripts\windows\restart_rpc.bat
"F:\Program Files\Lumerical\v242\python\python.exe" scripts\v1_smoke_test.py
```

成功标准：

- restart 脚本健康检查通过。
- FDTD GUI 出现在 Windows 桌面。
- smoke 每一步通过并生成 `.fsp`。
- 旧 `/session/stop` 返回弃用元数据。
- 测试结束后许可证会话关闭。

## 非目标

- 不修改或迁移旧 Autosweep 服务。
- 不运行 sweep、求解、MATLAB 后处理或物理质量检查。
- 不实现 Windows 服务、自启动、管理员安装或公网监听。
- 不开始持久 job/task；该部分在真实 smoke 通过后单独设计。
