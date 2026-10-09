"""Package tracked source and pinned recursive submodules without Git metadata."""
import argparse
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile

EXCLUDED_DIRS = {
    '.git', '.github', '__pycache__', '.venv', 'venv', 'env', 'ENV',
    '.pytest_cache', '.mypy_cache', '.ruff_cache', '.idea', '__MACOSX',
    'build', 'dist', 'htmlcov', 'test-results',
}
REQUIRED = {
    'README.md', 'CONFIGURATION.md', 'USER_GUIDE.md', 'launch_config.ini',
    'LaunchLogistics_MAC.command', 'LaunchLogistics_WIN.bat',
    'LaunchLogistics_LINUX_UV.sh', 'Python/launch.py',
    'Python/pyproject.toml', 'Python/uv.lock',
    'Python/commonUtils/launchers/LaunchPythonProject_MAC.command',
    'Python/commonUtils/launchers/LaunchPythonProject_WIN.bat',
    'Python/commonUtils/launchers/LaunchPythonProject_LINUX_UV.sh',
}


def included(name):
    path = PurePosixPath(name)
    return (not path.is_absolute() and '..' not in path.parts
            and not any(p in EXCLUDED_DIRS or p.endswith('.egg-info') for p in path.parts)
            and path.name not in {'.DS_Store', 'Thumbs.db', 'Desktop.ini', '.coverage', 'release.zip'}
            and not path.name.startswith('._')
            and path.suffix.lower() not in {'.pyc', '.pyo'}
            and path.parts[0] not in {'Temp', 'temp'})


def tracked_files(root):
    status = subprocess.check_output(
        ['git', 'submodule', 'status', '--recursive'], cwd=root, text=True)
    for line in status.splitlines():
        if not line.startswith(' '):
            raise RuntimeError(f'Submodule is missing, conflicted or differs from its pinned commit: {line}')
    data = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--recurse-submodules', '-z'], cwd=root)
    return sorted({os.fsdecode(name) for name in data.split(b'\0') if name})


def package(root, output, names=None, required=REQUIRED):
    root, output = Path(root).resolve(), Path(output).resolve()
    names = [name for name in (tracked_files(root) if names is None else names) if included(name)]
    missing = required.difference(names)
    if missing:
        raise RuntimeError(f'Missing required release files: {sorted(missing)}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            source = root / name
            target = 'Logistics/' + name
            # Never dereference a symlink into local resources outside the checkout.
            if source.is_symlink():
                info = zipfile.ZipInfo(target)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, os.fsencode(os.readlink(source)))
            elif source.is_file():
                archive.write(source, target)
            else:
                raise RuntimeError(f'Tracked release file is unavailable: {name}')
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Release ZIP integrity check failed')
    print(f'Packaged {len(names)} files into {output} under Logistics/')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package(args.root, args.output)
