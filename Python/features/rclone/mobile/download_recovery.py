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
import os
from pathlib import Path
from threading import Thread
from time import monotonic, sleep

from commonUtils.runtime.operations import check_cancelled
from services.documents.credential_state import MobileCredentialCipher
from features.rclone.transfers.download_recovery import DownloadQueue, RestartRequired, _stored, recover


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


class DownloadPipe:
    """Keep one native response open while the writer verifies each checkpoint."""

    def __init__(self, client, values, version, offset):
        self.client = client
        self.error = None
        read_fd, write_fd = os.pipe()
        self.reader = os.fdopen(read_fd, 'rb')

        def produce():
            try:
                written = client.request('download_stream', **values, expected=version['version'],
                                         offset=offset, fd=write_fd)
                if written != version['size'] - offset:
                    raise OSError('The download stream stopped before the saved file was complete.')
            except BaseException as error:
                self.error = error
            finally:
                os.close(write_fd)

        self.worker = Thread(target=produce, name='Logistics download stream')
        try:
            self.worker.start()
        except BaseException:
            self.reader.close()
            os.close(write_fd)
            raise

    def read(self, count):
        data = self.reader.read(count)
        if len(data) != count:
            self.finish()
            raise OSError('The download stream ended before the current checkpoint.')
        return data

    def finish(self):
        self.worker.join()
        if self.error is not None:
            raise self.error

    def close(self):
        self.reader.close()
        if self.worker.is_alive():
            try:
                self.client.cancel()
            except (OSError, ValueError):
                pass
        self.worker.join()


class NativeRanges:
    def __init__(self, source, path, destination, bandwidth, check):
        self.client = source.client
        self.values = dict(remote=source.remote, identity=source.identity, path=path)
        if destination.private:
            if destination.remote != source.remote:
                raise RestartRequired('This encrypted destination needs a new encryption stream. Download from byte zero?')
            self.values.update(destination_remote=destination.remote, destination_identity=destination.identity)
        self.bandwidth, self.check = bandwidth, check
        self.pipe = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.pipe is not None:
            self.pipe.close()

    def stat(self):
        if self.pipe is not None:
            self.pipe.finish()
        info = self.client.request('download_stat', **self.values)
        if not info['supported']:
            raise RestartRequired('This source and destination cannot verify a byte offset. Download from byte zero?')
        return info

    def read(self, version, offset, count):
        start = monotonic()
        if getattr(self.client, 'supports_download_streams', False):
            if self.pipe is None:
                self.pipe = DownloadPipe(self.client, self.values, version, offset)
            encoded = version['encoded']
            data = self.pipe.read(_stored(offset + count, encoded) - _stored(offset, encoded))
        else:
            data = self.client.request('download_range', **self.values, expected=version['version'],
                                       offset=offset, count=count)
            data = base64.b64decode(data, validate=True)
        if self.bandwidth:
            deadline = start + count / (self.bandwidth * 1024 * 1024)
            while (remaining := deadline - monotonic()) > 0:
                self.check()
                sleep(min(remaining, .1))
        return data


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
    recover(queue, selection, physical, lambda: work.enter_context(NativeRanges(
        source, path, destination, getattr(options, 'bw_limit', None), check)),
        check=check, progress=report, key=key)
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


def destination_target(destination, job):
    return destination.transfer_location(job['selection']['name'], directory=job.get('kind') == 'folder')


def matches_parent(target, job):
    info = target.parent.stat()
    return [info.st_dev, info.st_ino] == job['parent']


def restored_destination(app, source, job):
    selection = job['selection']
    if selection['encrypted']:
        from services.documents.locations import collection_path
        from features.rclone.localcrypt.mobile.locations import LocalCryptLocation
        from .service import native_service
        destination = native_service(source.client).localcrypt.open(LocalCryptLocation(
            collection_path(app.private_root, True), source.remote, namespace=selection['namespace'],
            storage_root=app.private_root, create=False))
        providers = [destination]
    else:
        from services.documents.locations import CollectionFiles
        locations = app.ordinary_file_roots()
        providers = [CollectionFiles(app.private_root), *(p for p in locations.values() if p is not None)]
    try:
        exact = next((provider for provider in providers if str(provider.root) == selection['root']), None)
        if exact is not None and str(target := destination_target(exact, job)) == job['target'] and matches_parent(target, job):
            return exact
        # iOS can move the application's data container between builds. Admit
        # a current storage provider only when it reaches the recorded directory.
        for provider in providers:
            try:
                target = destination_target(provider, job)
                if target.name == Path(job['target']).name and matches_parent(target, job):
                    return provider
            except (OSError, ValueError):
                continue
    except BaseException:
        if selection['encrypted']:
            destination.close()
        raise
    if selection['encrypted']:
        destination.close()
    raise ValueError('The saved download destination cannot be verified.')


def check_checkpoint(before, after):
    if (after['target'], after['offset'], after['digest']) != (before['target'], before['offset'], before['digest']):
        raise ValueError('The saved download changed. Review its current progress and try again.')


def rebind_checkpoint(queue, recovery, job, destination):
    old = Path(job['target'])
    target = destination_target(destination, job)
    if target == old:
        return
    if not old.is_absolute():
        raise ValueError('Invalid saved download destination.')
    with queue.writer(old, target):
        current = recovery.load(job['id'])
        check_checkpoint(job, current)
        if target.name != old.name or not matches_parent(target, current):
            raise ValueError('The download destination changed.')
        if current.get('child') is not None:
            old_stage = recovery.staged(old, current)
            member = Path(current['child']['target']).relative_to(old_stage)
            current['child']['target'] = str(recovery.staged(target, current) / member)
        current['selection']['root'] = str(destination.root)
        current['target'] = str(target)
        recovery.save(current)


def forget_checkpoint(queue, recovery, job):
    # A detached destination is never used for filesystem mutation. Retire only
    # the authenticated queue record, with its original writer lease.
    with queue.writer(Path(job['target'])):
        current = recovery.load(job['id'])
        check_checkpoint(job, current)
        recovery.remove(current)


async def queue_command(controller, action, args, visible):
    import asyncio
    import toga
    from .folder_recovery import FolderQueue
    from .remote_downloads import RemoteDownload
    from .service import native_service
    app = controller.app
    client = app.cloud_client
    if client is None or not getattr(client, 'package_records', ()):
        return
    generation = client.generation
    def current():
        return (visible() and not controller.transfer_busy and
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
            queue = mobile_queue(app.private_root, source)
            recovery = FolderQueue(queue) if folder else queue
            try:
                destination = restored_destination(app, source, job)
                await asyncio.to_thread(rebind_checkpoint, queue, recovery, job, destination)
            except (OSError, ValueError):
                if action != 'discard-download':
                    raise
                confirmed = await app.main_window.dialog(toga.ConfirmDialog('Remove interrupted download?',
                    'The saved folder cannot be verified. Remove this entry from Transfers and leave any partial data in place?'))
                if confirmed and current():
                    await asyncio.to_thread(forget_checkpoint, queue, recovery, job)
                return
            if action == 'discard-download':
                confirmed = await app.main_window.dialog(toga.ConfirmDialog('Discard interrupted download?',
                    'Remove this job and its partial data?'))
                if confirmed and current():
                    target = destination_target(destination, job)
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
            await app.main_window.dialog(toga.ErrorDialog(
                'Could not discard download' if action == 'discard-download' else 'Could not resume download', str(error)))
