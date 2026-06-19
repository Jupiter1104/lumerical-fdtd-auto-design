@echo off
setlocal
cd /d "%~dp0\..\.."

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

"%PYTHON%" scripts\build_real_run_preflight_packet.py ^
  --contract templates\metasurface\base_model.contract.json ^
  --output runtime\approvals\real_2x2_preflight.json
exit /b %ERRORLEVEL%
