"""Resume a selected folder using a sealed folder journal and verified file ranges."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
from threading import Event, Lock
from time import monotonic, sleep
from uuid import uuid4

from commonUtils.persistence import atomic_write_bytes
from commonUtils.persistence.publication import rename_exclusive
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.paths import resource_path
from features.rclone.transfers.download_recovery import (
    EMPTY, RestartRequired, _open_stage, _sync_directory, _unchanged, _valid_job, _verify_bytes, recover, stage_path,
)
from .download_recovery import NativeRanges, mobile_queue

FOLDER_TRANSFERS = 10
FOLDER_CHECKPOINT_WINDOW = 40
FOLDER_RECORD_LIMIT = 512 * 1024


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
                or job.get('authority') != self.queue.authority or job.get('schema') not in (1, 2)
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
                       for name in ('digest', 'manifest'))):
            raise ValueError('Invalid folder download checkpoint.')
        if job['schema'] == 1:
            child = job.pop('child', None)
            job['members'] = {str(job['done']): child} if child is not None else {}
            job['schema'] = 2
        members = job.get('members')
        indices = {str(index) for index in range(job['done'], job['done'] + FOLDER_CHECKPOINT_WINDOW)}
        if (not isinstance(members, dict) or not members.keys() <= indices
                or (members and job['state'] != 'copying')):
            raise ValueError('Invalid folder download member checkpoints.')
        for child in members.values():
            if not isinstance(child, dict):
                raise ValueError('Invalid folder download member checkpoint.')
            identity = child.get('id')
            if (not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{32}', identity)
                    or not _valid_job(child, identity, self.queue.authority)
                    or type(child.get('complete', False)) is not bool
                    or (child.get('complete') and child['state'] != 'publishing')):
                raise ValueError('Invalid folder download member checkpoint.')
        if job['offset'] != job['bytes'] + sum(child['offset'] for child in members.values()):
            raise ValueError('Invalid folder download checkpoint offset.')

    def load(self, key):
        self.queue.validate()
        with _open_stage(self._path(key), os.O_RDONLY)[0] as stream:
            data = stream.read(FOLDER_RECORD_LIMIT + 1)
        if len(data) > FOLDER_RECORD_LIMIT:
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
    """Share the folder journal while each member owns its byte-range writer."""

    def __init__(self, folders, job, files, index, lock):
        self.folders, self.job, self.files, self.index, self.lock = folders, job, files, str(index), lock
        self.authority = folders.queue.authority

    def writer(self, path):
        return nullcontext()  # The containing folder owns its writer lease.

    def matching(self, selection, target):
        with self.lock:
            child = self.job['members'].get(self.index)
            child = child.copy() if child is not None else None
        if child is not None and (child['selection'] != selection or child['target'] != str(target)):
            raise ValueError('The interrupted folder file changed.')
        return child

    def save(self, child):
        with self.lock:
            self.job['members'][self.index] = child.copy()
            self.save_folder()

    def remove(self, child):
        with self.lock:
            members = self.job['members']
            members[self.index] = dict(child, complete=True)
            while (first := members.get(str(self.job['done']))) is not None and first.get('complete'):
                index = self.job['done']
                name, _ = self.files[index]
                self.job['digest'] = _extend(self.job['digest'], name, first['digest'])
                self.job['done'] += 1
                self.job['bytes'] += first['offset']
                del members[str(index)]
            self.save_folder()

    def save_folder(self):
        self.job['offset'] = self.job['bytes'] + sum(child['offset'] for child in self.job['members'].values())
        self.folders.save(self.job)


class _VersionedRanges(NativeRanges):
    def __init__(self, source, path, destination, check, version, throttle):
        super().__init__(source, path, destination, None, check)
        self.version = version
        self.initial_stat = True
        self.throttle = throttle

    def stat(self):
        # The initial manifest already fetched this version. Every range still
        # compares its request with the live remote version, and the final stat
        # rechecks it even for empty files.
        if self.initial_stat:
            self.initial_stat = False
            return self.version
        if super().stat() != self.version:
            raise ValueError('A file in the selected folder changed. Discard the interrupted job.')
        return self.version

    def read(self, version, offset, count):
        self.throttle(count, self.check)
        return super().read(version, offset, count)


def _folder_throttle(bandwidth):
    lock = Lock()
    next_chunk = 0

    def throttle(count, check):
        nonlocal next_chunk
        if not bandwidth:
            return
        with lock:
            next_chunk = deadline = max(next_chunk, monotonic()) + count / (bandwidth * 1024 * 1024)
        while (remaining := deadline - monotonic()) > 0:
            check()
            sleep(min(remaining, .1))

    return throttle


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


def _verify(stage, files, job, check, progress):
    previous = EMPTY
    snapshots = {}
    measured = 0
    verification_total = job['bytes'] + sum(child['offset'] for child in job['members'].values()
                                            if child.get('complete'))

    def report(done, size):
        progress(measured + done, verification_total)

    for name, version in files[:job['done']]:
        check()
        path = stage / name
        if path.resolve(strict=True) != path:
            raise ValueError('The partial folder contains a linked file.')
        try:
            before, digest = _verify_bytes(path, version['size'], check, progress=report)
        except (OSError, ValueError) as error:
            raise ValueError(f'Could not verify the saved file {path.name}. {error}') from error
        snapshots[path] = before
        previous = _extend(previous, name, digest)
        measured += version['size']
    if previous != job['digest'] or measured != job['bytes']:
        raise ValueError('The saved folder contents differ from their verified checksums. The partial data was kept.')
    for index, child in job['members'].items():
        if int(index) >= len(files):
            raise ValueError('The interrupted folder file changed.')
        name, version = files[int(index)]
        path = stage / name
        if child['target'] != str(path) or child['source'] != version:
            raise ValueError('The interrupted folder file changed.')
        if child.get('complete'):
            check()
            if path.resolve(strict=True) != path:
                raise ValueError('The partial folder contains a linked file.')
            before, digest = _verify_bytes(path, version['size'], check, expected=child['inode'], progress=report)
            if digest != child['digest']:
                raise ValueError('The saved folder contents differ from their verified checksums. The partial data was kept.')
            snapshots[path] = before
            measured += version['size']
    return snapshots


def _copy_members(folders, job, files, stage, source, path, destination, bandwidth, check, progress, snapshots, workers):
    lock = Lock()
    stopped = Event()
    active = {}
    verifying = {}
    total = job['source']['size']
    throttle = _folder_throttle(bandwidth)

    def check_member():
        check_cancelled(stopped.is_set)
        check()

    def report():
        members = job['members']
        complete = job['done'] + sum(bool(child.get('complete')) for child in members.values())
        verified_bytes = job['bytes'] + sum(child['offset'] if child.get('complete') else verifying.get(index, 0)
                                           for index, child in members.items())
        phase = 'Verifying the local copy…' if job['offset'] == total and not active else 'Transferring'
        progress(phase=phase, files=complete, total_files=len(files), done=job['offset'],
                 total=total, active=len(active), active_files=list(active.values()),
                 verified_bytes=verified_bytes, verification_total=total)

    def verified(target, snapshot):
        with lock:
            snapshots[target] = snapshot

    def copy(index):
        check_member()
        name, version = files[index]
        member = '/'.join(filter(None, (path, name)))
        target = stage / name
        tracker = _FolderFile(folders, job, files, index, lock)
        if target.parent.resolve(strict=True) != target.parent:
            raise ValueError('The partial download folder contains a link.')

        def copied(offset, size):
            with lock:
                if offset < size:
                    active[name] = dict(name=name, bytes=offset, size=size)
                else:
                    active.pop(name, None)
                report()

        def verify_progress(done, size):
            with lock:
                verifying[tracker.index] = done
                report()

        try:
            with _VersionedRanges(source, member, destination, check_member, version, throttle) as ranges:
                recover(tracker, {'path': member}, target, ranges, check=check_member,
                        progress=copied, verify_progress=verify_progress, verified=verified)
        except RestartRequired as error:
            raise ValueError('A file no longer supports verified resume. Discard the interrupted job before starting again.') from error
        with lock:
            verifying.pop(tracker.index, None)
            report()

    if shutil.disk_usage(stage).free < total - job['offset']:
        raise OSError('Insufficient free space for the remaining folder download.')
    pending = set()
    index = job['done']
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='Logistics folder download') as executor:
        try:
            while index < len(files) or pending:
                check()
                # Keep a bounded window beyond the verified prefix. Finished
                # members in this window survive an interruption out of order.
                with lock:
                    limit = min(len(files), job['done'] + FOLDER_CHECKPOINT_WINDOW)
                    while index < limit and len(pending) < workers:
                        name, _ = files[index]
                        if stage / name not in snapshots:
                            pending.add(executor.submit(copy, index))
                        index += 1
                if not pending:
                    break
                finished, pending = wait(pending, timeout=.2, return_when=FIRST_COMPLETED)
                for future in finished:
                    future.result()
        except BaseException:
            stopped.set()
            for future in pending:
                future.cancel()
            cancel = getattr(source.client, 'cancel', None)
            if cancel is not None:
                try:
                    cancel()
                except (OSError, ValueError):
                    pass
            raise


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


def run_folder_download(root, source, path, destination, target, cancelled, progress, options, key=None, *, parallel=True):
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
            job = dict(id=uuid4().hex, kind='folder', authority=folders.queue.authority, schema=2, state='creating',
                       selection=selection, target=str(physical), parent=parent_id, inode=None, stage=uuid4().hex,
                       source={'size': total}, manifest=manifest, done=0, bytes=0, offset=0, digest=EMPTY, members={})
            folders.save(job)
        if job['manifest'] != manifest or job['source']['size'] != total or job['done'] > len(files):
            raise ValueError('The remote folder changed. Discard the interrupted job before starting again.')
        stage = folders.staged(physical, job)

        def verify_progress(done, size, *, copied=None, status='Verifying the saved bytes…'):
            progress(phase='Verifying the local copy…', files=job['done'],
                     total_files=len(files), done=job['offset'] if copied is None else copied,
                     total=total, verified_bytes=done, verification_total=size,
                     verification_status=status)

        if os.path.lexists(physical):
            if (_directory(physical) != job['inode'] or job['done'] != len(files)
                    or job['bytes'] != total or job['members']):
                raise ValueError('The published folder could not be matched to the verified download.')
            directories = _check_tree(physical, entries, check)
            snapshots = _verify(physical, files, job, check, verify_progress)
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

        # Rehash the sealed prefix once after a restart. Files completed in
        # this run contribute the verified inode returned by the file writer.
        snapshots = _verify(stage, files, job, check_stage, verify_progress)
        for name, row in entries.items():
            check_stage()
            if row is None:
                folder = stage / name
                if folder.parent.resolve(strict=True) != folder.parent:
                    raise ValueError('The partial download folder contains a link.')
                folder.mkdir(mode=0o700, exist_ok=True)
                _directory(folder)
        _copy_members(folders, job, files, stage, source, path, destination, bandwidth, check_stage,
                      progress, snapshots, FOLDER_TRANSFERS if parallel else 1)

        verify_progress(total, total, copied=total, status='Checking the source before publishing the folder…')
        if sha256(_encode(_manifest(source, path, destination, bandwidth, check_stage, cancelled))).hexdigest() != manifest:
            raise ValueError('The remote folder changed. Discard the interrupted job before starting again.')
        directories = _check_tree(stage, entries, check_stage)
        if job['done'] != len(files) or job['bytes'] != total or len(snapshots) != len(files):
            raise ValueError('The staged folder does not have a verified copy of every file.')
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
