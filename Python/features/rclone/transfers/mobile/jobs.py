"""Managed Local/LocalCrypt copies with verified, explicit pull and push."""
from services.documents.locations import collection_path
import shutil
import stat
from pathlib import Path
from threading import RLock

from services.identifiers import digest as valid_digest
from .models import CopyMapping, PullResult, CreatedCopy, MAX_COPIES
from features.rclone.transfers.local_policy import transfer_inventory, cleanup_candidates, remove_generated
from features.rclone.transfers.transfer_options import CLEANUP_NAMES
from features.rclone.transfers.scope import pull_name
from .records import CopyRecords
from .records import MAX_RECORD_BYTES as MAX_RECORD_BYTES  # Legacy public constant.
from .planning import CopyPlanner
from .transport import sync_copy
from features.rclone.mobile.bridge_protocol import crypt_path


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
        path = crypt_path(client, remote=job['remote'], identity=job['cipher_identity'],
            path=path, directory=True)
    return job['remote'], path


class MirrorJobs:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = RLock()
        self.records = CopyRecords(self.root, self.guard)
        self.planner = CopyPlanner(self.root, self.jobs, self.check_name, self.guard)

    @property
    def path(self):
        return self.records.path

    @property
    def jobs(self):
        return self.records.jobs

    @property
    def original(self):
        return self.records.original

    @property
    def error(self):
        return self.records.error

    @staticmethod
    def validate(job):
        CopyMapping.from_record(job)

    def save(self):
        self.records.save()

    def check_records(self):
        self.records.check_records()

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
        """Programmatic Pull uses the same proposal resolver as interactive review."""
        with self.lock:
            proposal = self.prepare_review(client, remote, folder, storage=storage)
            key = proposal['id']
            existing = key in self.jobs
            job = self.jobs.setdefault(key, proposal)
            try:
                result = self.pull(key, client, cancelled=cancelled, progress=progress)
                return CreatedCopy(job, result)
            except BaseException:
                if not existing and not self.target(job).exists():
                    self.jobs.pop(key, None)
                raise

    @staticmethod
    def request(client, job, action, **values):
        return client.request(action, decrypted=not job['crypt'], **values)

    def prepare_review(self, client, remote, folder='', *, storage=None):
        """Capture a proposal under the same lock used for execution admission."""
        with self.lock:
            self.check_records()
            if self.error:
                raise ValueError(self.error)
            return self.planner.pull(client, remote, folder, storage=storage).to_record()

    def prepare_push(self, client, local_folder, *, remote=None, specific=False):
        with self.lock:
            self.check_records()
            return self.planner.push(client, local_folder, remote=remote, specific=specific).to_record()

    @staticmethod
    def signature(job):
        return CopyMapping.from_record(job)

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
                if not new or len(self.jobs) >= MAX_COPIES:
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
        prefix = crypt_path(client, remote=job['remote'], path=job['prefix'],
            identity=job['cipher_identity'], directory=True)
        def decode(name, stopping):
            self.check(client, job, stopping)
            full = '/'.join(part for part in (job['prefix'], name) if part)
            plain = crypt_path(client, remote=job['remote'], path=full,
                identity=job['cipher_identity'])
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
        return sync_copy(job, client, check=self.check,
                         local_path=lambda: self.guard(self.target(job)), push=push,
                         cancelled=cancelled, progress=progress, options=options)

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
            return PullResult('updated')


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
