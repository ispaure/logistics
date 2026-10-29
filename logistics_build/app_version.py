"""One reviewed app-version edit across desktop, Briefcase and the uv lock."""
from pathlib import Path
import re
import tomllib

from build_manager.locking import workspace_lock


def set_version(root, version):
    if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Use a three-component numeric app version.')
    root = Path(root)
    with workspace_lock(root / 'mobile_build/.tools/build-manager/version.lock'):
        desktop = root / 'Python/pyproject.toml'
        mobile = root / 'mobile_build/pyproject.toml'
        lock = root / 'Python/uv.lock'
        before = {path: path.read_text() for path in (desktop, mobile, lock)}
        # Parse and identify every owner before writing any file. Dependency
        # versions and unrelated version fields are never rewritten.
        for path, table in ((desktop, 'project'), (mobile, 'tool')):
            metadata = tomllib.loads(before[path])[table]
            if path == mobile:
                metadata = metadata['briefcase']
            if not isinstance(metadata['version'], str):
                raise ValueError('Invalid tracked app version: ' + str(path))
        packages = tomllib.loads(before[lock])['package']
        if len([item for item in packages if item.get('name') == 'logistics']) != 1:
            raise ValueError('Cannot uniquely identify Logistics in the uv lock.')
        changed = {}
        for path in (desktop, mobile):
            text, count = re.subn(r'(?m)^version = "[^"\n]+"$',
                                 'version = "' + version + '"', before[path])
            if count != 1:
                raise ValueError('Cannot uniquely identify the app version: ' + str(path))
            changed[path] = text
        changed[lock], count = re.subn(
            r'(?m)(^\[\[package\]\]\nname = "logistics"\nversion = ")[^"\n]+(")',
            lambda match: match[1] + version + match[2], before[lock])
        if count != 1:
            raise ValueError('Cannot identify the locked Logistics package version.')
        written = []
        try:
            for path, text in changed.items():
                written.append(path)
                path.write_text(text)
        except OSError:
            for path in reversed(written):
                path.write_text(before[path])
            raise
    return dict(version=version, files=[str(path.relative_to(root)) for path in changed])
