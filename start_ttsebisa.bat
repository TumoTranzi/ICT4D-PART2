@echo off
setlocal
cd /d "%~dp0"
set "PORT=5002"
set "PYTHON="

rem Prefer the installed Python 3.13 when it already has Flask. This avoids
rem stale virtual environments that point to a removed Microsoft Store Python.
set "GLOBAL_PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if exist "%GLOBAL_PY%" (
  "%GLOBAL_PY%" -c "import flask" >nul 2>nul
  if not errorlevel 1 set "PYTHON=%GLOBAL_PY%"
)

rem Otherwise use the project's virtual environment if its interpreter works.
if not defined PYTHON if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import flask" >nul 2>nul
  if not errorlevel 1 set "PYTHON=%CD%\.venv\Scripts\python.exe"
)

rem As a last attempt, repair dependencies in a working existing virtual env.
if not defined PYTHON if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>nul
  if not errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if not errorlevel 1 set "PYTHON=%CD%\.venv\Scripts\python.exe"
  )
)

if not defined PYTHON (
  echo Could not find a Python environment with Flask.
  echo Install Python 3.13 with Flask, or recreate this project's .venv and install requirements.txt.
  pause
  exit /b 1
)

echo Starting TTsebisa with:
echo %PYTHON%
"%PYTHON%" app.py
pause
