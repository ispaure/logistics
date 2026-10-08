"""Application policy for destructive folder tools, independently of filesystem mechanics."""
from configparser import ConfigParser
from pathlib import Path
import os
import sys


def get_policy_path():
    return Path(__file__).resolve().parents[1] / 'maintenance.ini'


def protected_roots(platform=None, environ=None, home=None):
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform == 'win32':
        return tuple(Path(value) for value in (
            environ.get('SystemRoot', r'C:\Windows'),
            environ.get('ProgramFiles', r'C:\Program Files'),
            environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
            environ.get('ProgramW6432', r'C:\Program Files'),
            environ.get('ProgramData', r'C:\ProgramData')))
    if platform == 'darwin':
        return tuple(Path(path) for path in ('/System', '/Library', '/Applications', '/usr', '/bin', '/sbin', '/etc', '/var/db', '/var/root')) + (home / 'Applications',)
    return tuple(Path(path) for path in ('/usr', '/etc', '/bin', '/sbin', '/lib', '/lib64', '/boot', '/proc', '/sys', '/dev', '/opt', '/run', '/var/lib', '/var/cache'))


def require_safe_folder(folder, *, recursive=True):
    """Resolve aliases before rejecting protected folders and recursive ancestors."""
    folder = Path(folder).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    policy = ConfigParser(interpolation=None)
    policy_path = get_policy_path()
    if not policy_path.is_file():
        raise ValueError(f'Folder safety configuration is missing: {policy_path}')
    policy.read(policy_path, encoding='utf-8-sig')
    protected = list(protected_roots()) if policy.getboolean('FolderSafety', 'protect_system_folders', fallback=True) else []
    for value in policy.get('FolderSafety', 'additional_protected_paths', fallback='').splitlines():
        if value.strip():
            path = Path(os.path.expandvars(value.strip())).expanduser()
            protected.append(path if path.is_absolute() else policy_path.parent.parent / path)
    for root in protected:
        root = root.resolve()
        if folder == root or root in folder.parents or (recursive and folder in root.parents):
            raise ValueError(f'This operation is blocked in a protected system folder: {folder}\nProtected location: {root}')
    return folder
