"""Share blocks between exact Android test APK copies in completed Manager runs."""

from contextlib import ExitStack
import ctypes
import errno
import os
from pathlib import Path
import re
import stat
import sys
from tempfile import TemporaryDirectory

from build_manager.history import load_run
from build_manager.locking import workspace_lock
from build_manager.profiles import save_json
from build_manager.retention import has_retention_protection, linked, nested_workflow_hold_reason
from commonUtils.runtime.streams import file_sha256
from logistics_build.storage_extras import read

MANAGER_RESULTS = ('test-results/build-manager', 'tmp/test-results/build-manager')
APK_ROOTS = ('tmp/test-results', 'test-results', 'mobile_build/.tools/build-manager/workspaces/android')


def unlinked(path):
    return not any(linked(part) for part in (path, *path.parents))


def clone_file(source, destination):
    """Use macOS copy-on-write; never substitute a full copy."""
    clone = ctypes.CDLL(None, use_errno=True).clonefile
    clone.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int)
    clone.restype = ctypes.c_int
    if clone(os.fsencode(source), os.fsencode(destination), 0):
        error = ctypes.get_errno()
        if error in {errno.ENOTSUP, errno.EXDEV, errno.EINVAL, errno.ENOSYS}:
            return False
        raise OSError(error, os.strerror(error), str(destination))
    return True


def verified_clone(source, target, digest, *, apply):
    if not all(unlinked(path) and path.is_file() for path in (source, target)):
        return False
    source_info, target_info = source.stat(), target.stat()
    if (source_info.st_dev != target_info.st_dev or source_info.st_ino == target_info.st_ino
            or source_info.st_size != target_info.st_size or target_info.st_nlink != 1):
        return False
    marker = target.with_name('.' + target.name + '.clone.json')
    signature = dict(sha256=digest, inode=target_info.st_ino, mtime=target_info.st_mtime_ns)
    try:
        if read(marker, {}) == signature:
            return False
    except (OSError, ValueError):
        return False
    if file_sha256(source) != digest or file_sha256(target) != digest:
        return False
    if not apply:
        return True
    with TemporaryDirectory(dir=target.parent, prefix='.test-apk-clone-') as directory:
        clone = Path(directory) / 'package.apk'
        if not clone_file(source, clone) or file_sha256(clone) != digest:
            return False
        os.chmod(clone, stat.S_IMODE(target_info.st_mode))
        os.utime(clone, ns=(target_info.st_atime_ns, target_info.st_mtime_ns))
        os.replace(clone, target)
        signature['inode'] = target.stat().st_ino
        save_json(marker, signature)
    return True


def completed_run_copies(root, run, *, apply, targets=None):
    if (not any(run.is_relative_to(root / folder) for folder in APK_ROOTS[:2])
            or not unlinked(run) or run != run.resolve() or not all(unlinked(run / name) and (run / name).is_file()
                                            for name in ('plan.json', 'result.json'))
            or not unlinked(run / 'artifacts') or not any((run / 'artifacts').glob('*.apk'))):
        return []
    changed = []
    with ExitStack() as locks:
        locks.enter_context(workspace_lock(run / 'supervisor.lock'))
        locks.enter_context(workspace_lock(run.parent / ('.' + run.name + '.retention.lock')))
        plan, report = load_run(run / 'result.json')
        if (plan.project != 'Logistics' or report['status'] not in {'passed', 'failed', 'cancelled'}
                or report.get('holds') or any(row['status'] == 'unknown' for row in report['phases'])
                or has_retention_protection(run) or nested_workflow_hold_reason(run)
                or any((p / '.keep').exists() for p in run.parents if p.is_relative_to(root))):
            return changed
        declarations = {phase.id: phase.artifacts for phase in plan.phases}
        for phase in report['phases']:
            for artifact in phase.get('artifacts', ()):
                source = Path(artifact.get('original_path') or '')
                target = Path(artifact['path'])
                digest = artifact['sha256']
                if (source.name != 'validated-test.apk' or str(source) not in declarations[phase['id']]
                        or not re.fullmatch(r'emulator-[0-9a-f]{32}', source.parent.name)
                        or source.parent.parent not in {root / folder for folder in APK_ROOTS}
                        or target.parent != run / 'artifacts' or target.suffix != '.apk'
                        or (targets is not None and target not in targets)
                        or not re.fullmatch(r'[0-9a-f]{64}', digest)):
                    continue
                # Manager uses the backend workspace lock for Android branches.
                if any((parent / '.keep').exists() for parent in source.parents if parent.is_relative_to(root)):
                    continue
                android = root / APK_ROOTS[-1]
                if not unlinked(android) or not android.is_dir():
                    continue
                with workspace_lock(android / 'operation.lock'):
                    if verified_clone(source, target, digest, apply=apply):
                        changed.append(dict(path=str(target), bytes=target.stat().st_size))
    return changed


def coalesce_test_apks(root, *, apply=False, runs=None, targets=None):
    """Visit direct saved-run children unless older run folders are explicitly supplied."""
    if sys.platform != 'darwin':
        return []
    root = Path(root).resolve()
    if runs is None:
        runs = (path.parent for folder in MANAGER_RESULTS for path in (root / folder).glob('*/result.json'))
    changed = []
    for run in dict.fromkeys(Path(path).absolute() for path in runs):
        try:
            changed += completed_run_copies(root, run, apply=apply, targets=targets)
        except (OSError, ValueError, RuntimeError):
            # Malformed, busy and unsupported runs remain available for review.
            continue
    return changed
