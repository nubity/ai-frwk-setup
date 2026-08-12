#!/usr/bin/env python3
"""
AI Framework - Workspace Bootstrap Script

Single-file, zero-dependency Python script that initializes a new AI Framework
project workspace. Supports two invocation modes:

  CLI mode (terminal with arguments):
    python3 bootstrap.py <CRM_ID> [OPTIONS]

  Interactive mode (double-click or no arguments):
    Prompts the user for all required values via input().

One-liner examples:

  macOS/Linux:
    curl -sfo /tmp/bootstrap.py https://raw.githubusercontent.com/nubity/ai-frwk-setup/main/bootstrap.py && python3 /tmp/bootstrap.py 1150636000118094005

  Windows (CMD):
    curl -sfo "%TEMP%\bootstrap.py" https://raw.githubusercontent.com/nubity/ai-frwk-setup/main/bootstrap.py && python "%TEMP%\bootstrap.py" 1150636000118094005

Exit codes:
  0   Success
  1   Missing prerequisites or invalid arguments
  2   Git clone failed
  3   setup-workspace.py failed
"""

from __future__ import annotations

import atexit
import functools
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AIFRWK_REPO_SSH = 'git@github.com:nubity/ai-frwk.git'
AIFRWK_REPO_HTTPS = 'https://github.com/nubity/ai-frwk.git'
CLONE_DIR_NAME = 'ai-frwk-setup'
VERSION = '1.0.0'

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _info(msg: str) -> None:
    print(f'  {msg}')


def _ok(msg: str) -> None:
    print(f'  \033[32m[OK]\033[0m {msg}')


def _warn(msg: str) -> None:
    print(f'  \033[33m[!!]\033[0m {msg}', file=sys.stderr)


def _error(msg: str) -> None:
    print(f'  \033[31m[!!]\033[0m {msg}', file=sys.stderr)


def _step(name: str) -> None:
    print(f'\n--- {name} ---\n')


# ---------------------------------------------------------------------------
# Interactive mode detection
# ---------------------------------------------------------------------------


def _is_interactive() -> bool:
    """True when no arguments were provided and stdin is a terminal."""
    return len(sys.argv) == 1 and sys.stdin.isatty()


def _is_double_click() -> bool:
    """Heuristic: detect if launched via OS file manager (double-click)."""
    if not sys.stdin.isatty():
        return False
    # Windows: when double-clicked, PROMPT env var is absent.
    if os.name == 'nt' and 'PROMPT' not in os.environ:
        return True
    # macOS: launched via open(1) or Finder — parent is launchd.
    if platform.system() == 'Darwin':
        ppid = os.getppid()
        try:
            result = subprocess.run(
                ['ps', '-p', str(ppid), '-o', 'comm='],
                capture_output=True, text=True,
            )
            parent = result.stdout.strip()
            if parent in ('launchd', 'login'):
                return True
        except OSError:
            pass
    return _is_interactive()


_exit_success: bool = False


def _pause_on_exit() -> None:
    """Keep the terminal window open on failure when launched via OS UI.

    On success the window auto-closes after a brief countdown so the user
    can read the final message without being forced to press Enter.
    """
    if not _is_double_click():
        return
    print()
    if _exit_success:
        import time
        for remaining in range(5, 0, -1):
            print(f'\r  Closing in {remaining}s...', end='', flush=True)
            time.sleep(1)
        print()
    else:
        try:
            input('Press Enter to close this window...')
        except (KeyboardInterrupt, EOFError):
            pass


# ---------------------------------------------------------------------------
# Cleanup handler
# ---------------------------------------------------------------------------

_cleanup_path: Path | None = None


def _register_cleanup(workspace_dir: Path) -> None:
    """Register the workspace directory for removal on failure."""
    global _cleanup_path
    _cleanup_path = workspace_dir


def _unregister_cleanup() -> None:
    """Disable cleanup (called on success)."""
    global _cleanup_path
    _cleanup_path = None


def _cleanup() -> None:
    """Remove the workspace directory if setup failed."""
    if _cleanup_path and _cleanup_path.is_dir():
        _warn(f'Cleaning up partial workspace: {_cleanup_path}')
        shutil.rmtree(_cleanup_path, ignore_errors=True)


atexit.register(_cleanup)

# ---------------------------------------------------------------------------
# Base directory resolution
# ---------------------------------------------------------------------------


def _resolve_base_dir(explicit: str | None = None) -> Path:
    """
    Determine where workspace directories are created.

    Priority:
      1. Explicit value (--base-dir argument or interactive input)
      2. NUBITY_PROJECTS_DIR environment variable
      3. Platform default:
         - Windows (non-WSL) and macOS: <Desktop>/nubity-projects
         - Linux/WSL: ~/nubity-projects
    """
    if explicit:
        return Path(explicit).expanduser().resolve()

    env_val = os.environ.get('NUBITY_PROJECTS_DIR')
    if env_val:
        return Path(env_val).expanduser().resolve()

    home = Path.home()
    system = platform.system()
    is_wsl = system == 'Linux' and 'microsoft' in platform.release().lower()

    if system == 'Windows' and not is_wsl:
        desktop = _resolve_windows_desktop()
        return desktop / 'nubity-projects'

    if system == 'Darwin':
        return home / 'Desktop' / 'nubity-projects'

    return home / 'nubity-projects'


def _resolve_windows_desktop() -> Path:
    """Resolve the Desktop path on Windows using PowerShell, fallback to ~/Desktop."""
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Path.home() / 'Desktop'


# ---------------------------------------------------------------------------
# Prerequisites check
# ---------------------------------------------------------------------------


def _check_command(name: str) -> bool:
    """Check if a command is available in PATH."""
    return shutil.which(name) is not None


@functools.lru_cache(maxsize=1)
def _can_ssh_to_github() -> bool:
    """Check if SSH authentication to GitHub succeeds without user interaction."""
    try:
        result = subprocess.run(
            ['ssh', '-T',
             '-o', 'ConnectTimeout=5',
             '-o', 'StrictHostKeyChecking=accept-new',
             '-o', 'BatchMode=yes',
             'git@github.com'],
            capture_output=True, text=True, timeout=10,
        )
        # GitHub returns exit code 1 with "successfully authenticated" on success.
        combined = result.stdout + result.stderr
        return 'successfully authenticated' in combined.lower()
    except (OSError, subprocess.TimeoutExpired):
        return False


def _check_prerequisites(use_https: bool) -> bool:
    """Verify all required tools are available. Returns True if all pass."""
    _step('Checking prerequisites')
    ok = True

    # Git
    if _check_command('git'):
        _ok('git')
    else:
        _error('git not found in PATH.')
        ok = False

    # Python is obviously available since this script is running.
    _ok(f'python ({sys.executable})')

    # JIRA credentials (warning, not blocking).
    email = os.environ.get('ATLASSIAN_USER_EMAIL', '')
    token = os.environ.get('ATLASSIAN_API_TOKEN', '')
    if email and token:
        _ok('JIRA credentials (ATLASSIAN_USER_EMAIL, ATLASSIAN_API_TOKEN)')
    else:
        _warn('ATLASSIAN_USER_EMAIL and/or ATLASSIAN_API_TOKEN not set.')
        _warn('setup-workspace.py needs these for JIRA resolution.')
        _warn('The setup may produce an incomplete configuration.')

    # SSH check (only when using SSH clone).
    if not use_https:
        if _can_ssh_to_github():
            _ok('GitHub SSH authentication')
        else:
            _info('GitHub SSH not available - will use HTTPS automatically.')

    if ok:
        _ok('All prerequisites satisfied.')
    return ok


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def _prompt(label: str, default: str = '', validator=None) -> str:
    """Prompt the user for input with an optional default and validator."""
    suffix = f' [{default}]' if default else ''
    while True:
        try:
            value = input(f'  {label}{suffix}: ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(1)
        if not value:
            value = default
        if validator:
            err = validator(value)
            if err:
                _error(err)
                continue
        return value


def _prompt_yes_no(label: str, default: bool = False) -> bool:
    """Prompt for a yes/no answer."""
    hint = 'Y/n' if default else 'y/N'
    try:
        answer = input(f'  {label} [{hint}]: ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    if not answer:
        return default
    return answer in ('y', 'yes', 'si', 's')


def _validate_crm_id(value: str) -> str | None:
    """Return error message if CRM ID is invalid, None if valid."""
    if not value:
        return 'CRM ID is required.'
    if not value.isdigit() or len(value) != 19:
        return f"Invalid CRM ID: '{value}'. Must be exactly 19 digits."
    return None


def _gather_interactive() -> dict:
    """Gather all parameters via interactive prompts."""
    print()

    crm_id = _prompt('CRM ID (19 digits)', validator=_validate_crm_id)

    return {
        'crm_id': crm_id,
        'base_dir': '',
        'branch': 'main',
        'use_https': False,
        'repository': '',
        'onedrive_path': '',
    }


# ---------------------------------------------------------------------------
# Argument parsing (CLI mode)
# ---------------------------------------------------------------------------


def _parse_args() -> dict:
    """Parse command-line arguments. Returns a config dict."""
    args = sys.argv[1:]
    config = {
        'crm_id': '',
        'base_dir': '',
        'branch': 'main',
        'use_https': False,
        'repository': '',
        'onedrive_path': '',
    }

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ('-h', '--help'):
            print(__doc__)
            sys.exit(0)
        elif arg == '--version':
            print(f'bootstrap.py {VERSION}')
            sys.exit(0)
        elif arg == '--base-dir':
            i += 1
            if i >= len(args):
                _error('--base-dir requires a value.')
                sys.exit(1)
            config['base_dir'] = args[i]
        elif arg == '--branch':
            i += 1
            if i >= len(args):
                _error('--branch requires a value.')
                sys.exit(1)
            config['branch'] = args[i]
        elif arg == '--https':
            config['use_https'] = True
        elif arg == '--repository':
            i += 1
            if i >= len(args):
                _error('--repository requires a value.')
                sys.exit(1)
            config['repository'] = args[i]
        elif arg == '--onedrive-path':
            i += 1
            if i >= len(args):
                _error('--onedrive-path requires a value.')
                sys.exit(1)
            config['onedrive_path'] = args[i]
        elif arg.startswith('-'):
            _error(f'Unknown option: {arg}')
            print(__doc__)
            sys.exit(1)
        else:
            # Positional: CRM ID.
            if config['crm_id']:
                _error(f'Unexpected argument: {arg}')
                sys.exit(1)
            config['crm_id'] = arg
        i += 1

    return config


# ---------------------------------------------------------------------------
# Logo display
# ---------------------------------------------------------------------------

_LOGO_Z = (
    'eNrVkt0OgyAMhe95ij7sLrwcicxkCS/Hk0xQsT+jq2SZ0/QC2nL8egDg05ceNxQD3jrL0cEW'
    'LTH0Y9JuFtZPNcfo0u8P1/J8aBjwmyA37jqv9hxyd9pdfuER/L29DauvA839vhS3o8xh2rdh0p'
    'I45gatrMqBqicKTnic5balrwt4kxxTuOfgPD6FJy1tnSHmkhhyzAXeKnVRqWhh9rkoZFV6MjIGIM'
    '3lDxUZdYNVW7i82CM963KasyLYBbPBWS+I6HrKKSf3PCP9s/vK2A4pI9p1lLgv1+cBfEpLNlJJ4'
    'Fu7ZnmhL7646u4='
)


def _show_logo() -> None:
    """Print the embedded Nubity OS ASCII art logo."""
    import base64
    import zlib
    try:
        print()
        print(zlib.decompress(base64.b64decode(_LOGO_Z)).decode())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point: orchestrate the bootstrap process."""
    # --- Show logo -------------------------------------------------------------
    _show_logo()

    # Determine invocation mode.
    if _is_interactive():
        config = _gather_interactive()
    else:
        config = _parse_args()

    # Register exit pause for double-click launches.
    # --- Validate CRM ID -----------------------------------------------------
    crm_id = config['crm_id']
    err = _validate_crm_id(crm_id)
    if err:
        _error(err)
        sys.exit(1)

    use_https: bool = config['use_https']
    branch: str = config['branch']

    # --- Check prerequisites --------------------------------------------------
    if not _check_prerequisites(use_https):
        sys.exit(1)

    # --- Resolve workspace directory ------------------------------------------
    _step('Creating workspace')

    base_dir = _resolve_base_dir(config['base_dir'] or None)
    workspace_dir = base_dir / crm_id

    if workspace_dir.is_dir():
        _ok(f'Using existing directory: {workspace_dir}')
    else:
        workspace_dir.mkdir(parents=True, exist_ok=False)
        _register_cleanup(workspace_dir)
        _ok(f'Created: {workspace_dir}')

    # --- Clone ai-frwk --------------------------------------------------------
    _step(f'Cloning ai-frwk (branch: {branch})')

    # Resolve clone method: explicit --https > auto-detect SSH > fallback HTTPS.
    if use_https:
        repo_url = AIFRWK_REPO_HTTPS
    elif _can_ssh_to_github():
        repo_url = AIFRWK_REPO_SSH
    else:
        _info('SSH not available, using HTTPS.')
        repo_url = AIFRWK_REPO_HTTPS

    clone_path = workspace_dir / CLONE_DIR_NAME

    clone_cmd = [
        'git', 'clone', '--depth=1',
        '--branch', branch,
        repo_url,
        str(clone_path),
    ]

    result = subprocess.run(clone_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        _error(f'Failed to clone ai-frwk from {repo_url} (branch: {branch}).')
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                _info(f'  {line}')
        if not use_https:
            _info('')
            _info('Tip: If SSH keys are not configured, re-run with --https.')
        sys.exit(2)

    _ok(f'Cloned: {clone_path}')

    # --- Run setup-workspace.py -----------------------------------------------
    _step('Running setup-workspace.py')

    setup_script = clone_path / '.kiro' / 'scripts' / 'setup-workspace.py'
    if not setup_script.is_file():
        _error(f'Setup script not found: {setup_script}')
        _info('This indicates a broken clone. Verify the branch name and try again.')
        sys.exit(3)

    # Build the command with pass-through arguments.
    setup_cmd = [sys.executable, str(setup_script)]

    # The directory name IS the CRM ID, so setup-workspace.py infers it.
    # Pass --branch so the internal .git-source/ clone uses the same branch.
    setup_cmd.extend(['--branch', branch])

    if config['repository']:
        setup_cmd.extend(['--repository', config['repository']])
    if config['onedrive_path']:
        setup_cmd.extend(['--onedrive-path', config['onedrive_path']])

    # setup-workspace.py uses Path.cwd() as PROJECT_ROOT.
    proc = subprocess.run(setup_cmd, cwd=str(workspace_dir))

    if proc.returncode != 0:
        _error('setup-workspace.py failed.')
        _info('Review the output above for details.')
        _info('The workspace directory will be removed.')
        sys.exit(3)

    # --- Success --------------------------------------------------------------
    global _exit_success
    _exit_success = True
    _unregister_cleanup()
    _step('Setup complete')
    _ok(f'Workspace ready: {workspace_dir}')
    _info('')
    _info('Next steps:')
    _info(f'  cd {workspace_dir}')
    _info("  Open in Kiro IDE or start a conversation with 'kiro chat'")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n  Interrupted.')
        sys.exit(1)
    finally:
        _pause_on_exit()
