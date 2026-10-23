"""Curate source/resources for Qt's deployment tool, independently of Toga."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[2]

def stage(destination):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError('Use a fresh staging directory')
    destination.mkdir(parents=True)
    shutil.copy2(Path(__file__).with_name('main.py'), destination / 'main.py')
    shared = REPO / 'Python/commonUtils'
    files = subprocess.check_output(['git', '-C', str(shared), 'ls-files', '-z']).decode().split('\0')
    for relative in files:
        path = shared / relative
        if (not relative or relative.startswith(('tests/', 'docs/', '.'))
                or path.suffix not in ('.py', '.ini', '.svg', '.png', '.txt') and relative != 'LICENSE.md'):
            continue
        target = destination / 'commonUtils' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for relative in ('features/__init__.py', 'features/rclone/__init__.py',
                     'features/rclone/mobile/__init__.py', 'features/rclone/mobile/cloud.py',
                     'features/rclone/mobile/bridge_protocol.py',
                     'features/rclone/mobile/credential_state.py',
                     'features/rclone/credential_loading.py'):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / 'Python' / relative, target)
    pygments = Path(importlib.util.find_spec('pygments').origin).parent
    shutil.copytree(pygments, destination / 'pygments', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return destination

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(stage(args.destination))
