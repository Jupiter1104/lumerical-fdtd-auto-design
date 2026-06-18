@echo off
setlocal

cd /d "%~dp0\..\.."
set "PROJECT_ROOT=%CD%"

if not defined FDTD_PYTHON set "FDTD_PYTHON=F:\Program Files\Lumerical\v242\python\python.exe"
if not defined FDTD_RPC_PORT set "FDTD_RPC_PORT=5004"

set "RUNTIME_DIR=%PROJECT_ROOT%\runtime"
set "LOG_DIR=%PROJECT_ROOT%\logs"
set "PID_FILE=%RUNTIME_DIR%\rpc_server.pid"
set "STDOUT_LOG=%LOG_DIR%\rpc_server.out.log"
set "STDERR_LOG=%LOG_DIR%\rpc_server.err.log"

if not exist "%FDTD_PYTHON%" (
  echo [ERROR] Python not found: %FDTD_PYTHON%
  exit /b 1
)

if not exist "%PROJECT_ROOT%\rpc_server.py" (
  echo [ERROR] rpc_server.py not found under %PROJECT_ROOT%
  exit /b 1
)

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if exist "%PID_FILE%" (
  echo [ERROR] PID file already exists: %PID_FILE%
  echo Run scripts\windows\status_rpc.bat or stop_rpc.bat first.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$listener = Get-NetTCPConnection -State Listen -LocalPort $env:FDTD_RPC_PORT -ErrorAction SilentlyContinue; if ($listener) { Write-Error ('Port ' + $env:FDTD_RPC_PORT + ' is already in use.'); exit 1 }"
if errorlevel 1 exit /b 1

echo Starting FDTD RPC v1 on 127.0.0.1:%FDTD_RPC_PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$server = Join-Path $env:PROJECT_ROOT 'rpc_server.py'; $arguments = @($server, '--host', '127.0.0.1', '--port', $env:FDTD_RPC_PORT); $p = Start-Process -FilePath $env:FDTD_PYTHON -ArgumentList $arguments -WorkingDirectory $env:PROJECT_ROOT -RedirectStandardOutput $env:STDOUT_LOG -RedirectStandardError $env:STDERR_LOG -PassThru; Set-Content -LiteralPath $env:PID_FILE -Value $p.Id -NoNewline"
if errorlevel 1 (
  echo [ERROR] Failed to start RPC Server.
  exit /b 1
)

echo Waiting for /health...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$uri = 'http://127.0.0.1:' + $env:FDTD_RPC_PORT + '/health'; for ($i = 0; $i -lt 30; $i++) { try { $r = Invoke-RestMethod -Uri $uri -TimeoutSec 2; if ($r.ok -and $r.api_version -eq 'v1') { Write-Host ('[OK] ' + $uri); exit 0 } } catch {}; Start-Sleep -Seconds 1 }; Write-Error ('Health check failed. See ' + $env:STDERR_LOG); exit 1"
if errorlevel 1 (
  call "%~dp0stop_rpc.bat" >nul 2>&1
  exit /b 1
)

echo PID file: %PID_FILE%
echo stdout:  %STDOUT_LOG%
echo stderr:  %STDERR_LOG%
exit /b 0
