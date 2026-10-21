"""Managed copies and transfers which keep ordinary Documents usable."""
from features.rclone.mobile.storage_location import collection_path
import asyncio
from threading import Event, Lock
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from features.rclone.transfers.mobile.jobs import MirrorJobs
from features.rclone.mobile.messages import import_hint
from features.rclone.transfers.mobile.review_ui import TransferReviewUI


def coalesced_progress(loop, publish):
    """Keep only the newest worker snapshot while native UI rendering is busy."""
    lock = Lock()
    latest, scheduled = None, False

    def drain():
        nonlocal latest, scheduled
        with lock:
            values, latest, scheduled = latest, None, False
        # Rendering can be slow. Do not hold the worker lock across native UI;
        # arrivals during this call can schedule at most one successor.
        publish(values)

    def progress(**values):
        nonlocal latest, scheduled
        with lock:
            latest = values
            if scheduled:
                return
            scheduled = True
        loop.call_soon_threadsafe(drain)

    return progress


class MirrorUI(TransferReviewUI):
    def register_transfer_status(self, view, *, visible_when=lambda: True):
        import weakref
        button = toga.Button('Transfer details', on_press=self.show_transfers, style=Pack(height=48, flex=1))
        accessible_name = self.rclone_ui.accessible_name
        dismiss = accessible_name(toga.Button('×', on_press=self.dismiss_transfer_status, style=Pack(width=48, height=48)),
                                  'Dismiss transfer notification')
        progress = toga.ProgressBar(max=100, value=0, style=Pack(height=4))
        bar = toga.Box(children=[toga.Box(children=[button, dismiss], style=Pack(direction=ROW)), progress],
                       style=Pack(direction=COLUMN, margin_bottom=4))
        bar.notice, bar.progress, bar.dismiss = button, progress, dismiss
        bar.visible_when = visible_when
        view.transfer_banner = bar
        if not hasattr(self, 'transfer_banners'):
            self.transfer_banners = []
        self.transfer_banners.append((weakref.ref(view), weakref.ref(bar)))
        self.refresh_transfer_status()

    def dismiss_transfer_status(self, widget=None, **kwargs):
        if not getattr(self, 'transfer_busy', False):
            self.transfer_notification = False
            self.refresh_transfer_status()

    def refresh_transfer_status(self):
        self.rclone_ui.refresh_folder_source_actions()
        live = []
        busy = getattr(self, 'transfer_busy', False)
        visible = busy or getattr(self, 'transfer_notification', False)
        for parent_ref, bar_ref in getattr(self, 'transfer_banners', ()):
            parent, bar = parent_ref(), bar_ref()
            if parent is None or bar is None:
                continue
            live.append((parent_ref, bar_ref))
            if hasattr(parent, '_native_reader_buttons'):
                # Native title bars own reader status; keep document content clear.
                if bar in parent.children:
                    bar.progress.stop()
                    parent.remove(bar)
                continue
            # Immersive comics use the full reading area. Transfer work and
            # its notification state continue; show the banner with controls.
            if visible and bar.visible_when() and not (getattr(parent, '_comic_fullscreen', False)
                                or getattr(parent, '_reader_fullscreen', False)):
                if bar not in parent.children:
                    parent.insert(0, bar)
                bar.notice.text = 'Transfer in progress · Details' if busy else 'Transfer finished · 100% · Details'
                percentage = getattr(self, 'transfer_percentage', None)
                if busy and percentage is not None:
                    bar.notice.text = f'Transfer · {percentage:.0f}% of known work · Details'
                if not busy and not getattr(self, 'transfer_complete', False):
                    bar.notice.text = 'Transfer stopped · Details'
                bar.dismiss.enabled = not busy
                source = getattr(self, 'transfer_progress', None)
                if busy and source is not None and source.max is None:
                    if bar.progress.max is not None:
                        bar.progress.max = None
                        bar.progress.start()
                else:
                    if bar.progress.max is None:
                        bar.progress.stop()
                        bar.progress.max = 100
                    bar.progress.value = source.value if source is not None else 0
            elif bar in parent.children:
                bar.progress.stop()
                parent.remove(bar)
        self.transfer_banners = live
        refresh_chrome = getattr(self.rclone_ui, 'refresh_transfer_chrome', None)
        if refresh_chrome is not None:
            refresh_chrome()

    def existing_crypt_locations(self, *, roots=None):
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
        result = {}
        client = getattr(self, 'cloud_client', None)
        if client is None or not hasattr(client, 'request'):
            return result
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        store = self.mirror_store()
        from features.rclone.transfers.mobile.jobs import resolved_job
        for job in store.jobs.values():
            job = resolved_job(client, job)
            if not job['crypt'] or job['remote'] not in getattr(self, 'cloud_crypt_remotes', ()):
                continue
            try:
                if client.connection_identity(job['remote']) != job['identity'] or not store.target(job).exists():
                    continue
                provider = CryptFiles(collection_path(self.private_root, True), client, job['remote'], namespace=job['identity'], storage_root=self.private_root)
                result['LocalCrypt: ' + job['remote'] + ' (pulled)'] = provider
            except (OSError, ValueError):
                continue
        return result

    def mirror_store(self):
        if not hasattr(self, 'mirrors'):
            self.mirrors = MirrorJobs(self.private_root)
        return self.mirrors

    def show_transfers(self, widget=None, *, present=True, **kwargs):
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
        self.begin_transfer_review(key, push=False)

    @staticmethod
    def mirror_job_signature(job):
        return tuple(job.get(field) for field in ('id', 'remote', 'identity', 'cipher_identity', 'crypt', 'prefix', 'target')) if job else None


    def start_mirror_review(self, key):
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
        if getattr(self, 'transfer_busy', False):
            return False
        if not await self.mirror_connection_ready():
            self.show_transfers(present=self.native_host.state.destination == 'files')
            return False
        client, generation = self.cloud_client, self.cloud_client.generation
        self.transfer_endpoints = (source, destination) if source is not None and destination is not None else None
        self.transfer_busy = True
        self.transfer_notification = True
        self.transfer_complete = False
        self.transfer_percentage = None
        self.set_cloud_busy(True)
        self._transfer_cancel = Event()
        cancel = self._transfer_cancel
        self.transfer_message = 'Preparing transfer…'
        self.show_transfers(present=self.native_host.state.destination == 'files')
        self.refresh_transfer_status()
        epoch = self.transfer_epoch = getattr(self, 'transfer_epoch', 0) + 1
        progress = coalesced_progress(self.loop, lambda values: self.publish_mirror_progress(epoch, values))
        result = None
        try:
            result = await asyncio.to_thread(work, client, cancel.is_set, progress)
            if not self.active_host or client.generation != generation:
                return False
            if operation == 'push':
                self.transfer_message = f'Push sync verified: {result} file(s) sent. Destination-only entries were removed.'
            else:
                status, _ = result[1] if operation == 'create' else result
                self.transfer_message = ('Files changed during the operation; inspect the local destination.'
                                         if status == 'conflict' else 'Pull sync complete. The local folder now matches the remote.')
            self.transfer_message = '100% · ' + self.transfer_message
            return True
        except Exception as error:
            self.transfer_message = 'Sync stopped; completed destination changes remain. ' + str(error)[:350]
            return False
        finally:
            self.transfer_epoch += 1
            self._transfer_cancel = None
            self.transfer_busy = False
            self.set_cloud_busy(False)
            if self.active_host:
                self.transfer_complete = result is not None
                self.cloud_status.value = self.transfer_message
                self.cloud_transfer_progress.stop()
                self.cloud_transfer_progress.max = 100
                self.cloud_transfer_progress.value = 100 if result is not None else 0
                self.transfer_notice.text = import_hint(self.transfer_message.replace(' · ', '\n'))
                self.transfer_progress.stop()
                self.transfer_progress.max = 100
                self.transfer_progress.value = 100 if result is not None else 0
                self.refresh_transfer_status()
                if self.transfer_complete:
                    completed_epoch = self.transfer_epoch

                    def clear_completion():
                        if (self.active_host and not self.transfer_busy
                                and self.transfer_epoch == completed_epoch):
                            self.dismiss_transfer_status()

                    self.loop.call_later(5, clear_completion)
                screens = self.routes.screens[self.native_host.state.destination]
                if screens and screens[-1][0] == 'transfers':
                    # A transfer completion updates its own status. It does not
                    # take Documents away while a reader/editor is active.
                    self.show_transfers()

    def publish_mirror_progress(self, epoch, values):
        if not self.active_host or epoch != getattr(self, 'transfer_epoch', None) or not self.transfer_busy:
            return
        previous = getattr(self, 'transfer_message', None)
        phase, files = values['phase'], values['files']
        done, total = values['done'], values['total']
        total_files = values.get('total_files', 0)
        # Rclone discovers work while syncing. Prefer bytes; zero-byte files
        # can still supply a useful file-based total. Completion is verified
        # separately, so keep live progress below 100%.
        numerator, denominator = (done, total) if total > 0 else (files, total_files)
        self.transfer_percentage = min(99, max(0, 100 * numerator / denominator)) if denominator > 0 else None
        phase = {'Discovering / checking files': 'Finding and comparing files…',
                 'Checking / finishing sync': 'Finishing and checking the destination…',
                 'Sync complete; verifying local copy': 'Verifying the local copy…',
                 'Transferring': 'Copying files…'}.get(phase, phase)
        self.transfer_message = f'{phase} · Files copied: {files:,}'
        if total_files > 0:
            self.transfer_message += f' of {total_files:,} found so far'
        if self.transfer_percentage is not None:
            self.transfer_message += f' · {self.transfer_percentage:.0f}% of known work'
        if values.get('attempt', 0) > 1 or values.get('retrying'):
            state = 'Retrying' if values.get('retrying') else 'Attempt'
            self.transfer_message += f' · {state} {values["attempt"]}/{values["max_attempts"]}'
        if values.get('active', 0):
            self.transfer_message += f' · Copying now: {values["active"]:,} files'
        if values.get('listed', 0) or values.get('checks', 0):
            self.transfer_message += f' · Files found: {values.get("listed", 0):,} · Files compared: {values.get("checks", 0):,}'
        if total > 0:
            self.transfer_message += f' · {done / 1_000_000:,.2f} / {total / 1_000_000:,.2f} MB (known so far)'
        elif done > 0:
            self.transfer_message += f' · {done / 1_000_000:,.2f} MB transferred'
        widgets = (id(self.transfer_notice), id(self.cloud_status), id(self.transfer_progress),
                   id(getattr(self, 'cloud_transfer_progress', None)), done, total)
        if self.transfer_message == previous and widgets == getattr(self, '_mirror_progress_widgets', None):
            # Repeated polling must not force native text/layout redraws while
            # the user opens an unrelated local document during a transfer.
            # Keep exact byte counts in the key so rounded MB cannot hide a
            # changed percentage or a switch from discovery to a known total.
            return
        self._mirror_progress_widgets = widgets
        self.transfer_notice.text = import_hint(self.transfer_message.replace(' · ', '\n'))
        self.cloud_status.value = self.transfer_message
        origin = getattr(self, 'cloud_transfer_progress', None)
        for bar in (self.transfer_progress, origin):
            if bar is None:
                continue
            if self.transfer_percentage is not None:
                if bar.max is None:
                    bar.stop()
                    bar.max = 100
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
                from features.rclone.localcrypt.mobile.resources import CryptFiles
                _, folder = remote_location(client, dict(job))
                provider = CryptFiles(collection_path(self.private_root, True), client,
                                      job['remote'], namespace=job['identity'], storage_root=self.private_root)
                return folder, provider
            try:
                folder, provider = await asyncio.to_thread(resolve)
            except (OSError, ValueError) as error:
                self.file_status.value = str(error)
                return False
            if (not self.active_host or origin != self.navigation_generation or client is not self.cloud_client
                    or generation != getattr(client, 'generation', None)):
                return False
            label = 'LocalCrypt: ' + job['remote'] + ' (pulled)'
            self.file_roots[label] = provider
            self.update_file_locations()
            return await self.browser_file_location((label, folder))
        return await self.browser_file_location(('Local files', job['target']))
