"""Selected remote downloads into ordinary or unlocked encrypted storage."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import uuid4

from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.mutations import delete_resource
from commonUtils.runtime.resources.paths import resource_path
from features.rclone.transfers.mobile.models import TransferOutcome
from features.rclone.transfers.mobile.transport import sync_copy


@dataclass(frozen=True)
class RemoteDownload:
    provider: object
    path: str
    directory: bool
    kind: str = 'download'
    title: str = 'Download locally'
    primary: str = 'Download here'

    async def complete(self, app, destination, target, *, resume_key=None):
        options = app.transfer_options()
        from features.rclone.transfers.download_recovery import RestartRequired
        from_zero = False
        reason = None
        approved = None
        def work(client, cancelled, progress):
            nonlocal reason
            try:
                return self.execute(client, destination, target, cancelled, progress, options=options,
                                    root=app.private_root, resume_key=resume_key, from_zero=from_zero, approved=approved)
            except RestartRequired as error:
                reason = error
                raise
        async def run():
            identity = getattr(self.provider, 'identity', None)
            authority = {'authority': (self.provider.remote, identity)} if identity is not None else {}
            return await app.run_mirror_work(work, 'download', source=f'{self.provider.remote}:{self.path}',
                destination=f'{getattr(destination, "remote", "Local")} / {target}', **authority)
        result = await run()
        if not result and reason and self.provider.client is app.cloud_client and self.provider.generation == app.cloud_client.generation:
            import toga
            title = 'Download without resume?' if self.directory else 'Download from byte zero?'
            if await app.main_window.dialog(toga.ConfirmDialog(title, str(reason))):
                from_zero, approved, resume_key = True, reason.checkpoint, None
                return await run()
        return result

    def execute(self, client, destination, target, cancelled, progress, *, options=None,
                root=None, resume_key=None, from_zero=False, approved=None):
        target = resource_path(target)
        if not target or getattr(destination, 'remote_storage', False):
            raise ValueError('Choose a local destination folder and item name.')
        if client is not self.provider.client or client.generation != self.provider.generation:
            raise ValueError('The connection changed. Select the source again.')
        source = self.provider.reopen()
        temporary = '/'.join(p for p in (target.rpartition('/')[0], '.download-' + uuid4().hex) if p)
        created = False
        work = ExitStack()
        try:
            source.check()
            root = root or getattr(destination, 'private_root', None) or getattr(destination, 'collection_storage_root', None)
            if root is not None:
                if self.directory and not from_zero:
                    from .folder_recovery import run_folder_download
                    recovered = run_folder_download(root, source, self.path, destination, target, cancelled,
                                                    progress, options, resume_key)
                else:
                    from .download_recovery import run_download
                    recovered = not self.directory and run_download(
                        root, source, self.path, destination, target, cancelled, progress,
                        options, work, resume_key, from_zero, approved)
                if recovered:
                    return TransferOutcome('download', status='complete')
            try:
                destination.entry(target)
            except FileNotFoundError:
                pass
            else:
                raise ValueError('An item with that name already exists. Choose another name.')
            check_cancelled(cancelled)
            if from_zero and not self.directory:
                from shutil import disk_usage
                size = source.entry(self.path)['size']
                required = size + (32 + 16 * ((size + 65535) // 65536) if destination.private else 0)
                if required > disk_usage(destination.transfer_location(target).parent).free:
                    raise OSError('Insufficient free space to restart the download.')
            destination.mkdir(temporary)
            created = True
            encrypted = bool(getattr(destination, 'private', False))
            if encrypted and not getattr(destination, 'remote', None):
                raise ValueError('Choose an unlocked LocalCrypt destination.')
            def check(active, job, cancel):
                check_cancelled(cancel)
                source.check()
                if active is not source.client or active.generation != source.generation:
                    raise ValueError('The source connection changed.')
                if encrypted:
                    destination._access.check()
            job = dict(remote=source.remote, identity=source.identity, prefix=self.path, crypt=False)
            sync_copy(job, client, check=check,
                local_path=lambda: destination.transfer_location(temporary, directory=True),
                push=False, cancelled=cancelled, progress=progress, options=options,
                download=dict(download=True, directory=self.directory,
                    destination_remote=destination.remote if encrypted else '',
                    destination_identity=destination.identity if encrypted else ''))
            check(client, job, cancelled)
            staged = temporary if self.directory else temporary + '/' + PurePosixPath(self.path).name
            if from_zero:
                from commonUtils.persistence.publication import rename_exclusive
                rename_exclusive(destination.transfer_location(staged), destination.transfer_location(target))
            else:
                destination.rename(staged, target)
            return TransferOutcome('download', status='complete')
        finally:
            try:
                if created:
                    # Publication renamed the directory away, or left an empty
                    # staging directory after publishing one file. Never delete target.
                    try:
                        destination.entry(temporary)
                    except FileNotFoundError:
                        pass
                    else:
                        delete_resource(destination, temporary)
            finally:
                work.close()
                source.close()
