"""Repeatable one-way pulls with local-edit guards and recoverable publication."""
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import mutation_lock, rename_exclusive
from commonUtils.runtime.resource_provider import resource_path
from .cloud import download_name
from .folder_download import pull_folder

MAX_JOBS = 16
MAX_RECORD = 4 * 1024 * 1024


def digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_state(state):
    if not isinstance(state, dict) or len(state) > 10000:
        raise ValueError('Invalid pull baseline.')
    for path, value in state.items():
        if not isinstance(path, str) or not path or resource_path(path) != path or (value is not None and not digest(value)):
            raise ValueError('Invalid pull baseline entry.')
    return state


def folder_state(root, cancelled=lambda: False):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('The local pull folder is missing or linked; existing files were preserved.')
    result, pending = {}, [root]
    while pending:
        folder = pending.pop()
        for path in sorted(folder.iterdir()):
            if cancelled():
                raise ValueError('Pull cancelled; existing files were preserved.')
            if path.is_symlink():
                raise ValueError('Linked files cannot be part of a repeatable pull.')
            key = path.relative_to(root).as_posix()
            if path.is_dir():
                result[key] = None
                pending.append(path)
            else:
                before = path.stat()
                if not path.is_file() or before.st_nlink != 1:
                    raise ValueError('The pull folder contains an unsupported resource.')
                content = sha256()
                with path.open('rb') as stream:
                    while block := stream.read(64 * 1024):
                        if cancelled():
                            raise ValueError('Pull cancelled; existing files were preserved.')
                        content.update(block)
                after = path.stat()
                if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns):
                    raise ValueError('A local file changed during inspection; retry the pull.')
                result[key] = content.hexdigest()
            if len(result) > 10000:
                raise ValueError('Repeatable pulls are limited to 10,000 items.')
    return validate_state(result)


class PullJobs:
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError('Pull jobs require private application storage.')
        self.local = self.root / 'LocalFiles'
        self.path = self.root / 'pull-jobs.json'
        self.jobs, self.pending, self.error = {}, None, ''
        if not self.path.exists():
            return
        try:
            if self.path.is_symlink() or self.path.stat().st_size > MAX_RECORD:
                raise ValueError('Invalid pull job storage.')
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('jobs'), list) or len(data['jobs']) > MAX_JOBS:
                raise ValueError('Invalid pull job manifest.')
            for job in data['jobs']:
                self.validate_job(job)
                if job['id'] in self.jobs:
                    raise ValueError('Duplicate pull job.')
                self.jobs[job['id']] = job
            pending = data.get('pending')
            if pending is not None:
                if (not isinstance(pending, dict) or pending.get('job') not in self.jobs
                        or set(pending) != {'job', 'incoming', 'backup', 'baseline'}):
                    raise ValueError('Invalid pending pull publication.')
                self.leaf(pending['incoming'])
                self.leaf(pending['backup'])
                validate_state(pending['baseline'])
                self.pending = pending
        except (OSError, ValueError, TypeError, KeyError):
            self.jobs = {}
            self.error = 'Pull jobs could not be restored; their original file was preserved.'

    @staticmethod
    def leaf(value):
        if not isinstance(value, str) or download_name(value) != value or '/' in value:
            raise ValueError('Invalid local pull folder.')
        return value

    @classmethod
    def validate_job(cls, job):
        if (not isinstance(job, dict) or set(job) != {'id', 'remote', 'folder', 'identity', 'target', 'baseline', 'transient'}
                or not isinstance(job['id'], str) or len(job['id']) != 32
                or any(c not in '0123456789abcdef' for c in job['id'])
                or not isinstance(job['remote'], str) or not 0 < len(job['remote']) <= 80
                or any(ord(c) < 32 for c in job['remote']) or not digest(job['identity'])
                or not isinstance(job['folder'], str) or not job['folder']
                or resource_path(job['folder']) != job['folder'] or type(job['transient']) is not bool):
            raise ValueError('Invalid pull job.')
        cls.leaf(job['target'])
        validate_state(job['baseline'])

    def save(self):
        if self.error or self.path.is_symlink() or self.local.is_symlink():
            raise ValueError(self.error or 'Pull storage cannot be linked.')
        ordinary = [job for job in self.jobs.values() if not job['transient']]
        pending = self.pending if self.pending is None or not self.jobs[self.pending['job']]['transient'] else None
        atomic_write_json(self.path, dict(schema=1, jobs=ordinary, pending=pending), max_bytes=MAX_RECORD,
                          durable_directory=True)

    def create(self, client, remote, folder, *, decrypted=False, cancelled=lambda: False, progress=lambda count, path: None):
        with mutation_lock:
            return self._create(client, remote, folder, decrypted=decrypted, cancelled=cancelled, progress=progress)

    def _create(self, client, remote, folder, *, decrypted, cancelled, progress):
        if self.error or len(self.jobs) >= MAX_JOBS:
            raise ValueError(self.error or 'Remove a pull job before adding another (limit: 16).')
        folder = resource_path(folder)
        if not folder:
            raise ValueError('Select a remote folder before creating a pull job.')
        identity = client.connection_identity(remote)
        target = pull_folder(client, remote, folder, self.local, decrypted=decrypted, cancelled=cancelled, progress=progress)
        if client.connection_identity(remote) != identity:
            raise ValueError('Connection changed. The completed local snapshot was preserved.')
        job = dict(id=uuid4().hex, remote=remote, folder=folder, identity=identity,
                   target=target.name, baseline=folder_state(target, cancelled), transient=bool(decrypted))
        self.validate_job(job)
        self.jobs[job['id']] = job
        self.save()
        return job

    def reconcile(self):
        if self.pending is None:
            return
        pending = self.pending
        job = self.jobs[pending['job']]
        target, backup = self.local / job['target'], self.local / pending['backup']
        if target.exists():
            state = folder_state(target)
            if state == pending['baseline']:
                job['baseline'] = state  # Publication completed before metadata was committed.
            elif state != job['baseline']:
                raise ValueError('Interrupted pull has local changes. Inspect the current, previous and incoming folders before retrying.')
        elif backup.exists() and folder_state(backup) == job['baseline']:
            rename_exclusive(backup, target)
        else:
            raise ValueError('Interrupted pull cannot be reconciled automatically; all surviving folders were preserved.')
        self.pending = None
        self.save()

    def run(self, key, client, *, cancelled=lambda: False, progress=lambda count, path: None):
        with mutation_lock:
            if self.local.is_symlink():
                raise ValueError('The local pull directory cannot be linked.')
            self.reconcile()
            job = self.jobs[key]
            if client.connection_identity(job['remote']) != job['identity']:
                raise ValueError('This connection changed or is locked. Reload the original package or create a new pull; local files were preserved.')
            target = self.local / job['target']
            current = folder_state(target, cancelled)
            incoming = pull_folder(client, job['remote'], job['folder'], self.local,
                decrypted=job['transient'], cancelled=cancelled, progress=progress)
            baseline = folder_state(incoming, cancelled)
            if client.connection_identity(job['remote']) != job['identity']:
                raise ValueError('Connection changed. Both local snapshots were preserved.')
            if current != job['baseline'] or folder_state(target, cancelled) != current:
                return 'conflict', incoming
            if cancelled():
                raise ValueError('Pull cancelled. Both local snapshots were preserved.')
            backup = self.local / (job['target'] + '-previous-' + uuid4().hex[:8])
            self.pending = dict(job=key, incoming=incoming.name, backup=backup.name, baseline=baseline)
            self.save()  # Durable intent precedes either rename.
            rename_exclusive(target, backup)
            try:
                rename_exclusive(incoming, target)
            except BaseException:
                if not target.exists():
                    rename_exclusive(backup, target)
                raise
            job['baseline'] = baseline
            self.pending = None
            self.save()
            return 'updated', target

    def remove(self, key):
        if self.pending is not None and self.pending['job'] == key:
            raise ValueError('Reconcile the interrupted pull before removing its job.')
        job = self.jobs.pop(key)
        try:
            self.save()
        except BaseException:
            self.jobs[key] = job
            raise

    def forget_private(self):
        self.jobs = {key: job for key, job in self.jobs.items() if not job['transient']}
        if self.pending is not None and self.pending['job'] not in self.jobs:
            self.pending = None
