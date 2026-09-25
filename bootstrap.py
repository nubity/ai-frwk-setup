#!/usr/bin/env python3
"""
AI Framework - Workspace Bootstrap Script

Single-file, zero-dependency Python script that initializes a new AI Framework
project workspace. Supports three invocation modes:

  CLI mode (terminal with arguments):
    python3 bootstrap.py <CRM_ID> [OPTIONS]

  Interactive mode (double-click or no arguments):
    Prompts the user for all required values via input().

  Commercial mode (double-click from OneDrive-synced directory):
    Detected automatically when CWD is an OneDrive-synced directory with a
    CRM ID in its name and no .git/ present. Installs the framework to
    $HOME/.kiro/ instead of inside the workspace.

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
  4   Commercial setup failed
"""

from __future__ import annotations

import atexit
import functools
import os
import platform
import re
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
VERSION = '1.1.0'
CRM_ID_PATTERN = re.compile(r'\b(\d{19})\b')

# --- JIRA role probe -------------------------------------------------------
# The workspace layout (canonical delivery vs commercial) is role-driven: the
# authoritative determinant is whether the resolved role is a technical
# delivery role (see enumerations/role.py:nonTechnicalRoles). bootstrap.py must
# choose the download path/layer BEFORE the framework (and its authoritative
# resolver, _role_utils.resolveRoleFromJiraGroups) exists on disk. This probe
# reproduces that resolver's two-call contract with the standard library only,
# so bootstrap stays single-file and zero-dependency. It is used SOLELY to
# choose the layer; setup-workspace.py still resolves and persists the
# authoritative role. Any failure returns None (the caller degrades to the
# directory-name heuristic).

JIRA_BASE_URL = 'https://nubity.atlassian.net'

# naifw-* JIRA group name -> role slug. Mirrors _role_utils.NAIFW_GROUP_TO_ROLE
# and enumerations/role.py. Kept in sync manually; both are small and stable.
NAIFW_GROUP_TO_ROLE = {
    'naifw-am': 'account-manager',
    'naifw-presales': 'presales',
    'naifw-po': 'po',
    'naifw-tl': 'tl',
    'naifw-engineer': 'engineer',
    'naifw-ops': 'operations',
}

NAIFW_PREFIX = 'naifw-'

# Technical delivery roles use the canonical layout (framework inside the
# workspace, git repo). Every other role uses the commercial layout. Mirrors
# enumerations/role.py:technicalRoles / nonTechnicalRoles.
TECHNICAL_ROLES = frozenset({'tl', 'engineer', 'operations'})

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

    # Auto-detect CRM ID from CWD (commercial mode: OneDrive directory).
    cwd_name = Path.cwd().name
    match = CRM_ID_PATTERN.search(cwd_name)
    default_crm = match.group(1) if match else ''

    crm_id = _prompt(
        'CRM ID (19 digits)', default=default_crm, validator=_validate_crm_id,
    )

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
# Commercial mode detection and setup
# ---------------------------------------------------------------------------


def _jira_get(path: str) -> object | None:
    """
    Perform an authenticated GET against the JIRA REST API (stdlib only).

    Uses HTTP Basic auth built from ATLASSIAN_USER_EMAIL and
    ATLASSIAN_API_TOKEN, exactly as the framework's JIRA client does. Returns
    the parsed JSON body, or None on any failure (missing credentials, network
    error, non-2xx, malformed JSON). This is a best-effort probe: it never
    raises to the caller.

    :param path: The API path beginning with '/', e.g. '/rest/api/3/myself'.
    :return: The parsed JSON (dict or list), or None on any failure.
    """
    import base64
    import json as _json
    import urllib.error
    import urllib.request

    email = os.environ.get('ATLASSIAN_USER_EMAIL', '')
    token = os.environ.get('ATLASSIAN_API_TOKEN', '')
    if not email or not token:
        return None

    credentials = base64.b64encode(f'{email}:{token}'.encode()).decode('ascii')
    request = urllib.request.Request(
        f'{JIRA_BASE_URL}{path}',
        headers={
            'Authorization': f'Basic {credentials}',
            'Accept': 'application/json',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return _json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, OSError, ValueError):
        return None


@functools.lru_cache(maxsize=1)
def _probe_role_from_jira() -> str | None:
    """
    Resolve the user's role from naifw-* JIRA group membership (best-effort).

    Reproduces _role_utils.resolveRoleFromJiraGroups with the standard library
    only: resolves the accountId via /rest/api/3/myself, then reads
    /rest/api/3/user/groups and returns the role slug for the first naifw-*
    group found. Returns None when credentials are absent, the API is
    unreachable, the responses are malformed, or the user has no naifw-* group.

    The result is used ONLY to choose the workspace layer. It is never
    persisted here - setup-workspace.py remains the authoritative resolver.

    :return: The role slug (e.g. 'engineer', 'account-manager') or None.
    """
    myself = _jira_get('/rest/api/3/myself')
    if not isinstance(myself, dict):
        return None
    account_id = myself.get('accountId', '')
    if not account_id:
        return None

    groups = _jira_get(f'/rest/api/3/user/groups?accountId={account_id}')
    if not isinstance(groups, list):
        return None

    for group in groups:
        if not isinstance(group, dict):
            continue
        name = group.get('name', '')
        if name.startswith(NAIFW_PREFIX) and name in NAIFW_GROUP_TO_ROLE:
            return NAIFW_GROUP_TO_ROLE[name]

    return None


def _detect_commercial_mode(config: dict) -> tuple[bool, str]:
    """
    Determine if the bootstrap was invoked from a commercial workspace.

    The workspace layer is role-driven: technical delivery roles (tl, engineer,
    operations) always use the canonical layout, and non-technical roles use the
    commercial layout (see enumerations/role.py). The user's role is the
    authoritative signal; the directory-name convention is only a fallback for
    when the role cannot be resolved (missing JIRA credentials, offline, or the
    user has no naifw-* group yet).

    Decision order:
    1. An explicit positional CRM ID forces the canonical (delivery) flow.
    2. A local .kiro/config.json marks an already-set-up canonical workspace.
    3. If the JIRA role probe resolves a role, it is authoritative:
       - a technical role forces canonical (NOT commercial), even when invoked
         from inside an OneDrive-synced directory - a technical user must never
         be set up in place inside the shared directory;
       - a non-technical role selects commercial, provided a CRM ID is
         resolvable from the directory name (the commercial layer requires it).
    4. When the role cannot be resolved, fall back to the directory-name
       heuristic: an "Nubity Document Site - <CRM ID>" directory without a local
       .kiro/config.json is treated as commercial.

    Note: .git/ is NOT used as a disqualifier because old commercial setups
    may have a stale .git/ from the framework clone that previously lived
    inside the OneDrive directory.

    :param config: Parsed CLI arguments or interactive config dict.
    :return: Tuple of (is_commercial, crm_id). crm_id is empty when not commercial.
    """
    # (1) Explicit positional CRM ID -> canonical delivery flow.
    if config['crm_id']:
        return False, ''

    cwd = Path.cwd()

    # (2) A local .kiro/config.json is the canonical delivery signal.
    if (cwd / '.kiro' / 'config.json').is_file():
        return False, ''

    # Resolve the CRM ID the commercial layer would need, from the directory
    # name. Its presence gates commercial mode regardless of how the role is
    # resolved, because the commercial setup keys the project map by CRM ID.
    match = CRM_ID_PATTERN.search(cwd.name)
    dir_is_onedrive = cwd.name.startswith('Nubity Document Site - ') and bool(match)
    crm_id = match.group(1) if match else ''

    # (3) Role-driven decision (authoritative when the probe succeeds).
    role = _probe_role_from_jira()
    if role is not None:
        if role in TECHNICAL_ROLES:
            # Technical roles never use the commercial layout, even when invoked
            # from inside the OneDrive-synced directory.
            return False, ''
        # Non-technical role: commercial layout, but only if a CRM ID is
        # available (it comes from the OneDrive directory name).
        if dir_is_onedrive:
            return True, crm_id
        return False, ''

    # (4) Role unresolved -> fall back to the directory-name heuristic.
    if dir_is_onedrive:
        return True, crm_id
    return False, ''


def _commercial_setup(crm_id: str, branch: str, use_https: bool) -> None:
    """
    Execute the commercial workspace setup: install framework to $HOME/.kiro/.

    Steps:
    1. Clone ai-frwk into $HOME/.kiro/.git-source/ (shallow, single branch).
    2. Copy framework contents from the clone into $HOME/.kiro/.
    3. Delegate to setup-workspace.py --commercial for role resolution, config
       writing, directory creation, and Kiro IDE launch.

    :param crm_id: The 19-digit CRM ID extracted from the workspace path.
    :param branch: ai-frwk branch to clone.
    :param use_https: Whether to use HTTPS for cloning (vs SSH).
    """
    _step('Commercial mode - Installing to $HOME/.kiro/')

    home_kiro = Path.home() / '.kiro'
    git_source = home_kiro / '.git-source'
    workspace_root = Path.cwd()

    _info(f'Workspace: {workspace_root}')
    _info(f'Framework: {home_kiro}')
    _info(f'CRM ID:    {crm_id}')
    print()

    # --- Clone or update .git-source/ ----------------------------------------
    repo_url = _resolve_repo_url(use_https)

    if (git_source / '.git').is_dir():
        _info('Updating existing .git-source/...')
        result = subprocess.run(
            ['git', 'fetch', '--quiet', '--depth=1', 'origin', branch],
            capture_output=True, text=True, cwd=str(git_source),
            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'},
            timeout=30,
        )
        if result.returncode != 0:
            _error(f'git fetch failed: {result.stderr.strip()}')
            sys.exit(2)
        subprocess.run(
            ['git', 'reset', '--quiet', '--hard', 'FETCH_HEAD'],
            capture_output=True, text=True, cwd=str(git_source),
        )
        _ok('Updated .git-source/')
    else:
        _info('Cloning ai-frwk...')
        home_kiro.mkdir(parents=True, exist_ok=True)
        clone_cmd = [
            'git', 'clone', '--depth=1', '--branch', branch,
            repo_url, str(git_source),
        ]
        result = subprocess.run(
            clone_cmd, capture_output=True, text=True,
            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'},
            timeout=60,
        )
        if result.returncode != 0:
            _error(f'git clone failed: {result.stderr.strip()}')
            if not use_https:
                _info('Tip: If SSH keys are not configured, re-run with --https.')
            sys.exit(2)
        _ok('Cloned ai-frwk')

    # --- Copy framework contents to $HOME/.kiro/ -----------------------------
    _step('Copying framework contents')

    source_kiro = git_source / '.kiro'
    if not source_kiro.is_dir():
        _error('.kiro/ directory not found in cloned repository.')
        sys.exit(4)

    # Directories to copy from the source .kiro/ into $HOME/.kiro/.
    sync_dirs = [
        'steering', 'scripts', 'skills', 'hooks', 'agents',
        'role-workflows', 'powers', 'templates',
    ]
    # Files to copy at the root of .kiro/.
    sync_files = ['policies.json']

    for dirname in sync_dirs:
        src = source_kiro / dirname
        dst = home_kiro / dirname
        if src.is_dir():
            if dst.is_dir():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    for filename in sync_files:
        src = source_kiro / filename
        dst = home_kiro / filename
        if src.is_file():
            shutil.copy2(src, dst)

    _ok('Framework contents installed')

    # --- Patch paths for commercial layout -----------------------------------
    # The copied files reference .kiro/ (relative to workspace root). In
    # commercial layout, .kiro/ lives at $HOME — paths must be rewritten.
    # Also adapts python3 -> python on Windows.
    scripts_dir = home_kiro / 'scripts'
    if scripts_dir.is_dir():
        sys.path.insert(0, str(scripts_dir))
        try:
            from _sync_utils import patchCommercialLayout, patchPythonCommand
            patchPythonCommand(home_kiro)
            patchCommercialLayout(home_kiro)
            _ok('Paths adapted for commercial layout')
        except Exception as exc:
            _warn(f'Path patching failed: {exc}')
        finally:
            sys.path.pop(0)

    # --- Delegate to setup-workspace.py --------------------------------------
    _step('Running setup-workspace.py --commercial')

    setup_script = home_kiro / 'scripts' / 'setup-workspace.py'
    if not setup_script.is_file():
        _error(f'Setup script not found: {setup_script}')
        sys.exit(4)

    setup_cmd = [sys.executable, str(setup_script), '--commercial', '--branch', branch]

    proc = subprocess.run(setup_cmd, cwd=str(workspace_root))

    if proc.returncode != 0:
        _error('setup-workspace.py --commercial failed.')
        _info('Review the output above for details.')
        sys.exit(4)


def _resolve_repo_url(use_https: bool) -> str:
    """Resolve the ai-frwk clone URL based on SSH availability."""
    if use_https:
        return AIFRWK_REPO_HTTPS
    if _can_ssh_to_github():
        return AIFRWK_REPO_SSH
    _info('SSH not available, using HTTPS.')
    return AIFRWK_REPO_HTTPS


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point: orchestrate the bootstrap process."""
    global _exit_success

    # --- Show logo -------------------------------------------------------------
    _show_logo()

    # --- Early commercial mode detection (before any prompts) -----------------
    # Check if CWD is an OneDrive-synced directory with CRM ID and no .git/.
    # This check fires ONLY for interactive/launcher invocations (no CLI args).
    if _is_interactive():
        early_config = {'crm_id': '', 'use_https': False, 'branch': 'main'}
        is_commercial, inferred_crm = _detect_commercial_mode(early_config)
        if is_commercial:
            _info(f'Detected commercial workspace: {Path.cwd().name}')
            _info(f'CRM ID: {inferred_crm}')
            print()

            use_https = False
            branch = 'main'

            # Minimal prerequisite check for commercial mode (only git needed).
            _step('Checking prerequisites')
            if not _check_command('git'):
                _error('git not found in PATH.')
                _info('Install Git and ensure it is added to PATH.')
                sys.exit(1)
            _ok('git')
            _ok(f'python ({sys.executable})')

            _commercial_setup(inferred_crm, branch, use_https)

            _exit_success = True
            return

    # --- Standard flow (CLI args or interactive without commercial signals) ----
    if _is_interactive():
        config = _gather_interactive()
    else:
        config = _parse_args()

    # --- Check for commercial mode from CLI (explicit --branch/--https only) ---
    is_commercial, inferred_crm = _detect_commercial_mode(config)

    if is_commercial:
        use_https: bool = config['use_https']
        branch: str = config['branch']

        # Minimal prerequisite check for commercial mode (only git needed).
        _step('Checking prerequisites')
        if not _check_command('git'):
            _error('git not found in PATH.')
            _info('Install Git and ensure it is added to PATH.')
            sys.exit(1)
        _ok('git')
        _ok(f'python ({sys.executable})')

        _commercial_setup(inferred_crm, branch, use_https)

        _exit_success = True
        return

    # --- Standard (delivery) flow below ---------------------------------------

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
