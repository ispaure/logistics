"""Files/calendar drawer and contextual file commands for the Notes Library."""
import asyncio
import calendar
import posixpath
from datetime import date
from pathlib import PurePosixPath
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from commonUtils.runtime.operations import OperationCancelled
from features.notes_library import library_files
from services.documents.authoring.document_dialogs import DocumentTypeDialog


# Match the host's 13-sp captions and 16-sp controls in Toga CSS-point units.
CAPTION_FONT, CONTROL_FONT = 10, 12


class LibraryPanels:
    def init_panels(self):
        self.panel_tab = 'Files'
        self.calendar_month = date.today().replace(day=1)
        self.calendar_entries = None
        self.calendar_generation = 0
        self.calendar_task = None
        self.file_command_busy = False
        self.daily_opening = False
        children = list(self.tree.children)
        metadata = children[1]
        metadata.style.font_size = CAPTION_FONT
        metadata.style.font_style = 'italic'
        self.host.presentation.surface(metadata, radius=0, background='transparent', foreground='muted',
                                       outlined=False, eink_outlined=False)
        self.files_content = toga.Box(children=[], style=Pack(direction=COLUMN, flex=1))
        for child in children[2:]:
            self.tree.remove(child)
            self.files_content.add(child)
        self.tree.clear()
        self.panel_tabs = {}
        tabs = self.host.presentation.surface(toga.Box(style=Pack(direction=ROW)),
            radius=11, background='alternate', outlined=False)
        for name in ('Files', 'Calendar'):
            def select(widget=None, name=name, **kw):
                if self.panel_tab != name:
                    self.select_panel_tab(name)
            button = toga.Button(name, on_press=select,
                style=Pack(flex=1, height=48, font_size=CONTROL_FONT, margin=2))
            self.host.tab_style(button, name == self.panel_tab)
            self.panel_tabs[name] = button
            tabs.add(button)
        self.calendar_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.calendar_scroll = toga.ScrollContainer(content=self.calendar_content, horizontal=False, style=Pack(flex=1))
        self.panel_body = toga.Box(children=[self.files_content], style=Pack(direction=COLUMN, flex=1))
        self.tree.add(tabs, metadata, self.panel_body)
        self.search_mode.items = ['Search within Documents', 'Search in File Names']
        self.search_mode.value = 'Search within Documents'

    def select_panel_tab(self, name):
        if not self.valid() or name not in self.panel_tabs:
            return
        self.panel_tab = name
        selected = self.files_content if name == 'Files' else self.calendar_scroll
        if self.panel_body.children != [selected]:
            self.panel_body.clear()
            self.panel_body.add(selected)
        for key, button in self.panel_tabs.items():
            self.host.tab_style(button, key == name)
        if name == 'Calendar':
            self.search_generation += 1
            if self.search_task is not None:
                if not self.search_task.done():
                    self.search_paused = True
                    self.search_task.cancel()
                self.search_task = None
            self.render_tree()  # Cancel unfinished work for the unmounted tab.
            self.refresh_calendar()
        else:
            self.calendar_generation += 1
            if self.calendar_task is not None:
                self.calendar_task.cancel()
            self.render_tree()
            if self.search_paused:
                self.search_changed()
        self.sidebar.refresh_gestures()

    def refresh_calendar(self, widget=None, **kwargs):
        if not self.valid() or self.panel_tab != 'Calendar':
            return
        self.calendar_generation += 1
        generation = self.calendar_generation
        if self.calendar_task is not None:
            self.calendar_task.cancel()
        self.calendar_entries = None
        self.render_calendar('Finding daily notes…')
        async def scan():
            cancelled = lambda: not self.valid() or generation != self.calendar_generation
            try:
                entries = await asyncio.to_thread(library_files.daily_notes, self.library,
                    visible=self.host.folder_visible, cancelled=cancelled)
                if not cancelled():
                    self.calendar_entries = entries
                    self.render_calendar()
            except (OperationCancelled, asyncio.CancelledError):
                return
            except (OSError, ValueError) as error:
                if not cancelled():
                    self.render_calendar('Could not find daily notes: ' + str(error)[:120])
        self.calendar_task = self.host.loop.create_task(scan())

    def render_calendar(self, status=''):
        if not self.valid() or self.panel_tab != 'Calendar':
            return
        self.calendar_content.clear()
        month = self.calendar_month
        title = toga.Label(month.strftime('%B %Y'), style=Pack(flex=1, text_align='center'))
        def move(offset):
            if not self.valid() or self.panel_tab != 'Calendar':
                return
            value = month.year * 12 + month.month - 1 + offset
            if 1 <= value // 12 <= 9999:
                self.calendar_month = date(value // 12, value % 12 + 1, 1)
                self.render_calendar()
        self.calendar_content.add(toga.Box(children=[
            toga.Button('‹', on_press=lambda w: move(-1), style=Pack(width=44, height=44)),
            title, toga.Button('›', on_press=lambda w: move(1), style=Pack(width=44, height=44))],
            style=Pack(direction=ROW, align_items='center')))
        grid = toga.Box(style=Pack(direction=COLUMN))
        grid.add(toga.Box(children=[toga.Label(day, style=Pack(flex=1, text_align='center',
            font_size=CAPTION_FONT)) for day in ('M', 'T', 'W', 'T', 'F', 'S', 'S')],
            style=Pack(direction=ROW)))
        for week in calendar.monthcalendar(month.year, month.month):
            row = toga.Box(style=Pack(direction=ROW))
            for day in week:
                if not day:
                    row.add(toga.Box(style=Pack(flex=1)))
                    continue
                key = date(month.year, month.month, day).isoformat()
                exists = bool((self.calendar_entries or {}).get(key))
                async def choose(widget=None, key=key, **kw):
                    await self.open_daily_note(key)
                button = toga.Button(str(day) + ('•' if exists else ''), on_press=choose,
                    enabled=self.calendar_entries is not None and not self.file_command_busy,
                    style=Pack(flex=1, height=44, font_size=CAPTION_FONT,
                               font_weight='bold' if key == date.today().isoformat() else 'normal'))
                button.daily_date = key
                row.add(button)
            grid.add(row)
        self.calendar_content.add(grid,
            toga.Label(status or ('Finding daily notes…' if self.calendar_entries is None else '• Daily note exists · tap to open'),
                style=Pack(font_size=CAPTION_FONT)),
            toga.Button('Refresh daily notes', on_press=self.refresh_calendar, style=Pack(height=48)))
        self.sidebar.refresh_gestures()

    async def open_daily_note(self, key):
        if self.daily_opening:
            return False
        self.daily_opening = True
        try:
            return await self._open_daily_note(key)
        finally:
            self.daily_opening = False

    async def _open_daily_note(self, key):
        if not self.valid() or self.file_command_busy or self.calendar_entries is None:
            return False
        # A scan must complete before offering creation, including nested duplicates.
        paths = self.calendar_entries.get(key, [])
        if paths:
            if len(paths) > 1:
                dialog = DocumentTypeDialog(choices=[(posixpath.relpath(path, self.root or '.'), path) for path in paths])
                dialog.title, dialog.message = 'Choose daily note', key
                path = await self.view.window.dialog(dialog)
                if path not in paths or not self.valid():
                    return False
            else:
                path = paths[0]
            return await self.open_note(path)
        if not self.library.supports('create'):
            self.render_calendar('This library is read-only. Choose a day with an existing note.')
            return False
        if not await self.view.window.dialog(toga.ConfirmDialog('Create daily note?',
                'Create ' + key + '.md in the Notes Library root?')) or not self.valid():
            return False
        if not await self.prepare_leave():
            return False
        self.file_command_busy = True
        try:
            path = await asyncio.to_thread(self.library.create, key, self.root,
                cancelled=lambda: not self.valid())
            if not self.valid():
                return False
            if self.calendar_entries is not None:
                self.calendar_entries.setdefault(key, []).append(path)
            if self.panel_tab == 'Calendar':
                self.refresh_calendar()
            await self.load_folder(self.root)
            return await self.open_note(path)
        except (OSError, ValueError) as error:
            if self.valid():
                self.render_calendar(str(error)[:180])
            return False
        finally:
            self.file_command_busy = False
            if self.valid() and self.panel_tab == 'Calendar' and self.calendar_entries is not None:
                self.render_calendar()

    def update_tree_selection(self):
        # Opening changes only selection. Keep the detached native file rows
        # instead of rebuilding up to fifty buttons on the opening path.
        for row in self.rows.children:
            button = next((child for child in row.children if hasattr(child, 'vault_path')), None)
            if button is not None:
                selected = button.vault_path == self.selected_path
                if getattr(row, '_notes_selected', None) != selected:
                    self.host.highlight_entry(row, selected)
                    self.host.highlight_entry(button, selected)
                    row._notes_selected = selected

    def bind_file_hold(self, button, path, *, directory=False):
        def show():
            if self.valid():
                self.host.loop.create_task(self.file_actions(path))
        button.notes_file_actions = show
        if hasattr(self, 'file_drag') and self.library.supports('rename'):
            self.file_drag.bind(button, path, target=directory)
            return
        backend = type(button._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, SEL, objc_method
            global _hold_class
            if _hold_class is None:
                class NotesFileHold(ObjCClass('NSObject')):
                    @objc_method
                    def hold_(self, gesture) -> None:
                        if int(gesture.state) == 1:
                            self.invoke()
                _hold_class = NotesFileHold
            target = _hold_class.alloc().init()
            target.invoke = show
            gesture = ObjCClass('UILongPressGestureRecognizer').alloc().initWithTarget(target, action=SEL('hold:'))
            button._impl.native.addGestureRecognizer(gesture)
            button._notes_hold = (target, gesture)
        elif backend.startswith('toga_android.'):
            from android.view import View
            from java import dynamic_proxy
            class Hold(dynamic_proxy(View.OnLongClickListener)):
                def onLongClick(self, native):
                    show()
                    return True
            button._notes_hold = Hold()
            button._impl.native.setOnLongClickListener(button._notes_hold)

    def release_file_hold(self, button):
        if hasattr(self, 'file_drag'):
            self.file_drag.unbind(button)
        binding = getattr(button, '_notes_hold', None)
        backend = type(button._impl).__module__
        if binding is not None and backend.startswith('toga_iOS.'):
            target, gesture = binding
            button._impl.native.removeGestureRecognizer(gesture)
            target.invoke = lambda: None
        elif binding is not None and backend.startswith('toga_android.'):
            button._impl.native.setOnLongClickListener(None)
        button._notes_hold = None
        button.notes_file_actions = lambda: None

    async def file_actions(self, path):
        if not self.valid() or self.file_command_busy:
            return
        self.selected_path = path
        choices = []
        if self.library.supports('rename'):
            choices.append(('Move / rename…', 'move'))
        if all(self.library.supports(action) for action in ('create', 'rename', 'delete')):
            choices.append(('Copy…', 'copy'))
        if self.library.supports('delete'):
            choices.append(('Delete…', 'delete'))
        if not choices:
            return
        dialog = DocumentTypeDialog(choices=choices)
        dialog.title, dialog.message = PurePosixPath(path).name, 'Choose a file action.'
        action = await self.view.window.dialog(dialog)
        if not self.valid():
            return
        if action == 'move':
            self.sidebar.show_detail()
            self.manage_entry(move=True)
        elif action == 'copy':
            self.copy_entry_form(path)
        elif action == 'delete':
            await self.delete_entry(path)

    def copy_entry_form(self, path):
        self.sidebar.show_detail()
        name = toga.TextInput(value=posixpath.relpath(path, self.root or '.'), style=Pack(height=48))
        status = toga.Label('Choose a new path inside this library. Existing files are kept.')
        button = toga.Button('Copy', style=Pack(height=48))
        async def submit(widget=None, **kw):
            if self.file_command_busy or not self.valid():
                return
            self.file_command_busy = True
            button.enabled = False
            try:
                target = await asyncio.to_thread(library_files.copy, self.library, path,
                    posixpath.join(self.root, name.value), cancelled=lambda: not self.valid())
                if self.valid():
                    await self.load_folder(posixpath.dirname(target))
                    self.refresh_library_indexes()
                    self.present()
                    self.sidebar.show_sidebar()
            except (OSError, ValueError) as error:
                status.text = str(error)[:180]
            finally:
                self.file_command_busy = False
                button.enabled = True
        button.on_press = submit
        form = toga.Box(children=[toga.Label('Copy ' + PurePosixPath(path).name), name, status, button,
            toga.Button('Cancel', on_press=lambda w: self.present(), style=Pack(height=48))],
            style=Pack(direction=COLUMN, margin=16))
        self.host.show_view(form, destination=self.destination, route='notes-copy', title='Copy')

    async def delete_entry(self, path):
        def removed(current):
            return current == path or current.startswith(path + '/')
        if self.path and removed(self.path) and not await self.prepare_leave():
            return
        if not await self.view.window.dialog(toga.ConfirmDialog('Delete ' + PurePosixPath(path).name + '?',
                'Permanently delete this item and its contents? Links are not rewritten.')) or not self.valid():
            return
        self.file_command_busy = True
        try:
            await asyncio.to_thread(library_files.remove, self.library, path, cancelled=lambda: not self.valid())
            if not self.valid():
                return
            try:
                await asyncio.to_thread(self.host.relocate_references, self.provider, path, None)
            except (OSError, ValueError, PermissionError):
                self.notice.text = 'Deleted; some saved references could not be updated.'
            retained_index = sum(not removed(current) for current in self.history[:self.history_index + 1]) - 1
            self.history = [current for current in self.history if not removed(current)]
            self.search_rows = [row for row in self.search_rows if not removed(row['path'])]
            self.positions = {current: value for current, value in self.positions.items() if not removed(current)}
            self.expanded = {current for current in self.expanded if not removed(current)}
            self.folders = {current: rows for current, rows in self.folders.items() if not removed(current)}
            if self.path and removed(self.path):
                self.speech.close()
                self.retire_editor()
                self.path = None
                self.up_button.enabled = False
                self.article.clear()
                self.article.add(self.welcome)
                self.edit.enabled = self.speech.button.enabled = False
            self.selected_path = None
            await self.load_folder(posixpath.dirname(path))
            self.refresh_library_indexes()
            self.history_index = retained_index if self.path in self.history else -1
            self.back_button.enabled = self.history_index > 0
            self.forward_button.enabled = self.history_index < len(self.history) - 1
            self.refresh_reader_actions()
            self.refresh_chrome()
            self.host.render()
            if self.panel_tab == 'Calendar':
                self.refresh_calendar()
        except (OSError, ValueError) as error:
            if self.valid():
                self.notice.text = str(error)[:180]
        finally:
            self.file_command_busy = False

    def dispose_panels(self):
        self.calendar_generation += 1
        if self.calendar_task is not None:
            self.calendar_task.cancel()
        self.calendar_entries = None
        self.calendar_content.clear()


_hold_class = None


class LibraryOpening:
    """Retain the current page while a cancellable full-pane opening runs."""
    def __init__(self, owner):
        self.owner = owner
        self.active = False
        self.panel = None
        self.retained = []

    def start(self, path, *, finding=False):
        self.finish()
        self.active = True
        article = self.owner.article
        self.retained = list(article.children)
        article.clear()
        self.spinner = toga.ProgressBar(max=None, style=Pack(height=6, margin_top=24))
        self.filename = toga.Label(PurePosixPath(path).name, style=Pack(font_size=18, text_align='center'))
        self.status = toga.Label('Finding file…' if finding else 'Opening document…',
                                 style=Pack(text_align='center', margin_top=12))
        content = toga.Box(children=[
            self.filename,
            self.spinner,
            self.status,
            toga.Button('Cancel', on_press=self.cancel, style=Pack(height=48, margin_top=16))],
            style=Pack(direction=COLUMN, margin=32))
        self.panel = toga.Box(children=[toga.Box(style=Pack(flex=1)), content,
            toga.Box(style=Pack(flex=1))], style=Pack(direction=COLUMN, flex=1))
        article.add(self.panel)
        self.spinner.start()

    def opening(self, path):
        if self.active:
            self.filename.text = PurePosixPath(path).name
            self.status.text = 'Opening document…'

    def cancel(self, widget=None, **kwargs):
        self.owner.epoch += 1
        self.finish()

    def finish(self):
        if not self.active:
            return
        self.active = False
        self.spinner.stop()
        self.filename.text = self.status.text = ''
        if self.panel.parent is self.owner.article:
            self.owner.article.remove(self.panel)
            for child in self.retained:
                self.owner.article.add(child)
        self.retained.clear()
        self.panel = None
