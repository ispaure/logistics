"""
Actions for the Logistics Obsidian feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import json
import os
import secrets
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from commonUtils import ui
from commonUtils.debugUtils import Severity, log
from commonUtils.dirUtils import Directory
from commonUtils.osUtils import OS, get_os


# ----------------------------------------------------------------------------------------------------------------------
# CONSTANTS

_OBSIDIAN_FLATPAK_ID = 'md.obsidian.Obsidian'
_OBSIDIAN_URI_SCHEME = 'x-scheme-handler/obsidian'


# ----------------------------------------------------------------------------------------------------------------------
# REGISTRY LOCATION

def _get_linux_protocol_handler() -> str | None:
    """Return the desktop entry registered for obsidian:// URIs on Linux."""

    if shutil.which('xdg-mime') is None:
        return None

    try:
        result = subprocess.run(
            ['xdg-mime', 'query', 'default', _OBSIDIAN_URI_SCHEME],
            capture_output=True,
            text=True,
            check=False
        )
    except OSError:
        return None

    handler = result.stdout.strip()
    return handler or None


def _is_flatpak_installed() -> bool:
    """Return whether the Obsidian Flatpak is installed for the current user/system."""

    if shutil.which('flatpak') is None:
        return False

    try:
        result = subprocess.run(
            ['flatpak', 'info', _OBSIDIAN_FLATPAK_ID],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except OSError:
        return False

    return result.returncode == 0


def _is_snap_installed() -> bool:
    """Return whether an Obsidian Snap is installed."""

    if shutil.which('snap') is None:
        return False

    try:
        result = subprocess.run(
            ['snap', 'list', 'obsidian'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except OSError:
        return False

    return result.returncode == 0


def _get_linux_registry_path() -> Path:
    """Return the registry path belonging to the Obsidian install handling obsidian:// URIs."""

    xdg_config_home = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))

    native_path = xdg_config_home / 'obsidian' / 'obsidian.json'
    flatpak_path = Path.home() / '.var' / 'app' / _OBSIDIAN_FLATPAK_ID / 'config' / 'obsidian' / 'obsidian.json'
    snap_path = Path.home() / 'snap' / 'obsidian' / 'current' / '.config' / 'obsidian' / 'obsidian.json'

    handler = _get_linux_protocol_handler()

    if handler is not None:
        handler_lower = handler.lower()

        if _OBSIDIAN_FLATPAK_ID.lower() in handler_lower:
            return flatpak_path

        if 'snap' in handler_lower:
            return snap_path

        return native_path

    existing_paths = [path for path in (native_path, flatpak_path, snap_path) if path.is_file()]

    if len(existing_paths) == 1:
        return existing_paths[0]

    if len(existing_paths) > 1:
        most_recent_path = max(existing_paths, key=lambda path: path.stat().st_mtime)
        log(
            Severity.WARNING,
            'Obsidian',
            f'Multiple Obsidian registries were found and no obsidian:// handler could be identified. '
            f'Using the most recently modified registry: "{most_recent_path}"'
        )
        return most_recent_path

    if _is_flatpak_installed():
        return flatpak_path

    if _is_snap_installed():
        return snap_path

    return native_path


def get_registry_path() -> Path:
    """Return the platform-specific Obsidian global vault registry path."""

    match get_os():
        case OS.WIN:
            appdata = os.environ.get('APPDATA')
            base_path = Path(appdata) if appdata else Path.home() / 'AppData' / 'Roaming'
            return base_path / 'Obsidian' / 'obsidian.json'

        case OS.MAC:
            return Path.home() / 'Library' / 'Application Support' / 'obsidian' / 'obsidian.json'

        case OS.LINUX:
            return _get_linux_registry_path()

        case _:
            raise RuntimeError('Unsupported operating system for Obsidian.')


# ----------------------------------------------------------------------------------------------------------------------
# REGISTRY HELPERS

def _normalize_path(path: Path) -> str:
    """Return a normalized absolute path suitable for comparing vault registry entries."""

    try:
        resolved_path = path.expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        resolved_path = path.expanduser().absolute()

    return os.path.normcase(os.path.normpath(str(resolved_path)))


def _load_registry(registry_path: Path) -> dict[str, Any]:
    """Load the Obsidian registry while preserving unknown top-level settings."""

    if not registry_path.is_file():
        return {'vaults': {}}

    try:
        with registry_path.open('r', encoding='utf-8') as registry_file:
            registry = json.load(registry_file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f'Could not read Obsidian registry "{registry_path}": {error}') from error

    if not isinstance(registry, dict):
        raise RuntimeError(f'Obsidian registry "{registry_path}" does not contain a JSON object.')

    vaults = registry.setdefault('vaults', {})

    if not isinstance(vaults, dict):
        raise RuntimeError(f'Obsidian registry "{registry_path}" has an invalid "vaults" value.')

    return registry


def _write_registry(registry_path: Path, registry: dict[str, Any]) -> None:
    """Atomically write an Obsidian registry, preserving existing file permissions when possible."""

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = registry_path.with_name(f'.{registry_path.name}.logistics.tmp')

    existing_mode = None
    if registry_path.exists():
        existing_mode = stat.S_IMODE(registry_path.stat().st_mode)

    try:
        with temp_path.open('w', encoding='utf-8', newline='\n') as registry_file:
            json.dump(registry, registry_file, separators=(',', ':'), ensure_ascii=False)
            registry_file.write('\n')

        if existing_mode is not None:
            temp_path.chmod(existing_mode)

        os.replace(temp_path, registry_path)
    except OSError as error:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

        raise RuntimeError(f'Could not write Obsidian registry "{registry_path}": {error}') from error


def _find_registered_vault_id(registry: dict[str, Any], vault_path: Path) -> str | None:
    """Return the registered vault ID matching a filesystem path, if present."""

    normalized_vault_path = _normalize_path(vault_path)

    for vault_id, vault_data in registry.get('vaults', {}).items():
        if not isinstance(vault_data, dict):
            continue

        registered_path = vault_data.get('path')
        if not isinstance(registered_path, str):
            continue

        if _normalize_path(Path(registered_path)) == normalized_vault_path:
            return str(vault_id)

    return None


def _register_vault(registry_path: Path, registry: dict[str, Any], vault_path: Path) -> str:
    """Add a vault to Obsidian's registry and return its newly generated vault ID."""

    vaults = registry['vaults']

    while True:
        vault_id = secrets.token_hex(8)
        if vault_id not in vaults:
            break

    vaults[vault_id] = {
        'path': str(vault_path.expanduser().resolve(strict=False)),
        'ts': int(time.time() * 1000)
    }

    _write_registry(registry_path, registry)
    return vault_id


# ----------------------------------------------------------------------------------------------------------------------
# INSTALLATION DETECTION

def _is_obsidian_installed_windows() -> bool:
    """Return whether Windows has an application registered for the obsidian:// URI scheme."""

    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'obsidian\shell\open\command') as key:
            command, _ = winreg.QueryValueEx(key, None)
            return bool(str(command).strip())
    except (ImportError, OSError):
        return False


def _is_obsidian_installed_macos() -> bool:
    """Return whether macOS can resolve the Obsidian application."""

    try:
        result = subprocess.run(
            ['open', '-Ra', 'Obsidian'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except OSError:
        return False

    return result.returncode == 0


def _is_obsidian_installed_linux() -> bool:
    """Return whether Linux has an Obsidian install or obsidian:// protocol handler available."""

    if _get_linux_protocol_handler() is not None:
        return True

    if shutil.which('obsidian') is not None:
        return True

    return _is_flatpak_installed() or _is_snap_installed()


def is_obsidian_installed() -> bool:
    """Return whether Obsidian appears to be installed and launchable on this computer."""

    match get_os():
        case OS.WIN:
            return _is_obsidian_installed_windows()
        case OS.MAC:
            return _is_obsidian_installed_macos()
        case OS.LINUX:
            return _is_obsidian_installed_linux()
        case _:
            return False


# ----------------------------------------------------------------------------------------------------------------------
# PROCESS DETECTION

def _is_obsidian_running_windows() -> bool:
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq Obsidian.exe', '/FO', 'CSV', '/NH'],
            capture_output=True,
            text=True,
            check=False
        )
    except OSError:
        return False

    return 'obsidian.exe' in result.stdout.lower()


def _is_obsidian_running_macos() -> bool:
    try:
        result = subprocess.run(
            ['pgrep', '-x', 'Obsidian'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except OSError:
        return False

    return result.returncode == 0


def _is_obsidian_running_linux() -> bool:
    proc_path = Path('/proc')

    if proc_path.is_dir():
        for process_path in proc_path.iterdir():
            if not process_path.name.isdigit():
                continue

            try:
                command_name = (process_path / 'comm').read_text(encoding='utf-8', errors='ignore').strip().lower()
                if command_name == 'obsidian':
                    return True

                command_line = (process_path / 'cmdline').read_bytes().replace(b'\x00', b' ').decode(
                    'utf-8', errors='ignore'
                ).lower()

                if _OBSIDIAN_FLATPAK_ID.lower() in command_line:
                    return True
            except (OSError, PermissionError):
                continue

        return False

    try:
        result = subprocess.run(
            ['pgrep', '-x', 'obsidian'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except OSError:
        return False

    return result.returncode == 0


def is_obsidian_running() -> bool:
    """Return whether the Obsidian desktop application is currently running."""

    match get_os():
        case OS.WIN:
            return _is_obsidian_running_windows()
        case OS.MAC:
            return _is_obsidian_running_macos()
        case OS.LINUX:
            return _is_obsidian_running_linux()
        case _:
            return False


# ----------------------------------------------------------------------------------------------------------------------
# ACTIONS

def _open_uri(uri: str) -> None:
    """Open a URI using the operating system's registered protocol handler."""

    match get_os():
        case OS.WIN:
            os.startfile(uri)

        case OS.MAC:
            subprocess.Popen(
                ['open', uri],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True
            )

        case OS.LINUX:
            subprocess.Popen(
                ['xdg-open', uri],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True
            )

        case _:
            raise RuntimeError('Unsupported operating system for Obsidian.')


def _show_error(message: str) -> None:
    log(Severity.ERROR, 'Obsidian', message)
    ui.display_msg_box_ok('Obsidian', message)


def open_vault(vault: Directory) -> bool:
    """
    Open an Obsidian vault.

    Registered vaults are opened immediately by vault ID. If the vault is not yet known to Obsidian, it is first added
    to the platform's global ``obsidian.json`` registry. Obsidian must be closed while a new registration is written so
    that the running application cannot overwrite or ignore the external registry change.
    """

    if not isinstance(vault, Directory):
        raise TypeError(f'Expected Directory, got {type(vault).__name__}')

    if not vault.path.is_dir() or not (vault.path / '.obsidian').is_dir():
        _show_error(f'Unable to open "{vault.path}" because it is not a valid Obsidian vault.')
        return False

    if not is_obsidian_installed():
        _show_error(
            'Obsidian does not appear to be installed or registered on this computer.\n\n'
            'Install and launch Obsidian once, then try again.'
        )
        return False

    registry_path = get_registry_path()

    try:
        registry = _load_registry(registry_path)
    except RuntimeError as error:
        _show_error(str(error))
        return False

    vault_id = _find_registered_vault_id(registry, vault.path)

    if vault_id is None:
        if is_obsidian_running():
            ui.display_msg_box_ok(
                'Obsidian - Close Application',
                f'The vault "{vault.name}" has not been opened by Obsidian on this computer yet.\n\n'
                'Close Obsidian completely, then try again. Logistics needs to add this vault to Obsidian\'s known '
                'vaults list before launching it for the first time.'
            )
            return False

        try:
            vault_id = _register_vault(registry_path, registry, vault.path)
        except RuntimeError as error:
            _show_error(str(error))
            return False

        log(
            Severity.DEBUG,
            'Obsidian',
            f'Registered Obsidian vault "{vault.path}" as "{vault_id}" in "{registry_path}"'
        )

    vault_uri = f'obsidian://open?vault={quote(vault_id, safe="")}'

    try:
        _open_uri(vault_uri)
    except Exception as error:
        _show_error(f'Could not launch Obsidian vault "{vault.name}": {type(error).__name__}: {error}')
        return False

    return True
