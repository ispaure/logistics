"""Explicit repeatable remote-to-local pulls; no remote writeback."""
import asyncio
from threading import Event
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .pull_jobs import PullJobs
from .cloud_ui import import_hint


class PullJobsUI:
    def pull_jobs_store(self):
        if not hasattr(self, 'pull_jobs'):
            self.pull_jobs = PullJobs(self.private_root)
        return self.pull_jobs

    def show_pull_jobs(self, widget=None, **kwargs):
        store = self.pull_jobs_store()
        box = self.pull_job_box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Folder pulls', style=Pack(font_size=22)))
        box.add(toga.Label('Refresh a local folder from its remote.\nLocal edits produce a separate snapshot.\nRemote files are never changed.'))
        for job in list(store.jobs.values()):
            key = job['id']
            box.add(toga.Label(import_hint(job['remote'] + ':/' + job['folder'] + (' · session only' if job['transient'] else ''))))
            async def refresh(widget=None, selected=key, **kw):
                await self.run_pull_job(selected)
            async def open_folder(widget=None, selected=key, **kw):
                await self.open_pull_folder(store.jobs[selected]['target'])
            def remove(widget=None, selected=key, **kw):
                try:
                    store.remove(selected)
                    self.show_pull_jobs()
                except (OSError, ValueError) as error:
                    self.pull_status.text = import_hint(str(error))
            box.add(toga.Box(children=[toga.Button('Refresh', on_press=refresh, style=Pack(height=44, flex=1)),
                toga.Button('Open local', on_press=open_folder, style=Pack(height=44, flex=1)),
                toga.Button('Remove job', on_press=remove, style=Pack(height=44))], style=Pack(direction=ROW)))
        self.pull_status = toga.Label(import_hint(store.error or getattr(self, 'pull_message', 'Remove job keeps all local folders.')))
        box.add(self.pull_status)
        box.add(toga.Button('Cancel running pull', on_press=self.cancel_cloud, style=Pack(height=44)))
        box.add(toga.Button('Browse remote folders', on_press=self.show_cloud, style=Pack(height=44)))
        self.show_view(toga.ScrollContainer(content=box, style=Pack(flex=1)), destination='files', route='pull-jobs', title='Folder pulls')

    async def create_pull_job(self, widget=None, **kwargs):
        row = self.cloud_rows.get(self.cloud_entries.value)
        if self.cloud_busy:
            return False
        if not row or not row['directory'] or self.selected_cloud_remote() != self.cloud_open_remote:
            self.cloud_status.value = 'Select a remote folder before saving a repeatable pull.'
            return False
        remote, folder = self.cloud_open_remote, row['path']
        return await self.perform_pull(lambda client, cancelled, progress: self.pull_jobs_store().create(
            client, remote, folder, decrypted=remote in self.cloud_crypt_remotes,
            cancelled=cancelled, progress=progress), create=True)

    async def run_pull_job(self, key):
        self.show_cloud(present=False)
        restore = getattr(self, 'cloud_restore_task', None)
        if restore is not None and not restore.done():
            await restore
        if self.cloud_busy:
            return False
        if not self.clear_private_reader():
            self.pull_message = 'Save or discard provider edits before refreshing their local files.'
            return False
        return await self.perform_pull(lambda client, cancelled, progress: self.pull_jobs_store().run(
            key, client, cancelled=cancelled, progress=progress), create=False)

    async def perform_pull(self, work, *, create):
        if self.cloud_client is None:
            self.pull_message = 'Load the matching connection in Settings first.'
            return False
        store = self.pull_jobs_store()
        client, generation = self.cloud_client, self.cloud_client.generation
        self.set_cloud_busy(True)
        cancel = self._crypt_cancel = Event()
        self.pull_message = 'Downloading a complete remote snapshot…'
        def progress(count, path):
            def publish():
                if self.active_host and client.generation == generation:
                    self.cloud_status.value = f'Pulling folder: {count} files\n{path}'
                    if hasattr(self, 'pull_status'):
                        self.pull_status.text = import_hint(f'Pulling folder: {count} files\n{path}')
            self.loop.call_soon_threadsafe(publish)
        try:
            result = await asyncio.to_thread(work, client, cancel.is_set, progress)
            if not self.active_host or client.generation != generation:
                return False
            if create:
                self.cloud_downloaded_folder = result['target']
                self.pull_message = 'Pull job saved. Refresh it from Files → Folder pulls.'
            else:
                status, target = result
                self.cloud_downloaded_folder = target.name
                self.pull_message = ('Local edits preserved. The remote version was saved in a separate folder: '
                                     if status == 'conflict' else 'Local folder refreshed. Its previous version was preserved beside it: ') + target.name
            self.cloud_status.value = self.pull_message
            return True
        except Exception as error:
            self.pull_message = 'Pull failed; surviving local copies were preserved. ' + str(error)[:300]
            self.cloud_status.value = self.pull_message
            return False
        finally:
            self._crypt_cancel = None
            self.set_cloud_busy(False)
            if hasattr(self, 'pull_status'):
                self.pull_status.text = import_hint(self.pull_message)
            if store.pending is not None:
                self.pull_message += ' An interrupted publication will be reconciled before retry.'

    async def open_pull_folder(self, folder):
        await self.show_local_location()
        await self.browser_file_location(('Local files', folder))
