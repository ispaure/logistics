"""Managed copies and transfers which keep ordinary Documents usable."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from services.documents.locations import collection_path
from services.transfer_notifications import start_transfer_notice, transfer_notice
from services.folders.labels import encrypted_copy_label
import asyncio
from time import monotonic
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from features.rclone.transfers.mobile.jobs import MirrorJobs
from .execution import transfer_progress
from features.rclone.mobile.messages import import_hint
from features.rclone.transfers.mobile.review_ui import TransferReviewUI


class MirrorUI(TransferReviewUI):
    def register_transfer_status(self, view, *, visible_when=lambda: True):
        # Compatibility for existing feature callers; status belongs to main tabs.
        view.transfer_banner = None

    def dismiss_transfer_status(self, widget=None, **kwargs):
        if not getattr(self, 'transfer_busy', False):
            self.transfer_notification = False
            self.refresh_transfer_status()

    def refresh_transfer_status(self):
        self.rclone_ui.refresh_folder_source_actions()
        refresh_chrome = getattr(self.rclone_ui, 'refresh_transfer_chrome', None)
        if refresh_chrome is not None:
            refresh_chrome()

    def existing_crypt_locations(self, *, roots=None):
        if not self.app.feature_enabled('rclone'):
            return {}
        result = {}
        client = getattr(self, 'cloud_client', None)
        if client is None or not hasattr(client, 'request'):
            return result
        visible_remotes = self.rclone_ui.visible_remotes
        # Published fingerprints are sufficient to discover local directories;
        # actual crypt reads still pass native admission/identity checks.
        identities = {remote: identity for record in getattr(client, 'package_records', ())
                      for remote, identity in record.get('crypt_identities', {}).items()}
        base = None
        for remote in visible_remotes(getattr(self, 'cloud_crypt_remotes', ())):
            try:
                identity = identities.get(remote) or client.request('crypt_path', remote=remote, path='', directory=True)['identity']
                if roots is not None:
                    roots[encrypted_copy_label(remote)] = (remote, identity)
                if base is None:
                    base = collection_path(self.private_root, True)
                path = base / identity
                if path.is_dir() and not path.is_symlink() and any(path.iterdir()):
                    result[encrypted_copy_label(remote)] = remote
            except (OSError, ValueError):
                continue
        return result

    def crypt_folder_target(self, remote):
        identity = self.cloud_client.request('crypt_path', remote=remote, path='', directory=True)['identity']
        return self.mirror_store().guard(collection_path(self.private_root, True) / identity)

    def linked_crypt_locations(self, *, folders=None, locked=None):
        if not self.app.feature_enabled('rclone'):
            return {}
        result = {}
        client = getattr(self, 'cloud_client', None)
        from features.rclone.localcrypt.mobile.locations import LocalCryptLocation
        from features.rclone.mobile.service import native_service
        from features.rclone.transfers.mobile.jobs import loaded_copy_cipher, resolved_job
        store = self.mirror_store()
        candidates = self.app.home_unlock_candidates() if locked is not None else ()
        for job in store.jobs.values():
            if not job['crypt']:
                continue
            if folders is not None and not all(self.app.folder_path_visible(name)
                    for name in (job['remote'], job['target'])):
                continue
            label = encrypted_copy_label(job['target'])
            try:
                if not store.guard(store.target(job)).is_dir():
                    continue
            except (OSError, ValueError):
                continue
            provider = None
            try:
                if client is not None and hasattr(client, 'request'):
                    resolved = resolved_job(client, job)
                    cipher = loaded_copy_cipher(client, resolved)
                    remote = cipher or resolved['remote']
                    if (remote in getattr(self, 'cloud_crypt_remotes', ())
                            and (cipher or client.connection_identity(remote) == job['identity'])):
                        provider = native_service(client).localcrypt.open(LocalCryptLocation(
                            collection_path(self.private_root, True), remote, namespace=job['identity'],
                            storage_root=self.private_root, create=False, cipher_identity=job['cipher_identity']))
                        if folders is not None:
                            folders[label] = provider.mapping(job['prefix'], directory=True, decode=True)
                        else:
                            label = encrypted_copy_label(remote + ' · ' + job['target'])
                        result[label] = provider
                        continue
            except (OSError, ValueError):
                if provider is not None:
                    provider.close()
            for key, item in candidates:
                name = job['remote']
                if item['remotes'].get(name) != job['identity']:
                    name = item.get('aliases', {}).get(name)
                if item['remotes'].get(name) == job['identity']:
                    locked[label + ' (Locked)'] = key, name, job['identity'], label
                    break
        return result

    def mirror_store(self):
        if not hasattr(self, 'mirrors'):
            self.mirrors = MirrorJobs(self.private_root)
        return self.mirrors

    def show_transfers(self, widget=None, *, present=True, detail=False, **kwargs):
        if not self.app.require_feature('rclone'):
            return
        from types import SimpleNamespace

        route = 'transfer-detail' if detail else 'transfers'
        name = '_progress_surface' if detail else '_transfers_overview'
        surface = self.transfer_surface(name, route, detail=detail)
        if not hasattr(self, 'transfer_view') or present:
            self.transfer_view = surface

        # Retain the existing programmatic status handles used by cloud callers.
        if not hasattr(self, 'transfer_notice'):
            self.transfer_notice = toga.Label('')
        if not hasattr(self, 'transfer_progress'):
            self.transfer_progress = toga.ProgressBar(max=100, value=0)
        self.transfer_files = getattr(self, 'transfer_files', SimpleNamespace(text=''))
        self.transfer_bytes = getattr(self, 'transfer_bytes', SimpleNamespace(text=''))
        self.render_transfer_summary()
        if present:
            if not self.transfer_busy:
                self.dismiss_transfer_status()
            self.show_view(surface, destination=None if detail else 'files', route=route,
                           title='Transfer progress' if detail else 'Transfers')
            surface.queue_send()
            if not detail:
                self.loop.create_task(self.refresh_transfer_history())
        percentage = getattr(self, 'transfer_percentage', None)
        self.transfer_progress.stop()
        self.transfer_progress.max = 100 if percentage is not None or not self.transfer_busy else None
        if self.transfer_progress.max is not None:
            self.transfer_progress.value = 100 if self.transfer_complete else percentage if percentage is not None else 0

    def transfer_surface(self, name, route, *, detail):
        from .surface import TransferSurface

        old = getattr(self, name, None)
        credentials = getattr(self.cloud_client, 'credential_state', None)
        if old is not None and old._credential_state is not credentials:
            old.dispose()
        if old is not None and not old.closed:
            return old

        def visible():
            if not self.active_host:
                return False
            screens = self.routes.screens[self.native_host.state.destination]
            return bool(screens and screens[-1][0] == route
                        and getattr(self, name, None) in screens[-1][1].children)

        async def command(action, args):
            if not visible():
                return
            if detail:
                if action == 'background':
                    self.routes.back()
                elif action == 'stop' and self.transfer_busy:
                    epoch = self.transfer_epoch
                    confirmed = await self.main_window.dialog(toga.ConfirmDialog('Stop this transfer?',
                        'Files already copied, replaced or deleted will stay changed.'))
                    if confirmed and visible() and self.transfer_busy and epoch == self.transfer_epoch:
                        self.cancel_mirror_transfer()
                return
            if action == 'open-transfer':
                if self.transfer_busy and getattr(self, '_transfer_review_view', None) is not None:
                    self.show_view(self._transfer_review_view, destination='files',
                                   route='transfer-review', title='Review changes')
                else:
                    self.show_transfers(detail=True)
            elif action == 'downloads':
                await self.refresh_transfer_history()
            elif action in ('resume-download', 'discard-download') and not self.transfer_busy:
                from features.rclone.mobile.download_recovery import queue_command
                await queue_command(self, action, args, visible)
                await self.refresh_transfer_history()
            elif action == 'clear-history' and not self.transfer_busy:
                from time import time_ns
                cutoff = time_ns()
                client = self.cloud_client
                generation = getattr(client, 'generation', None)
                confirmed = await self.main_window.dialog(toga.ConfirmDialog('Clear transfer history?',
                    'Clear completed records for saved and unlocked connections? Files and interrupted downloads stay in place.'))
                if (confirmed and visible() and not self.transfer_busy and client is self.cloud_client
                        and getattr(client, 'generation', None) == generation):
                    await self.refresh_transfer_history(clear_through=cutoff)
            elif action == 'settings' and not self.transfer_busy:
                self.show_transfer_options()

        surface = TransferSurface(self.app, command, visible=visible, native=True)
        setattr(self, name, surface)
        return surface

    def render_transfer_summary(self):
        from features.rclone.transfers.presentation import progress_model
        model = progress_model(self.state)
        if self.state.display_revoked and not self.transfer_busy:
            model.update(phase='idle', message='No transfer is running.')
        if self.mirror_store().error:
            model.update(phase='failed', message=self.mirror_store().error)
        self.transfer_notice.text = import_hint(self.transfer_message)
        self.transfer_files.text = 'Files\n' + f"{model['files']:,}" + (f" / {model['total_files']:,}" if model['total_files'] else '')
        self.transfer_bytes.text = f"Data (MB)\n{model['done'] / 1_000_000:,.2f} /\n{model['total'] / 1_000_000:,.2f}"
        detail = getattr(self, '_progress_surface', None)
        if detail is not None and not detail.closed:
            detail.update(dict(model, detail=True))
        overview = getattr(self, '_transfers_overview', None)
        if overview is not None and not overview.closed:
            history = {key: overview.model[key] for key in
                       ('downloads', 'history', 'downloads_notice', 'history_notice', 'history_error')
                       if key in overview.model}
            overview.update(dict(history, mode='overview', busy=model['busy'], phase=model['phase'],
                                 operation=model['operation'], workspace=model['workspace'],
                                 percentage=model['percentage']))

    async def refresh_transfer_history(self, *, clear_through=None, write_failed=False):
        from features.rclone.mobile.download_recovery import available_jobs
        from .history import visible_history

        surface = getattr(self, '_transfers_overview', None)
        if surface is None or surface.closed or not self.active_host or (self.transfer_busy and clear_through is not None):
            return
        client = self.cloud_client
        generation = getattr(client, 'generation', None)
        refresh = self._history_refresh = object()
        busy = self.transfer_busy
        unlocked = bool(getattr(client, 'package_records', ()))

        def load():
            downloads_notice = ('No interrupted downloads for the unlocked connections.' if unlocked else
                                'Unlock the original connection to see interrupted downloads.')
            history_notice = 'No completed transfers.'
            downloads, history = [], []
            try:
                jobs = available_jobs(self.app, client=client) if client is not None else ()
                for _, job in jobs:
                    downloads.append(dict(id=job['id'], name=job['selection']['name'], path=job['selection']['path'],
                                          offset=job['offset'], size=job['source']['size'], folder=job.get('kind') == 'folder'))
            except (OSError, ValueError):
                downloads_notice = 'Interrupted downloads could not be loaded.'
            try:
                history = visible_history(self.private_root, client, generation, clear_through=clear_through)
            except (OSError, ValueError):
                history_notice = ('Transfer history could not be cleared.' if clear_through is not None else
                                  'Transfer history could not be loaded.')
            history_error = ('The completed transfer could not be saved in history.' if write_failed else '')
            return dict(downloads=downloads, downloads_notice=downloads_notice, history=history,
                        history_notice=history_notice, history_error=history_error)

        model = await asyncio.to_thread(load)
        if (not surface.closed and self.active_host and busy == self.transfer_busy
                and self._history_refresh is refresh and self.cloud_client is client
                and getattr(client, 'generation', None) == generation):
            surface.update(dict(surface.model, **model))

    def choose_transfer_copy(self, jobs, *, push=False):
        """Resolve an ambiguous transfer without turning details into a folder list."""
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Choose local copy', style=Pack(font_size=22)))
        for job in jobs:
            label = encrypted_copy_label(job['target']) if job['crypt'] else job['target']
            def choose(widget=None, selected=job['id'], **kwargs):
                (self.start_mirror_review if push else self.start_mirror_pull)(selected)
            box.add(toga.Button(label, on_press=choose, style=Pack(height=48)))
        box.add(toga.Button('Choose another workspace', on_press=self.show_locations, style=Pack(height=44)))
        self.show_view(box, destination='files', route='transfer-copy', title='Choose local copy')

    async def delete_mirror_copy(self, key):
        if self.cloud_busy or getattr(self, 'transfer_busy', False) or not self.clear_private_reader():
            return False
        store = self.mirror_store()
        job = store.jobs[key]
        confirmed = await self.main_window.dialog(toga.ConfirmDialog('Delete local folder?',
            'Delete ' + job['remote'] + ' from ' + ('LocalCrypt' if job['crypt'] else 'Local') +
            '? This permanently deletes the folder and everything inside it. It cannot be undone. Online files are kept.'))
        if not confirmed or self.cloud_busy or getattr(self, 'transfer_busy', False):
            return False
        self.set_cloud_busy(True)
        try:
            await asyncio.to_thread(store.delete_copy, key)
            self.transfer_message = 'Local folder deleted. Online files were kept.'
            if hasattr(self, 'files_view'):
                self.file_roots = {**self.app.ordinary_file_roots(include_collections=False),
                                   **self.existing_crypt_locations(), **self.linked_crypt_locations()}
                self.file_provider = None
                self.update_file_locations()
            self.show_transfers()
            return True
        except (OSError, ValueError) as error:
            self.transfer_notice.text = import_hint('Deletion stopped: ' + str(error)[:250])
            return False
        finally:
            self.set_cloud_busy(False)

    async def mirror_connection_ready(self, *, preserve_documents=False):
        self.show_cloud(present=False)
        restore = getattr(self, 'cloud_restore_task', None)
        if restore is not None and not restore.done():
            await restore
        if self.cloud_busy or self.cloud_client is None:
            self.transfer_message = 'Wait for the current request, or load the matching connection in Settings.'
            return False
        if not preserve_documents and not self.clear_private_reader():
            self.transfer_message = 'Save or close provider edits before transferring their local files.'
            return False
        return True

    def start_mirror_pull(self, key):
        if not self.app.require_feature('rclone'):
            return
        self.begin_transfer_review(key, push=False)

    @staticmethod
    def mirror_job_signature(job):
        return tuple(job.get(field) for field in ('id', 'remote', 'identity', 'cipher_identity', 'crypt', 'prefix', 'target')) if job else None


    def start_mirror_review(self, key):
        if not self.app.require_feature('rclone'):
            return
        self.begin_transfer_review(key, push=True)

    async def pull_remote_copy(self, widget=None, **kwargs):
        if getattr(self, 'cloud_busy', False) or getattr(self, 'transfer_busy', False):
            return
        remote = self.selected_cloud_remote()
        if not remote or remote != self.cloud_open_remote:
            self.cloud_status.value = 'Open a remote before pulling its folder.'
            return
        selected = self.cloud_rows.get(self.cloud_entries.value)
        folder = selected['path'] if selected and selected['directory'] else self.cloud_path
        client, generation = self.cloud_client, self.cloud_client.generation
        self.set_cloud_busy(True)
        try:
            raw = await asyncio.to_thread(client.request, 'mirror_info', remote=remote, path=folder)
            logical = await asyncio.to_thread(client.request, 'mirror_info', remote=remote, path=folder, decrypted=True)
            matches = [job for job in self.mirror_store().jobs.values() if job['remote'] == remote
                       and job['identity'] == raw['identity'] and job['prefix'] == (raw if job['crypt'] else logical)['prefix']]
            if not self.active_host or client.generation != generation:
                return
        except Exception as error:
            self.cloud_status.value = 'Could not prepare pull: ' + str(error)[:250]
            return
        finally:
            self.set_cloud_busy(False)
        if len(matches) == 1:
            self.start_mirror_pull(matches[0]['id'])
            return
        if matches:
            self.choose_transfer_copy(matches)
            return
        # Credential storage and file storage are separate choices. Saved packages
        # create ordinary Local copies; only session-loaded crypts offer LocalCrypt.
        session_only = any(remote in record.get('remotes', ()) and not record.get('saved', False)
                           for record in getattr(client, 'package_records', ()))
        storage = 'Local'
        if raw['crypt'] and session_only:
            encrypted = await self.main_window.dialog(toga.QuestionDialog(
                'Use an encrypted copy (recommended)?',
                'An encrypted copy is strongly recommended for session-only credentials. '
                'Yes: keep the existing encrypted names and file contents on disk. '
                'No: create a regular Local copy with decrypted files that remain '
                'readable after credentials lock or the app exits. Both copies remain '
                'on disk. You can review and cancel the transfer after choosing.'))
            storage = 'LocalCrypt' if encrypted else 'Local'
        if not self.active_host or client is not self.cloud_client or client.generation != generation:
            self.cloud_status.value = 'Connections changed. Select the source again.'
            return
        self.begin_transfer_review(remote=remote, folder=folder, storage=storage)

    async def run_mirror_work(self, work, operation, *, source=None, destination=None, authority=None):
        result = await self.execution.run(work, operation, source=source, destination=destination)
        write_failed = False
        if result and authority is not None and source is not None and destination is not None:
            from .history import record_completed
            client = self.cloud_client
            try:
                await asyncio.to_thread(record_completed, self.private_root, client, client.generation,
                                        *authority, operation, source, destination,
                                        self.state.metrics.get('done', 0))
            except (OSError, ValueError):
                write_failed = True
        await self.refresh_transfer_history(write_failed=write_failed)
        return result

    def publish_mirror_progress(self, epoch, values):
        if not self.active_host or epoch != getattr(self, 'transfer_epoch', None) or not self.transfer_busy:
            return
        previous = getattr(self, 'transfer_message', None)
        snapshot = transfer_progress(values)
        self._transfer_progress_snapshot = (epoch, snapshot)
        if hasattr(self, 'state'):
            now = monotonic()
            previous_sample = getattr(self, '_transfer_rate_sample', None)
            self._transfer_rate_sample = (epoch, now, snapshot.done)
            self.state.metrics = dict(values)
            if previous_sample is not None:
                sample_epoch, stamp, offset = previous_sample
                elapsed = now - stamp
                if sample_epoch == epoch and elapsed >= .2 and snapshot.done >= offset:
                    self.state.metrics['bytes_per_second'] = (snapshot.done - offset) / elapsed
        self.transfer_percentage, self.transfer_message = snapshot.percentage, snapshot.message
        done, total = snapshot.done, snapshot.total
        widgets = (id(self.transfer_notice), id(self.cloud_status), id(self.transfer_progress),
                   id(getattr(self, 'cloud_transfer_progress', None)), done, total)
        if hasattr(self, '_progress_surface') or hasattr(self, '_transfers_overview'):
            self.render_transfer_summary()
        if self.transfer_message == previous and widgets == getattr(self, '_mirror_progress_widgets', None):
            # Repeated polling must not force native text/layout redraws while
            # the user opens an unrelated local document during a transfer.
            # Keep exact byte counts in the key so rounded MB cannot hide a
            # changed percentage or a switch from discovery to a known total.
            return
        self._mirror_progress_widgets = widgets
        notice = import_hint(self.transfer_message.replace(' · ', '\n'))
        if self.transfer_notice.text != notice:
            self.transfer_notice.text = notice
        if self.cloud_status.value != self.transfer_message:
            self.cloud_status.value = self.transfer_message
        origin = getattr(self, 'cloud_transfer_progress', None)
        for bar in (self.transfer_progress, origin):
            if bar is None:
                continue
            if self.transfer_percentage is not None:
                if bar.max is None:
                    bar.stop()
                    bar.max = 100
                if bar.value != self.transfer_percentage:
                    bar.value = self.transfer_percentage
            elif bar.max is not None:
                bar.max = None
                bar.start()

        self.refresh_transfer_status()

    def cancel_mirror_transfer(self, widget=None, **kwargs):
        review = getattr(self, '_cancel_transfer_review', None)
        if review is not None:
            review()
            return
        if getattr(self, 'transfer_busy', False):
            if self._transfer_cancel is not None:
                self._transfer_cancel.set()
            if self.cloud_client is not None:
                self.cloud_client.cancel()
            self.transfer_message = 'Stopping transfer… Files already copied, replaced or deleted will stay changed.'
            self.transfer_notice.text = import_hint(self.transfer_message)
            if hasattr(self, '_progress_surface') or hasattr(self, '_transfers_overview'):
                self.render_transfer_summary()



    async def open_mirror_copy(self, key):
        local_read_available = self.rclone_ui.local_read_available
        if self.cloud_busy and not local_read_available(self, private=True):
            return False
        store = self.mirror_store()
        job = store.jobs[key]
        if not job['crypt']:
            return await self.show_files(location=('Local files', job['target']))
        if await self.show_local_location() is False:
            return False
        client, generation = self.cloud_client, getattr(self.cloud_client, 'generation', None)
        origin = self.navigation_generation
        def resolve():
            from features.rclone.transfers.mobile.jobs import local_copy_location
            from features.rclone.localcrypt.mobile.locations import LocalCryptLocation
            from features.rclone.mobile.service import native_service
            remote, folder = local_copy_location(client, job)
            provider = native_service(client).localcrypt.open(LocalCryptLocation(
                collection_path(self.private_root, True), remote, namespace=job['identity'],
                storage_root=self.private_root, create=False, cipher_identity=job['cipher_identity']))
            return remote, folder, provider
        try:
            remote, folder, provider = await asyncio.to_thread(resolve)
        except (OSError, ValueError) as error:
            self.file_status.value = str(error)
            return False
        if (not self.active_host or origin != self.navigation_generation or client is not self.cloud_client
                or generation != getattr(client, 'generation', None)):
            provider.close()
            return False
        label = encrypted_copy_label(remote + ' · ' + job['target'])
        self.file_roots[label] = provider
        self.update_file_locations()
        self.files_view._folder_entry_location = (label, folder)
        self.app.file_browser.history.clear()
        return await self.browser_file_location((label, folder))


class TransferExecutionPresentation:
    """Project retained execution state into controls and the existing routes."""
    def __init__(self, controller):
        self.controller = controller

    async def ready(self, operation):
        self.origin = self.controller.navigation_generation
        return await self.controller.mirror_connection_ready(
            preserve_documents=operation in {'pull', 'download', 'create'})

    def connection(self):
        client = self.controller.cloud_client
        return client, client.generation

    def current(self, client, generation):
        owner = self.controller
        return owner.active_host and owner.cloud_client is client and client.generation == generation

    def show_origin_detail(self):
        owner = self.controller
        destination = owner.native_host.state.destination
        screens = owner.routes.screens[destination]
        same_origin = owner.navigation_generation == getattr(self, 'origin', None)
        if same_origin and screens and screens[-1][0] == 'local-push':
            owner.routes.back()
            setup = getattr(owner, '_transfer_setup_surface', None)
            if setup is not None:
                setup.dispose()
        from_browser = bool(screens and screens[-1][0] in ('browser', 'remote-browser', 'workspace-browser'))
        owner.show_transfers(present=same_origin and (destination == 'files' or from_browser), detail=True)

    def unavailable(self):
        self.show_origin_detail()

    def started(self):
        owner = self.controller
        self.completion = start_transfer_notice()
        self.awake = owner.app.acquire_awake_lease()
        owner.set_cloud_busy(True)
        self.show_origin_detail()
        owner.refresh_transfer_status()

    def progress(self, epoch, values):
        self.controller.publish_mirror_progress(epoch, values)

    def finished(self):
        owner = self.controller
        awake, self.awake = getattr(self, 'awake', None), None
        if awake is not None:
            awake.close()
        owner.set_cloud_busy(False)
        if not owner.active_host:
            return
        state = owner.state
        surfaces = (getattr(owner, '_progress_surface', None), getattr(owner, '_transfers_overview', None))
        observed = owner.rclone_ui.transfer_foreground() and any(
            surface is not None and not surface.closed and surface.visible() for surface in surfaces)
        outcome = {'complete': 'success', 'conflict': 'failure', 'failed': 'failure'}.get(state.result, state.result)
        completion, self.completion = getattr(self, 'completion', None), None
        notice = transfer_notice(completion, outcome, observed=observed, details='Transfers',
                                 locked=state.display_revoked) if completion is not None else None
        if state.display_revoked:
            state.message = 'Connection locked or changed. Review again after unlocking.'
        owner.cloud_status.value = owner.transfer_message
        for bar in (owner.cloud_transfer_progress, owner.transfer_progress):
            bar.stop()
            bar.max = 100
            bar.value = 100 if owner.transfer_complete else 0
        owner.transfer_notice.text = import_hint(owner.transfer_message.replace(' · ', '\n'))
        owner.refresh_transfer_status()
        if owner.transfer_complete and notice is None:
            completed_epoch = owner.transfer_epoch

            def clear_completion():
                if owner.active_host and not owner.transfer_busy and owner.transfer_epoch == completed_epoch:
                    owner.dismiss_transfer_status()

            owner.loop.call_later(5, clear_completion)
        owner.render_transfer_summary()
        if notice is not None:
            epoch = state.epoch

            def details():
                if owner.active_host and owner.state.epoch == epoch:
                    owner.show_transfers(detail=True)

            owner.rclone_ui.publish_transfer_notice(notice, details)
