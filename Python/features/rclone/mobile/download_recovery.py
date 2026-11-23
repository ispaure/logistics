"""Reopen selected-file jobs with the active native provider and destination guards."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import base64
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep

from commonUtils.runtime.operations import check_cancelled
from services.documents.credential_state import MobileCredentialCipher
from features.rclone.transfers.download_recovery import DownloadQueue, RestartRequired, recover


class SavedTransferCipher:
    def __init__(self, client, authority):
        self.client = client
        self.binding = sha256(('Logistics download queue v1:' + authority).encode()).hexdigest()

    def transform(self, data, decode=False):
        key = self.client.vault.unlock(create=False)
        if key is None:
            raise PermissionError('The device credential key is unavailable.')
        reply = self.client.request('unprotect_package' if decode else 'protect_package',
            key=key['key'], id=self.binding, data=base64.b64encode(data).decode())
        return base64.b64decode(reply, validate=True)


def mobile_queue(root, source):
    client = source.client
    source.check()
    record = next((r for r in client.package_records
                   if r.get('identities', {}).get(source.remote) == source.identity), None)
    if record is None:
        raise ValueError('Unlock the matching source connection.')
    if record['saved']:
        if getattr(client, 'vault', None) is None:
            raise RestartRequired('Device-protected transfer records are unavailable. Download from byte zero?')
        cipher = SavedTransferCipher(client, source.identity)
    else:
        cipher = MobileCredentialCipher(source, client=client)
        try:
            cipher.identity
        except PermissionError:
            raise RestartRequired('This session has no password-bound transfer record. Download from byte zero?') from None
    original = next((name for name, alias in record.get('aliases', {}).items() if alias == source.remote), source.remote)
    return DownloadQueue(root, [record['package_name'], original, source.identity,
                                record.get('document_cache_id')], source.check, cipher)


class NativeRanges:
    def __init__(self, source, path, destination, bandwidth, check):
        self.client = source.client
        self.values = dict(remote=source.remote, identity=source.identity, path=path)
        if destination.private:
            if destination.remote != source.remote:
                raise RestartRequired('This encrypted destination needs a new encryption stream. Download from byte zero?')
            self.values.update(destination_remote=destination.remote, destination_identity=destination.identity)
        self.bandwidth, self.check = bandwidth, check

    def stat(self):
        info = self.client.request('download_stat', **self.values)
        if not info['supported']:
            raise RestartRequired('This source and destination cannot verify a byte offset. Download from byte zero?')
        return info

    def read(self, version, offset, count):
        start = monotonic()
        data = self.client.request('download_range', **self.values, expected=version['version'], offset=offset, count=count)
        if self.bandwidth:
            deadline = start + count / (self.bandwidth * 1024 * 1024)
            while (remaining := deadline - monotonic()) > 0:
                self.check()
                sleep(min(remaining, .1))
        return base64.b64decode(data, validate=True)


def run_download(root, source, path, destination, target, cancelled, progress, options, work,
                 key=None, from_zero=False, approved=None):
    physical = destination.transfer_location(target)
    selection = dict(path=path, name=target, root=str(destination.root),
                     namespace=getattr(destination, 'storage_namespace', ''), encrypted=destination.private)
    def check():
        check_cancelled(cancelled)
        source.check()
        if destination.transfer_location(target) != physical:
            raise ValueError('Download destination changed.')

    def report(done, total):
        progress(phase='Verifying the local copy…' if done == total else 'Transferring',
                 files=0, total_files=1, done=done, total=total, active=int(done < total),
                 active_files=[dict(name=path, bytes=done, size=total)] if done < total else [])

    from features.rclone.transfers.download_recovery import MINIMUM
    try:
        queue = mobile_queue(root, source)
    except RestartRequired:
        if key:
            raise
        queue = None
    if from_zero:
        entry = source.entry(path)
        if entry['directory']:
            raise ValueError('The selected file became a directory. Select the source again.')
        if queue:
            size = entry['size']
            required = size + (32 + 16 * ((size + 65535) // 65536) if destination.private else 0)
            work.enter_context(queue.restart(selection, physical, approved, required))
        return False
    job = queue.matching(selection, physical) if queue and not key else None
    if not key and not job:
        size = source.entry(path)['size']
        if 0 <= size < MINIMUM:
            return False
    queue = queue or mobile_queue(root, source)
    recover(queue, selection, physical, lambda: NativeRanges(source, path, destination,
            getattr(options, 'bw_limit', None), check), check=check, progress=report, key=key)
    return True


def download_origins(client, *, saved=None):
    from features.rclone.remote_access import NativeRemoteLocation
    generation = client.generation
    for record in getattr(client, 'package_records', ()):
        if saved is None or record['saved'] == saved:
            for remote, identity in record.get('identities', {}).items():
                yield NativeRemoteLocation(remote, identity, generation)


def available_jobs(app, *, client=None):
    from .folder_recovery import FolderQueue
    from .service import native_service
    client = app.cloud_client if client is None else client
    rows = []
    if client is None or not (Path(app.private_root) / 'DownloadQueue').is_dir():
        return rows
    for origin in download_origins(client):
        source = native_service(client).remotes.open(origin)
        try:
            try:
                queue = mobile_queue(app.private_root, source)
            except RestartRequired:
                continue
            for job in (*queue.jobs(), *FolderQueue(queue).jobs()):
                rows.append((origin, job))
        finally:
            source.close()
    return rows


def restored_destination(app, source, job):
    selection = job['selection']
    if selection['encrypted']:
        from services.documents.locations import collection_path
        from features.rclone.localcrypt.mobile.locations import LocalCryptLocation
        from .service import native_service
        destination = native_service(source.client).localcrypt.open(LocalCryptLocation(
            collection_path(app.private_root, True), source.remote, namespace=selection['namespace'],
            storage_root=app.private_root, create=False))
    else:
        from services.documents.locations import CollectionFiles
        locations = app.ordinary_file_roots()
        providers = [CollectionFiles(app.private_root), *(p for p in locations.values() if p is not None)]
        destination = next((p for p in providers if str(p.root) == selection['root']), None)
        if destination is None:
            raise ValueError('The original download folder is unavailable.')
    if str(destination.transfer_location(selection['name'], directory=job.get('kind') == 'folder')) != job['target']:
        if destination.private:
            destination.close()
        raise ValueError('The destination changed. Reopen the original storage.')
    return destination


async def queue_command(controller, action, args, visible):
    import asyncio
    import toga
    from .folder_recovery import FolderQueue
    from .remote_downloads import RemoteDownload
    from .service import native_service
    app, surface = controller.app, controller._progress_surface
    client = app.cloud_client
    if client is None or not getattr(client, 'package_records', ()):
        return
    generation = client.generation
    def current():
        return (visible() and not surface.closed and not controller.transfer_busy and
                app.cloud_client is client and client.generation == generation)
    try:
        rows = await asyncio.to_thread(available_jobs, app, client=client)
        if not current():
            return
        match = next(((origin, j) for origin, j in rows if j['id'] == args.get('id')), None)
        if match is None:
            return
        origin, job = match
        folder = job.get('kind') == 'folder'
        source = native_service(client).remotes.open(origin)
        destination = None
        try:
            destination = restored_destination(app, source, job)
            if action == 'discard-download':
                confirmed = await app.main_window.dialog(toga.ConfirmDialog('Discard interrupted download?',
                    'Remove this job and its partial data?'))
                if confirmed and current():
                    queue = mobile_queue(app.private_root, source)
                    recovery = FolderQueue(queue) if folder else queue
                    target = destination.transfer_location(job['selection']['name'], directory=folder)
                    await asyncio.to_thread(recovery.discard, job['id'], target,
                                            expected=(job['id'], job['offset'], job['digest']))
                    controller.render_transfer_summary()
            elif current():
                request = RemoteDownload(source, job['selection']['path'], folder)
                if await request.complete(app, destination, job['selection']['name'], resume_key=job['id']):
                    await controller.rclone_ui.refresh_download_directory(destination, job['selection']['name'])
        finally:
            if destination is not None and destination.private:
                destination.close()
            source.close()
    except (OSError, ValueError) as error:
        if current():
            surface.update(dict(surface.model, message=str(error)))
