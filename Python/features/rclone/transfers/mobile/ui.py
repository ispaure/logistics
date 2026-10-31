"""Managed copies and transfers which keep ordinary Documents usable."""
from services.documents.locations import collection_path
import asyncio
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
                    roots['LocalCrypt: ' + remote] = (remote, identity)
                if base is None:
                    base = collection_path(self.private_root, True)
                path = base / identity
                if path.is_dir() and not path.is_symlink() and any(path.iterdir()):
                    result['LocalCrypt: ' + remote] = remote
            except (OSError, ValueError):
                continue
        return result

    def crypt_folder_target(self, remote):
        identity = self.cloud_client.request('crypt_path', remote=remote, path='', directory=True)['identity']
        return self.mirror_store().guard(collection_path(self.private_root, True) / identity)

    def linked_crypt_locations(self):
        if not self.app.feature_enabled('rclone'):
            return {}
        result = {}
        client = getattr(self, 'cloud_client', None)
        if client is None or not hasattr(client, 'request'):
            return result
        from features.rclone.localcrypt.mobile.locations import LocalCryptLocation
        from features.rclone.mobile.service import native_service
        store = self.mirror_store()
        from features.rclone.transfers.mobile.jobs import resolved_job
        for job in store.jobs.values():
            job = resolved_job(client, job)
            if not job['crypt'] or job['remote'] not in getattr(self, 'cloud_crypt_remotes', ()):
                continue
            try:
                if client.connection_identity(job['remote']) != job['identity'] or not store.target(job).exists():
                    continue
                provider = native_service(client).localcrypt.open(LocalCryptLocation(collection_path(self.private_root, True), job['remote'], namespace=job['identity'], storage_root=self.private_root))
                result['LocalCrypt: ' + job['remote'] + ' (pulled)'] = provider
            except (OSError, ValueError):
                continue
        return result

    def mirror_store(self):
        if not hasattr(self, 'mirrors'):
            self.mirrors = MirrorJobs(self.private_root)
        return self.mirrors

    def show_transfers(self, widget=None, *, present=True, **kwargs):
        if not self.app.require_feature('rclone'):
            return
        if getattr(self, '_transfer_review_view', None) is not None:
            if present:
                self.show_view(self._transfer_review_view, destination='files', route='transfer-review', title='Transfer review')
            return
        store = self.mirror_store()
        box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        box.add(toga.Label('Transfer details', style=Pack(font_size=22)))
        endpoints = getattr(self, 'transfer_endpoints', None)
        if endpoints:
            source, destination = endpoints
            box.add(toga.Label(import_hint(f'From: {source}\nTo: {destination}'),
                               style=Pack(font_size=12, margin_bottom=8)))
        box.add(toga.Button('Back', on_press=lambda widget, **kwargs: self.routes.back(), style=Pack(height=48)))
        self.transfer_progress = toga.ProgressBar(max=100, value=100 if getattr(self, 'transfer_complete', False) else 0, style=Pack(height=12))
        self.transfer_notice = toga.Label(import_hint((store.error or getattr(self, 'transfer_message', 'No transfer is running.')).replace(' · ', '\n')))
        box.add(self.transfer_progress)
        box.add(self.transfer_notice)
        box.add(toga.Label(import_hint('You can leave this screen while the transfer continues. Local documents remain available. Cloud previews must wait until the transfer finishes.\n\nThe total can grow as more files are found. Progress reaches 100% after verification.'), style=Pack(font_size=12, margin_top=12)))
        if not getattr(self, 'transfer_busy', False):
            box.add(toga.Button('Transfer settings…', on_press=self.show_transfer_options, style=Pack(height=44)))
        if getattr(self, 'transfer_busy', False):
            box.add(toga.Button('Cancel transfer', on_press=self.cancel_mirror_transfer, style=Pack(height=44)))
        self.transfer_view = toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))
        if present:
            self.show_view(self.transfer_view, route='transfers', title='Transfer details')
        if getattr(self, 'transfer_busy', False):
            percentage = getattr(self, 'transfer_percentage', None)
            if percentage is None:
                self.transfer_progress.max = None
                self.transfer_progress.start()
            else:
                self.transfer_progress.value = percentage

    def choose_transfer_copy(self, jobs, *, push=False):
        """Resolve an ambiguous transfer without turning details into a folder list."""
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Choose local copy', style=Pack(font_size=22)))
        for job in jobs:
            storage = 'LocalCrypt' if job['crypt'] else 'Local'
            def choose(widget=None, selected=job['id'], **kwargs):
                (self.start_mirror_review if push else self.start_mirror_pull)(selected)
            box.add(toga.Button(storage + '/' + job['target'], on_press=choose, style=Pack(height=48)))
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
                self.file_roots = {'Local files': None, **self.existing_crypt_locations(), **self.linked_crypt_locations()}
                self.file_provider = None
                self.update_file_locations()
            self.show_transfers()
            return True
        except (OSError, ValueError) as error:
            self.transfer_notice.text = import_hint('Deletion stopped: ' + str(error)[:250])
            return False
        finally:
            self.set_cloud_busy(False)

    async def mirror_connection_ready(self):
        self.show_cloud(present=False)
        restore = getattr(self, 'cloud_restore_task', None)
        if restore is not None and not restore.done():
            await restore
        if self.cloud_busy or self.cloud_client is None:
            self.transfer_message = 'Wait for the current request, or load the matching connection in Settings.'
            return False
        if not self.clear_private_reader():
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
                'Use LocalCrypt (recommended)?',
                'LocalCrypt is strongly recommended for session-only credentials. '
                'Yes: keep the existing encrypted names and file contents on disk. '
                'No: create a regular Local copy with decrypted files that remain '
                'readable after credentials lock or the app exits. Both copies remain '
                'on disk. You can review and cancel the transfer after choosing.'))
            storage = 'LocalCrypt' if encrypted else 'Local'
        if not self.active_host or client is not self.cloud_client or client.generation != generation:
            self.cloud_status.value = 'Connections changed. Select the source again.'
            return
        self.begin_transfer_review(remote=remote, folder=folder, storage=storage)

    async def push_remote_copy(self, widget=None, **kwargs):
        if self.cloud_busy or getattr(self, 'transfer_busy', False):
            return
        remote = self.selected_cloud_remote()
        if remote != self.cloud_open_remote:
            self.cloud_status.value = 'Open the remote before reviewing a push.'
            return
        jobs = [job for job in self.mirror_store().jobs.values()
                if job['remote'] == remote and self.mirror_store().target(job).is_dir()]
        if len(jobs) == 1:
            self.start_mirror_review(jobs[0]['id'])
        elif jobs:
            self.choose_transfer_copy(jobs, push=True)
        else:
            self.cloud_status.value = 'No local copy exists. Choose a folder in Files and Pull first.'

    async def run_mirror_work(self, work, operation, *, source=None, destination=None):
        return await self.execution.run(work, operation, source=source, destination=destination)

    def publish_mirror_progress(self, epoch, values):
        if not self.active_host or epoch != getattr(self, 'transfer_epoch', None) or not self.transfer_busy:
            return
        previous = getattr(self, 'transfer_message', None)
        snapshot = transfer_progress(values)
        self.transfer_percentage, self.transfer_message = snapshot.percentage, snapshot.message
        done, total = snapshot.done, snapshot.total
        widgets = (id(self.transfer_notice), id(self.cloud_status), id(self.transfer_progress),
                   id(getattr(self, 'cloud_transfer_progress', None)), done, total)
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



    async def open_mirror_copy(self, key):
        local_read_available = self.rclone_ui.local_read_available
        if self.cloud_busy and not local_read_available(self, private=True):
            return False
        store = self.mirror_store()
        job = store.jobs[key]
        await self.show_local_location()
        if job['crypt']:
            client, generation = self.cloud_client, getattr(self.cloud_client, 'generation', None)
            origin = self.navigation_generation
            def resolve():
                from features.rclone.transfers.mobile.jobs import remote_location
                from features.rclone.localcrypt.mobile.locations import LocalCryptLocation
                from features.rclone.mobile.service import native_service
                _, folder = remote_location(client, dict(job))
                provider = native_service(client).localcrypt.open(LocalCryptLocation(
                    collection_path(self.private_root, True), job['remote'], namespace=job['identity'], storage_root=self.private_root))
                return folder, provider
            try:
                folder, provider = await asyncio.to_thread(resolve)
            except (OSError, ValueError) as error:
                self.file_status.value = str(error)
                return False
            if (not self.active_host or origin != self.navigation_generation or client is not self.cloud_client
                    or generation != getattr(client, 'generation', None)):
                provider.close()
                return False
            label = 'LocalCrypt: ' + job['remote'] + ' (pulled)'
            self.file_roots[label] = provider
            self.update_file_locations()
            return await self.browser_file_location((label, folder))
        return await self.browser_file_location(('Local files', job['target']))


class TransferExecutionPresentation:
    """Project retained execution state into controls and the existing routes."""
    def __init__(self, controller):
        self.controller = controller

    async def ready(self):
        self.origin = self.controller.navigation_generation
        return await self.controller.mirror_connection_ready()

    def connection(self):
        client = self.controller.cloud_client
        return client, client.generation

    def current(self, client, generation):
        owner = self.controller
        return owner.active_host and owner.cloud_client is client and client.generation == generation

    def unavailable(self):
        owner = self.controller
        owner.show_transfers(present=(owner.native_host.state.destination == 'files'
            and owner.navigation_generation == getattr(self, 'origin', None)))

    def started(self):
        owner = self.controller
        owner.set_cloud_busy(True)
        owner.show_transfers(present=(owner.native_host.state.destination == 'files'
            and owner.navigation_generation == getattr(self, 'origin', None)))
        owner.refresh_transfer_status()

    def progress(self, epoch, values):
        self.controller.publish_mirror_progress(epoch, values)

    def finished(self):
        owner = self.controller
        owner.set_cloud_busy(False)
        if not owner.active_host:
            return
        owner.cloud_status.value = owner.transfer_message
        for bar in (owner.cloud_transfer_progress, owner.transfer_progress):
            bar.stop()
            bar.max = 100
            bar.value = 100 if owner.transfer_complete else 0
        owner.transfer_notice.text = import_hint(owner.transfer_message.replace(' · ', '\n'))
        owner.refresh_transfer_status()
        if owner.transfer_complete:
            completed_epoch = owner.transfer_epoch

            def clear_completion():
                if owner.active_host and not owner.transfer_busy and owner.transfer_epoch == completed_epoch:
                    owner.dismiss_transfer_status()

            owner.loop.call_later(5, clear_completion)
        screens = owner.routes.screens[owner.native_host.state.destination]
        if screens and screens[-1][0] == 'transfers':
            owner.show_transfers()
