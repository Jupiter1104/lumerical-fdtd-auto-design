@echo off
setlocal

cd /d "%~dp0\..\.."
set "PROJECT_ROOT=%CD%"
if not defined FDTD_RPC_PORT set "FDTD_RPC_PORT=5004"
set "PID_FILE=%PROJECT_ROOT%\runtime\rpc_server.pid"

if exist "%PID_FILE%" (
  set /p RPC_PID=<"%PID_FILE%"
  echo Recorded PID: %RPC_PID%
) else (
  echo Recorded PID: none
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$uri = 'http://127.0.0.1:' + $env:FDTD_RPC_PORT + '/health'; try { $r = Invoke-RestMethod -Uri $uri -TimeoutSec 3; $r | ConvertTo-Json -Compress; if (-not $r.ok) { exit 1 } } catch { Write-Error $_; exit 1 }"
exit /b %errorlevel%
