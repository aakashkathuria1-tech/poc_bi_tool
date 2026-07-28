@echo off
REM Setup for poc_bi_tool on Windows - cmd.exe fallback.
REM
REM Use this when PowerShell script execution is blocked by policy and you
REM cannot change it. Otherwise prefer scripts\setup.ps1, which gives better
REM diagnostics.
REM
REM Usage:  scripts\setup.bat

setlocal enabledelayedexpansion

set "REPO_ROOT=%~dp0.."
set "VENV_DIR=%REPO_ROOT%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

echo poc_bi_tool - Windows setup
echo repo: %REPO_ROOT%
echo.

REM --- 1. Find Python ---------------------------------------------------------
echo ==^> Locating Python
set "PY_CMD="
where py >nul 2>&1 && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>&1 && set "PY_CMD=python"
)
if not defined PY_CMD (
    echo.
    echo ERROR: No Python found on PATH.
    echo   winget install Python.Python.3.12
    echo   ...or https://www.python.org/downloads/windows/
    echo Tick "Add python.exe to PATH", then open a NEW terminal.
    exit /b 1
)

%PY_CMD% --version
if errorlevel 1 (
    echo ERROR: Python failed to run. If the Microsoft Store opened, turn off
    echo the Python App execution aliases in Windows Settings.
    exit /b 1
)

REM --- 2. Create the venv -----------------------------------------------------
echo.
echo ==^> Preparing virtual environment
if exist "%VENV_PYTHON%" (
    echo     Reusing existing .venv
) else (
    %PY_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: venv creation failed.
        exit /b 1
    )
    echo     Created %VENV_DIR%
)

REM --- 3. Install dependencies ------------------------------------------------
echo.
echo ==^> Installing dependencies
"%VENV_PYTHON%" -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo ERROR: pip upgrade failed.
    exit /b 1
)
"%VENV_PYTHON%" -m pip install -r "%REPO_ROOT%\requirements.txt"
if errorlevel 1 (
    echo ERROR: dependency install failed.
    exit /b 1
)

REM --- 4. Verify --------------------------------------------------------------
echo.
echo ==^> Running tests
"%VENV_PYTHON%" -m pytest
if errorlevel 1 (
    echo ERROR: tests failed.
    exit /b 1
)

echo.
echo ==^> Running data health check
"%VENV_PYTHON%" "%REPO_ROOT%\scripts\verify_data.py"
if errorlevel 1 (
    echo ERROR: data health check reported errors.
    exit /b 1
)

echo.
echo Setup complete. Launch the dashboard with:
echo     .venv\Scripts\streamlit.exe run app.py
echo.
echo Or activate the environment first:
echo     .venv\Scripts\activate.bat
exit /b 0
