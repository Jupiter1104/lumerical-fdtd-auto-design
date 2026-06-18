@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0manage_rpc.ps1" -Action Status
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
