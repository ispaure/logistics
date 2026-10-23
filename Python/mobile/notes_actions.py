"""Location actions resolve a single Notes Library root without opening a browser."""
import asyncio
from contextlib import contextmanager
from pathlib import Path
from features.text_editor.notes import vault_root
from commonUtils.runtime.operations import OperationCancelled


class RemoteNotes:
    private = remote_storage = True
    def __init__(self, client, remote):
        from features.rclone.mobile.service import native_service
        from features.rclone.remote_access import NativeRemoteLocation
        self.resource = native_service(client).remotes.open(NativeRemoteLocation(remote))
        self.root = self.resource.root
        self.remote = self.resource.remote

    def relative(self, path):
        return self.resource.relative(path)

    def check(self):
        self.resource.check()

    def list(self, path='', *, cancelled=lambda: False):
        return self.resource.list(path, cancelled=cancelled)

    def entry(self, path):
        return self.resource.entry(path)

    @contextmanager
    def open(self, path):
        if self.entry(path)['size'] > 2 * 1024 * 1024:
            raise ValueError('Note exceeds the 2 MiB preview limit.')
        with self.resource.open(path) as stream:
            if stream.size > 2 * 1024 * 1024:
                raise ValueError('Note exceeds the 2 MiB preview limit.')
            yield stream


def resolve_source(app, entry):
    from features.rclone.mobile.storage_location import collection_path
    from commonUtils.runtime.resources.local import LocalFiles
    from features.rclone.localcrypt.mobile.resources import encrypted_storage, CryptFiles
    kind, value = entry['kind'], entry['value']
    client = getattr(app, 'cloud_client', None)
    job = app.mirror_store().jobs.get(value) if kind in ('job', 'job-remote') else None
    if kind in ('job', 'job-remote') and job is None:
        raise ValueError('This location mapping is no longer available.')
    if kind == 'shared-local':
        from .local_sources import shared_files
        return shared_files(app.private_root), value
    if kind == 'local':
        return LocalFiles(collection_path(app.private_root)), value
    if kind == 'job' and not job['crypt']:
        return LocalFiles(collection_path(app.private_root)), job['target']
    if kind == 'crypt':
        return encrypted_storage(app.private_root, client, value, create=False), ''
    if job:
        from features.rclone.transfers.mobile.jobs import remote_location
        remote, folder = remote_location(client, dict(job))
        if kind == 'job':
            return CryptFiles(collection_path(app.private_root, True), client, remote,
                namespace=job['identity'], storage_root=app.private_root, create=False), folder
    else:
        remote, folder = value
    return RemoteNotes(client, remote), folder


async def offer_notes(app, entry, box, button, status):
    """A single immediate-root listing, only for the currently selected action page."""
    origin = app.navigation_generation
    client = getattr(app, 'cloud_client', None)
    generation = getattr(client, 'generation', None)
    def valid():
        return (app.active_host and (entry['source'] == 'Local' or (client is app.cloud_client
            and generation == getattr(client, 'generation', None))))
    def current():
        return valid() and app.navigation_generation == origin
    def probe():
        if not current():
            return None
        provider, root = resolve_source(app, entry)
        rows = provider.list(root, cancelled=lambda: not current())
        return (provider, root) if vault_root(provider, root, rows) is not None else None
    try:
        if app.cloud_busy and entry['source'] != 'Local':
            return
        found = await asyncio.to_thread(probe)
        if not current() or found is None:
            return
        provider, root = found
        async def open_notes(widget=None, **kwargs):
            if not valid():
                status.text = 'Reopen this location after unlocking its connection.'
                return
            try:
                command_origin = app.navigation_generation
                rows = await asyncio.to_thread(provider.list, root, cancelled=lambda: not valid())
                if not valid() or app.navigation_generation != command_origin:
                    return
                if vault_root(provider, root, rows) is None:
                    raise ValueError('This folder no longer contains an .obsidian directory.')
                from .obsidian import open_vault
                await open_vault(app, provider, root, title=entry['name'], rows=rows)
            except (OSError, ValueError) as error:
                status.text = str(error)[:180]
        button.on_press = open_notes
        box.insert(max(0, box.children.index(status)), button)
    except OperationCancelled:
        return
    except (OSError, ValueError, AttributeError, KeyError) as error:
        if current():
            status.text = 'Notes Library check unavailable: ' + str(error)[:120]
