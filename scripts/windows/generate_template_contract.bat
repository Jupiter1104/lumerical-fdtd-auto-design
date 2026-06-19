@echo off
setlocal
cd /d "%~dp0\..\.."

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

"%PYTHON%" scripts\generate_template_contract.py ^
  --profile templates\metasurface\template-inspection-profile.json ^
  --probe templates\metasurface\base_model.probe.json ^
  --output templates\metasurface\base_model.contract.json
exit /b %ERRORLEVEL%
