"""Crash-safe checkpoints for one selected file, scoped to its unlocked credentials."""
from contextlib import contextmanager
from hashlib import new as new_hash, sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
from uuid import uuid4

from commonUtils.persistence import atomic_write_bytes
from commonUtils.persistence.locking import file_lock
from commonUtils.persistence.publication import rename_exclusive

CHUNK = 4 * 1024 * 1024  # Native range limit and a whole number of crypt data blocks.
MINIMUM = 2 * CHUNK
EMPTY = sha256(b'').hexdigest()


class RestartRequired(ValueError):
    """The normal one-shot copy needs explicit authorization to start at zero."""
    checkpoint = None

    def bind(self, job):
        if job is not None:
            self.checkpoint = (job['id'], job['offset'], job['digest'])
            self.args = (f"{self} Restarting discards {job['offset']:,} verified bytes.",)
        return self


def _sync_directory(path):
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _independent(info):
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not info.st_ino:
        raise ValueError('The download needs an independent regular file with a stable identity.')
    return [info.st_dev, info.st_ino]


def stage_path(target, job):
    return target.with_name('.logistics-' + job['id'] + '.00000000.partial')


class DownloadQueue:
    """Opaque random job names. Only a matching active authority can load a bucket."""

    def __init__(self, root, authority, check, cipher=None):
        self.root = Path(root) / 'DownloadQueue'
        self.check, self.cipher = check, cipher
        self.authority = sha256(json.dumps(authority, sort_keys=True).encode()).hexdigest()
        self.bucket = self.root / self.authority

    def validate(self):
        self.check()
        if any(part.is_symlink() for part in (self.bucket, self.root)):
            raise ValueError('Linked transfer records cannot be opened.')

    def path(self, key):
        if not re.fullmatch('[0-9a-f]{32}', key):
            raise ValueError('Invalid download identity.')
        path = self.bucket / (key + '.job')
        if path.is_symlink():
            raise ValueError('Linked transfer records cannot be opened.')
        return path

    def load(self, key):
        self.validate()
        path = self.path(key)
        with path.open('rb') as stream:
            _independent(os.fstat(stream.fileno()))
            data = stream.read(128 * 1024 + 1)
        if len(data) > 128 * 1024:
            raise ValueError('Invalid download record size.')
        if self.cipher:
            data = self.cipher.transform(data, True)
        job = json.loads(data)
        if not _valid_job(job, key, self.authority):
            raise ValueError('Invalid download checkpoint.')
        self.validate()
        return job

    def jobs(self):
        self.validate()
        result = []
        for path in sorted(self.bucket.glob('*.job')):
            try:
                result.append(self.load(path.stem))
            except FileNotFoundError:
                continue  # Another worker completed publication.
        self.validate()
        return result

    def matching(self, selection, target):
        return next((job for job in self.jobs()
                     if job['selection'] == selection and job['target'] == str(target)), None)

    def save(self, job):
        self.validate()
        data = json.dumps(job).encode()
        if self.cipher:
            data = self.cipher.transform(data)
        atomic_write_bytes(self.path(job['id']), data, validate=self.validate, file_mode=0o600)
        _sync_directory(self.bucket)

    @contextmanager
    def writer(self, target):
        self.validate()
        self.bucket.mkdir(parents=True, exist_ok=True, mode=0o700)
        _sync_directory(self.root.parent)
        _sync_directory(self.root)
        # A bounded set of stable locks also serializes duplicate selections in other processes.
        stripe = sha256(os.fsencode(target)).hexdigest()[:2]
        path = self.root / (stripe + '.lock')
        if path.is_symlink():
            raise ValueError('Linked transfer lock.')
        with file_lock(path) as acquired:
            if not acquired:
                raise ValueError('Another download is using this destination. Retry when it finishes.')
            self.validate()
            yield

    def remove(self, job):
        self.validate()
        self.path(job['id']).unlink()
        _sync_directory(self.bucket)

    def discard(self, key, target, *, expected=None):
        with self.writer(target):
            self._discard(self.load(key), target, expected)

    def _discard(self, job, target, expected, restart_size=None):
        if expected is not None and expected != (job['id'], job['offset'], job['digest']):
            raise ValueError('The saved download advanced. Review its current progress before discarding it.')
        parent = target.parent.stat()
        if str(target) != job['target'] or [parent.st_dev, parent.st_ino] != job['parent']:
            raise ValueError('Download destination changed.')
        stage = stage_path(target, job)
        owned = os.path.lexists(stage)
        if owned and job['state'] == 'creating':
            owned = bool(_reserved_inode(stage, job))
        elif owned and _independent(stage.lstat()) != job['inode']:
            raise ValueError('The partial file was replaced. Move it aside before discarding this job.')
        if restart_size is not None:
            available = shutil.disk_usage(target.parent).free
            if owned:
                info = stage.lstat()
                available += info.st_blocks * 512 if hasattr(info, 'st_blocks') else info.st_size
            if available < restart_size:
                raise OSError('Insufficient free space to restart the download.')
        if owned:
            stage.unlink()
            _sync_directory(target.parent)
        if job['state'] == 'creating' and job.get('reservation'):
            temporary = _allocation(target, job)
            if os.path.lexists(temporary) and _reserved_inode(temporary, job):
                temporary.unlink()
                _sync_directory(target.parent)
        self.remove(job)

    @contextmanager
    def restart(self, selection, target, approved, required):
        with self.writer(target):
            if os.path.lexists(target):
                raise FileExistsError('An item with that name already exists. Choose another name.')
            job = self.matching(selection, target)
            if job:
                if not approved or approved[0] != job['id']:
                    raise ValueError('A saved download exists. Review it in Interrupted downloads before restarting.')
                self._discard(job, target, approved, restart_size=required)
            elif approved:
                raise ValueError('The saved download was completed or discarded. Select the source again.')
            yield


def _valid_job(job, key, authority):
    if not isinstance(job, dict):
        return False
    source, offset, state = job.get('source'), job.get('offset'), job.get('state')
    if (not isinstance(source, dict) or type(source.get('size')) is not int or
            type(offset) is not int or not 0 <= offset <= source['size']):
        return False
    def identity(value):
        return isinstance(value, list) and len(value) == 2 and all(type(n) is int for n in value)
    return (job.get('id') == key and job.get('authority') == authority and job.get('schema') == 1
            and isinstance(job.get('selection'), dict) and isinstance(job.get('target'), str)
            and identity(job.get('parent')) and type(source.get('encoded')) is bool
            and 'version' in source and isinstance(job.get('digest'), str)
            and re.fullmatch('[0-9a-f]{64}', job['digest'])
            and ((state == 'creating' and offset == 0 and job.get('inode') is None and job['digest'] == EMPTY)
                 or (state in ('copying', 'publishing') and identity(job.get('inode'))
                     and (state == 'copying' or offset == source['size']))))


def _reservation(job, identity):
    # Bind the marker to this particular inode. Even a byte-for-byte copy
    # at the stage path cannot be mistaken for the original allocation.
    return sha256(f"{job['reservation']}:{identity[0]}:{identity[1]}".encode()).digest()


def _allocation(target, job):
    name = sha256(job['reservation'].encode()).hexdigest()[:32]
    return stage_path(target, {'id': name})


def _reserved_inode(stage, job):
    if not job.get('reservation') or not stat.S_ISREG(stage.lstat().st_mode):
        return None
    try:
        stream, identity = _open_stage(stage, os.O_RDONLY)
        with stream:
            before = _stage_snapshot(stage, stream)
            if stream.read(33) == _reservation(job, identity) and _unchanged(stage, before):
                return identity
    except ValueError:
        return None


def _create_stage(queue, target, job, check):
    stage = stage_path(target, job)
    if not os.path.lexists(stage):
        if not job.get('reservation'):
            job['reservation'] = uuid4().hex
            queue.save(job)
        # Publish a complete inode-bound marker atomically. Until the copying
        # checkpoint is durable this marker can recover the allocation by itself.
        temporary = _allocation(target, job)
        if os.path.lexists(temporary) and not _reserved_inode(temporary, job):
            # An interruption before the marker write is indistinguishable from
            # an unrelated file. Preserve it and reserve a fresh name.
            job['reservation'] = uuid4().hex
            queue.save(job)
            temporary = _allocation(target, job)
        if not os.path.lexists(temporary):
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(_reservation(job, _independent(os.fstat(stream.fileno()))))
                stream.flush()
                os.fsync(stream.fileno())
        if not _reserved_inode(temporary, job):
            raise ValueError('The download reservation changed. Retry the empty job.')
        check()
        rename_exclusive(temporary, stage)
        _sync_directory(target.parent)
    inode = _reserved_inode(stage, job)
    if not inode:
        raise ValueError('The partial file was replaced. Move it aside or discard this empty job.')
    job.update(state='copying', inode=inode)
    queue.save(job)


def _open_stage(path, flags, expected=None):
    _independent(path.lstat())
    fd = os.open(path, flags | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        identity = _independent(os.fstat(fd))
        if identity != _independent(path.lstat()) or (expected is not None and identity != expected):
            raise ValueError('The partial file was replaced. Inspect the interrupted download.')
        return os.fdopen(fd, 'rb' if flags == os.O_RDONLY else 'r+b'), identity
    except BaseException:
        os.close(fd)
        raise


def _prefix(stream, length, algorithm, check):
    running = sha256()
    content = new_hash(algorithm) if algorithm else None
    while length:
        check()
        block = stream.read(min(CHUNK, length))
        if not block:
            raise ValueError('The partial file is shorter than its checkpoint.')
        running.update(block)
        if content:
            content.update(block)
        length -= len(block)
    return running, content


def _stored(size, encrypted):
    return size + 32 + 16 * ((size + 65535) // 65536) if encrypted and size else size


def recover(queue, selection, target, source, *, check, progress, key=None):
    """Open the versioned range reader only when remote data is still required.

    The logical offset is distinct from the stored length of authenticated crypt blocks.
    All publication recovery uses the recorded inode and the full staged SHA-256.
    """
    target = Path(target)
    parent = target.parent.stat()
    parent_id = [parent.st_dev, parent.st_ino]
    validate_access = check
    def check():
        validate_access()
        info = target.parent.stat()
        if [info.st_dev, info.st_ino] != parent_id or target.parent.resolve(strict=True) != target.parent:
            raise ValueError('The download folder was moved or replaced.')

    check()
    with queue.writer(target):
        job = queue.load(key) if key else queue.matching(selection, target)
        if job and (job['selection'] != selection or job['target'] != str(target) or job['parent'] != parent_id):
            raise ValueError('The download selection or destination changed.')
        if os.path.lexists(target):
            if not job or job['state'] != 'publishing' or os.path.lexists(stage_path(target, job)):
                raise FileExistsError('An item with that name already exists. Choose another name.')
            _retire_published(queue, job, target, check)
            return target
        try:
            if job and job['state'] == 'publishing':
                current = job['source']
            else:
                if callable(source):
                    source = source()
                current = source.stat()
            if current['encoded'] and current['size'] == 0:
                raise RestartRequired('This empty encrypted file needs a fresh header. Download from byte zero?')
        except RestartRequired as error:
            raise error.bind(job)
        if job is not None and current != job['source']:
            raise ValueError('The source version changed. Discard the interrupted job before starting again.')
        if job is None:
            job = dict(schema=1, id=uuid4().hex, authority=queue.authority, state='creating', reservation=uuid4().hex,
                       selection=selection, target=str(target), parent=parent_id, source=current, inode=None, offset=0, digest=EMPTY)
            queue.save(job)
        stage = stage_path(target, job)
        if job['state'] == 'creating':
            _create_stage(queue, target, job, check)
        _complete_stage(queue, job, stage, target, source, check, progress)
        return target


def _retire_published(queue, job, target, check):
    stream, _ = _open_stage(target, os.O_RDONLY, job['inode'])
    with stream:
        before = _stage_snapshot(target, stream)
        length = _stored(job['offset'], job['source']['encoded'])
        if (before.st_size != length or _prefix(stream, length, '', check)[0].hexdigest() != job['digest']
                or not _unchanged(target, before)):
            raise ValueError('The published file changed. Inspect it before clearing the job.')
    check()
    _sync_directory(target.parent)
    queue.remove(job)


def _complete_stage(queue, job, stage, target, source, check, progress):
    current = job['source']
    size, encoded = current['size'], current['encoded']
    offset = job['offset']
    chunk = getattr(source, 'chunk_size', CHUNK)
    stored = _stored(offset, encoded)
    stream, _ = _open_stage(stage, os.O_RDWR, job['inode'])
    with stream:
        digest, content = _prefix(stream, stored, current.get('algorithm'), check)
        if digest.hexdigest() != job['digest']:
            raise ValueError('The partial file contents changed. Discard the job before starting again.')
        # A killed writer can leave the uncommitted tail of its last range.
        disk_size = os.fstat(stream.fileno()).st_size
        if job['state'] == 'publishing' and disk_size != stored:
            raise ValueError('The complete partial file changed before publication.')
        if disk_size > stored + _stored(chunk, encoded):
            raise ValueError('The partial file grew beyond its checkpoint.')
        stream.truncate(stored)
        if shutil.disk_usage(target.parent).free < _stored(size, encoded) - stored:
            raise OSError('Insufficient free space for the remaining download.')
        progress(offset, size)
        while offset < size:
            check()
            count = min(chunk, size - offset)
            try:
                data = source.read(current, offset, count)
            except RestartRequired as error:
                raise error.bind(job)
            if len(data) != _stored(offset + count, encoded) - _stored(offset, encoded):
                raise OSError('The source returned an incomplete or invalid range.')
            check()
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            digest.update(data)
            if content:
                content.update(data)
            offset += count
            job.update(offset=offset, digest=digest.hexdigest())
            queue.save(job)
            progress(offset, size)
        if content and content.hexdigest() != current['checksum']:
            raise ValueError('Downloaded content does not match the source checksum. Discard the job.')
        if job['state'] != 'publishing':
            try:
                if source.stat() != current:
                    raise ValueError('The source changed during download. Discard the interrupted job.')
            except RestartRequired as error:
                raise error.bind(job)
    # Windows can update a file's timestamps when the write handle closes.
    # Verify a settled file using path metadata on both sides of the read.
    stream, _ = _open_stage(stage, os.O_RDONLY, job['inode'])
    with stream:
        before = _stage_snapshot(stage, stream)
        if (before.st_size != _stored(size, encoded)
                or _prefix(stream, before.st_size, '', check)[0].hexdigest() != job['digest']):
            raise ValueError('Staged download verification failed.')
        job['state'] = 'publishing'
        queue.save(job)
    check()
    if not _unchanged(stage, before):
        raise ValueError('The staged download changed before publication.')
    rename_exclusive(stage, target)
    _sync_directory(target.parent)
    queue.remove(job)


def _stage_snapshot(path, stream):
    info = path.lstat()
    if _independent(info) != _independent(os.fstat(stream.fileno())):
        raise ValueError('The partial file was replaced. Inspect the interrupted download.')
    return info


def _unchanged(path, before):
    info = path.lstat()
    return (_independent(info) == _independent(before) and info.st_size == before.st_size
            and info.st_mtime_ns == before.st_mtime_ns and info.st_ctime_ns == before.st_ctime_ns)
