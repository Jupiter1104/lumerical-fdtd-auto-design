@echo off
setlocal
cd /d "%~dp0\..\.."

if "%FDTD_PYTHON%"=="" (
  set "FDTD_PYTHON=F:\Program Files\Lumerical\v242\python\python.exe"
)

"%FDTD_PYTHON%" scripts\build_production_sweep_packet.py %*
exit /b %ERRORLEVEL%
