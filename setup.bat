@echo off
:: AI Framework - Workspace Setup (Windows Launcher)
::
:: Double-click this file to initialize a new project workspace.
:: Downloads and executes the bootstrap script with interactive prompts.
::
:: Prerequisite: Python 3.11+ in PATH.
::

echo.
echo   AI Framework - Workspace Setup
echo   ================================
echo.

:: Verify python is available.
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [!!] Python not found in PATH.
    echo   [!!] Install Python 3.11+ and ensure it is added to PATH.
    echo.
    pause
    exit /b 1
)

:: Download bootstrap.py using Python's stdlib (no curl dependency).
:: stderr is suppressed to avoid raw Python tracebacks on network errors.
echo   Downloading bootstrap script...
python -c "import urllib.request,sys;urllib.request.urlretrieve('https://raw.githubusercontent.com/nubity/ai-frwk-setup/main/bootstrap.py',sys.argv[1])" "%TEMP%\nubity-bootstrap.py" 2>nul
if %errorlevel% neq 0 (
    echo   [!!] Failed to download the bootstrap script.
    echo   [!!] Check your internet connection and try again.
    echo.
    pause
    exit /b 1
)

echo   [OK] Downloaded.
echo.

:: Run the bootstrap in interactive mode (no arguments = prompts).
python "%TEMP%\nubity-bootstrap.py" %*

:: Cleanup temp file.
del "%TEMP%\nubity-bootstrap.py" >nul 2>&1

echo.
pause
