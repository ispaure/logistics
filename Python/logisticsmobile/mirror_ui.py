"""Managed copies and transfers which keep ordinary Documents usable."""
import asyncio
from threading import Event
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .mirror_jobs import MirrorJobs


class MirrorUI:
    def mirror_store(self):
        if not hasattr(self, 'mirrors'):
            self.mirrors = MirrorJobs(self.private_root)
        return self.mirrors

    def show_transfers(self, widget=None, **kwargs):
        store = self.mirror_store()
        box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        box.add(toga.Label('Local copies & transfers', style=Pack(font_size=22)))
        box.add(toga.Label('Pull brings files to Local or encrypted LocalCrypt.\nPush is reviewed before it changes remote files.'))
        self.transfer_progress = toga.ProgressBar(max=100, value=100 if getattr(self, 'transfer_complete', False) else 0, style=Pack(height=12))
        self.transfer_notice = toga.Label(store.error or getattr(self, 'transfer_message', 'Writing and ordinary reading can continue during a transfer.'))
        box.add(self.transfer_progress)
        box.add(self.transfer_notice)
        if getattr(self, 'mirror_push_plan', None) is not None:
            box.add(toga.Button('Open pending push review', on_press=lambda widget, **kw: self.show_mirror_push_review(), style=Pack(height=44)))
        box.add(toga.Button('Cancel transfer', on_press=self.cancel_mirror_transfer, enabled=getattr(self, 'transfer_busy', False), style=Pack(height=44)))
        for job in list(store.jobs.values()):
            key = job['id']
            title = ('LocalCrypt · ' if job['crypt'] else 'Local · ') + job['remote']
            box.add(toga.Label(title, style=Pack(font_size=18, margin_top=12)))
            def open_copy(widget=None, selected=key, **kw):
                self.loop.create_task(self.open_mirror_copy(selected))
            def pull(widget=None, selected=key, **kw):
                self.start_mirror_pull(selected)
            def review(widget=None, selected=key, **kw):
                self.start_mirror_review(selected)
            box.add(toga.Box(children=[toga.Button('Open', on_press=open_copy, style=Pack(height=44, flex=1)),
                toga.Button('Pull', on_press=pull, style=Pack(height=44, flex=1)),
                toga.Button('Push…', on_press=review, style=Pack(height=44, flex=1))], style=Pack(direction=ROW)))
            for index, snapshot in enumerate(job['snapshots'][:3]):
                async def open_snapshot(widget=None, selected=key, source=snapshot, **kw):
                    await self.open_mirror_copy(selected, snapshot=source)
                box.add(toga.Button('Open retained snapshot ' + str(index + 1), on_press=open_snapshot, style=Pack(height=44)))
            def remove(widget=None, selected=key, **kw):
                if getattr(self, 'transfer_busy', False):
                    return
                try:
                    store.remove(selected)
                    if getattr(self, 'mirror_push_plan', None) is not None and self.mirror_push_plan['job'] == selected:
                        self.mirror_push_plan = None
                    self.show_transfers()
                except (OSError, ValueError) as error:
                    self.transfer_notice.text = str(error)
            box.add(toga.Button('Remove mapping (keep files)', on_press=remove, style=Pack(height=44)))
        box.add(toga.Button('Choose a remote to pull', on_press=self.show_cloud, style=Pack(height=44, margin_top=12)))
        self.show_view(toga.ScrollContainer(content=box, style=Pack(flex=1)), destination='files', route='transfers', title='Local copies & transfers')
        if getattr(self, 'transfer_busy', False):
            self.transfer_progress.max = None
            self.transfer_progress.start()

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
        if not getattr(self, 'transfer_busy', False):
            self.transfer_task = self.loop.create_task(self.run_mirror_work(
                lambda client, cancel, progress: self.mirror_store().pull(key, client, cancelled=cancel, progress=progress), 'pull'))

    def start_mirror_review(self, key):
        if not getattr(self, 'transfer_busy', False):
            self.transfer_task = self.loop.create_task(self.run_mirror_work(
                lambda client, cancel, progress: self.mirror_store().push_plan(key, client, cancelled=cancel, progress=progress), 'review'))

    def pull_remote_copy(self, widget=None, **kwargs):
        if getattr(self, 'cloud_busy', False) or getattr(self, 'transfer_busy', False):
            return
        remote = self.selected_cloud_remote()
        if not remote or remote != self.cloud_open_remote:
            self.cloud_status.value = 'Open a remote before pulling its folder.'
            return
        selected = self.cloud_rows.get(self.cloud_entries.value)
        folder = selected['path'] if selected and selected['directory'] else self.cloud_path
        self.transfer_task = self.loop.create_task(self.run_mirror_work(
            lambda client, cancel, progress: self.mirror_store().create(client, remote, folder, cancelled=cancel, progress=progress), 'create'))

    async def run_mirror_work(self, work, operation):
        if getattr(self, 'transfer_busy', False):
            return False
        if not await self.mirror_connection_ready():
            self.show_transfers()
            return False
        client, generation = self.cloud_client, self.cloud_client.generation
        self.transfer_busy = True
        self.transfer_complete = False
        self.set_cloud_busy(True)
        self._crypt_cancel = Event()
        cancel = self._crypt_cancel
        self.transfer_message = 'Preparing transfer…'
        self.show_transfers()
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
                self.transfer_message = f'Push verified: {result} file(s). Remote-only files were kept.'
                self.mirror_push_plan = None
            else:
                status, snapshot = result[1] if operation == 'create' else result
                self.transfer_message = ('Local changes were kept. The remote version is available as a retained snapshot.'
                                         if status == 'conflict' else 'Pull complete. Local copies are ready; previous files were retained.')
            return True
        except Exception as error:
            self.transfer_message = 'Transfer stopped: ' + str(error)[:350]
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
        phase, files = values['phase'], values['files']
        done, total = values['done'], values['total']
        self.transfer_message = f'{phase} · {files} file(s)' + (f' · {done:,} / {total:,}' if total > 0 else '')
        self.transfer_notice.text = self.transfer_message
        self.cloud_status.value = self.transfer_message
        origin = getattr(self, 'cloud_transfer_progress', None)
        if total > 0:
            self.transfer_progress.stop()
            self.transfer_progress.max = 100
            self.transfer_progress.value = min(99, 100 * done / total)
            if origin is not None:
                origin.stop()
                origin.max = 100
                origin.value = self.transfer_progress.value
        else:
            self.transfer_progress.max = None
            self.transfer_progress.start()
            if origin is not None:
                origin.max = None
                origin.start()

    def cancel_mirror_transfer(self, widget=None, **kwargs):
        if getattr(self, 'transfer_busy', False):
            self.cancel_cloud()
            self.transfer_message = 'Cancelling transfer; verified completed files and backups are retained.'
            self.transfer_notice.text = self.transfer_message

    def show_mirror_push_review(self):
        plan = self.mirror_push_plan
        job = self.mirror_store().jobs[plan['job']]
        replaced = sum(bool(item['expected']) for item in plan['writes'])
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Review push to ' + job['remote'], style=Pack(font_size=22)))
        box.add(toga.Label(f'{len(plan["writes"])} file(s) to send, including {replaced} replacement(s).\n'
                          f'{plan["unchanged"]} file(s) already match.\nRemote-only files are kept.\n'
                          'Replaced remote files get verified backups.\nCancelled pushes can leave completed files on the remote.'))
        def confirm(widget=None, **kw):
            if not getattr(self, 'transfer_busy', False):
                self.mirror_push_plan = None
                self.transfer_task = self.loop.create_task(self.run_mirror_work(
                    lambda client, cancel, progress: self.mirror_store().push(plan, client, cancelled=cancel, progress=progress), 'push'))
        def cancel(widget=None, **kw):
            self.mirror_push_plan = None
            self.show_transfers()
        box.add(toga.Button('Push these files', on_press=confirm, enabled=bool(plan['writes']), style=Pack(height=48)))
        box.add(toga.Button('Cancel', on_press=cancel, style=Pack(height=44)))
        self.show_view(box, destination='files', route='push-review', title='Review push')

    async def open_mirror_copy(self, key, *, snapshot=None):
        if getattr(self, 'cloud_busy', False):
            return False
        store = self.mirror_store()
        job = store.jobs[key]
        if snapshot is not None and snapshot not in job['snapshots']:
            raise ValueError('This snapshot is no longer recorded for that local copy.')
        await self.show_local_location()
        if job['crypt']:
            try:
                matched = self.cloud_client is not None and self.cloud_client.connection_identity(job['remote']) == job['identity']
            except (OSError, ValueError):
                matched = False
            if not matched:
                self.file_status.value = 'Unlock the matching connection before opening this LocalCrypt copy.'
                return False
            label = 'LocalCrypt: ' + job['remote']
            if snapshot is None:
                folder = self.cloud_client.request('crypt_path', remote=job['remote'], identity=job['cipher_identity'],
                                                 path=job['prefix'], directory=True, decode=True)['path']
                return await self.browser_file_location((label, folder))
            from .file_resources import CryptFiles
            root = self.private_root / 'TransferSnapshots' / snapshot
            provider = CryptFiles(root, self.cloud_client, job['remote'])
            folder = provider.mapping(job['prefix'], directory=True, decode=True)
        else:
            if snapshot is None:
                return await self.browser_file_location(('Local files', job['target']))
            from commonUtils.runtime.local_files import LocalFiles
            provider = LocalFiles(store.snapshot(job, snapshot))
            folder = ''
        label = 'Retained snapshot ' + snapshot[:8]
        self.file_roots[label] = provider
        self.file_storage.items = list(self.file_roots)
        return await self.browser_file_location((label, folder))
