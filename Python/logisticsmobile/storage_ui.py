"""Android collection drive selection; file-manager permission is user controlled."""
import asyncio
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from features.rclone.mobile.storage_location import collection_base, selection, switch_location, recover_location, wipe_destination


def android_drives(app):
    from java import jclass
    Context = jclass('android.content.Context')
    manager = app._impl.native.getSystemService(Context.STORAGE_SERVICE)
    drives = {'App internal storage': None}
    volumes = manager.getStorageVolumes()
    for index in range(volumes.size()):
        volume = volumes.get(index)
        directory = volume.getDirectory()
        if str(volume.getState()) == 'mounted' and directory is not None:
            path = Path(str(directory.getAbsolutePath()))
            label = str(volume.getDescription(app._impl.native))
            drives[f'{label} · {path}'] = path
    return drives


def all_files_allowed():
    from java import jclass
    return bool(jclass('android.os.Environment').isExternalStorageManager())


class StorageUI:
    async def open_android_developer_settings(self, widget=None, **kwargs):
        from java import jclass
        try:
            Intent = jclass('android.content.Intent')
            self._impl.native.startActivity(Intent('android.settings.APPLICATION_DEVELOPMENT_SETTINGS'))
        except Exception:
            await self.main_window.dialog(toga.InfoDialog('Developer settings unavailable',
                'Android could not open developer settings. Developer mode must be enabled first.'))

    def show_collection_storage(self, widget=None, **kwargs):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Local / LocalCrypt location', style=Pack(font_size=22)))
        try:
            base = collection_base(self.private_root)
            current = str(base) if selection(self.private_root) else 'App internal storage'
        except (OSError, ValueError) as error:
            current = str(error)
        box.add(toga.Label('Current: ' + current))
        box.add(toga.Label('On a selected drive, both collections use:\nLogistics/Local\nLogistics/LocalCrypt'))
        self.collection_drives = android_drives(self)
        try:
            chosen = selection(self.private_root)
        except (OSError, ValueError):
            chosen = None
        label = next((label for label, path in self.collection_drives.items()
                      if str(path) == (chosen['volume'] if chosen else 'None')), next(iter(self.collection_drives)))
        self.collection_drive = toga.Selection(items=list(self.collection_drives), value=label, style=Pack(height=48))
        box.add(self.collection_drive)
        box.add(toga.Button('Allow SD card / shared storage access…', on_press=self.allow_collection_storage, style=Pack(height=48)))
        box.add(toga.Label('Android requires All files access for these folders.\nCredentials and settings stay internal.\nLocal files are readable by other apps with storage access.\nLocalCrypt files remain encrypted.'))
        box.add(toga.Button('Copy collections and use this drive…', on_press=self.change_collection_storage, style=Pack(height=48)))
        box.add(toga.Button('Recover existing collections on this drive…', on_press=self.recover_collection_storage, style=Pack(height=48)))
        box.add(toga.Button('Wipe inactive collections on this drive…', on_press=self.wipe_collection_storage, style=Pack(height=48)))
        box.add(toga.Button('Refresh drives / permission', on_press=self.show_collection_storage, style=Pack(height=48)))
        self.collection_storage_status = toga.Label('Existing downloads are copied and verified.\nOriginal copies stay as a recovery backup.\nRestart Logistics after changing location.')
        box.add(self.collection_storage_status)
        self.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)),
                       destination='settings', route='collection-storage', title='Collection location')

    def allow_collection_storage(self, widget=None, **kwargs):
        from java import jclass
        Intent, Uri = jclass('android.content.Intent'), jclass('android.net.Uri')
        intent = Intent('android.settings.MANAGE_APP_ALL_FILES_ACCESS_PERMISSION')
        intent.setData(Uri.parse('package:' + str(self._impl.native.getPackageName())))
        self._impl.native.startActivity(intent)

    async def change_collection_storage(self, widget=None, **kwargs):
        await self._collection_operation('copy', widget)

    async def recover_collection_storage(self, widget=None, **kwargs):
        await self._collection_operation('recover', widget)

    async def wipe_collection_storage(self, widget=None, **kwargs):
        await self._collection_operation('wipe', widget)

    async def _collection_operation(self, action, widget):
        if getattr(self, 'cloud_busy', False) or getattr(self, 'transfer_busy', False) or getattr(self, '_storage_changing', False):
            self.collection_storage_status.text = 'Wait for the current operation to finish.'
            return
        volume = self.collection_drives[self.collection_drive.value]
        try:
            external_source = action == 'copy' and selection(self.private_root) is not None
        except (OSError, ValueError) as error:
            self.collection_storage_status.text = 'Use Recover existing collections to repair storage settings: ' + str(error)
            return
        if (volume is not None or external_source) and not all_files_allowed():
            self.collection_storage_status.text = 'Tap Allow SD card / shared storage access, enable permission, then return here.'
            return
        if any(session.provider != 'managed-text' for session in self.workspace.sessions.values()):
            self.collection_storage_status.text = 'Close open readers and local/remote documents in Open documents, then retry.'
            return
        if not self.checkpoint():
            self.collection_storage_status.text = 'Save your current document before changing storage.'
            return
        destination = str(volume / 'Logistics') if volume else 'app internal storage'
        prompts = {
            'copy': ('Change collection drive?', 'Copy Local and LocalCrypt to ' + destination +
                     '? Different destination files stop the copy. Original copies remain as a backup.'),
            'recover': ('Recover existing collections?', 'Use the existing Local and LocalCrypt collections in ' + destination +
                        '? This does not copy or merge your current collection. A retained backup may be older and omit recent changes. LocalCrypt still needs its original credentials.'),
            'wipe': ('Permanently wipe inactive collections?', 'Delete Local, LocalCrypt, and interrupted collection copies in ' + destination +
                     '? These files cannot be recovered by Logistics. Other folders and private credentials are kept. The active collection cannot be wiped.'),
        }
        title, message = prompts[action]
        if action != 'wipe':
            message += ' The app will close when finished; reopen it to use this location.'
        self._storage_changing = True
        if widget is not None:
            widget.enabled = False
        changed = False
        busy = False
        try:
            if not await self.main_window.dialog(toga.ConfirmDialog(title, message)):
                return
            if getattr(self, 'cloud_busy', False) or getattr(self, 'transfer_busy', False):
                self.collection_storage_status.text = 'Wait for the current operation to finish.'
                return
            if any(session.provider != 'managed-text' for session in self.workspace.sessions.values()) or not self.checkpoint():
                self.collection_storage_status.text = 'Save and close open readers and local/remote documents, then retry.'
                return
            self.set_cloud_busy(True)
            busy = True
            self.collection_storage_status.text = {
                'copy': 'Copying and verifying collections… Keep Logistics open.',
                'recover': 'Checking existing collections… Keep Logistics open.',
                'wipe': 'Deleting inactive collection data… Keep Logistics open.',
            }[action]
            operation = {'copy': switch_location, 'recover': recover_location, 'wipe': wipe_destination}[action]
            changed = await asyncio.to_thread(operation, self.private_root, volume)
            self.collection_storage_status.text = ('Inactive collections wiped. You can copy collections to this drive now.' if action == 'wipe'
                else 'Storage location saved. Reopen Logistics.' if changed else 'Already using this location.')
        except (OSError, ValueError) as error:
            self.collection_storage_status.text = 'Location unchanged: ' + str(error)
        finally:
            self._storage_changing = False
            if busy:
                self.set_cloud_busy(False)
            if widget is not None:
                widget.enabled = True
        if changed:
            await self.main_window.dialog(toga.InfoDialog('Collection location saved', 'Reopen Logistics to use the new drive. The app will close now.'))
            self.exit()
