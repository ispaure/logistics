"""
Actions for the Logistics Obsidian feature.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

from commonUtils import ui
from commonUtils.filesystem.directories import Directory
from commonUtils.runtime.diagnostics import Severity, log
from commonUtils.runtime.platform import OS, get_os

from features.obsidian.registry import RegistrySnapshot


# ----------------------------------------------------------------------------------------------------------------------
# SHARED PLATFORM HELPERS

_OBSIDIAN_FLATPAK_ID = 'md.obsidian.Obsidian'
_OBSIDIAN_URI_SCHEME = 'x-scheme-handler/obsidian'


def _command_succeeds(command: list[str]) -> bool:
    """Run a quiet installation or process probe."""

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except OSError:
        return False

    return result.returncode == 0


# ----------------------------------------------------------------------------------------------------------------------
# LINUX HANDLER AND PACKAGE PROBES

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

    return _command_succeeds(['flatpak', 'info', _OBSIDIAN_FLATPAK_ID])


def _is_snap_installed() -> bool:
    """Return whether an Obsidian Snap is installed."""

    if shutil.which('snap') is None:
        return False

    return _command_succeeds(['snap', 'list', 'obsidian'])


# ----------------------------------------------------------------------------------------------------------------------
# REGISTRY LOCATION

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

    return _command_succeeds(['open', '-Ra', 'Obsidian'])


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
    return _command_succeeds(['pgrep', '-x', 'Obsidian'])


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

    return _command_succeeds(['pgrep', '-x', 'obsidian'])


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


def _ask_to_close_obsidian(vault_name: str) -> None:
    ui.display_msg_box_ok(
        'Obsidian - Close Application',
        f'The vault "{vault_name}" has not been opened by Obsidian on this computer yet.\n\n'
        'Close Obsidian completely, then try again. Logistics needs to add this vault to Obsidian\'s known '
        'vaults list before launching it for the first time.'
    )


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
        registry = RegistrySnapshot.read(registry_path)
    except RuntimeError as error:
        _show_error(str(error))
        return False

    vault_id = registry.find_vault_id(vault.path)
    if vault_id is None:
        if is_obsidian_running():
            _ask_to_close_obsidian(vault.name)
            return False

        try:
            vault_id = registry.register(vault.path)
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
