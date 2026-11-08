"""Android collection drive selection; file-manager permission is user controlled."""
import asyncio
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from services.documents.locations import collection_base, selection, switch_location, recover_location, wipe_destination, start_empty_location, describe_location


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

    def _storage_note(self, text):
        from .settings.forms import connection_note
        return connection_note(text)

    def _storage_button(self, title, callback, *, primary=False, destructive=False):
        from .settings.forms import OPTION_FONT_SIZE
        from .appearance import surface
        button = toga.Button(title, on_press=callback,
                             style=Pack(height=48, font_size=OPTION_FONT_SIZE, margin_bottom=8))
        if destructive:
            button.action_role = 'destructive'
            surface(button, radius=12, background='destructive_fill', foreground='on_destructive')
        elif primary:
            surface(button, radius=12, background='text', foreground='surface')
        return button

    def _storage_heading(self, text):
        from .settings.forms import SettingsLabel, OPTION_FONT_SIZE
        return SettingsLabel(text, style=Pack(font_size=OPTION_FONT_SIZE, font_weight='bold', margin_bottom=12))

    def _storage_disclosure(self, title, children):
        from commonUtils.ui.native.forms import collapsible
        from .settings.forms import fit_section, OPTION_FONT_SIZE
        from .appearance import surface
        def changed(box):
            section = box
            while isinstance(section.parent, toga.Box):
                section = section.parent
            fit_section(section, max(280, self.app.adaptive.content_width('settings')))
        def style(button):
            button.style.font_size = OPTION_FONT_SIZE
            return surface(button, radius=0, background='transparent', foreground='text')
        return collapsible(title, children, changed=changed, style_button=style)[0]

    def _show_storage_page(self, box, title, route, *, footer=None):
        from .settings.forms import fit_section
        from .appearance import surface
        from .layout_participants import participants, reflow_settings_section
        surface(box, radius=0, background='settings_background')
        self.collection_storage_page = box
        view = toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))
        if footer is not None:
            view = toga.Box(children=[view, footer], style=Pack(direction=COLUMN, flex=1))
        participants(self.app).register(route, box, reflow_settings_section)
        width = max(280, self.app.adaptive.content_width('settings'))
        fit_section(box, width)
        if footer is not None:
            participants(self.app).register(route + '-footer', footer, reflow_settings_section)
            fit_section(footer, width)
        self.show_view(view, destination='settings', route=route, title=title)

    def _storage_paths(self, volume):
        try:
            state = describe_location(self.private_root, volume)
            return self._storage_disclosure('Folder paths',
                [self._storage_note(path + '\n' + status) for path, status in state['folders']])
        except (OSError, ValueError) as error:
            return self._storage_note('Location unavailable: ' + str(error))

    def _storage_permission(self, box, action):
        volume = self.collection_drives[self.collection_drive.value]
        try:
            source_external = action == 'copy' and selection(self.private_root) is not None
        except (OSError, ValueError):
            source_external = False
        needed = (volume is not None or source_external) and android_sdk() >= 30
        if needed and not all_files_allowed():
            box.add(self._storage_heading('Allow storage access'),
                self._storage_note('Android needs All files access for this location. Other apps with storage access can read ordinary files and Rclone Copies; LocalCrypt stays encrypted.'),
                self._storage_button('Open Android settings', self.allow_collection_storage),
                self._storage_button('Check access', lambda widget: self._show_storage_target(action)
                    if action == 'wipe' else self._show_storage_review(action)))
            return False
        if volume is not None and android_sdk() < 30:
            box.add(self._storage_note('No storage permission is needed. Android removes these app storage folders if you uninstall Logistics or clear its app data. Keep a separate backup.'))
        return True

    def show_collection_storage(self, widget=None, **kwargs):
        if getattr(self, '_storage_changing', False) and getattr(self, 'collection_storage_progress_view', None) is not None:
            self.show_view(self.collection_storage_progress_view, destination='settings',
                           route='collection-storage-progress', title='File storage progress')
            return
        from .settings.forms import OPTION_FONT_SIZE, group_rows
        from .appearance import surface
        self._collection_target_box = None
        raw_drives = android_drives(self)
        # Paths belong in details, not in the location picker. Keep duplicate
        # volume names distinct without guessing which mounted drive is meant.
        self.collection_drives = {}
        for raw, path in raw_drives.items():
            base_label = raw.split(' · ')[0]
            label, suffix = base_label, 2
            while label in self.collection_drives:
                label = f'{base_label} ({suffix})'
                suffix += 1
            self.collection_drives[label] = path
        try:
            chosen = selection(self.private_root)
            current = next((name for name, path in self.collection_drives.items()
                            if str(path) == (chosen['volume'] if chosen else 'None')),
                           'Unavailable storage')
            collection_base(self.private_root)
        except (OSError, ValueError):
            current = 'Unavailable storage'
        selected = current if current in self.collection_drives else next(iter(self.collection_drives))
        self.collection_drive = toga.Selection(items=list(self.collection_drives), value=selected,
                                             style=Pack(height=48, font_size=OPTION_FONT_SIZE))
        self.collection_target_status = self._storage_note('')
        self.collection_storage_status = self._storage_note('')
        self.collection_copy = self._storage_button('Copy and switch', self.change_collection_storage, primary=True)
        self.collection_existing = self._storage_button('Use these files', self.recover_collection_storage, primary=True)
        self.collection_empty = self._storage_button('Start empty and switch', self.start_empty_collection, primary=True)
        self.collection_erase = self._storage_button('Delete files…', self.wipe_collection_storage, destructive=True)
        self.collection_drive.on_change = self.collection_target_changed
        box = toga.Box(style=Pack(direction=COLUMN, margin=20))
        location = toga.Box(children=[self._storage_heading(current),
            self._storage_note('Rclone Copies · LocalCrypt · On This Phone')], style=Pack(direction=COLUMN, margin=16))
        surface(location, radius=16, background='settings_group')
        box.add(self._storage_note('Current location'), location,
                self._storage_note('Choose where these files are stored. LocalCrypt stays encrypted.'),
                self._storage_button('Change location', lambda widget: self._show_storage_target('copy'), primary=True))
        options = [self._storage_button(title, lambda widget, action=action: self._show_storage_target(action))
                   for title, action in (('Use files from another location', 'recover'),
                                         ('Start with empty folders', 'empty'),
                                         ('Delete files from an old location', 'wipe'))]
        box.add(self._storage_disclosure('Other storage options', [group_rows(options)]),
                self._storage_disclosure('What stays on this device?', [self._storage_note(
                    'Settings, credentials and app-managed documents stay in the app. Only Rclone Copies, LocalCrypt and On This Phone change location.')]),
                self.collection_storage_status)
        self.collection_target_changed()
        self._show_storage_page(box, 'File storage', 'collection-storage')

    def _show_storage_target(self, action):
        if getattr(self, '_storage_changing', False):
            return
        from .file_drawer import detach
        titles = {'copy': 'Change location', 'recover': 'Use existing files',
                  'empty': 'Start empty', 'wipe': 'Delete old files'}
        box = toga.Box(style=Pack(direction=COLUMN, margin=20))
        box.add(self._storage_heading('Choose a location'), self._storage_note(
            'The location currently in use cannot be deleted.' if action == 'wipe'
            else 'Your current location stays unchanged until you confirm.'))
        for control in (self.collection_drive, self.collection_target_status):
            detach(control)
            box.add(control)
        box.add(self._storage_button('Refresh locations', lambda widget: self._refresh_storage_target(action)))
        detach(self.collection_storage_status)
        box.add(self.collection_storage_status)
        self.collection_storage_status.text = ''
        self._collection_target_action = action
        self._collection_target_box = box
        self.collection_storage_page = box
        self._collection_target_details = None
        self._collection_delete_footer = toga.Box(style=Pack(direction=COLUMN, margin=(8, 20, 20, 20))) if action == 'wipe' else None
        self.collection_target_changed()
        self._show_storage_page(box, titles[action], 'collection-storage-target', footer=self._collection_delete_footer)

    def _refresh_storage_target(self, action):
        volume = self.collection_drives[self.collection_drive.value]
        self.show_collection_storage()
        selected = next((name for name, path in self.collection_drives.items() if path == volume), None)
        if selected is not None:
            self.collection_drive.value = selected
        self._show_storage_target(action)

    def _render_storage_target(self):
        from .file_drawer import detach
        action, box = self._collection_target_action, self._collection_target_box
        previous = self._collection_target_details
        if previous is not None:
            detach(previous)
        details = toga.Box(style=Pack(direction=COLUMN, margin_top=16))
        self._collection_target_details = details
        box.add(details)
        if action == 'wipe':
            details.add(self._storage_note('Permanently delete Rclone Copies, LocalCrypt and On This Phone at this location, including interrupted copies. Your active storage and other files are kept.'),
                        self._storage_paths(self.collection_drives[self.collection_drive.value]))
            allowed = self._storage_permission(details, action)
            detach(self.collection_erase)
            self._collection_delete_footer.add(self.collection_erase)
            self.collection_erase.enabled = self.collection_erase.enabled and allowed
        else:
            proceed = self._storage_button('Continue', lambda widget: self._show_storage_review(action), primary=True)
            proceed.enabled = getattr(self, 'collection_' + {'copy': 'copy', 'recover': 'existing', 'empty': 'empty'}[action]).enabled
            details.add(proceed)
        from .settings.forms import fit_section
        fit_section(box, max(280, self.app.adaptive.content_width('settings')))

    def _show_storage_review(self, action):
        if getattr(self, '_storage_changing', False):
            return
        from .file_drawer import detach
        box = toga.Box(style=Pack(direction=COLUMN, margin=20))
        target = self.collection_drive.value
        box.add(self._storage_note('New location'), self._storage_heading(target))
        explanations = {
            'copy': ('Copy your files and switch', 'Copy and verify Rclone Copies, LocalCrypt and On This Phone. Original files stay where they are.'),
            'recover': ('Use the files already here', 'No files are copied or merged. These files may be older than your current collection. LocalCrypt needs its original credentials.'),
            'empty': ('Start with empty folders', 'Create empty Rclone Copies, LocalCrypt and On This Phone folders. Your current files stay at their old location. The destination must be empty.'),
        }
        title, note = explanations[action]
        box.add(self._storage_heading(title), self._storage_note(note))
        allowed = self._storage_permission(box, action)
        try:
            state = describe_location(self.private_root, self.collection_drives[target])
            contains_files = any(status == 'contains files or folders' for _, status in state['folders'])
        except (OSError, ValueError):
            contains_files = False
        if contains_files and action in ('copy', 'empty'):
            box.add(self._storage_note('This location already has files. Copying stops if any files differ; nothing is merged or overwritten.'
                if action == 'copy' else 'This location already has files. Choose an empty location or use the files already here.'))
            box.add(self._storage_button('Use existing files instead', lambda widget: self._show_storage_review('recover')))
        box.add(self._storage_paths(self.collection_drives[target]))
        status = self.collection_storage_status
        detach(status)
        status.text = ''
        box.add(status)
        if allowed:
            box.add(self._storage_note('Logistics will close when finished. Reopen it to use this location.'))
            button = getattr(self, 'collection_' + {'copy': 'copy', 'recover': 'existing', 'empty': 'empty'}[action])
            detach(button)
            if action == 'empty' and contains_files:
                button.enabled = False
            box.add(button)
        self._show_storage_page(box, 'Review change', 'collection-storage-review')

    def collection_target_changed(self, widget=None, **kwargs):
        if not hasattr(self, 'collection_target_status'):
            return
        try:
            state = describe_location(self.private_root, self.collection_drives[self.collection_drive.value])
            self.collection_target_status.text = ('Currently in use' if state['active'] else
                'Existing files found' if any(status == 'contains files or folders' for _, status in state['folders'])
                else 'No collection files found')
            enabled = not state['active'] and not getattr(self, '_storage_changing', False)
            for name in ('collection_copy', 'collection_existing', 'collection_empty', 'collection_erase'):
                getattr(self, name).enabled = enabled
        except (OSError, ValueError) as error:
            self.collection_target_status.text = 'Cannot inspect this location: ' + str(error)
            for name in ('collection_copy', 'collection_existing', 'collection_empty'):
                getattr(self, name).enabled = not getattr(self, '_storage_changing', False)
            self.collection_erase.enabled = False
        from .routes import contains
        if (getattr(self, '_collection_target_box', None) is not None
                and (self.collection_storage_page is self._collection_target_box
                     or contains(self.app.body, self._collection_target_box))
                and not getattr(self, '_storage_changing', False)):
            self.collection_storage_page = self._collection_target_box
            self._render_storage_target()
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
            self.collection_storage_status.text = 'Open Android settings, enable permission for All files access, then return and choose Check access.'
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
            from .settings.forms import fit_section, fit_text
            width = max(280, self.app.adaptive.content_width('settings'))
            progress_box = toga.Box(style=Pack(direction=COLUMN, margin=16))
            heading = {'copy': 'Copying your files', 'recover': 'Selecting existing files',
                       'empty': 'Preparing empty folders', 'wipe': 'Erasing files at selected location'}[action]
            progress_box.add(self._storage_heading(heading))
            if action == 'copy':
                progress_box.add(self._storage_note('From: ' + str(collection_base(self.private_root))))
            progress_box.add(self._storage_note('To: ' + destination if action != 'wipe' else 'Location: ' + destination))
            progress_box.add(self._storage_note('Keep Logistics open until this finishes. Original files stay in place when copying.'))
            self.collection_storage_status = self._storage_note('Preparing…')
            progress_bar = toga.ProgressBar(max=None, style=Pack(height=12, margin_top=12, margin_bottom=12))
            details = self._storage_note('Finding files…')
            current_file = self._storage_note('')
            done_button = self._storage_button('Back to storage settings', self.show_collection_storage)
            done_button.enabled = False
            progress_box.add(self.collection_storage_status, progress_bar, details, current_file, done_button)
            self.collection_storage_page = progress_box
            from .layout_participants import participants, reflow_settings_section
            participants(self.app).register('collection_storage_page', progress_box, reflow_settings_section)
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
            'copy': ('Change collection drive?', 'Copy Rclone Copies, LocalCrypt and On This Phone to ' + destination +
                     '? Different destination files stop the copy. Original copies remain as a backup.'),
            'empty': ('Start empty at this location?', 'Create and use empty Rclone Copies, LocalCrypt and On This Phone folders in ' + destination + '? No files are copied or erased. Current files stay at their old location. The destination must be empty.'),
            'recover': ('Use existing files here without copying?', 'Use the existing Rclone Copies, LocalCrypt and On This Phone collections in ' + destination +
                        '? This does not copy or merge your current collection. A retained backup may be older and omit recent changes. LocalCrypt still needs its original credentials.'),
            'wipe': ('Permanently erase these collection folders?',
                     'Delete the displayed collection folders and any interrupted .storage-copy-* folders at '
                     + destination + '? Other files and the active location are kept.'),
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
