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
                 files=0, total_files=1, done=done, total=total)

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


def available_jobs(app):
    from features.rclone.remote_access import NativeRemoteLocation
    from .service import native_service
    client = app.cloud_client
    rows = []
    if client is None or not (Path(app.private_root) / 'DownloadQueue').is_dir():
        return rows
    for record in client.package_records:
        for remote, identity in record.get('identities', {}).items():
            origin = NativeRemoteLocation(remote, identity)
            source = native_service(client).remotes.open(origin)
            try:
                try:
                    queue = mobile_queue(app.private_root, source)
                except RestartRequired:
                    continue
                for job in queue.jobs():
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
    if str(destination.transfer_location(selection['name'])) != job['target']:
        if destination.private:
            destination.close()
        raise ValueError('The destination changed. Reopen the original storage.')
    return destination


async def queue_command(controller, action, args, visible):
    import asyncio
    import toga
    from .remote_downloads import RemoteDownload
    from .service import native_service
    app, surface = controller.app, controller._progress_surface
    client = app.cloud_client
    if client is None:
        return
    generation = client.generation
    def current():
        return (visible() and not surface.closed and not controller.transfer_busy and
                app.cloud_client is client and client.generation == generation)
    try:
        rows = await asyncio.to_thread(available_jobs, app)
        if not current():
            return
        if action == 'downloads':
            model = dict(surface.model, downloads=[dict(id=j['id'], path=j['selection']['path'],
                         name=j['selection']['name'], offset=j['offset'], size=j['source']['size']) for _, j in rows])
            if rows and controller.state.display_revoked:
                # This list has a fresh grant. Keep the previous transfer redacted.
                model.update(phase='idle', message='Choose a download to resume or discard.')
            elif not rows:
                model['message'] = 'No interrupted downloads for the unlocked connections.'
            surface.update(model)
            return
        match = next(((origin, j) for origin, j in rows if j['id'] == args.get('id')), None)
        if match is None:
            return
        origin, job = match
        source = native_service(client).remotes.open(origin)
        destination = None
        try:
            destination = restored_destination(app, source, job)
            if action == 'discard-download':
                confirmed = await app.main_window.dialog(toga.ConfirmDialog('Discard interrupted download?',
                    'Remove this job and its partial file?'))
                if confirmed and current():
                    queue = mobile_queue(app.private_root, source)
                    await asyncio.to_thread(queue.discard, job['id'], destination.transfer_location(job['selection']['name']),
                                            expected=(job['id'], job['offset'], job['digest']))
                    controller.render_transfer_summary()
            elif current():
                request = RemoteDownload(source, job['selection']['path'], False)
                if await request.complete(app, destination, job['selection']['name'], resume_key=job['id']):
                    await controller.rclone_ui.refresh_download_directory(destination, job['selection']['name'])
        finally:
            if destination is not None and destination.private:
                destination.close()
            source.close()
    except (OSError, ValueError) as error:
        if current():
            surface.update(dict(surface.model, message=str(error)))
