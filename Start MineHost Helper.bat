@echo off
setlocal
cd /d "%~dp0"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start.ps1"
if errorlevel 1 (
  echo.
  echo MineHost Helper stopped because of an error.
  pause
)
