@echo off
setlocal

call "%~dp0stop_rpc.bat"
if errorlevel 1 exit /b 1

call "%~dp0start_rpc.bat"
exit /b %errorlevel%
