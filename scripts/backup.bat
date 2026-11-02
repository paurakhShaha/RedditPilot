@echo off
setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
  echo The virtual environment is missing. Run scripts\start.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" scripts\backup_db.py %*
echo.
pause
