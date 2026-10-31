"""Single remote-item pulls into a chosen ordinary or unlocked encrypted folder."""
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

    async def complete(self, app, destination, target):
        options = app.transfer_options()
        def work(client, cancelled, progress):
            return self.execute(client, destination, target, cancelled, progress, options=options)
        return await app.run_mirror_work(work, 'download',
            source=f'{self.provider.remote}:{self.path}',
            destination=f'{getattr(destination, "remote", "Local")} / {target}')

    def execute(self, client, destination, target, cancelled, progress, *, options=None):
        target = resource_path(target)
        if not target or getattr(destination, 'remote_storage', False):
            raise ValueError('Choose a local destination folder and item name.')
        if client is not self.provider.client or client.generation != self.provider.generation:
            raise ValueError('The connection changed. Select the source again.')
        source = self.provider.reopen()
        temporary = '/'.join(p for p in (target.rpartition('/')[0], '.download-' + uuid4().hex) if p)
        created = False
        try:
            source.check()
            try:
                destination.entry(target)
            except FileNotFoundError:
                pass
            else:
                raise ValueError('An item with that name already exists. Choose another name.')
            check_cancelled(cancelled)
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
                source.close()
