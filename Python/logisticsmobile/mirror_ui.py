"""Managed copies and transfers which keep ordinary Documents usable."""
import asyncio
from threading import Event
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .mirror_jobs import MirrorJobs


class MirrorUI:
    def register_transfer_status(self, view):
        import weakref
        button = toga.Button('Transfer details', on_press=self.show_transfers, style=Pack(height=36, flex=1))
        dismiss = toga.Button('×', on_press=self.dismiss_transfer_status, style=Pack(width=36, height=36))
        progress = toga.ProgressBar(max=100, value=0, style=Pack(height=4))
        bar = toga.Box(children=[toga.Box(children=[button, dismiss], style=Pack(direction=ROW)), progress],
                       style=Pack(direction=COLUMN, margin_bottom=4))
        bar.notice, bar.progress, bar.dismiss = button, progress, dismiss
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
        live = []
        busy = getattr(self, 'transfer_busy', False)
        visible = busy or getattr(self, 'transfer_notification', False)
        for parent_ref, bar_ref in getattr(self, 'transfer_banners', ()):
            parent, bar = parent_ref(), bar_ref()
            if parent is None or bar is None:
                continue
            live.append((parent_ref, bar_ref))
            # Immersive comics use the full reading area. Transfer work and
            # its notification state continue; show the banner with controls.
            if visible and not getattr(parent, '_comic_fullscreen', False):
                if bar not in parent.children:
                    parent.insert(0, bar)
                bar.notice.text = 'Transfer in progress · Details' if busy else 'Transfer finished · Details'
                if not busy and getattr(self, 'mirror_push_plan', None) is not None:
                    bar.notice.text = 'Push review ready · Details'
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

    def existing_crypt_locations(self):
        result = {}
        client = getattr(self, 'cloud_client', None)
        if client is None or not hasattr(client, 'request'):
            return result
        from .folder_hub import visible_remotes
        for remote in visible_remotes(getattr(self, 'cloud_crypt_remotes', ())):
            try:
                identity = client.request('crypt_path', remote=remote, path='', directory=True)['identity']
                path = self.private_root / 'LocalCryptFolders' / identity
                if path.is_dir() and not path.is_symlink() and any(path.iterdir()):
                    result['LocalCrypt: ' + remote] = remote
            except (OSError, ValueError):
                continue
        return result

    def linked_crypt_locations(self):
        result = {}
        client = getattr(self, 'cloud_client', None)
        if client is None or not hasattr(client, 'request'):
            return result
        from .file_resources import CryptFiles
        store = self.mirror_store()
        for job in store.jobs.values():
            if not job['crypt'] or job['remote'] not in getattr(self, 'cloud_crypt_remotes', ()):
                continue
            try:
                if client.connection_identity(job['remote']) != job['identity'] or not store.target(job).exists():
                    continue
                provider = CryptFiles(self.private_root / 'LocalCryptFolders', client, job['remote'], namespace=job['identity'])
                result['LocalCrypt: ' + job['remote'] + ' (pulled)'] = provider
            except (OSError, ValueError):
                continue
        return result

    def mirror_store(self):
        if not hasattr(self, 'mirrors'):
            self.mirrors = MirrorJobs(self.private_root)
        return self.mirrors

    def show_transfers(self, widget=None, *, present=True, **kwargs):
        store = self.mirror_store()
        box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        box.add(toga.Label('Local copies & transfers', style=Pack(font_size=22)))
        box.add(toga.Label('Pull: remote → device · Push: device → remote', style=Pack(font_size=12, margin_bottom=8)))
        self.transfer_progress = toga.ProgressBar(max=100, value=100 if getattr(self, 'transfer_complete', False) else 0, style=Pack(height=12))
        self.transfer_notice = toga.Label(store.error or getattr(self, 'transfer_message', 'Writing and ordinary reading can continue during a transfer.'))
        box.add(self.transfer_progress)
        box.add(self.transfer_notice)
        if getattr(self, 'mirror_push_plan', None) is not None:
            box.add(toga.Button('Open pending push review', on_press=lambda widget, **kw: self.show_mirror_push_review(), style=Pack(height=44)))
        if getattr(self, 'transfer_busy', False):
            box.add(toga.Button('Cancel transfer', on_press=self.cancel_mirror_transfer, style=Pack(height=44)))
        for job in list(store.jobs.values()):
            key = job['id']
            card = toga.Box(style=Pack(direction=COLUMN, margin_top=12, margin_bottom=8))
            box.add(card)
            card.add(toga.Label(job['remote'], style=Pack(font_size=18, font_weight='bold')))
            card.add(toga.Label(('Encrypted app-private copy' if job['crypt'] else 'On this device/Local/' + job['target'])
                               + (' · downloaded' if store.target(job).exists() else ' · not downloaded')))
            def open_copy(widget=None, selected=key, **kw):
                self.loop.create_task(self.open_mirror_copy(selected))
            def pull(widget=None, selected=key, **kw):
                self.start_mirror_pull(selected)
            def review(widget=None, selected=key, **kw):
                self.start_mirror_review(selected)
            card.add(toga.Box(children=[toga.Button('Open', on_press=open_copy, style=Pack(height=44, flex=1)),
                toga.Button('Pull', on_press=pull, style=Pack(height=44, flex=1)),
                toga.Button('Push…', on_press=review, style=Pack(height=44, flex=1))], style=Pack(direction=ROW)))
            def remove(widget=None, selected=key, **kw):
                if self.cloud_busy or getattr(self, 'transfer_busy', False):
                    return
                try:
                    store.remove(selected)
                    if getattr(self, 'mirror_push_plan', None) is not None and self.mirror_push_plan['job'] == selected:
                        self.invalidate_mirror_review()
                    self.show_transfers()
                except (OSError, ValueError) as error:
                    self.transfer_notice.text = str(error)
            async def delete_copy(widget=None, selected=key, **kw):
                await self.delete_mirror_copy(selected)
            from .action_menu import FeatureCommands
            more = toga.Button('Folder options', style=Pack(height=44))
            card.commands = FeatureCommands(more, self, [('Remove mapping (keep files)', remove),
                ('Delete local folder…', delete_copy)], lambda selected=key: self.show_transfer_folder_options(selected))
            card.add(more)
        box.add(toga.Button('Choose a remote to pull', on_press=self.show_cloud, style=Pack(height=44, margin_top=12)))
        self.transfer_view = toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))
        if present:
            self.show_view(self.transfer_view, destination='files', route='transfers', title='Local copies & transfers')
        if getattr(self, 'transfer_busy', False):
            self.transfer_progress.max = None
            self.transfer_progress.start()

    def show_transfer_folder_options(self, key):
        box = toga.Box(children=[toga.Button('Delete local folder…',
            on_press=lambda widget, **kw: self.loop.create_task(self.delete_mirror_copy(key)), style=Pack(height=48)),
            toga.Button('Return to transfers', on_press=self.show_transfers, style=Pack(height=44))],
            style=Pack(direction=COLUMN, margin=16))
        self.show_view(box, destination='files', route='transfer-folder-options', title='Folder options')

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
            self.invalidate_mirror_review()
            self.transfer_message = 'Local folder deleted. Online files were kept.'
            if hasattr(self, 'files_view'):
                self.file_roots = {'Local files': None, **self.existing_crypt_locations(), **self.linked_crypt_locations()}
                self.file_provider = None
                self.update_file_locations()
            self.show_transfers()
            return True
        except (OSError, ValueError) as error:
            self.transfer_notice.text = 'Deletion stopped: ' + str(error)[:250]
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
        if not getattr(self, 'transfer_busy', False) and not getattr(self, '_transfer_confirmation_pending', False):
            job = self.mirror_store().jobs.get(key)
            if job is None:
                return
            signature = self.mirror_job_signature(job)
            storage = 'LocalCrypt' if job['crypt'] else 'Local'
            self.transfer_task = self.loop.create_task(self.confirmed_mirror_work(
                lambda client, cancel, progress: self.mirror_store().pull(key, client, cancelled=cancel, progress=progress),
                'pull', 'Pull folder?',
                f'From: {job["remote"]}:{job["prefix"]}\nTo: {storage}/{job["target"]}\n\n'
                'Local files may be replaced or removed to match the remote folder. Continue?',
                valid=lambda: self.mirror_job_signature(self.mirror_store().jobs.get(key)) == signature))

    @staticmethod
    def mirror_job_signature(job):
        return tuple(job.get(field) for field in ('id', 'remote', 'identity', 'cipher_identity', 'crypt', 'prefix', 'target')) if job else None

    async def confirmed_mirror_work(self, work, operation, title, message, *, valid=lambda: True):
        if (not self.active_host or self.cloud_busy or getattr(self, 'transfer_busy', False)
                or getattr(self, '_transfer_confirmation_pending', False) or not valid()):
            return False
        client = self.cloud_client
        if client is None:
            return False
        generation = client.generation
        self._transfer_confirmation_pending = True
        try:
            if not await self.main_window.dialog(toga.ConfirmDialog(title, message)):
                return False
            if (not self.active_host or self.cloud_client is not client or client.generation != generation
                    or self.cloud_busy or getattr(self, 'transfer_busy', False) or not valid()):
                return False
            return await self.run_mirror_work(work, operation)
        finally:
            self._transfer_confirmation_pending = False

    def start_mirror_review(self, key):
        if not getattr(self, 'transfer_busy', False) and not getattr(self, '_transfer_confirmation_pending', False):
            self.transfer_task = self.loop.create_task(self.run_mirror_work(
                lambda client, cancel, progress: self.mirror_store().push_plan(key, client, cancelled=cancel, progress=progress), 'review'))

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
            self.show_transfers()
            self.transfer_notice.text = 'Multiple local copies match. Choose Pull beside the destination you want.'
            return
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Pull ' + remote, style=Pack(font_size=22)))
        box.add(toga.Label('Choose app-private storage.\nLocal stores readable files.\nLocalCrypt retains encrypted names and bytes.\nPull replaces local contents to match this remote.'))
        def start(storage):
            def handler(widget=None, **kw):
                if client is not self.cloud_client or client.generation != generation:
                    self.cloud_status.value = 'Connections changed. Select the source again.'
                    self.show_cloud()
                    return
                self.transfer_task = self.loop.create_task(self.confirmed_mirror_work(
                    lambda client, cancel, progress: self.mirror_store().create(client, remote, folder,
                        storage=storage, cancelled=cancel, progress=progress), 'create', 'Pull folder?',
                    f'From: {remote}:{folder}\nTo: {storage} on this device\n\n'
                    'Existing local files may be replaced or removed to match the remote. Continue?',
                    valid=lambda: client is self.cloud_client and client.generation == generation))
            return handler
        box.add(toga.Button('Pull to Local', on_press=start('Local'), style=Pack(height=48)))
        box.add(toga.Button('Pull to LocalCrypt', on_press=start('LocalCrypt'), enabled=raw['crypt'], style=Pack(height=48)))
        if not raw['crypt']:
            box.add(toga.Label('LocalCrypt needs a crypt remote in your credential ZIP.'))
        box.add(toga.Button('Cancel', on_press=self.show_cloud, style=Pack(height=44)))
        self.show_view(box, destination='files', route='pull-destination', title='Pull destination')

    async def push_remote_copy(self, widget=None, **kwargs):
        if self.cloud_busy or getattr(self, 'transfer_busy', False):
            return
        remote = self.selected_cloud_remote()
        if remote != self.cloud_open_remote:
            self.cloud_status.value = 'Open the remote before reviewing a push.'
            return
        # Transfer cards retain prefix and identity so a Push cannot select another account.
        self.show_transfers()
        self.transfer_notice.text = 'Choose Push beside the local copy to review its destination and replacements.'

    async def run_mirror_work(self, work, operation):
        if getattr(self, 'transfer_busy', False):
            return False
        if not await self.mirror_connection_ready():
            self.show_transfers(present=self.native_host.state.destination == 'files')
            return False
        client, generation = self.cloud_client, self.cloud_client.generation
        self.transfer_busy = True
        self.transfer_notification = True
        self.transfer_complete = False
        self.set_cloud_busy(True)
        self._crypt_cancel = Event()
        cancel = self._crypt_cancel
        self.transfer_message = 'Preparing transfer…'
        self.show_transfers(present=self.native_host.state.destination == 'files')
        self.refresh_transfer_status()
        epoch = self.transfer_epoch = getattr(self, 'transfer_epoch', 0) + 1
        def progress(**values):
            self.loop.call_soon_threadsafe(self.publish_mirror_progress, epoch, values)
        result = None
        try:
            result = await asyncio.to_thread(work, client, cancel.is_set, progress)
            if not self.active_host or client.generation != generation:
                return False
            if operation == 'review':
                self.mirror_push_plan = result
                self.transfer_message = 'Push review is ready.'
            elif operation == 'push':
                self.transfer_message = f'Push sync verified: {result} file(s) sent. Destination-only entries were removed.'
                self.mirror_push_plan = None
            else:
                status, _ = result[1] if operation == 'create' else result
                self.transfer_message = ('Files changed during the operation; inspect the local destination.'
                                         if status == 'conflict' else 'Pull sync complete. The local folder now matches the remote.')
            return True
        except Exception as error:
            self.transfer_message = 'Sync stopped; completed destination changes remain. ' + str(error)[:350]
            return False
        finally:
            self.transfer_epoch += 1
            self._crypt_cancel = None
            self.transfer_busy = False
            self.set_cloud_busy(False)
            if self.active_host:
                self.transfer_complete = result is not None
                self.cloud_status.value = self.transfer_message
                self.cloud_transfer_progress.stop()
                self.cloud_transfer_progress.max = 100
                self.cloud_transfer_progress.value = 100 if result is not None else 0
                self.transfer_notice.text = self.transfer_message
                self.transfer_progress.stop()
                self.transfer_progress.max = 100
                self.transfer_progress.value = 100 if result is not None else 0
                self.refresh_transfer_status()
                if operation == 'review' and result is not None and self.native_host.state.destination == 'files':
                    self.show_mirror_push_review()
                elif (self.native_host.state.destination == 'files' and self.routes.screens['files']
                      and self.routes.screens['files'][-1][0] == 'transfers'):
                    # A transfer completion updates its own status. It does not
                    # take Documents away while a reader/editor is active.
                    self.show_transfers()

    def publish_mirror_progress(self, epoch, values):
        if not self.active_host or epoch != getattr(self, 'transfer_epoch', None) or not self.transfer_busy:
            return
        previous = getattr(self, 'transfer_message', None)
        phase, files = values['phase'], values['files']
        done, total = values['done'], values['total']
        self.transfer_message = f'{phase} · {files:,} file(s) completed'
        if values.get('total_files', 0):
            self.transfer_message += f' / {values["total_files"]:,} known'
        if values.get('active', 0):
            self.transfer_message += f' · {values["active"]:,} transferring'
        if values.get('listed', 0) or values.get('checks', 0):
            self.transfer_message += f' · {values.get("listed", 0):,} discovered · {values.get("checks", 0):,} checked'
        if total > 0:
            self.transfer_message += f' · {done:,} / {total:,} bytes (known so far)'
        elif done > 0:
            self.transfer_message += f' · {done:,} bytes transferred'
        widgets = (id(self.transfer_notice), id(self.cloud_status), id(self.transfer_progress),
                   id(getattr(self, 'cloud_transfer_progress', None)))
        if self.transfer_message == previous and widgets == getattr(self, '_mirror_progress_widgets', None):
            # Repeated polling must not force native text/layout redraws while
            # the user opens an unrelated local document during a transfer.
            return
        self._mirror_progress_widgets = widgets
        self.transfer_notice.text = self.transfer_message
        self.cloud_status.value = self.transfer_message
        origin = getattr(self, 'cloud_transfer_progress', None)
        for bar in (self.transfer_progress, origin):
            if bar is None:
                continue
            if total > 0:
                if bar.max is None:
                    bar.stop()
                    bar.max = 100
                bar.value = min(99, 100 * done / total)
            elif bar.max is not None:
                bar.max = None
                bar.start()

        self.refresh_transfer_status()

    def cancel_mirror_transfer(self, widget=None, **kwargs):
        if getattr(self, 'transfer_busy', False):
            self.cancel_cloud()
            self.transfer_message = 'Cancelling sync; completed destination changes remain.'
            self.transfer_notice.text = self.transfer_message

    def show_mirror_push_review(self):
        plan = self.mirror_push_plan
        job = self.mirror_store().jobs[plan['job']]
        folder = job['prefix']
        if job['crypt']:
            try:
                if self.cloud_client.connection_identity(job['remote']) != job['identity']:
                    raise ValueError('The matching connection is unavailable.')
                folder = self.cloud_client.request('crypt_path', remote=job['remote'], identity=job['cipher_identity'],
                                                   path=folder, directory=True, decode=True)['path']
            except (OSError, ValueError):
                self.invalidate_mirror_review()
                self.transfer_message = 'Unlock the matching connection and review this push again.'
                self.show_transfers()
                return
        replaced = sum(bool(item['expected']) for item in plan['writes'])
        box = self.mirror_review_view = toga.Box(style=Pack(direction=COLUMN, margin=16))
        from .cloud_ui import import_hint
        box.add(toga.Label(import_hint('Review push to ' + job['remote']), style=Pack(font_size=22)))
        source = ('LocalCrypt' if job['crypt'] else 'Local') + '/' + (folder if job['crypt'] else job['target'])
        box.add(toga.Label(import_hint(f'From: {source}\nTo: {job["remote"]}:{folder}\n'
                          f'{len(plan["writes"])} file(s) to send, including {replaced} replacement(s).\n'
                          f'{plan["unchanged"]} file(s) already match.\n'
                          f'{len(plan["deletes"])} destination-only or conflicting entry(s) will be removed.\n'
                          f'{len(plan["directories"])} folder(s) will be checked or created.\n'
                          'This is plain rclone sync: replacements and deletions have no backup.\nCancelled syncs can leave completed changes on the destination.\n'
                          'Avoid another writer in this remote folder during Push.')))
        if plan['deletes']:
            removed = []
            for path in plan['deletes']:
                name = path
                if job['crypt']:
                    full = '/'.join(part for part in (job['prefix'], path) if part)
                    name = self.cloud_client.request('crypt_path', remote=job['remote'], identity=job['cipher_identity'],
                        path=full, directory=plan['remote'][path] is None, decode=True)['path']
                removed.append(name)
            box.add(toga.MultilineTextInput(value='Remove from destination:\n' + '\n'.join(removed), readonly=True, style=Pack(height=160)))
        signature = self.mirror_job_signature(job)
        async def confirm(widget=None, **kw):
            if self.active_host and self.mirror_push_plan is plan and not getattr(self, 'transfer_busy', False):
                self.transfer_task = self.loop.create_task(self.confirmed_mirror_work(
                    lambda client, cancel, progress: self.mirror_store().push(plan, client, cancelled=cancel, progress=progress),
                    'push', 'Push folder?',
                    f'From: {source}\nTo: {job["remote"]}:{folder}\n\n'
                    f'Send {len(plan["writes"])} file(s), replace {replaced}, and remove {len(plan["deletes"])} destination entry(s)?\n'
                    'Remote changes have no backup.', valid=lambda: self.mirror_push_plan is plan
                    and self.mirror_job_signature(self.mirror_store().jobs.get(plan['job'])) == signature))
                await self.transfer_task
        def cancel(widget=None, **kw):
            self.mirror_push_plan = None
            self.show_transfers()
        box.add(toga.Button('Push these files', on_press=confirm, enabled=bool(plan['writes'] or plan['directories'] or plan['deletes']), style=Pack(height=48)))
        box.add(toga.Button('Cancel', on_press=cancel, style=Pack(height=44)))
        self.show_view(box, destination='files', route='push-review', title='Review push')

    def invalidate_mirror_review(self):
        self.mirror_push_plan = None
        box = getattr(self, 'mirror_review_view', None)
        if box is not None:
            for child in list(box.children):
                box.remove(child)
            box.add(toga.Label('Push review closed. Review again with the current connection.'))

    async def open_mirror_copy(self, key):
        if getattr(self, 'cloud_busy', False):
            return False
        store = self.mirror_store()
        job = store.jobs[key]
        await self.show_local_location()
        if job['crypt']:
            try:
                matched = self.cloud_client is not None and self.cloud_client.connection_identity(job['remote']) == job['identity']
            except (OSError, ValueError):
                matched = False
            if not matched:
                self.file_status.value = 'Unlock the matching connection before opening this LocalCrypt copy.'
                return False
            label = 'LocalCrypt: ' + job['remote'] + ' (pulled)'
            folder = self.cloud_client.request('crypt_path', remote=job['remote'], identity=job['cipher_identity'],
                                             path=job['prefix'], directory=True, decode=True)['path']
            from .file_resources import CryptFiles
            provider = CryptFiles(self.private_root / 'LocalCryptFolders', self.cloud_client, job['remote'], namespace=job['identity'])
            self.file_roots[label] = provider
            self.update_file_locations()
            return await self.browser_file_location((label, folder))
        return await self.browser_file_location(('Local files', job['target']))
