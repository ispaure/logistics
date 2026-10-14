"""Managed Local/LocalCrypt copies with verified, explicit pull and push."""
import json
import os
import shutil
from pathlib import Path, PurePosixPath
from threading import RLock, Event, Thread
from uuid import uuid4

from commonUtils.persistence import atomic_write_bytes
from commonUtils.persistence.publication import rename_exclusive
from commonUtils.runtime.resource_provider import resource_path
from .pull_jobs import folder_state, validate_state, digest
from .workspace import uuid


class MirrorJobs:
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError('Transfers require private storage.')
        self.path = self.root / 'mirror-jobs.json'
        self.jobs, self.error = {}, ''
        self.original = None
        self.loaded_schema = 3
        self.lock = RLock()
        try:
            if self.path.exists():
                if self.path.is_symlink() or self.path.stat().st_size > 4 * 1024 * 1024:
                    raise ValueError('Invalid transfer records.')
                self.original = self.path.read_bytes()
                value = json.loads(self.original)
                if not isinstance(value, dict) or value.get('schema') not in (1, 2, 3):
                    raise ValueError('Invalid transfer records.')
                fields = {'schema', 'jobs'} if value['schema'] == 3 else {'schema', 'jobs', 'pending'}
                if set(value) != fields:
                    raise ValueError('Invalid transfer records.')
                self.loaded_schema = value['schema']
                if not isinstance(value['jobs'], list) or len(value['jobs']) > 16:
                    raise ValueError('Invalid transfer records.')
                for job in value['jobs']:
                    job = dict(job)
                    job.pop('snapshots', None)
                    self.validate(job)
                    if job['id'] in self.jobs:
                        raise ValueError('Duplicate local copy.')
                    self.jobs[job['id']] = job
                # Legacy pending journals are ignored; never restore local trees.
        except (OSError, ValueError, TypeError, KeyError):
            self.jobs = {}
            self.error = 'Transfer records could not be restored; the original file was preserved.'

    @staticmethod
    def validate(job):
        fields = {'id', 'remote', 'identity', 'cipher_identity', 'crypt', 'prefix', 'target', 'baseline'}
        if (not isinstance(job, dict) or set(job) != fields or not uuid(job['id'])
                or not isinstance(job['remote'], str) or not 0 < len(job['remote']) <= 80
                or any(ord(c) < 32 for c in job['remote']) or not digest(job['identity'])
                or type(job['crypt']) is not bool or (job['crypt'] and not digest(job['cipher_identity']))
                or (not job['crypt'] and job['cipher_identity'] != '')
                or not isinstance(job['prefix'], str) or resource_path(job['prefix']) != job['prefix']
                or not isinstance(job['target'], str) or not job['target'] or resource_path(job['target']) != job['target']
                or '/' in job['target']):
            raise ValueError('Invalid local copy mapping.')
        validate_state(job['baseline'])

    def save(self):
        if self.error or self.path.is_symlink():
            raise ValueError(self.error or 'Transfer records cannot be linked.')
        for job in self.jobs.values():
            self.validate(job)
        data = json.dumps({'schema': 3, 'jobs': list(self.jobs.values())},
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(data) > 4 * 1024 * 1024:
            raise ValueError('Transfer records exceed the size limit.')
        atomic_write_bytes(self.path, data, validate=self.check_records)
        self.original = data
        self.loaded_schema = 3
        descriptor = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def check_records(self):
        self.guard(self.path)
        current = None
        if self.path.exists():
            with self.path.open('rb') as stream:
                current = stream.read(4 * 1024 * 1024 + 1)
        if current != self.original:
            raise OSError('Local copy records changed; reopen Logistics before transferring again.')

    def target(self, job):
        if job['crypt']:
            return self.root / 'LocalCryptFolders' / job['identity'] / job['prefix']
        return self.root / 'LocalFiles' / job['target']

    def guard(self, path):
        path = Path(path)
        if '..' in path.parts or not path.is_relative_to(self.root):
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
            raise ValueError('Transfer cancelled; completed changes remain in the destination.')
        if client.connection_identity(job['remote']) != job['identity']:
            raise ValueError('The connection changed. Unlock the original package before transferring this copy.')

    @staticmethod
    def copy_name(remote, folder, crypt):
        name = remote if crypt else folder.rpartition('/')[2] or remote
        if (not name or name.startswith('.') or name.endswith((' ', '.'))
                or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)
                or name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                    *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
            raise ValueError('The remote must have a valid local folder name. Rename it before pulling.')
        return name

    def check_name(self, name, crypt, *, own=None, adopt=False):
        if any(job['id'] != own and job['target'].casefold() == name.casefold() and job['crypt'] == crypt
               for job in self.jobs.values()):
            raise ValueError('This local folder name belongs to another copy. Rename the remote before pulling.')
        if not crypt:
            local_root = self.root / 'LocalFiles'
            self.guard(local_root)
            if local_root.exists():
                for child in local_root.iterdir():
                    if child.name.casefold() != name.casefold():
                        continue
                    if adopt and child.name == name and not child.is_symlink() and child.is_dir():
                        continue
                    raise ValueError('The local folder already exists without this mapping. Move it before pulling.')

    def update_legacy_name(self, job, folder):
        if not job['target'].endswith('-' + job['id'][:8]):
            return
        name = self.copy_name(job['remote'], folder, job['crypt'])
        self.check_name(name, job['crypt'], own=job['id'])
        old_name, old_path = job['target'], self.guard(self.target(job))
        job['target'] = name
        new_path = self.guard(self.target(job))
        moved = False
        try:
            if old_path != new_path and old_path.exists():
                rename_exclusive(old_path, new_path)
                moved = True
            self.save()
        except BaseException:
            job['target'] = old_name
            if moved:
                rename_exclusive(new_path, old_path)
            raise

    def create(self, client, remote, folder='', *, storage=None, cancelled=lambda: False, progress=lambda **kw: None):
        with self.lock:
            self.check_records()
            self.reconcile()
            if self.error:
                raise ValueError(self.error)
            if storage not in (None, 'Local', 'LocalCrypt'):
                raise ValueError('Choose Local or LocalCrypt.')
            info = client.request('mirror_info', remote=remote, path=folder, decrypted=storage == 'Local')
            if storage == 'LocalCrypt' and not info['crypt']:
                raise ValueError('LocalCrypt requires a crypt remote with encryption keys.')
            existing = next((job for job in self.jobs.values()
                             if job['remote'] == remote and job['identity'] == info['identity'] and job['prefix'] == info['prefix'] and job['crypt'] == info['crypt']), None)
            if existing is not None:
                self.update_legacy_name(existing, folder)
                return existing, self.pull(existing['id'], client, cancelled=cancelled, progress=progress)
            if len(self.jobs) >= 16:
                raise ValueError('Remove a local copy mapping before adding another (limit: 16).')
            key = uuid4().hex
            target = self.copy_name(remote, folder, info['crypt'])
            self.check_name(target, info['crypt'], adopt=True)
            job = dict(id=key, remote=remote, identity=info['identity'], cipher_identity=info['cipher_identity'],
                       crypt=info['crypt'], prefix=info['prefix'], target=target, baseline={})
            self.validate(job)
            self.jobs[key] = job
            try:
                result = self.pull(key, client, cancelled=cancelled, progress=progress, initial=True)
                return job, result
            except BaseException:
                if not self.target(job).exists():
                    self.jobs.pop(key, None)
                raise

    @staticmethod
    def request(client, job, action, **values):
        return client.request(action, decrypted=not job['crypt'], **values)

    def sync(self, job, client, *, push, cancelled, progress):
        self.check(client, job, cancelled)
        run = uuid4().hex
        done = Event()
        def monitor():
            while not done.wait(.2):
                try:
                    state = client.request('mirror_progress', run=run)
                    progress(phase=state['phase'] or 'Discovering / checking files', files=state.get('files', 0),
                             done=state['done'], total=state['total'], total_files=state.get('total_files', 0),
                             checks=state.get('checks', 0), listed=state.get('listed', 0), active=state.get('active', 0))
                except (OSError, ValueError, TypeError, KeyError):
                    pass
        watcher = Thread(target=monitor, daemon=True)
        watcher.start()
        try:
            progress(phase='Discovering / checking files', files=0, done=0, total=0)
            result = self.request(client, job, 'mirror_sync', remote=job['remote'], path=job['prefix'],
                identity=job['identity'], local_path=str(self.guard(self.target(job)).resolve()), run=run, push=push)
            state = client.request('mirror_progress', run=run)
            progress(phase='Sync complete; verifying local copy', files=result, done=state['done'], total=state['total'])
            return result
        finally:
            done.set()
            watcher.join()

    def pull(self, key, client, *, cancelled=lambda: False, progress=lambda **kw: None, initial=False):
        with self.lock:
            self.check_records()
            self.reconcile()
            job = self.jobs[key]
            self.check(client, job, cancelled)
            self.update_legacy_name(job, job['prefix'])
            target = self.guard(self.target(job))
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Inspect links before rclone receives an app-private path. Partial
            # transfers stay in the recorded destination, as with CLI sync.
            self.state(target, cancelled)
            self.save()
            self.sync(job, client, push=False, cancelled=cancelled, progress=progress)
            self.check(client, job, cancelled)
            job['baseline'] = self.state(target, cancelled)
            self.save()
            return 'updated', None

    def reconcile(self):
        """Discard obsolete transfer backups; never restore a local tree."""
        self.check_records()
        legacy = self.guard(self.root / 'TransferSnapshots')
        if legacy.exists():
            shutil.rmtree(legacy)
        if self.loaded_schema != 3:
            self.save()

    def wipe_folder(self, path):
        """Permanently remove a confirmed local tree without a preflight inventory.

        Only named folders under LocalFiles/LocalCryptFolders are admitted.
        rmtree removes nested symlinks themselves instead of following them.
        """
        with self.lock:
            path = self.guard(path)
            relative = path.relative_to(self.root)
            if len(relative.parts) < 2 or relative.parts[0] not in ('LocalFiles', 'LocalCryptFolders'):
                raise ValueError('Choose a local folder, not a storage root.')
            self.reconcile()
            if path.exists():
                shutil.rmtree(path)

    def delete_copy(self, key):
        with self.lock:
            self.check_records()
            job = self.jobs[key]
            self.wipe_folder(self.target(job))
            self.remove(key)

    def remote_state(self, job, client, cancelled):
        result, pending = {}, [job['prefix']]
        while pending:
            folder = pending.pop()
            self.check(client, job, cancelled)
            for row in self.request(client, job, 'mirror_list', remote=job['remote'], path=folder, identity=job['identity']):
                path = row['path']
                if (not isinstance(path, str) or not path or resource_path(path) != path
                        or str(PurePosixPath(path).parent) != (folder or '.')):
                    raise ValueError('Unsafe remote sync entry.')
                key = path[len(job['prefix']) + 1:] if job['prefix'] else path
                if key in result or len(result) >= 10000:
                    raise ValueError('Repeated entry or sync exceeds 10,000 entries.')
                result[key] = (None if row['directory'] else self.request(client, job, 'mirror_stat',
                    remote=job['remote'], path=path, identity=job['identity']))
                if row['directory']:
                    pending.append(path)
        validate_state(result)
        return result

    def push_plan(self, key, client, *, cancelled=lambda: False, progress=lambda **kw: None):
        with self.lock:
            self.check_records()
            self.reconcile()
            job = self.jobs[key]
            self.check(client, job, cancelled)
            progress(phase='Checking local files', files=0, done=0, total=0)
            local = self.state(self.target(job), cancelled)
            if local is None:
                raise ValueError('Pull this folder before pushing it.')
            remote_state = self.remote_state(job, client, cancelled)
            writes, unchanged = [], 0
            for path, value in local.items():
                if value is None:
                    continue
                self.check(client, job, cancelled)
                remote_path = '/'.join(part for part in (job['prefix'], path) if part)
                with (self.target(job) / path).open('rb') as stream:
                    checked = self.request(client, job, 'mirror_validate', remote=job['remote'], path=remote_path,
                                             identity=job['identity'], fd=stream.fileno())
                if checked != value:
                    raise ValueError('A local file changed during push inspection; review again.')
                progress(phase='Checking remote files', files=len(writes) + unchanged, done=0, total=0)
                remote = remote_state.get(path) or ''
                if remote == value:
                    unchanged += 1
                    continue
                writes.append(dict(path=path, remote=remote_path, expected=remote, digest=value))
            directories = [path for path, value in local.items() if value is None]
            deletes = [path for path, value in remote_state.items() if path not in local
                       or (value is None) != (local[path] is None)]
            deletes.sort(key=lambda path: (remote_state[path] is None, -path.count('/'), path))
            return dict(job=key, local=local, remote=remote_state, deletes=deletes, writes=writes,
                        directories=directories, unchanged=unchanged, run=uuid4().hex)

    def push(self, plan, client, *, cancelled=lambda: False, progress=lambda **kw: None):
        with self.lock:
            self.check_records()
            if (not isinstance(plan, dict) or set(plan) != {'job', 'local', 'remote', 'deletes', 'writes', 'directories', 'unchanged', 'run'}
                    or plan['job'] not in self.jobs or not uuid(plan['run'])):
                raise ValueError('Invalid push review; review again.')
            validate_state(plan['local'])
            validate_state(plan['remote'])
            job = self.jobs[plan['job']]
            self.check(client, job, cancelled)
            if self.state(self.target(job), cancelled) != plan['local']:
                raise ValueError('Local files changed since review. Review the push again.')
            if self.remote_state(job, client, cancelled) != plan['remote']:
                raise ValueError('Remote files changed since review. Review the push again.')
            result = self.sync(job, client, push=True, cancelled=cancelled, progress=progress)
            self.check(client, job, cancelled)
            job['baseline'] = self.state(self.target(job), cancelled)
            self.save()
            return result

    def remove(self, key):
        with self.lock:
            job = self.jobs.pop(key)
            try:
                self.save()
            except BaseException:
                self.jobs[key] = job
                raise
