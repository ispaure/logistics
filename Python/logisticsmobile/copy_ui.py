"""Guided remote-to-device copies with a browsable local destination."""
import asyncio
import threading
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.runtime.local_files import LocalFiles
from commonUtils.ui.native_browser import NativeBrowser
from .folder_download import pull_item


class CopyUI:
    async def choose_cloud_copy(self, widget=None, *, current_folder=False, **kwargs):
        if self.cloud_busy:
            return False
        row = (dict(path=self.cloud_path, directory=True) if current_folder and self.cloud_path
               else self.cloud_rows.get(self.cloud_entries.value))
        if not row or self.selected_cloud_remote() != self.cloud_open_remote:
            self.cloud_status.value = 'Select a file, or open a folder and tap Copy this folder.'
            return False
        if hasattr(self, 'copy_browser'):
            await self.copy_browser.close()
        self.copy_source = (self.cloud_client, getattr(self.cloud_client, 'generation', None),
                            self.cloud_open_remote, dict(row))
        root = self.private_root / 'LocalFiles'
        root.mkdir(exist_ok=True)
        self.copy_provider = LocalFiles(root)
        self.copy_folder = ''
        self.copy_result = None
        self.copy_destination = toga.Label('To: On this device', style=Pack(font_size=16))
        self.copy_progress = toga.ProgressBar(max=100, value=0, style=Pack(height=12))
        self.copy_status = toga.MultilineTextInput(readonly=True, style=Pack(height=64))
        self.copy_browser = NativeBrowser(open_folder=self.copy_enter_folder,
                                         navigate=self.copy_visit_folder, preview=False)
        self.copy_confirm = toga.Button('Copy here', on_press=self.confirm_cloud_copy, style=Pack(height=48))
        self.copy_cancel = toga.Button('Cancel', on_press=self.cancel_cloud_copy, style=Pack(height=48))
        self.copy_open = toga.Button('Open copied location', on_press=self.open_cloud_copy, style=Pack(height=48), enabled=False)
        source = f'From: {self.cloud_open_remote}:/{row["path"]}'
        from .cloud_ui import import_hint
        note = ('This saves an unencrypted copy.' if self.cloud_open_remote in self.cloud_crypt_remotes
                else 'The remote original stays in place.')
        self.copy_view = toga.Box(children=[
            toga.Label('Copy to device', style=Pack(font_size=22)),
            toga.Label(import_hint(source), style=Pack(font_size=14)),
            toga.Label(note, style=Pack(font_size=14)), self.copy_destination,
            toga.ScrollContainer(content=self.copy_browser.widget, style=Pack(flex=1)),
            self.copy_progress, self.copy_status, self.copy_confirm, self.copy_cancel],
            style=Pack(direction=COLUMN, margin=12, flex=1))
        await self.copy_visit_folder(('Local files', ''))
        return self.show_view(self.copy_view, destination='files', route='copy-to-device', title='Copy to device')

    async def copy_current_folder(self, widget=None, **kwargs):
        return await self.choose_cloud_copy(current_folder=True)

    async def copy_enter_folder(self, row):
        return await self.copy_visit_folder(('Local files', row['path']))

    async def copy_visit_folder(self, location):
        if self.cloud_busy or self.copy_result is not None:
            return False
        folder = location[1]
        try:
            rows = await asyncio.to_thread(self.copy_provider.list, folder)
            self.copy_folder = folder
            self.copy_browser.set_entries(self.copy_provider, folder,
                [row for row in rows if row['directory']], location=('Local files', folder))
            from .cloud_ui import import_hint
            self.copy_destination.text = import_hint('To: On this device/' + folder)
            self.copy_status.value = 'Open a folder, then tap Copy here. Existing files are kept.'
            return True
        except (OSError, ValueError) as error:
            self.copy_status.value = 'Could not open destination: ' + str(error)[:200]
            return False

    async def confirm_cloud_copy(self, widget=None, **kwargs):
        if self.cloud_busy or self.copy_result is not None:
            return False
        client, generation, remote, row = self.copy_source
        if client is not self.cloud_client or getattr(client, 'generation', None) != generation:
            self.copy_status.value = 'Connections changed. Return to remote files and select the source again.'
            return False
        self.set_cloud_busy(True)
        self.copy_confirm.enabled = False
        self._crypt_cancel = threading.Event()
        self.copy_status.value = 'Copying…'
        self.copy_progress.max = None
        self.copy_progress.start()
        self.copy_files_done = 0
        try:
            root = self.copy_provider._locate(self.copy_folder)
            def progress(count, path):
                self.loop.call_soon_threadsafe(setattr, self, 'copy_files_done', count)
            def bytes_progress(done, total, path):
                self.loop.call_soon_threadsafe(self.update_copy_progress, done, total, path)
            target = await asyncio.to_thread(pull_item, client, remote, row, root,
                decrypted=remote in self.cloud_crypt_remotes,
                cancelled=self._crypt_cancel.is_set, progress=progress, transfer_progress=bytes_progress)
            self.copy_result = (str(target.relative_to(self.copy_provider.root)), row['directory'])
            self.copy_progress.stop()
            self.copy_progress.max = 100
            self.copy_progress.value = 100
            self.copy_status.value = 'Copied to On this device/' + self.copy_result[0]
            await self.copy_browser.close()
            self.copy_open.enabled = True
            self.copy_view.remove(self.copy_confirm)
            self.copy_view.insert(len(self.copy_view.children) - 1, self.copy_open)
            self.copy_cancel.text = 'Back to remote files'
            return True
        except Exception as error:
            self.copy_status.value = 'Copy failed: ' + str(error)[:250] + '\nChoose Copy here to retry.'
            self.copy_confirm.enabled = True
            return False
        finally:
            self.copy_progress.stop()
            self._crypt_cancel = None
            self.set_cloud_busy(False)

    def update_copy_progress(self, done, total, path):
        if (not self.cloud_busy or self.copy_result is not None
                or (self._crypt_cancel is not None and self._crypt_cancel.is_set())):
            return
        if total > 0:
            self.copy_progress.stop()
            self.copy_progress.max = 100
            self.copy_progress.value = min(99, done * 100 / total)
            amount = f'{done:,} / {total:,} bytes'
        else:
            self.copy_progress.max = None
            self.copy_progress.start()
            amount = f'{done:,} bytes'
        self.copy_status.value = f'Copying {Path(path).name}\n{amount} · {self.copy_files_done} files saved'

    def cancel_cloud_copy(self, widget=None, **kwargs):
        if self.cloud_busy:
            self.cancel_cloud()
            self.copy_status.value = 'Cancelling copy…'
        else:
            self.show_cloud()

    async def open_cloud_copy(self, widget=None, **kwargs):
        if self.cloud_busy or self.copy_result is None:
            return
        path, directory = self.copy_result
        await self.show_local_location()
        await self.browser_file_location(('Local files', path if directory else path.rpartition('/')[0]))
        if not directory:
            row = next((row for row in self.file_rows.values() if row['path'] == path), None)
            if row is not None:
                self.browser_file_selected(row)
