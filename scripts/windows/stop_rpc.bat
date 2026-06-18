@echo off
setlocal

cd /d "%~dp0\..\.."
set "PROJECT_ROOT=%CD%"
set "PID_FILE=%PROJECT_ROOT%\runtime\rpc_server.pid"

if not exist "%PID_FILE%" (
  echo [INFO] RPC Server PID file does not exist.
  exit /b 0
)

set /p RPC_PID=<"%PID_FILE%"
if not defined RPC_PID (
  echo [ERROR] PID file is empty: %PID_FILE%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $env:RPC_PID) -ErrorAction SilentlyContinue; if (-not $p) { Write-Host '[INFO] Recorded process is no longer running.'; exit 0 }; if ($p.CommandLine -notlike '*rpc_server.py*' -or $p.CommandLine -notlike ('*' + $env:PROJECT_ROOT + '*')) { Write-Error ('Refusing to stop PID ' + $env:RPC_PID + ': command line does not match this project.'); exit 1 }; Stop-Process -Id ([int]$env:RPC_PID) -Force; Write-Host ('[OK] Stopped RPC Server PID ' + $env:RPC_PID)"
if errorlevel 1 exit /b 1

del /q "%PID_FILE%" >nul 2>&1
exit /b 0
