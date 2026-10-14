"""Managed Local/LocalCrypt copies with verified, explicit pull and push."""
import json
import os
from pathlib import Path, PurePosixPath
import shutil
from threading import RLock
from uuid import uuid4

from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import mutation_lock, rename_exclusive
from commonUtils.runtime.resource_provider import resource_path
from .pull_jobs import folder_state, validate_state, digest
from .workspace import uuid


class MirrorJobs:
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError('Transfers require private storage.')
        self.path = self.root / 'mirror-jobs.json'
        self.jobs, self.pending, self.error = {}, None, ''
        self.lock = RLock()
        try:
            if self.path.exists():
                if self.path.is_symlink() or self.path.stat().st_size > 4 * 1024 * 1024:
                    raise ValueError('Invalid transfer records.')
                value = json.loads(self.path.read_text())
                if not isinstance(value, dict) or set(value) != {'schema', 'jobs', 'pending'} or value['schema'] != 1:
                    raise ValueError('Invalid transfer records.')
                if not isinstance(value['jobs'], list) or len(value['jobs']) > 16:
                    raise ValueError('Invalid transfer records.')
                for job in value['jobs']:
                    self.validate(job)
                    if job['id'] in self.jobs:
                        raise ValueError('Duplicate local copy.')
                    self.jobs[job['id']] = job
                pending = value['pending']
                if pending is not None:
                    if (not isinstance(pending, dict) or set(pending) != {'job', 'incoming', 'backup', 'baseline'}
                            or pending['job'] not in self.jobs or not uuid(pending['incoming']) or not uuid(pending['backup'])):
                        raise ValueError('Invalid interrupted transfer.')
                    validate_state(pending['baseline'])
                self.pending = pending
        except (OSError, ValueError, TypeError, KeyError):
            self.jobs = {}
            self.error = 'Transfer records could not be restored; the original file was preserved.'

    @staticmethod
    def validate(job):
        fields = {'id', 'remote', 'identity', 'cipher_identity', 'crypt', 'prefix', 'target', 'baseline', 'snapshots'}
        if (not isinstance(job, dict) or set(job) != fields or not uuid(job['id'])
                or not isinstance(job['remote'], str) or not 0 < len(job['remote']) <= 80
                or any(ord(c) < 32 for c in job['remote']) or not digest(job['identity'])
                or type(job['crypt']) is not bool or (job['crypt'] and not digest(job['cipher_identity']))
                or (not job['crypt'] and job['cipher_identity'] != '')
                or not isinstance(job['prefix'], str) or resource_path(job['prefix']) != job['prefix']
                or not isinstance(job['target'], str) or not job['target'] or resource_path(job['target']) != job['target']
                or '/' in job['target'] or not isinstance(job['snapshots'], list) or len(job['snapshots']) > 8
                or any(not uuid(item) for item in job['snapshots'])):
            raise ValueError('Invalid local copy mapping.')
        validate_state(job['baseline'])

    def save(self):
        if self.error or self.path.is_symlink():
            raise ValueError(self.error or 'Transfer records cannot be linked.')
        for job in self.jobs.values():
            self.validate(job)
        atomic_write_json(self.path, {'schema': 1, 'jobs': list(self.jobs.values()), 'pending': self.pending},
                          max_bytes=4 * 1024 * 1024, durable_directory=True)

    def target(self, job):
        if job['crypt']:
            return self.root / 'LocalCryptFolders' / job['cipher_identity'] / job['prefix']
        return self.root / 'LocalFiles' / job['target']

    def snapshot(self, job, key):
        if not uuid(key):
            raise ValueError('Invalid snapshot identity.')
        root = self.root / 'TransferSnapshots' / key
        return root / job['cipher_identity'] / job['prefix'] if job['crypt'] else root / 'tree'

    def guard(self, path):
        path = Path(path)
        if not path.is_relative_to(self.root):
            raise ValueError('Transfer path escaped private storage.')
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError('Linked transfer storage is not supported.')
            if parent == self.root:
                break
        return path

    def state(self, path, cancelled=lambda: False):
        self.guard(path)
        return folder_state(path, cancelled) if path.exists() else None

    def check(self, client, job, cancelled):
        if cancelled():
            raise ValueError('Transfer cancelled; completed copies and backups were preserved.')
        if client.connection_identity(job['remote']) != job['identity']:
            raise ValueError('The connection changed. Unlock the original package before transferring this copy.')

    def create(self, client, remote, folder='', *, cancelled=lambda: False, progress=lambda **kw: None):
        with self.lock:
            self.reconcile()
            if self.error or len(self.jobs) >= 16:
                raise ValueError(self.error or 'Remove a local copy mapping before adding another (limit: 16).')
            info = client.request('mirror_info', remote=remote, path=folder)
            existing = next((job for job in self.jobs.values()
                             if job['remote'] == remote and job['identity'] == info['identity'] and job['prefix'] == info['prefix']), None)
            if existing is not None:
                return existing, self.pull(existing['id'], client, cancelled=cancelled, progress=progress)
            key = uuid4().hex
            name = ''.join(c if c.isalnum() or c in '-_.' else '-' for c in remote)[:60].strip('.') or 'Remote'
            job = dict(id=key, remote=remote, identity=info['identity'], cipher_identity=info['cipher_identity'],
                       crypt=info['crypt'], prefix=info['prefix'], target=name + '-' + key[:8], baseline={}, snapshots=[])
            self.validate(job)
            self.jobs[key] = job
            try:
                result = self.pull(key, client, cancelled=cancelled, progress=progress, initial=True)
                return job, result
            except BaseException:
                if self.pending is None:
                    self.jobs.pop(key, None)
                raise

    def collect(self, job, client, incoming, cancelled, progress):
        incoming = self.guard(incoming)
        incoming.mkdir(parents=True, mode=0o700)
        pending, seen, count = [(job['prefix'], incoming)], set(), 0
        while pending:
            self.check(client, job, cancelled)
            folder, destination = pending.pop()
            rows = client.request('mirror_list', remote=job['remote'], path=folder, identity=job['identity'])
            for row in rows:
                self.check(client, job, cancelled)
                path = row['path']
                if (not isinstance(path, str) or not path or resource_path(path) != path or path in seen
                        or str(PurePosixPath(path).parent) != (folder or '.')):
                    raise ValueError('Remote returned an unsafe or repeated entry.')
                seen.add(path)
                if len(seen) > 10000:
                    raise ValueError('Transfers are limited to 10,000 entries.')
                target = self.guard(destination / PurePosixPath(path).name)
                if row['directory']:
                    target.mkdir(mode=0o700)
                    pending.append((path, target))
                else:
                    # A monitor samples ciphertext/plain file growth; publication
                    # still waits for the native authenticated read to finish.
                    from .folder_download import stream_download
                    bridge = MirrorDownload(client, job)
                    def bytes_progress(done, total, source):
                        progress(phase='Pulling', files=count, done=done, total=total)
                    with target.open('xb') as stream:
                        os.chmod(target, 0o600)
                        stream_download(bridge, job['remote'], row, stream, progress=bytes_progress)
                        stream.flush()
                        os.fsync(stream.fileno())
                    count += 1
                    progress(phase='Pulling', files=count, done=0, total=0)
        return folder_state(incoming, cancelled)

    def pull(self, key, client, *, cancelled=lambda: False, progress=lambda **kw: None, initial=False):
        with self.lock:
            self.reconcile()
            job = self.jobs[key]
            self.check(client, job, cancelled)
            target = self.guard(self.target(job))
            original = self.state(target, cancelled)
            incoming_id, backup_id = uuid4().hex, uuid4().hex
            incoming, backup = self.snapshot(job, incoming_id), self.snapshot(job, backup_id)
            published = False
            try:
                baseline = self.collect(job, client, incoming, cancelled, progress)
                self.check(client, job, cancelled)
                with mutation_lock:
                    current = self.state(target, cancelled)
                    expected = {} if initial else job['baseline']
                    if current != original or (current is not None and current != expected):
                        if initial:
                            job['baseline'] = baseline
                        job['snapshots'] = [incoming_id, *job['snapshots']][:8]
                        self.save()
                        published = True
                        return 'conflict', incoming_id
                    self.pending = dict(job=key, incoming=incoming_id, backup=backup_id, baseline=baseline)
                    self.save()
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    if target.exists():
                        backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        rename_exclusive(target, backup)
                    rename_exclusive(incoming, target)
                    published = True
                    job['baseline'] = baseline
                    if backup.exists():
                        job['snapshots'] = [backup_id, *job['snapshots']][:8]
                    self.pending = None
                    self.save()
                    return 'updated', None
            finally:
                # Interrupted publications retain both stage and intent for
                # recovery. Only our unpublished, unrecorded staging is removed.
                if not published and self.pending is None:
                    shutil.rmtree(self.root / 'TransferSnapshots' / incoming_id, ignore_errors=True)

    def reconcile(self):
        if self.pending is None:
            return
        pending = self.pending
        job = self.jobs[pending['job']]
        target = self.target(job)
        backup = self.snapshot(job, pending['backup'])
        incoming = self.snapshot(job, pending['incoming'])
        current = self.state(target)
        if current == pending['baseline']:
            job['baseline'] = pending['baseline']
        elif current is None and self.state(backup) == job['baseline']:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            rename_exclusive(backup, target)
        elif current is None and self.state(backup) is None and job['baseline'] == {}:
            if self.state(incoming) != pending['baseline']:
                raise ValueError('Interrupted pull needs inspection; all surviving files were preserved.')
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            rename_exclusive(incoming, target)
            job['baseline'] = pending['baseline']
        elif current != job['baseline']:
            raise ValueError('Interrupted pull has local changes; inspect the retained snapshots before retrying.')
        for name in ('incoming', 'backup'):
            if self.snapshot(job, pending[name]).exists():
                job['snapshots'] = [pending[name], *job['snapshots']][:8]
        self.pending = None
        self.save()

    def push_plan(self, key, client, *, cancelled=lambda: False, progress=lambda **kw: None):
        with self.lock:
            self.reconcile()
            job = self.jobs[key]
            self.check(client, job, cancelled)
            progress(phase='Checking local files', files=0, done=0, total=0)
            local = self.state(self.target(job), cancelled)
            if local is None:
                raise ValueError('Pull this folder before pushing it.')
            writes, unchanged = [], 0
            for path, value in local.items():
                if value is None:
                    continue
                self.check(client, job, cancelled)
                remote_path = '/'.join(part for part in (job['prefix'], path) if part)
                progress(phase='Checking remote files', files=len(writes) + unchanged, done=0, total=0)
                remote = client.request('mirror_stat', remote=job['remote'], path=remote_path, identity=job['identity'])
                if remote == value:
                    unchanged += 1
                    continue
                if remote != (job['baseline'].get(path) or ''):
                    raise ValueError('A remote file changed. Pull it into a separate snapshot before reviewing this push.')
                writes.append(dict(path=path, remote=remote_path, expected=remote, digest=value))
            return dict(job=key, local=local, writes=writes, unchanged=unchanged, run=uuid4().hex)

    def push(self, plan, client, *, cancelled=lambda: False, progress=lambda **kw: None):
        with self.lock:
            if (not isinstance(plan, dict) or set(plan) != {'job', 'local', 'writes', 'unchanged', 'run'}
                    or plan['job'] not in self.jobs or not uuid(plan['run'])
                    or not isinstance(plan['writes'], list) or len(plan['writes']) > 10000):
                raise ValueError('Invalid push review; review the source again.')
            validate_state(plan['local'])
            job = self.jobs[plan['job']]
            seen = set()
            for item in plan['writes']:
                if (not isinstance(item, dict) or set(item) != {'path', 'remote', 'expected', 'digest'}
                        or item['path'] not in plan['local'] or item['path'] in seen
                        or not digest(item['digest']) or plan['local'][item['path']] != item['digest']
                        or (item['expected'] != '' and not digest(item['expected']))
                        or item['remote'] != '/'.join(part for part in (job['prefix'], item['path']) if part)):
                    raise ValueError('Invalid push review; review the source again.')
                seen.add(item['path'])
            self.check(client, job, cancelled)
            target = self.target(job)
            if self.state(target, cancelled) != plan['local']:
                raise ValueError('Local files changed since review. Review the push again.')
            staging_id = uuid4().hex
            staging = self.snapshot(job, staging_id)
            self.guard(staging)
            staging.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            # A stable private copy prevents edits during an upload from becoming
            # a different push than the reviewed one. Ciphertext stays ciphertext.
            shutil.copytree(target, staging, symlinks=True)
            try:
                if folder_state(staging, cancelled) != plan['local'] or self.state(target, cancelled) != plan['local']:
                    raise ValueError('Files changed during push staging; review again.')
                for count, item in enumerate(plan['writes']):
                    self.check(client, job, cancelled)
                    progress(phase='Validating and pushing', files=count, done=count, total=len(plan['writes']))
                    source = staging / item['path']
                    with source.open('rb') as stream:
                        actual = client.request('mirror_write', remote=job['remote'], path=item['remote'], identity=job['identity'],
                                                expected=item['expected'], run=plan['run'], fd=stream.fileno())
                    if actual != item['digest']:
                        raise ValueError('Remote verification differed; inspect the retained remote backup.')
                    # Record each successful file so a cancelled multi-file push
                    # can be reviewed and resumed without losing prior progress.
                    job['baseline'][item['path']] = actual
                    self.save()
                job['baseline'] = dict(plan['local'])
                self.save()
                progress(phase='Push verified', files=len(plan['writes']), done=len(plan['writes']), total=len(plan['writes']))
                return len(plan['writes'])
            finally:
                shutil.rmtree(self.root / 'TransferSnapshots' / staging_id, ignore_errors=True)

    def remove(self, key):
        with self.lock:
            if self.pending is not None:
                raise ValueError('Resolve the interrupted transfer before removing a mapping.')
            job = self.jobs.pop(key)
            try:
                self.save()
            except BaseException:
                self.jobs[key] = job
                raise


class MirrorDownload:
    def __init__(self, client, job):
        self.client, self.job = client, job

    def download_into(self, remote, path, descriptor):
        return self.client.request('mirror_read', remote=remote, path=path, identity=self.job['identity'], fd=descriptor)
