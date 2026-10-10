"""Connect an optional sibling Ally checkout without tracking its private files."""
import os
import subprocess
from pathlib import Path


def activate(logistics_root, ally_root):
    logistics_root, ally_root = Path(logistics_root).resolve(), Path(ally_root).resolve()
    source = ally_root / 'Python' / 'ally_feature'
    if not (source / '__init__.py').is_file():
        raise RuntimeError(f'Ally feature package is missing: {source}')
    link = logistics_root / 'Python' / 'features' / 'emulation'
    junction = getattr(link, 'is_junction', lambda: False)
    if link.is_symlink() or junction():
        if link.resolve() == source:
            os.environ['LOGISTICS_ALLY_ROOT'] = str(ally_root)
            return
        if junction():
            link.rmdir()
        else:
            link.unlink()
    elif link.exists():
        raise RuntimeError(f'Refusing to replace a real file or directory: {link}')
    if os.name == 'nt':
        # Directory junctions do not require Developer Mode or administrator rights.
        # Pass cmd its native command line. list2cmdline adds backslash escapes
        # around a whole command argument, which cmd's mklink does not understand.
        subprocess.run(f'cmd /d /s /c "mklink /J "{link}" "{source}""', check=True)
    else:
        link.symlink_to(source, target_is_directory=True)
    os.environ['LOGISTICS_ALLY_ROOT'] = str(ally_root)


def is_active(feature_path):
    root = os.environ.get('LOGISTICS_ALLY_ROOT')
    return bool(root and Path(feature_path).resolve() == Path(root).resolve() / 'Python' / 'ally_feature')
