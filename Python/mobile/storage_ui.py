"""Android collection drive selection; file-manager permission is user controlled."""
import asyncio
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from features.rclone.mobile.storage_location import collection_base, selection, switch_location, recover_location, wipe_destination, start_empty_location, describe_location


def android_sdk():
    from java import jclass
    return int(jclass('android.os.Build$VERSION').SDK_INT)


def android_drives(app):
    from java import jclass
    Context = jclass('android.content.Context')
    manager = app._impl.native.getSystemService(Context.STORAGE_SERVICE)
    drives = {'App internal storage': None}
    if android_sdk() < 30:
        # Pre-Android 11 has no all-files grant. WRITE_EXTERNAL_STORAGE also
        # cannot grant arbitrary writes to a removable card. Use the public,
        # permission-free app directories rather than hidden volume APIs or
        # guessing /storage paths. Null entries represent unavailable volumes.
        Environment = jclass('android.os.Environment')
        for directory in app._impl.native.getExternalFilesDirs(None):
            if directory is None or str(Environment.getExternalStorageState(directory)) != 'mounted':
                continue
            volume = manager.getStorageVolume(directory)
            if volume is None:
                continue
            path = Path(str(directory.getAbsolutePath()))
            label = str(volume.getDescription(app._impl.native))
            drives[f'{label} · app storage · {path}'] = path
        return drives
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
    # Older Android drive choices are restricted to our app-owned directories;
    # these need no runtime storage permission, including on removable cards.
    if android_sdk() < 30:
        return True
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
        if getattr(self, '_storage_changing', False) and getattr(self, 'collection_storage_progress_view', None) is not None:
            self.show_view(self.collection_storage_progress_view, destination='settings',
                           route='collection-storage-progress', title='File storage progress')
            return
        from .settings.forms import SettingsLabel, fit_section
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        self.collection_storage_page = box
        box.add(SettingsLabel('Collection storage', style=Pack(font_size=22)))
        try:
            base = collection_base(self.private_root)
            current = str(base) if selection(self.private_root) else 'App internal storage'
        except (OSError, ValueError) as error:
            current = 'Unavailable: ' + str(error)
        box.add(SettingsLabel('Currently used for Local, LocalCrypt and Received Files:\n' + current))
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
        if android_sdk() < 30:
            box.add(SettingsLabel('SD card and device storage use Logistics’ app storage folders. No storage permission is needed. '
                'Android removes these folders if you uninstall Logistics or clear its app data. Keep a separate backup. '
                'LocalCrypt stays encrypted.'))
        else:
            box.add(toga.Button('Allow SD card / shared storage access…', on_press=self.allow_collection_storage, style=Pack(height=48)))
            box.add(SettingsLabel('Android requires All files access. Local files are readable by other apps with storage access. LocalCrypt stays encrypted.'))
        self.collection_copy = toga.Button('Copy current files here, then use them…', on_press=self.change_collection_storage, style=Pack(height=48))
        self.collection_existing = toga.Button('Use existing files here — no copy…', on_press=self.recover_collection_storage, style=Pack(height=48))
        self.collection_empty = toga.Button('Start empty here — keep old files…', on_press=self.start_empty_collection, style=Pack(height=48))
        self.collection_erase = toga.Button('Erase collection files at this location…', on_press=self.wipe_collection_storage, style=Pack(height=48))
        for button, explanation in (
            (self.collection_copy, 'Copies and verifies Local + LocalCrypt + Received Files. Keeps the original files. Stops if the destination has different files; no merge or overwrite.'),
            (self.collection_existing, 'Switches to files already at the selected location without scanning or copying their contents. Current files stay where they are. These files may be an older backup; LocalCrypt needs its original credentials.'),
            (self.collection_empty, 'Selects empty Local + LocalCrypt + Received Files folders without copying anything. Current files stay where they are. Refuses a destination that already contains files.'),
            (self.collection_erase, 'Permanently deletes only the three collection folders shown above and interrupted copy folders at that location. Does not switch location. Disabled for the collection currently in use.')):
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
        from .settings.forms import fit_text
        fit_text(self.collection_target_status, max(248, self.app.adaptive.content_width('settings') - 32))

    def allow_collection_storage(self, widget=None, **kwargs):
        if android_sdk() < 30:
            # The all-files settings action does not exist on these versions.
            self.show_collection_storage()
            return
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
        title, message, destination = self._collection_prompt(action, volume)
        self._storage_changing = True
        self.collection_drive.enabled = False
        if widget is not None:
            widget.enabled = False
        changed = False
        busy = False
        progress_bar = None
        done_button = None
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
            from .settings.forms import SettingsLabel, fit_section, fit_text
            width = max(280, self.app.adaptive.content_width('settings'))
            progress_box = toga.Box(style=Pack(direction=COLUMN, margin=16))
            heading = {'copy': 'Moving Local + LocalCrypt + Received Files', 'recover': 'Selecting existing collection',
                       'empty': 'Preparing empty folders', 'wipe': 'Erasing files at selected location'}[action]
            progress_box.add(SettingsLabel(heading, style=Pack(font_size=22, margin_bottom=16)))
            if action == 'copy':
                progress_box.add(SettingsLabel('From: ' + str(collection_base(self.private_root))))
            progress_box.add(SettingsLabel('To: ' + destination if action != 'wipe' else 'Location: ' + destination))
            progress_box.add(SettingsLabel('Keep Logistics open until this finishes. Original files stay in place when copying.'))
            self.collection_storage_status = SettingsLabel('Preparing…', style=Pack(margin_top=16))
            progress_bar = toga.ProgressBar(max=None, style=Pack(height=12, margin_top=12, margin_bottom=12))
            details = SettingsLabel('Finding files…')
            current_file = SettingsLabel('')
            done_button = toga.Button('Back to storage settings', enabled=False,
                                      on_press=self.show_collection_storage, style=Pack(height=48, margin_top=24))
            progress_box.add(self.collection_storage_status, progress_bar, details, current_file, done_button)
            self.collection_storage_page = progress_box
            fit_section(progress_box, width)
            self.collection_storage_progress_view = toga.ScrollContainer(horizontal=False, content=progress_box, style=Pack(flex=1))
            self.show_view(self.collection_storage_progress_view,
                           destination='settings', route='collection-storage-progress', title='File storage progress')
            progress_bar.start()
            loop = asyncio.get_running_loop()
            status_label = self.collection_storage_status

            render = self._collection_progress_renderer(status_label, progress_bar, details,
                                                        current_file, width, fit_text=fit_text)

            operation = {'copy': switch_location, 'recover': recover_location, 'wipe': wipe_destination, 'empty': start_empty_location}[action]
            def change_storage():
                from commonUtils.persistence.publication import mutation_lock
                from .incoming_files import inbox_path
                with mutation_lock:
                    if action == 'copy':
                        inbox_path(self.private_root)
                    return operation(self.private_root, volume,
                        progress=lambda event: loop.call_soon_threadsafe(render, event))
            changed = await asyncio.to_thread(change_storage)
            progress_bar.stop()
            progress_bar.max = 100
            progress_bar.value = 100
            details.text = ('Location saved. Existing file contents were not scanned.' if action == 'recover'
                            else 'Finished. All checks passed.')
            current_file.text = ''
            self.collection_storage_status.text = ('Collection folders erased. You can copy files here or start empty here now.' if action == 'wipe'
                else 'Storage location saved. Reopen Logistics.' if changed else 'Already using this location.')
        except (OSError, ValueError) as error:
            if progress_bar is not None:
                progress_bar.stop()
                progress_bar.max = 100
                progress_bar.value = 0
                details.text = 'Stopped before completion. Check the location and permission, then retry.'
            self.collection_storage_status.text = ('Erase incomplete; retry this location: ' if action == 'wipe' else 'Location unchanged: ') + str(error)
        finally:
            if done_button is not None:
                done_button.enabled = True
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

    def _collection_prompt(self, action, volume):
        destination = str(volume / 'Logistics') if volume else 'app internal storage'
        prompts = {
            'copy': ('Change collection drive?', 'Copy Local, LocalCrypt and Received Files to ' + destination +
                     '? Different destination files stop the copy. Original copies remain as a backup.'),
            'empty': ('Start empty at this location?', 'Create and use empty Local, LocalCrypt and Received Files folders in ' + destination + '? No files are copied or erased. Current files stay at their old location. The destination must be empty.'),
            'recover': ('Use existing files here without copying?', 'Use the existing Local, LocalCrypt and Received Files collections in ' + destination +
                        '? This does not copy or merge your current collection. A retained backup may be older and omit recent changes. LocalCrypt still needs its original credentials.'),
            'wipe': ('Permanently erase these collection folders?', 'Delete ' + str(volume / 'Logistics/Local' if volume else self.private_root / 'LocalFiles') + ' and ' + str(volume / 'Logistics/LocalCrypt' if volume else self.private_root / 'LocalCryptFolders') + ', ' + str(volume / 'Logistics/Received Files' if volume else self.private_root / 'Received Files') + ', plus interrupted .storage-copy-* folders at ' + destination + '? The files cannot be recovered by Logistics. Other folders, private credentials, settings and metadata are kept. The location currently in use cannot be erased.'),
        }
        title, message = prompts[action]
        if action != 'wipe':
            message += ' The app will close when finished; reopen it to use this location.'
        return title, message, destination

    def _collection_progress_renderer(self, status_label, progress_bar, details, current_file, width, *, fit_text):
        """Keep queued progress bound to the controls captured for this operation."""
        def render(event):
            status_label.text = event['phase']
            total = event['total']
            if total is None:
                progress_bar.max = None
                progress_bar.start()
                details.text = f"{event['files']} files checked · {event['bytes'] / 1048576:.1f} MiB read"
            else:
                progress_bar.stop()
                progress_bar.max = 100
                percent = min(100, event['bytes'] * 100 / total) if total else 100
                progress_bar.value = percent
                details.text = f"Current folder: {percent:.0f}% · {event['bytes'] / 1048576:.1f} / {total / 1048576:.1f} MiB · {event['files']} files copied"
            current_file.text = event['path']
            for label in (status_label, details, current_file):
                fit_text(label, width - 32)

        return render
