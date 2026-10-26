"""Managed Local/LocalCrypt copies with verified, explicit pull and push."""
from services.documents.locations import collection_path
import json
import os
import shutil
import stat
from pathlib import Path
from threading import RLock, Event, Thread
from uuid import uuid4

from commonUtils.persistence import atomic_write_bytes
from commonUtils.runtime.resources.paths import resource_path
from services.identifiers import uuid, digest as valid_digest
from features.rclone.transfers.local_policy import transfer_inventory, cleanup_candidates, remove_generated
from features.rclone.transfers.transfer_options import TransferOptions, DEFAULT_EXCLUDES, CLEANUP_NAMES
from features.rclone.transfers.scope import pull_name, push_scope

MAX_RECORD_BYTES = 4 * 1024 * 1024


def copy_target(root, job):
    root = Path(root)
    return (collection_path(root, True) / job['identity'] / job['prefix'] if job['crypt']
            else collection_path(root) / job['target'])


def resolved_job(client, job):
    resolve = getattr(client, 'resolve_remote', None)
    return dict(job, remote=resolve(job['remote'], job['identity'])) if resolve else job


def remote_location(client, job):
    job = resolved_job(client, job)
    if client.connection_identity(job['remote']) != job['identity']:
        raise ValueError('Load the matching connection first.')
    path = job['prefix']
    if job['crypt']:
        path = client.request('crypt_path', remote=job['remote'], identity=job['cipher_identity'],
            path=path, directory=True, decode=True)['path']
    return job['remote'], path


class MirrorJobs:
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError('Transfers require private storage.')
        self.path = self.root / 'mirror-jobs.json'
        self.jobs, self.error = {}, ''
        self.original = None
        self.lock = RLock()
        try:
            if self.path.exists():
                if self.path.is_symlink() or self.path.stat().st_size > MAX_RECORD_BYTES:
                    raise ValueError('Invalid transfer records.')
                with self.path.open('rb') as stream:
                    self.original = stream.read(MAX_RECORD_BYTES + 1)
                if len(self.original) > MAX_RECORD_BYTES:
                    raise ValueError('Invalid transfer records.')
                value = json.loads(self.original)
                if not isinstance(value, dict) or value.get('schema') not in (3, 4):
                    raise ValueError('Invalid transfer records.')
                if set(value) != {'schema', 'jobs'}:
                    raise ValueError('Invalid transfer records.')
                if not isinstance(value['jobs'], list) or len(value['jobs']) > 16:
                    raise ValueError('Invalid transfer records.')
                for job in value['jobs']:
                    job = dict(job)
                    if value['schema'] == 3:
                        job.pop('baseline', None)
                    self.validate(job)
                    if job['id'] in self.jobs:
                        raise ValueError('Duplicate local copy.')
                    self.jobs[job['id']] = job
        except (OSError, ValueError, TypeError, KeyError):
            self.jobs = {}
            self.error = 'Transfer records could not be restored; the original file was preserved.'

    @staticmethod
    def validate(job):
        fields = {'id', 'remote', 'identity', 'cipher_identity', 'crypt', 'prefix', 'target'}
        if (not isinstance(job, dict) or set(job) != fields or not uuid(job['id'])
                or not isinstance(job['remote'], str) or not 0 < len(job['remote']) <= 80
                or any(ord(c) < 32 for c in job['remote']) or not valid_digest(job['identity'])
                or type(job['crypt']) is not bool or (job['crypt'] and not valid_digest(job['cipher_identity']))
                or (not job['crypt'] and job['cipher_identity'] != '')
                or not isinstance(job['prefix'], str) or resource_path(job['prefix']) != job['prefix']
                or not isinstance(job['target'], str) or not job['target'] or resource_path(job['target']) != job['target']
                or '/' in job['target']):
            raise ValueError('Invalid local copy mapping.')

    def save(self):
        if self.error or self.path.is_symlink():
            raise ValueError(self.error or 'Transfer records cannot be linked.')
        for job in self.jobs.values():
            self.validate(job)
        data = json.dumps({'schema': 4, 'jobs': list(self.jobs.values())},
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(data) > MAX_RECORD_BYTES:
            raise ValueError('Transfer records exceed the size limit.')
        atomic_write_bytes(self.path, data, validate=self.check_records)
        self.original = data
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
                current = stream.read(MAX_RECORD_BYTES + 1)
        if current != self.original:
            raise OSError('Local copy records changed; reopen Logistics before transferring again.')

    def target(self, job):
        return copy_target(self.root, job)

    def guard(self, path):
        path = Path(path)
        roots = [self.root] if path == self.path else [collection_path(self.root), collection_path(self.root, True)]
        boundary = next((root for root in roots if path.is_relative_to(root)), None)
        if '..' in path.parts or boundary is None:
            raise ValueError('Transfer path escaped collection storage.')
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError('Linked transfer storage is not supported.')
            if parent == boundary:
                break
        return path

    def inspect(self, path, cancelled=lambda: False, *, copy_links=False, allow_missing=False):
        self.guard(path)
        return transfer_inventory(path, cancelled, copy_links=copy_links,
                                  allow_missing=allow_missing) if path.exists() else None

    @staticmethod
    def inspect_file(path):
        from features.rclone.transfers.local_policy import stamp
        return stamp(path.stat()), stamp(path.lstat())

    def check(self, client, job, cancelled):
        if cancelled():
            raise ValueError('Transfer cancelled; completed changes remain in the destination.')
        job['remote'] = resolved_job(client, job)['remote']
        if client.connection_identity(job['remote']) != job['identity']:
            raise ValueError('The connection changed. Unlock the original package before transferring this copy.')

    @staticmethod
    def copy_name(remote, folder, crypt):
        return pull_name(remote, folder, crypt=crypt)

    def check_name(self, name, crypt, *, own=None, adopt=False):
        if any(job['id'] != own and job['target'].casefold() == name.casefold() and job['crypt'] == crypt
               for job in self.jobs.values()):
            raise ValueError('This local folder name belongs to another copy. Rename the remote before pulling.')
        if not crypt:
            local_root = collection_path(self.root)
            self.guard(local_root)
            if local_root.exists():
                for child in local_root.iterdir():
                    if child.name.casefold() != name.casefold():
                        continue
                    if adopt and child.name == name and not child.is_symlink() and child.is_dir():
                        continue
                    raise ValueError('The local folder already exists without this mapping. Move it before pulling.')

    def create(self, client, remote, folder='', *, storage=None, cancelled=lambda: False, progress=lambda **kw: None):
        with self.lock:
            self.check_records()
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
                return existing, self.pull(existing['id'], client, cancelled=cancelled, progress=progress)
            if len(self.jobs) >= 16:
                raise ValueError('Remove a local copy mapping before adding another (limit: 16).')
            key = uuid4().hex
            target = self.copy_name(remote, folder, info['crypt'])
            self.check_name(target, info['crypt'], adopt=True)
            job = dict(id=key, remote=remote, identity=info['identity'], cipher_identity=info['cipher_identity'],
                       crypt=info['crypt'], prefix=info['prefix'], target=target)
            self.validate(job)
            self.jobs[key] = job
            try:
                result = self.pull(key, client, cancelled=cancelled, progress=progress)
                return job, result
            except BaseException:
                if not self.target(job).exists():
                    self.jobs.pop(key, None)
                raise

    @staticmethod
    def request(client, job, action, **values):
        return client.request(action, decrypted=not job['crypt'], **values)

    def prepare_review(self, client, remote, folder='', *, storage=None):
        """Resolve a proposed copy without writing records or creating a folder."""
        with self.lock:
            self.check_records()
            if self.error:
                raise ValueError(self.error)
            info = client.request('mirror_info', remote=remote, path=folder, decrypted=storage == 'Local')
            if storage == 'LocalCrypt' and not info['crypt']:
                raise ValueError('LocalCrypt requires a crypt remote with encryption keys.')
            existing = next((job for job in self.jobs.values() if job['remote'] == remote
                and job['identity'] == info['identity'] and job['prefix'] == info['prefix'] and job['crypt'] == info['crypt']), None)
            if existing is not None:
                return dict(existing)
            if len(self.jobs) >= 16:
                raise ValueError('Remove a local copy mapping before adding another (limit: 16).')
            target = self.copy_name(remote, folder, info['crypt'])
            self.check_name(target, info['crypt'], adopt=True)
            job = dict(id=uuid4().hex, remote=remote, identity=info['identity'], cipher_identity=info['cipher_identity'],
                       crypt=info['crypt'], prefix=info['prefix'], target=target)
            self.validate(job)
            return job

    def prepare_push(self, client, local_folder, *, remote=None, specific=False):
        """Infer a new ordinary Push from its local name; mappings retain ownership."""
        with self.lock:
            self.check_records()
            target = self.guard(collection_path(self.root) / local_folder)
            if not target.is_dir():
                raise ValueError('Choose an existing local folder.')
            remote, prefix = push_scope(local_folder, remote, specific=specific)
            info = client.request('mirror_info', remote=remote, path=prefix, decrypted=True)
            existing = next((job for job in self.jobs.values() if not job['crypt']
                             and job['target'].casefold() == local_folder.casefold()), None)
            if existing is not None:
                if existing['remote'] != remote or existing['identity'] != info['identity'] or existing['prefix'] != info['prefix']:
                    raise ValueError('This local folder belongs to another copy.')
                return dict(existing)
            if len(self.jobs) >= 16:
                raise ValueError('Remove a local copy mapping before adding another (limit: 16).')
            self.check_name(local_folder, False, adopt=True)
            job = dict(id=uuid4().hex, remote=remote, identity=info['identity'], cipher_identity='',
                       crypt=False, prefix=info['prefix'], target=local_folder)
            self.validate(job)
            return job

    @staticmethod
    def signature(job):
        return tuple(job[field] for field in ('id', 'remote', 'identity', 'cipher_identity', 'crypt', 'prefix', 'target'))

    def execute_review(self, proposal, client, *, push=False, new=False, options=None, cancelled=lambda: False, progress=lambda **kw: None):
        """Execute the approved mapping; never resolve or rename its destination again."""
        with self.lock:
            self.check_records()
            self.validate(proposal)
            self.check(client, proposal, cancelled)
            current = self.jobs.get(proposal['id'])
            if current is not None:
                if self.signature(current) != self.signature(proposal):
                    raise ValueError('The destination changed. Review the transfer again.')
            else:
                if not new or len(self.jobs) >= 16:
                    raise ValueError('The copy mapping changed. Review the transfer again.')
                self.check_name(proposal['target'], proposal['crypt'], adopt=True)
                self.jobs[proposal['id']] = dict(proposal)
            try:
                return (self.execute_push(proposal['id'], client, options=options, cancelled=cancelled, progress=progress) if push
                        else self.pull(proposal['id'], client, options=options, cancelled=cancelled, progress=progress))
            except BaseException:
                if current is None and not self.target(proposal).exists():
                    self.jobs.pop(proposal['id'], None)
                raise

    def cleanup_plan(self, job, client, cancelled=lambda: False):
        if not job['crypt']:
            return {}
        prefix = client.request('crypt_path', remote=job['remote'], path=job['prefix'],
            identity=job['cipher_identity'], directory=True, decode=True)['path']
        def decode(name, stopping):
            self.check(client, job, stopping)
            full = '/'.join(part for part in (job['prefix'], name) if part)
            plain = client.request('crypt_path', remote=job['remote'], path=full,
                identity=job['cipher_identity'], decode=True)['path']
            return plain[len(prefix) + 1:] if prefix else plain
        return cleanup_candidates(self.guard(self.target(job)), decode, cancelled)

    def execute_push(self, key, client, *, options=None, cancelled=lambda: False, progress=lambda **kw: None):
        """Execution after shared review; crypt integrity remains mandatory."""
        with self.lock:
            self.check_records()
            job = self.jobs[key]
            self.check(client, job, cancelled)
            cleanup = self.cleanup_plan(job, client, cancelled)
            encrypted_junk = {}
            for name, (label, version) in cleanup.items():
                with (self.target(job) / name).open('rb') as stream:
                    encrypted = stream.read(8) == b'RCLONE\x00\x00'
                if Path(name).name.casefold() in CLEANUP_NAMES and not encrypted:
                    remove_generated(self.target(job), name, version)
                else:
                    encrypted_junk[name] = (label, version)
            state = self.inspect(self.target(job), cancelled, copy_links=not job['crypt'])
            if state is None:
                raise ValueError('Pull this folder before pushing it.')
            if job['crypt']:
                for path, expected in state.items():
                    if stat.S_ISDIR(expected[0][2]):
                        client.request('crypt_path', remote=job['remote'],
                            identity=job['cipher_identity'], path='/'.join(part for part in (job['prefix'], path) if part),
                            directory=True, decode=True)
                        continue
                    self.check(client, job, cancelled)
                    progress(phase='Validating encrypted files', files=0, done=0, total=0)
                    with (self.target(job) / path).open('rb') as stream:
                        digest = self.request(client, job, 'mirror_validate', remote=job['remote'],
                            path='/'.join(part for part in (job['prefix'], path) if part), identity=job['identity'], fd=stream.fileno())
                    if not valid_digest(digest) or self.inspect_file(self.target(job) / path) != expected:
                        raise ValueError('An encrypted file changed during validation. Review again.')
                if self.inspect(self.target(job), cancelled, copy_links=not job['crypt']) != state:
                    raise ValueError('LocalCrypt changed during validation. Review again.')
                for name, (_, version) in encrypted_junk.items():
                    self.check(client, job, cancelled)
                    remove_generated(self.target(job), name, version)
            self.save()
            result = self.sync(job, client, push=True, options=options, cancelled=cancelled, progress=progress)
            self.check(client, job, cancelled)
            self.inspect(self.target(job), cancelled, copy_links=not job['crypt'])
            self.save()
            return result

    def sync(self, job, client, *, push, cancelled, progress, options=None):
        self.check(client, job, cancelled)
        run = uuid4().hex
        done = Event()
        def monitor():
            while not done.wait(.2):
                if cancelled():
                    try:
                        client.cancel()
                    except (OSError, ValueError):
                        pass
                    return
                try:
                    state = client.request('mirror_progress', run=run)
                    progress(phase=state['phase'] or 'Discovering / checking files', files=state.get('files', 0),
                             done=state['done'], total=state['total'], total_files=state.get('total_files', 0),
                             checks=state.get('checks', 0), listed=state.get('listed', 0), active=state.get('active', 0), attempt=state.get('attempt', 0),
                             max_attempts=state.get('max_attempts', 0), retrying=state.get('retrying', False))
                except (OSError, ValueError, TypeError, KeyError):
                    pass
        watcher = Thread(target=monitor, daemon=True)
        watcher.start()
        try:
            progress(phase='Discovering / checking files', files=0, done=0, total=0)
            self.check(client, job, cancelled)
            result = self.request(client, job, 'mirror_sync', remote=job['remote'], path=job['prefix'],
                identity=job['identity'], local_path=str(self.guard(self.target(job)).resolve()), run=run, push=push,
                **(options or TransferOptions(excludes=DEFAULT_EXCLUDES)).bridge_arguments(push=push))
            state = client.request('mirror_progress', run=run)
            progress(phase='Sync complete; verifying local copy', files=result, done=state['done'], total=state['total'])
            return result
        finally:
            done.set()
            watcher.join()

    def pull(self, key, client, *, options=None, cancelled=lambda: False, progress=lambda **kw: None):
        with self.lock:
            self.check_records()
            job = self.jobs[key]
            self.check(client, job, cancelled)
            target = self.guard(self.target(job))
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Inspect links before rclone receives an app-private path. Partial
            # transfers stay in the recorded destination, as with CLI sync.
            # A disappearing destination entry is missing data for Pull to
            # download, not a changed source snapshot as it would be for Push.
            self.inspect(target, cancelled, copy_links=not job['crypt'], allow_missing=True)
            self.save()
            self.sync(job, client, push=False, options=options, cancelled=cancelled, progress=progress)
            self.check(client, job, cancelled)
            if self.inspect(target, cancelled, copy_links=not job['crypt'], allow_missing=True) is None:
                raise FileNotFoundError('Pull destination became unavailable. Check collection storage and retry.')
            self.save()
            return 'updated', None


    def wipe_folder(self, path):
        """Permanently remove a confirmed local tree without a preflight inventory.

        Only named folders under LocalFiles/LocalCryptFolders are admitted.
        rmtree removes nested symlinks themselves instead of following them.
        """
        with self.lock:
            path = self.guard(path)
            roots = (collection_path(self.root), collection_path(self.root, True))
            if not any(path != root and path.is_relative_to(root) for root in roots):
                raise ValueError('Choose a local folder, not a storage root.')
            if path.exists():
                shutil.rmtree(path)

    def delete_copy(self, key):
        with self.lock:
            self.check_records()
            job = self.jobs[key]
            self.wipe_folder(self.target(job))
            self.remove(key)




    def remove(self, key):
        with self.lock:
            job = self.jobs.pop(key)
            try:
                self.save()
            except BaseException:
                self.jobs[key] = job
                raise
