"""Resume a selected folder using a sealed folder journal and verified file ranges."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from contextlib import nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
from uuid import uuid4

from commonUtils.persistence import atomic_write_bytes
from commonUtils.persistence.publication import rename_exclusive
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.paths import resource_path
from features.rclone.transfers.download_recovery import (
    EMPTY, RestartRequired, _open_stage, _prefix, _sync_directory, _unchanged, _valid_job, recover, stage_path,
)
from .download_recovery import NativeRanges, mobile_queue


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def _directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or not info.st_ino:
        raise ValueError('The download folder was replaced. Inspect the interrupted download.')
    return [info.st_dev, info.st_ino]


class FolderQueue:
    """Read only folder jobs for the already-admitted download authority."""

    def __init__(self, queue):
        self.queue = queue

    def _path(self, key):
        record = self.queue.path(key).with_suffix('.folder')
        if record.is_symlink():
            raise ValueError('Linked transfer records cannot be opened.')
        return record

    def _validate(self, job, key):
        fields = ('parent', 'inode')
        if (not isinstance(job, dict) or job.get('id') != key or job.get('kind') != 'folder'
                or job.get('authority') != self.queue.authority or job.get('schema') != 1
                or job.get('state') not in ('creating', 'copying', 'publishing')
                or not isinstance(job.get('selection'), dict) or not isinstance(job.get('target'), str)
                or not isinstance(job.get('stage'), str) or not re.fullmatch('[a-f0-9]{32}', job['stage'])
                or any(not isinstance(job.get(name), list) or len(job[name]) != 2
                       or any(type(number) is not int for number in job[name])
                       for name in fields if name != 'inode' or job['state'] != 'creating')
                or any(type(job.get(name)) is not int or job[name] < 0 for name in ('done', 'offset', 'bytes'))
                or not isinstance(job.get('source'), dict) or type(job['source'].get('size')) is not int
                or not 0 <= job['bytes'] <= job['offset'] <= job['source']['size']
                or any(not isinstance(job.get(name), str) or not re.fullmatch('[a-f0-9]{64}', job[name])
                       for name in ('digest', 'manifest'))
                or (job.get('child') is not None and not isinstance(job['child'], dict))):
            raise ValueError('Invalid folder download checkpoint.')
        child = job.get('child')
        if child is not None:
            identity = child.get('id')
            if (not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{32}', identity)
                    or not _valid_job(child, identity, self.queue.authority)
                    or job['offset'] != job['bytes'] + child['offset']):
                raise ValueError('Invalid folder download member checkpoint.')

    def load(self, key):
        self.queue.validate()
        with _open_stage(self._path(key), os.O_RDONLY)[0] as stream:
            data = stream.read(128 * 1024 + 1)
        if len(data) > 128 * 1024:
            raise ValueError('Invalid folder download checkpoint.')
        job = json.loads(self.queue.cipher.transform(data, True))
        self._validate(job, key)
        self.queue.validate()
        return job

    def jobs(self):
        self.queue.validate()
        rows = []
        for path in sorted(self.queue.bucket.glob('*.folder')):
            try:
                rows.append(self.load(path.stem))
            except FileNotFoundError:
                continue
        return rows

    def save(self, job):
        self.queue.validate()
        self._validate(job, job['id'])
        atomic_write_bytes(self._path(job['id']), self.queue.cipher.transform(_encode(job)),
                           validate=self.queue.validate, file_mode=0o600)
        _sync_directory(self.queue.bucket)

    def remove(self, job):
        self.queue.validate()
        self._path(job['id']).unlink()
        _sync_directory(self.queue.bucket)

    @staticmethod
    def staged(target, job):
        return stage_path(target, {'id': job['stage']})

    def discard(self, key, target, *, expected=None):
        target = Path(target)
        with self.queue.writer(target):
            job = self.load(key)
            if expected is not None and expected != (key, job['offset'], job['digest']):
                raise ValueError('The saved download advanced. Review its current progress before discarding it.')
            if str(target) != job['target'] or _directory(target.parent) != job['parent']:
                raise ValueError('The download folder was moved or replaced.')
            stage = self.staged(target, job)
            if job['inode'] is not None and os.path.lexists(stage):
                self.queue.validate()
                _discard_staging_folder(stage, job['inode'])
                _sync_directory(target.parent)
            self.remove(job)


def _discard_staging_folder(stage, inode):
    failure = 'The partial folder cannot be removed safely. Inspect it before discarding.'
    if not shutil.rmtree.avoids_symlink_attacks or _directory(stage) != inode:
        raise ValueError(failure)
    fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if [info.st_dev, info.st_ino] != inode:
            raise ValueError(failure)
        for name in os.listdir(fd):
            child = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(child.st_mode):
                shutil.rmtree(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)
        if _directory(stage) != inode:
            raise ValueError(failure)
        stage.rmdir()
    finally:
        os.close(fd)


class _FolderFile:
    """Use the same crash-safe byte-range writer for the current member."""

    def __init__(self, folders, job, name):
        self.folders, self.job, self.name = folders, job, name
        self.authority = folders.queue.authority

    def writer(self, path):
        return nullcontext()  # The containing folder owns its writer lease.

    def matching(self, selection, target):
        child = self.job.get('child')
        if child is not None and (child['selection'] != selection or child['target'] != str(target)):
            raise ValueError('The interrupted folder file changed.')
        return child

    def save(self, child):
        self.job['child'] = child
        self.job['offset'] = self.job['bytes'] + child['offset']
        self.folders.save(self.job)

    def remove(self, child):
        self.job['digest'] = _extend(self.job['digest'], self.name, child['digest'])
        self.job['done'] += 1
        self.job['bytes'] += child['offset']
        self.job['offset'] = self.job['bytes']
        self.job['child'] = None
        self.folders.save(self.job)


class _VersionedRanges(NativeRanges):
    def __init__(self, source, path, destination, bandwidth, check, version):
        super().__init__(source, path, destination, bandwidth, check)
        self.version = version

    def stat(self):
        if super().stat() != self.version:
            raise ValueError('A file in the selected folder changed. Discard the interrupted job.')
        return self.version


def _extend(previous, name, digest):
    return sha256(_encode([previous, name, digest])).hexdigest()


def _manifest(source, path, destination, bandwidth, check, cancelled):
    pending = [path]
    entries = {}
    while pending:
        folder = pending.pop()
        check()
        for row in source.list(folder, cancelled=cancelled):
            child = resource_path(row['path'])
            if child.rpartition('/')[0] != folder or child == folder:
                raise ValueError('The remote listed an item outside the selected folder.')
            name = child[len(path) + 1:] if path else child
            if name in entries:
                raise ValueError('The remote returned the same entry twice.')
            if row['directory']:
                pending.append(child)
                entries[name] = None
            else:
                entries[name] = NativeRanges(source, child, destination, bandwidth, check).stat()
    return dict(sorted(entries.items()))


def _verify(stage, files, job, check):
    previous = EMPTY
    snapshots = {}
    for name, version in files[:job['done']]:
        check()
        path = stage / name
        if path.resolve(strict=True) != path:
            raise ValueError('The partial folder contains a linked file.')
        stream, _ = _open_stage(path, os.O_RDONLY)
        with stream:
            before = path.lstat()
            if before.st_size != version['size']:
                raise ValueError('A completed file in the partial folder changed.')
            digest = _prefix(stream, version['size'], '', check)[0].hexdigest()
            if not _unchanged(path, before):
                raise ValueError('A completed file in the partial folder changed.')
        snapshots[path] = before
        previous = _extend(previous, name, digest)
    if previous != job['digest']:
        raise ValueError('A completed file in the partial folder changed.')
    return snapshots


def _check_tree(folder, expected, check):
    seen = set()
    directories = {}
    pending = [folder]
    while pending:
        check()
        parent = pending.pop()
        before = parent.lstat()
        if not stat.S_ISDIR(before.st_mode):
            raise ValueError('The staged folder changed during verification.')
        directories[parent] = before
        for path in parent.iterdir():
            name = path.relative_to(folder).as_posix()
            mode = path.lstat().st_mode
            directory = stat.S_ISDIR(mode)
            if (name not in expected or directory != (expected[name] is None)
                    or not (directory or stat.S_ISREG(mode))):
                raise ValueError('The staged folder has unexpected contents.')
            if directory:
                pending.append(path)
            seen.add(name)
    if seen != expected.keys():
        raise ValueError('The staged folder is incomplete.')
    return directories


def _check_publication(directories, files, check):
    for path, before in directories.items():
        check()
        current = path.lstat()
        if (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_ctime_ns) != (
                before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns):
            raise ValueError('The staged folder changed before publication.')
    for path, before in files.items():
        check()
        if not _unchanged(path, before):
            raise ValueError('The staged folder changed before publication.')


def run_folder_download(root, source, path, destination, target, cancelled, progress, options, key=None):
    path = resource_path(path)
    if destination.private:
        if key:
            raise ValueError('Restore this job to its original unencrypted storage.')
        raise RestartRequired('Folder resume needs ordinary on-device storage. Continue without resume?')
    target = destination.relative(target)
    physical = destination.transfer_location(target, directory=True)
    selection = dict(path=path, name=target, root=str(destination.root),
                     namespace=getattr(destination, 'storage_namespace', ''), encrypted=False)
    parent_id = _directory(physical.parent)
    bandwidth = getattr(options, 'bw_limit', None)
    folders = FolderQueue(mobile_queue(root, source))

    def check():
        check_cancelled(cancelled)
        source.check()
        if (destination.transfer_location(target, directory=True) != physical
                or _directory(physical.parent) != parent_id):
            raise ValueError('The download folder was moved or replaced.')

    check()
    with folders.queue.writer(physical):
        job = folders.load(key) if key else next(
            (row for row in folders.jobs() if row['selection'] == selection and row['target'] == str(physical)), None)
        if job is not None and (job['selection'] != selection or job['target'] != str(physical)
                                or job['parent'] != parent_id):
            raise ValueError('The download selection or destination changed.')
        if os.path.lexists(physical) and (job is None or job['state'] != 'publishing'
                                        or os.path.lexists(folders.staged(physical, job))):
            raise FileExistsError('An item with that name already exists. Choose another name.')
        progress(phase='Discovering / checking files', files=0, total_files=0, done=0, total=0)
        try:
            entries = _manifest(source, path, destination, bandwidth, check, cancelled)
        except RestartRequired as error:
            if job is not None:
                raise ValueError('A file no longer supports verified resume. Discard this job before starting again.') from error
            raise RestartRequired('At least one file cannot supply verified download ranges. Continue without resume?') from error
        files = [(name, row) for name, row in entries.items() if row is not None]
        manifest = sha256(_encode(entries)).hexdigest()
        total = sum(row['size'] for _, row in files)
        if job is None:
            job = dict(id=uuid4().hex, kind='folder', authority=folders.queue.authority, schema=1, state='creating',
                       selection=selection, target=str(physical), parent=parent_id, inode=None, stage=uuid4().hex,
                       source={'size': total}, manifest=manifest, done=0, bytes=0, offset=0, digest=EMPTY, child=None)
            folders.save(job)
        if job['manifest'] != manifest or job['source']['size'] != total or job['done'] > len(files):
            raise ValueError('The remote folder changed. Discard the interrupted job before starting again.')
        stage = folders.staged(physical, job)
        if os.path.lexists(physical):
            if (_directory(physical) != job['inode'] or job['done'] != len(files)
                    or job['bytes'] != total or job['child'] is not None):
                raise ValueError('The published folder could not be matched to the verified download.')
            directories = _check_tree(physical, entries, check)
            snapshots = _verify(physical, files, job, check)
            _check_publication(directories, snapshots, check)
            _sync_directory(physical.parent)
            folders.remove(job)
            return True
        if job['state'] == 'creating':
            if os.path.lexists(stage):
                # A crash before the inode was saved leaves an unproven directory.
                job['stage'] = uuid4().hex
                folders.save(job)
                stage = folders.staged(physical, job)
            stage.mkdir(mode=0o700)
            _sync_directory(physical.parent)
            job.update(inode=_directory(stage), state='copying')
            folders.save(job)

        def check_stage():
            check()
            if _directory(stage) != job['inode']:
                raise ValueError('The partial folder was replaced. Inspect the interrupted download.')

        _verify(stage, files, job, check_stage)
        for name, row in entries.items():
            check_stage()
            if row is None:
                folder = stage / name
                if folder.parent.resolve(strict=True) != folder.parent:
                    raise ValueError('The partial download folder contains a link.')
                folder.mkdir(mode=0o700, exist_ok=True)
                _directory(folder)
        for name, version in files[job['done']:]:
            check_stage()
            member = '/'.join(filter(None, (path, name)))
            target_file = stage / name
            child_selection = {'path': member}
            tracker = _FolderFile(folders, job, name)
            if target_file.parent.resolve(strict=True) != target_file.parent:
                raise ValueError('The partial download folder contains a link.')

            def report(offset, size):
                progress(phase='Transferring', files=job['done'], total_files=len(files),
                         done=job['bytes'] + offset, total=total)

            ranges = _VersionedRanges(source, member, destination, bandwidth, check_stage, version)
            try:
                recover(tracker, child_selection, target_file, ranges, check=check_stage, progress=report)
            except RestartRequired as error:
                raise ValueError('A file no longer supports verified resume. Discard this job before starting again.') from error

        progress(phase='Sync complete; verifying local copy', files=len(files), total_files=len(files), done=total, total=total)
        if sha256(_encode(_manifest(source, path, destination, bandwidth, check_stage, cancelled))).hexdigest() != manifest:
            raise ValueError('The remote folder changed. Discard the interrupted job before starting again.')
        directories = _check_tree(stage, entries, check_stage)
        snapshots = _verify(stage, files, job, check_stage)
        for folder in reversed(directories):
            check_stage()
            _sync_directory(folder)
        job['state'] = 'publishing'
        folders.save(job)
        _check_publication(directories, snapshots, check_stage)
        check_stage()
        rename_exclusive(stage, physical)
        _sync_directory(physical.parent)
        folders.remove(job)
        return True
