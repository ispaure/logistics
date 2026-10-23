"""Existing encrypted-copy catalog and reading controls for the mobile rclone feature."""
from commonUtils.ui.native.password_input import PasswordInput
import asyncio
import toga
from toga.style import Pack
from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
from features.rclone.localcrypt.mobile.locations import OfflineCryptLocation
from features.rclone.mobile.service import native_service


class LocalCryptUI:
    def build_localcrypt(self):
        self.crypt_copies = LocalCryptCopies(self.private_root / 'LocalCrypt', self.cloud_client)
        self._crypt_cancel = None
        self.crypt_labels = {}
        self.crypt_selector = toga.Selection(style=Pack(height=44))
        self.crypt_refresh = toga.Button('Refresh encrypted copies', on_press=self.refresh_crypt, style=Pack(height=44))
        self.crypt_open = toga.Button('Read encrypted copy', on_press=self.open_crypt, style=Pack(height=44))
        self.crypt_password = PasswordInput(placeholder='Inner ZIP password (if needed)', style=Pack(height=44))
        self.crypt_resume = toga.Button('Return to private reader/editor', on_press=self.resume_crypt, style=Pack(height=44))
        return [toga.Label('LocalCrypt · encrypted offline copies'),
                self.crypt_selector, self.crypt_refresh, self.crypt_password, self.crypt_open, self.crypt_resume, self.build_file_manager()]

    async def refresh_crypt(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None:
            return
        self.set_cloud_busy(True)
        try:
            rows = await asyncio.to_thread(self.crypt_copies.items)
            self.crypt_labels = {f'{i + 1}. {name}': key for i, (key, name) in enumerate(rows)}
            self.crypt_selector.items = list(self.crypt_labels)
        except Exception:
            self.cloud_status.value = 'Encrypted copies could not be listed.'
        finally:
            self.set_cloud_busy(False)

    async def use_downloaded_file(self, widget=None, **kwargs):
        key = self.crypt_labels.get(self.crypt_selector.value)
        result = []
        def work(cancelled):
            if not key:
                raise ValueError('Select an offline encrypted copy on the remote-files screen first.')
            provider = native_service(self.cloud_client).localcrypt.open(OfflineCryptLocation(self.crypt_copies, key))
            result.extend((provider, provider.entry(provider.name)))
        if await self.file_work(work):
            self.file_provider, row = result
            self.file_path = ''
            self.file_rows = {row['name']: row}
            self.set_file_items(list(self.file_rows))
            self.populate_file_browser([row])
            self.file_status.value = 'Choose a destination and move this existing offline copy into your folders.'

