# 项目 SOP

这个文件用于记录项目内可重复执行的流程。

## SOP-001 - Windows 端环境搭建

1. 确认 Lumerical v242 已安装并在 license 有效期内。
2. Python 使用 Lumerical 自带的：`F:\Program Files\Lumerical\v242\python\python.exe`。
3. 安装依赖：
   ```cmd
   F:\Program Files\Lumerical\v242\python\python.exe -m pip install flask numpy scipy
   ```
4. 验证：
   ```cmd
   F:\Program Files\Lumerical\v242\python\python.exe -c "import lumapi; import matlab.engine; import numpy; import scipy; print('OK')"
   ```

## SOP-002 - Windows 端启动 RPC Server

1. 启动（默认端口 5003）：
   ```cmd
   F:\Program Files\Lumerical\v242\python\python.exe rpc_server.py --port 5003
   ```
2. 健康检查：
   ```cmd
   curl http://localhost:5003/health
   ```
3. 启动 headless 会话（生产）：
   ```cmd
   curl -X POST http://localhost:5003/session/start -H "Content-Type: application/json" -d "{\"hide\":true}"
   ```
4. 启动 GUI 会话（调试，需 RDP 连接）：
   ```cmd
   curl -X POST http://localhost:5003/session/start
   ```

## SOP-003 - Mac 端环境搭建

1. 确保 Python 3.10+ 可用。
2. 安装依赖：
   ```bash
   pip install requests
   ```
3. 建立 SSH 隧道（推荐）或直连：
   ```bash
   ssh -L 5003:localhost:5003 32482@192.168.31.26
   # 或直连: export FDTD_RPC_URL=http://192.168.31.26:5003
   ```
4. 验证连接：
   ```bash
   curl http://localhost:5003/health
   ```

## SOP-004 - 端到端验证

1. 确保 Windows RPC Server 正在运行。
2. Session 已启动（`fdtd_connected=true`）。
3. Mac 端运行 smoke test：
   ```bash
   python scripts/smoke_test.py --rpc http://localhost:5003
   ```
4. 预期：4/4 valid, 0 missing。

## SOP-005 - 扫参前检查清单

1. `base_model.fsp` 模板完好，含 `::model::s_params` 分析组。
2. 模板参数 `ratio`、`height`、`period` 已定义。
3. RPC Server `_run_pipeline` 内：
   - `fdtd.clearjobs()` 在 Phase 1 循环前
   - `fdtd.setnamed("FDTD", "express mode", 1)` 在每次 `load()` 后 `save()` 前
4. 端口未被幽灵进程占用（`netstat -ano | findstr 5003`）。

## SOP-006 - 交付

1. 确保新增脚本可通过 `python scripts/xxx.py --help` 打印使用说明。
2. 更新 `DEV_LOG.md`。
3. 如果发现踩坑或可复用经验，写入对应文档。
