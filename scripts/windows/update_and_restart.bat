@echo off
setlocal

cd /d "%~dp0\..\.."

where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] git is not available in PATH.
  exit /b 1
)

for /f "delims=" %%I in ('git status --porcelain') do (
  echo [ERROR] Working tree is not clean. Commit or discard local changes first.
  git status --short
  exit /b 1
)

echo Pulling origin/main...
git pull --ff-only
if errorlevel 1 exit /b 1

call "%~dp0restart_rpc.bat"
exit /b %errorlevel%
