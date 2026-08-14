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
:: Commercial roles (double-click from an OneDrive-synced project directory
:: whose name carries the 19-digit CRM ID) skip the WSL probe entirely -
:: they never use WSL and the probe otherwise incurs a slow WSL2 VM
:: cold-start before any CRM ID work begins.
::
:: Prerequisite: Python 3.11+ in PATH (Windows or WSL).
::

:: Ensure CWD is the directory where this script lives.
cd /d "%~dp0"

echo.
echo   AI Framework - Workspace Setup
echo   ================================
echo.

:: Verify python is available (needed for CRM detection, download, and the
:: bootstrap itself). Check it once here so both paths can rely on it.
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [!!] Python not found in PATH.
    echo   [!!] Install Python 3.11+ and ensure it is added to PATH.
    goto :done
)

:: Commercial mode: this launcher lives inside an OneDrive-synced project
:: directory whose name carries the 19-digit CRM ID. Commercial roles
:: (Account Manager, Pre-sales, PO) do NOT use WSL, so skip the WSL probe
:: entirely for them - it triggers a slow WSL2 VM cold-start (several
:: seconds, sometimes a hang when a distro is installing or absent) with
:: no benefit. Detection reuses bootstrap.py's exact rule (a token of
:: EXACTLY 19 digits bounded by word boundaries) so the two agree.
call :detect_crm_id
if defined CRM_IN_DIR goto :windows_path

:: Delivery mode: probe for a working WSL distro (technical roles run the
:: setup from Linux). The probe can be slow on first invocation, so show a
:: line of feedback instead of a silent pause.
echo   Checking environment...
wsl -- echo ok >nul 2>&1
if %errorlevel% equ 0 goto :wsl_path
goto :windows_path

:: -----------------------------------------------------------------
:detect_crm_id
:: Sets CRM_IN_DIR when the current directory name contains a token of
:: exactly 19 digits, matching bootstrap.py's CRM_ID_PATTERN = \b(\d{19})\b.
:: findstr cannot express word boundaries or an exact-count quantifier, so
:: the check is delegated to a one-line Python invocation using the same
:: regex. os.path.basename(os.getcwd()) is the folder name the launcher was
:: double-clicked from (CWD was set to the script's own directory above).
:: -----------------------------------------------------------------
set "CRM_IN_DIR="
for /f %%R in ('python -c "import os,re,sys; sys.stdout.write('1' if re.search(r'\b\d{19}\b', os.path.basename(os.getcwd())) else '')" 2^>nul') do set "CRM_IN_DIR=%%R"
goto :eof

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
:: Python was already verified up-front, before WSL/commercial detection.

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
