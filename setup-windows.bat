@echo off
:: AI Framework - Workspace Setup (Windows Launcher)
::
:: Double-click this file to initialize a new project workspace.
:: Downloads and executes the bootstrap script with interactive prompts.
::
:: If WSL is detected (technical roles), the user is directed to run
:: the setup from their Linux terminal instead. Otherwise, it runs
:: natively on Windows Python.
::
:: Prerequisite: Python 3.11+ in PATH (Windows or WSL).
::

echo.
echo   AI Framework - Workspace Setup
echo   ================================
echo.

:: Check if WSL is available with a working distro.
wsl -- echo ok >nul 2>&1
if %errorlevel% equ 0 goto :wsl_path
goto :windows_path

:: -----------------------------------------------------------------
:wsl_path
:: -----------------------------------------------------------------
echo   WSL detected. This setup must run from your Linux terminal.
echo.
echo   Open Ubuntu from the Start menu and paste the setup command.
echo.
set /p COPY_CHOICE="  Copy command to clipboard? [Y/n]: "
if /i "%COPY_CHOICE%"=="n" goto :wsl_show
>"%TEMP%\nubity-cmd.txt" echo curl -sfo /tmp/bootstrap.py https://raw.githubusercontent.com/nubity/ai-frwk-setup/main/bootstrap.py ^&^& python3 /tmp/bootstrap.py
clip < "%TEMP%\nubity-cmd.txt"
del "%TEMP%\nubity-cmd.txt" >nul 2>&1
echo.
echo   [OK] Copied to clipboard. Paste it in Ubuntu with Ctrl+V.
echo.
goto :done

:wsl_show
echo.
echo   Run this in your Linux terminal:
echo.
echo     curl -sfo /tmp/bootstrap.py https://raw.githubusercontent.com/nubity/ai-frwk-setup/main/bootstrap.py ^&^& python3 /tmp/bootstrap.py
echo.
goto :done

:: -----------------------------------------------------------------
:windows_path
:: -----------------------------------------------------------------
:: Verify python is available.
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [!!] Python not found in PATH.
    echo   [!!] Install Python 3.11+ and ensure it is added to PATH.
    goto :done
)

:: Write a small download helper to a temp file (avoids CMD quoting issues).
echo   Downloading bootstrap script...
(
echo import sys, os
echo import urllib.request
echo url = 'https://raw.githubusercontent.com/nubity/ai-frwk-setup/main/bootstrap.py'
echo dest = os.path.join(os.environ['TEMP'], 'nubity-bootstrap.py'^)
echo try:
echo     urllib.request.urlretrieve(url, dest^)
echo except Exception as e:
echo     print(f'  [!!] {e}'^)
echo     sys.exit(1^)
) > "%TEMP%\nubity-download.py"

python "%TEMP%\nubity-download.py"
if %errorlevel% neq 0 (
    echo   [!!] Check your internet connection and try again.
    del "%TEMP%\nubity-download.py" >nul 2>&1
    goto :done
)

del "%TEMP%\nubity-download.py" >nul 2>&1
echo   [OK] Downloaded.
echo.

:: Run the bootstrap in interactive mode (no arguments = prompts).
python "%TEMP%\nubity-bootstrap.py" %*
set BOOTSTRAP_EXIT=%errorlevel%

:: Cleanup temp file.
del "%TEMP%\nubity-bootstrap.py" >nul 2>&1

:: On success, the bootstrap script already showed a countdown. Exit cleanly.
if %BOOTSTRAP_EXIT% equ 0 goto :eof
goto :done

:: -----------------------------------------------------------------
:done
:: -----------------------------------------------------------------
echo.
pause
