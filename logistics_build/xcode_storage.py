"""Identify project-owned Xcode caches from Xcode's recorded workspace paths."""
from datetime import datetime, timezone
from pathlib import Path
import plistlib
import re
import subprocess
import time

from build_manager.retention import linked, pinned

GIB = 1024 ** 3


def workspace(path):
    """Missing/corrupt metadata is not evidence of cache ownership."""
    try:
        metadata = path / 'info.plist'
        if linked(metadata) or metadata.stat().st_size > 262144:
            return None
        data = plistlib.loads(metadata.read_bytes())
        source = Path(data['WorkspacePath'])
        if not source.is_absolute() or '..' in source.parts:
            return None
        accessed = data.get('LastAccessedDate')
        stamp = accessed.replace(tzinfo=timezone.utc).timestamp() if isinstance(accessed, datetime) else 0
        return source, max(path.stat().st_mtime, stamp)
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException):
        return None


def source_snapshot(project, source):
    parent = project / 'mobile_build/.tools/build-manager/snapshots'
    try:
        name = source.relative_to(parent).parts[0]
    except (ValueError, IndexError):
        return None
    return parent / name if re.fullmatch('[0-9a-f]{64}', name) else None


def owned_workspace(project, source):
    """Only this checkout's generated projects, never another checkout by name."""
    for name in ('mobile_build', 'Mobile'):
        try:
            relative = source.relative_to(project / name)
        except ValueError:
            continue
        return source.suffix == '.xcodeproj' and 'build' in relative.parts
    return False


def storage_group(project, *, cache_root=None, processes=None, now=None):
    project = Path(project).absolute()
    cache_root = Path(cache_root) if cache_root is not None else Path.home() / 'Library/Developer/Xcode/DerivedData'
    now = time.time() if now is None else now
    if processes is None:
        # A failed process inventory is a failed safety check, not an idle host.
        processes = subprocess.check_output(['/bin/ps', '-Ao', 'command='], text=True, timeout=15)
    lines = processes.splitlines()
    gui_open = any('/Xcode.app/Contents/MacOS/Xcode' in line or
                   re.search(r'/Xcode[^/]*\.app/Contents/MacOS/Xcode(?:\s|$)', line) for line in lines)

    def eligible(path):
        info = workspace(path)
        if not info or gui_open:
            return False
        source, accessed = info
        if not owned_workspace(project, source) or now - accessed < 3600:
            return False
        snapshot = source_snapshot(project, source)
        if snapshot and snapshot.exists() and pinned(snapshot):
            return False
        scope = str(snapshot) if snapshot else str(source)
        if any(('xcodebuild' in line or 'briefcase' in line) and
               (scope in line or str(path) in line) for line in lines):
            return False
        return True

    def lock_path(path):
        info = workspace(path)
        snapshot = source_snapshot(project, info[0]) if info else None
        return snapshot.with_suffix('.lock') if snapshot else cache_root / ('.' + path.name + '.retention.lock')

    return dict(root=cache_root, eligible=eligible, lock_path=lock_path)


def access_order(path):
    info = workspace(path)
    return (info[1] if info else path.stat().st_mtime, path.name)
