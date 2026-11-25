"""Retention for reviewed raw attachments from completed standalone validations."""

import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import time

from build_manager.locking import workspace_lock
from build_manager.profiles import save_json
from build_manager.retention import linked, protection_reason
from commonUtils.runtime.streams import file_sha256
from logistics_build.storage_extras import private, read

AGE_DAYS = 14
ATTACHMENT_SUFFIXES = {'.log', '.jsonl', '.stderr', '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mov'}
RESULT_ROOTS = ('tmp/test-results', 'test-results')
RELEASE_DIRECTORY = re.compile(r'(^|[-_.])(release|alpha\d*|beta\d*|testflight|firebase|promotion[s]?)([-_.]|$)', re.I)
PROBE_ATTACHMENTS = {
    'ios': ('ios-create.log', 'ios-build.log', 'ios-console.log', 'ios-restart-console.log', 'ios-final.png'),
    'android': ('android-create.log', 'android-build.log', 'android-emulator.log', 'android-final.png'),
}


def evidence_paths(root, report, attachment):
    """Accept explicitly selected raw local files within the report's own run."""
    for path in (report, attachment):
        if not path.is_absolute() or any(linked(part) for part in (path, *path.parents)) or path != path.resolve():
            return False
    base = next((root / folder for folder in RESULT_ROOTS if report.is_relative_to(root / folder)), None)
    if (base is None or report.parent == base or not attachment.is_relative_to(report.parent)
            or report.suffix.lower() not in {'.json', '.xml'}
            or attachment.suffix.lower() not in ATTACHMENT_SUFFIXES):
        return False
    for directory in attachment.parents:
        if directory == base:
            break
        if (directory.name.startswith('.') or directory.name in {'build-manager', 'mobile-evidence', 'artifacts'}
                or RELEASE_DIRECTORY.search(directory.name) or (directory / 'plan.json').exists()):
            return False
    return True


def identity(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('Evidence must be a regular file.')
    return dict(size=info.st_size, mtime_ns=info.st_mtime_ns, inode=info.st_ino, device=info.st_dev)


def record_folder(root):
    folder = private(root) / 'standalone-evidence'
    if any(linked(part) for part in (folder, *folder.parents)):
        raise ValueError('Standalone evidence registration refuses linked metadata storage.')
    return folder


def register(root, report, attachments):
    """Enroll exact file identities after a standalone producer closes its outputs."""
    root = Path(root).resolve()
    report = Path(report).absolute()
    attachments = tuple(dict.fromkeys(Path(path).absolute() for path in attachments))
    if not attachments:
        return []
    folder = record_folder(root)
    records = {}
    for path in attachments:
        if not evidence_paths(root, report, path):
            raise ValueError('Select a standalone report and its raw attachments outside protected release storage.')
        records[path] = identity(path)
    report_digest = file_sha256(report)
    with workspace_lock(folder / 'registry.lock'):
        for path, metadata in records.items():
            key = hashlib.sha256(os.fsencode(path.relative_to(root))).hexdigest()
            marker = folder / (key + '.json')
            if linked(marker):
                raise ValueError('Standalone evidence record is linked.')
            save_json(marker, dict(schema=1, path=str(path), report=str(report),
                                  report_sha256=report_digest, identity=metadata))
    return list(map(str, records))


def protected(root, attachment):
    """Honor ancestor pins and holds, including standalone file-specific pins."""
    if os.path.lexists(attachment.with_name(attachment.name + '.keep')):
        return True
    for path in (attachment, *attachment.parents):
        if path != attachment and os.path.lexists(path / '.keep'):
            return True
        hold = path.with_name('.' + path.name + '.manager-holds.json')
        if os.path.lexists(hold) and (path == attachment or protection_reason(path)):
            return True
        if path == root:
            break
    return False


def prune(root, *, apply=False, now=None, selections=None):
    """Remove only expired registered files, rechecking the report and file identity."""
    root = Path(root).resolve()
    folder = record_folder(root)
    cutoff = (time.time() if now is None else now) - AGE_DAYS * 86400
    removed = []
    if not folder.is_dir():
        return removed
    with workspace_lock(folder / 'registry.lock'):
        for marker in sorted(folder.glob('*.json')):
            try:
                record = read(marker)
                path, report = Path(record['path']), Path(record['report'])
                if selections is not None and path not in selections:
                    continue
                if (record['schema'] != 1 or not evidence_paths(root, report, path) or protected(root, path)
                        or not path.is_file() or not report.is_file()):
                    continue
                metadata = identity(path)
                if (metadata != record['identity'] or metadata['mtime_ns'] >= cutoff * 10**9
                        or file_sha256(report) != record['report_sha256']
                        or identity(path) != metadata):
                    continue
                if apply:
                    path.unlink()
                    marker.unlink()
                removed.append(str(path))
            except (OSError, ValueError, KeyError, TypeError):
                # Missing, changed or unreadable evidence stays outside cleanup.
                continue
    return removed


def register_probe(root, report, names):
    """Mark only the producer's named attachments in the checkout-local results layout."""
    root = Path(root).resolve()
    report = Path(report).absolute()
    if not report.is_relative_to(root / RESULT_ROOTS[0]) or not report.is_file():
        return
    attachments = [report.parent / name for name in names if (report.parent / name).is_file()]
    attachments = [path for path in attachments if evidence_paths(root, report, path)]
    if attachments:
        try:
            register(root, report, attachments)
        except (OSError, ValueError, RuntimeError) as error:
            print(f'Standalone diagnostics retained without expiry: {error}', file=sys.stderr)


def register_mobile_probe(root, output, platform):
    """Record disposable simulator diagnostics after a passed standalone probe."""
    output = Path(output)
    reports = [output / f'{platform}-result.json']
    if (output / 'matrix.json').is_file():
        reports.extend(output.glob(f'*/{platform}-result.json'))
    for report in reports:
        try:
            cleanup = read(report.with_name(f'{platform}-cleanup.json'), {})
            result = read(report, {})
            if cleanup.get('removed') is True and result.get('success') is True:
                register_probe(root, report, PROBE_ATTACHMENTS[platform])
        except (OSError, ValueError, AttributeError):
            # An unclassified or unreadable diagnostic remains available.
            continue
