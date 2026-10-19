"""Android collection drive selection; file-manager permission is user controlled."""
import asyncio
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from features.rclone.mobile.storage_location import collection_base, selection, switch_location, recover_location, wipe_destination, start_empty_location, describe_location


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
        from .settings_ui import SettingsLabel, fit_section
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        self.collection_storage_page = box
        box.add(SettingsLabel('Collection storage', style=Pack(font_size=22)))
        try:
            base = collection_base(self.private_root)
            current = str(base) if selection(self.private_root) else 'App internal storage'
        except (OSError, ValueError) as error:
            current = 'Unavailable: ' + str(error)
        box.add(SettingsLabel('Currently used for Local and LocalCrypt:\n' + current))
        box.add(SettingsLabel('Choose a location to inspect. Choosing it here does not change where files are stored.'))
        self.collection_drives = android_drives(self)
        try:
            chosen = selection(self.private_root)
        except (OSError, ValueError):
            chosen = None
        label = next((label for label, path in self.collection_drives.items()
                      if str(path) == (chosen['volume'] if chosen else 'None')), next(iter(self.collection_drives)))
        self.collection_drive = toga.Selection(items=list(self.collection_drives), value=label, style=Pack(height=48))
        self.collection_drive.on_change = self.collection_target_changed
        box.add(self.collection_drive)
        self.collection_target_status = SettingsLabel('')
        box.add(self.collection_target_status)
        box.add(toga.Button('Allow SD card / shared storage access…', on_press=self.allow_collection_storage, style=Pack(height=48)))
        box.add(SettingsLabel('Android requires All files access. Local files are readable by other apps with storage access. LocalCrypt stays encrypted.'))
        self.collection_copy = toga.Button('Copy current files here, then use them…', on_press=self.change_collection_storage, style=Pack(height=48))
        self.collection_existing = toga.Button('Use existing files here — no copy…', on_press=self.recover_collection_storage, style=Pack(height=48))
        self.collection_empty = toga.Button('Start empty here — keep old files…', on_press=self.start_empty_collection, style=Pack(height=48))
        self.collection_erase = toga.Button('Erase collection files at this location…', on_press=self.wipe_collection_storage, style=Pack(height=48))
        for button, explanation in (
            (self.collection_copy, 'Copies and verifies Local + LocalCrypt. Keeps the original files. Stops if the destination has different files; no merge or overwrite.'),
            (self.collection_existing, 'Switches to files already at the selected location. Copies nothing. Current files stay where they are. These files may be an older backup; LocalCrypt needs its original credentials.'),
            (self.collection_empty, 'Selects empty Local + LocalCrypt folders without copying anything. Current files stay where they are. Refuses a destination that already contains files.'),
            (self.collection_erase, 'Permanently deletes only the two collection folders shown above and interrupted copy folders at that location. Does not switch location. Disabled for the collection currently in use.')):
            box.add(button, SettingsLabel(explanation))
        box.add(SettingsLabel('All four actions keep private app documents, credentials, settings and metadata. For a full app reset, use Settings → Reset.'))
        box.add(toga.Button('Refresh drives / permission', on_press=self.show_collection_storage, style=Pack(height=48)))
        self.collection_storage_status = SettingsLabel('After switching, Logistics closes. Reopen it to use the selected location.')
        box.add(self.collection_storage_status)
        for child in box.children:
            if isinstance(child, toga.Label):
                child.style.margin_bottom = 12
        self.collection_target_changed()
        fit_section(box, max(280, self.app.adaptive.content_width('settings')))
        self.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)),
                       destination='settings', route='collection-storage', title='Collection storage')

    def collection_target_changed(self, widget=None, **kwargs):
        if not hasattr(self, 'collection_target_status'):
            return
        try:
            state = describe_location(self.private_root, self.collection_drives[self.collection_drive.value])
            self.collection_target_status.text = ('Selected location: CURRENTLY IN USE' if state['active']
                else 'Selected location: NOT CURRENTLY IN USE') + '\n' + '\n'.join(
                    path + ' · ' + status for path, status in state['folders'])
            for name in ('collection_copy', 'collection_existing', 'collection_empty', 'collection_erase'):
                getattr(self, name).enabled = not state['active'] and not getattr(self, '_storage_changing', False)
        except (OSError, ValueError) as error:
            self.collection_target_status.text = 'Cannot inspect this location: ' + str(error)
            for name in ('collection_copy', 'collection_existing', 'collection_empty'):
                getattr(self, name).enabled = not getattr(self, '_storage_changing', False)
            self.collection_erase.enabled = False
            # Recovery can repair a damaged private selection. Erase still
            # refuses an unreadable active selection in the storage service.
        from .settings_ui import fit_text
        fit_text(self.collection_target_status, max(248, self.app.adaptive.content_width('settings') - 32))

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

    async def start_empty_collection(self, widget=None, **kwargs):
        await self._collection_operation('empty', widget)

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
            self.collection_storage_status.text = 'Use existing files here to repair storage settings: ' + str(error)
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
            'empty': ('Start empty at this location?', 'Create and use empty Local and LocalCrypt folders in ' + destination + '? No files are copied or erased. Current files stay at their old location. The destination must be empty.'),
            'recover': ('Use existing files here without copying?', 'Use the existing Local and LocalCrypt collections in ' + destination +
                        '? This does not copy or merge your current collection. A retained backup may be older and omit recent changes. LocalCrypt still needs its original credentials.'),
            'wipe': ('Permanently erase these collection folders?', 'Delete ' + str(volume / 'Logistics/Local' if volume else self.private_root / 'LocalFiles') + ' and ' + str(volume / 'Logistics/LocalCrypt' if volume else self.private_root / 'LocalCryptFolders') + ', plus interrupted .storage-copy-* folders at ' + destination + '? The files cannot be recovered by Logistics. Other folders, private credentials, settings and metadata are kept. The location currently in use cannot be erased.'),
        }
        title, message = prompts[action]
        if action != 'wipe':
            message += ' The app will close when finished; reopen it to use this location.'
        self._storage_changing = True
        self.collection_drive.enabled = False
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
                'empty': 'Preparing empty collection folders…',
                'wipe': 'Deleting inactive collection data… Keep Logistics open.',
            }[action]
            operation = {'copy': switch_location, 'recover': recover_location, 'wipe': wipe_destination, 'empty': start_empty_location}[action]
            changed = await asyncio.to_thread(operation, self.private_root, volume)
            self.collection_storage_status.text = ('Collection folders erased. You can copy files here or start empty here now.' if action == 'wipe'
                else 'Storage location saved. Reopen Logistics.' if changed else 'Already using this location.')
        except (OSError, ValueError) as error:
            self.collection_storage_status.text = 'Location unchanged: ' + str(error)
        finally:
            self._storage_changing = False
            self.collection_drive.enabled = True
            if busy:
                self.set_cloud_busy(False)
            if widget is not None:
                widget.enabled = True
        self.collection_target_changed()
        if changed:
            await self.main_window.dialog(toga.InfoDialog('Collection location saved', 'Reopen Logistics to use the new drive. The app will close now.'))
            self.exit()
