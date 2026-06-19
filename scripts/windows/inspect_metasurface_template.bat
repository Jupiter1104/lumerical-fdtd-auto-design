@echo off
setlocal
cd /d "%~dp0\..\.."

set "FDTD_PYTHON=F:\Program Files\Lumerical\v242\python\python.exe"
set "TEMPLATE=templates\metasurface\base_model.fsp"
set "PROFILE=templates\metasurface\template-inventory-profile.json"
set "OUTPUT=templates\metasurface\base_model.inventory.json"

if not exist "%FDTD_PYTHON%" (
  echo [ERROR] Lumerical Python not found: %FDTD_PYTHON%
  pause
  exit /b 1
)

"%FDTD_PYTHON%" scripts\inspect_metasurface_template.py --inventory ^
  --template "%TEMPLATE%" ^
  --profile "%PROFILE%" ^
  --output "%OUTPUT%"

set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
