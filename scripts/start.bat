@echo off
setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1

echo.
echo  RedditPilot - local editorial workspace
echo  ---------------------------------------

if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python virtual environment...
  py -3 -m venv .venv >nul 2>nul
  if errorlevel 1 python -m venv .venv
  if errorlevel 1 goto :error
  echo Installing Python dependencies...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)

if not exist ".env" (
  if exist ".env.example" copy ".env.example" ".env" >nul
)

if not exist "frontend\dist\index.html" (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo Node.js and npm are required to build the dashboard.
    echo Install Node.js 20 or newer, then run this script again.
    goto :error
  )
  echo Building the dashboard...
  pushd frontend
  call npm install
  if errorlevel 1 (
    popd
    goto :error
  )
  call npm run build
  if errorlevel 1 (
    popd
    goto :error
  )
  popd
)

echo Preparing the database...
".venv\Scripts\python.exe" scripts\init_db.py
if errorlevel 1 goto :error

set HOST=127.0.0.1
set PORT=8000
if not "%RP_HOST%"=="" set HOST=%RP_HOST%
if not "%RP_PORT%"=="" set PORT=%RP_PORT%

echo.
echo Opening http://%HOST%:%PORT%
echo Press Ctrl+C to stop the server.
echo.
start "" "http://%HOST%:%PORT%"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host %HOST% --port %PORT%
goto :eof

:error
echo.
echo Startup failed. See the messages above.
pause
exit /b 1
