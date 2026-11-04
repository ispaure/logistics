"""Files, Search and Calendar panels with compact commands below the tabs."""
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
from ..navigation import PathChange
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
        self.files_content = toga.Box(children=[], style=Pack(direction=COLUMN, flex=1))
        for child in children[2:]:
            self.tree.remove(child)
            if child not in (self.search, self.search_mode):
                self.files_content.add(child)
        self.rows_scroll = self.files_content.children[0]
        search_rows = toga.Box(style=Pack(direction=COLUMN))
        search_scroll = toga.ScrollContainer(content=search_rows, horizontal=False, style=Pack(flex=1))
        self._row_panel = 'Files'
        self._row_panels = {
            'Files': dict(rows=self.rows, scroll=self.rows_scroll, _row_cache={}, shown=50,
                          _rows_message=None, _more_rows=None),
            'Search in File Names': dict(rows=search_rows, scroll=search_scroll, _row_cache={}, shown=50,
                           _rows_message=None, _more_rows=None),
        }
        self._search_scope = 'Search in File Names'
        document_rows = toga.Box(style=Pack(direction=COLUMN))
        self._row_panels['Search within Documents'] = dict(rows=document_rows,
            scroll=toga.ScrollContainer(content=document_rows, horizontal=False, style=Pack(flex=1)),
            _row_cache={}, shown=50, _rows_message=None, _more_rows=None)
        self.search_query = None
        self._search_interfaces = {
            'Search in File Names': dict(control=self.search, search_rows=[], search_status='',
                search_paused=False, search_query=None),
            'Search within Documents': dict(control=toga.TextInput(placeholder='Search in documents',
                on_change=self.search_changed, style=Pack(height=48)), search_rows=[], search_status='',
                search_paused=False, search_query=None),
        }
        self.search.placeholder = 'Search file names'
        self.search_scope = toga.Box(style=Pack(direction=ROW))
        self.search_scope_buttons = {}
        for label, value in (('In documents', 'Search within Documents'), ('File names', 'Search in File Names')):
            def choose(widget=None, value=value, **kwargs):
                self.search_mode.value = value
            button = toga.Button(label, on_press=choose, style=Pack(flex=1, height=44, font_size=CONTROL_FONT))
            self.search_scope_buttons[value] = button
            self.search_scope.add(button)
        self.search_content = toga.Box(children=[self.search, self.search_scope, search_scroll],
            style=Pack(direction=COLUMN, flex=1, gap=4))
        self.tree.clear()
        self.tree.style.margin = 0
        self.host.presentation.surface(self.tree, radius=0, background='alternate', outlined=False)
        self.panel_tabs = {}
        self.panel_tab_indicators = {}
        tabs = self.host.presentation.surface(toga.Box(style=Pack(direction=ROW)),
            radius=0, background='transparent', outlined=False)
        for name in ('Files', 'Search', 'Calendar'):
            def select(widget=None, name=name, **kw):
                if self.panel_tab != name:
                    self.select_panel_tab(name)
            button = toga.Button(name, on_press=select,
                style=Pack(height=46, font_size=CONTROL_FONT))
            self.panel_tabs[name] = button
            indicator = toga.Box(style=Pack(height=2))
            self.panel_tab_indicators[name] = indicator
            tabs.add(toga.Box(children=[button, indicator], style=Pack(direction=COLUMN, flex=1)))
            self.style_panel_tab(name, name == self.panel_tab)
        self.calendar_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.calendar_scroll = toga.ScrollContainer(content=self.calendar_content, horizontal=False, style=Pack(flex=1))
        self.panel_body = toga.Box(children=[self.files_content], style=Pack(direction=COLUMN, flex=1))
        self.panel_body.style.margin_left = self.panel_body.style.margin_right = 8
        self.panel_body.style.margin_top = 8
        # Symmetric flex spaces make Pack allocate the complete pane width.
        # Justify alone leaves a fixed-width command row at its intrinsic width.
        self.panel_actions = toga.Box(children=[toga.Box(style=Pack(flex=1))],
            style=Pack(direction=ROW, gap=4, justify_content='center'))
        self.tree.add(tabs, self.panel_actions, self.panel_body)
        self.search_mode.items = ['Search within Documents', 'Search in File Names']
        self.search_mode.value = 'Search in File Names'
        self.search_mode.on_change = self.search_scope_changed
        self.sync_search_scope()

    def remember_search_interface(self):
        state = self._search_interfaces[self._search_scope]
        for field in ('search_rows', 'search_status', 'search_paused', 'search_query'):
            state[field] = getattr(self, field)

    def search_scope_changed(self, widget=None, **kwargs):
        if not self.valid():
            return
        scope = self.search_mode.value
        if scope == self._search_scope:
            return
        self.search_generation += 1
        if self.search_task is not None:
            if not self.search_task.done():
                self.search_paused = True
                self.search_task.cancel()
            self.search_task = None
        self.remember_search_interface()
        self._search_scope = scope
        state = self._search_interfaces[scope]
        self.search = state['control']
        for field in ('search_rows', 'search_status', 'search_paused', 'search_query'):
            setattr(self, field, state[field])
        if self.panel_tab == 'Search':
            self.select_panel_rows(scope)
        self.search_content.clear()
        self.search_content.add(self.search, self.search_scope, self._row_panels[scope]['scroll'])
        self.sync_search_scope()
        if self.panel_tab == 'Search':
            self.render_tree()
            self.resume_search_interface()
        self.sidebar.refresh_gestures()

    def resume_search_interface(self):
        if self.search_paused or self.search_query != (self.search.value or ''):
            self.search_changed()

    def invalidate_search_interfaces(self):
        for state in self._search_interfaces.values():
            state['search_query'] = None
        self.search_query = None

    def remember_panel_rows(self):
        state = self._row_panels[self._row_panel]
        for name in ('_row_cache', 'shown', '_rows_message', '_more_rows'):
            state[name] = getattr(self, name, state[name])

    def select_panel_rows(self, name):
        if name == self._row_panel:
            return
        task = getattr(self, 'tree_task', None)
        if task is not None and not task.done():
            task.cancel()
        self.remember_panel_rows()
        self._row_panel = name
        state = self._row_panels[name]
        self.rows, self.rows_scroll = state['rows'], state['scroll']
        for field in ('_row_cache', 'shown', '_rows_message', '_more_rows'):
            if state[field] is not None:
                setattr(self, field, state[field])
            elif hasattr(self, field):
                delattr(self, field)

    def dispose_panel_rows(self):
        self.remember_panel_rows()
        for state in self._row_panels.values():
            for row in state['_row_cache'].values():
                for button in row.children:
                    if hasattr(button, 'vault_path'):
                        self.release_file_hold(button)
            state['_row_cache'].clear()
            state['rows'].clear()
            state['_rows_message'] = state['_more_rows'] = None
        self._row_cache = {}
        for field in ('_rows_message', '_more_rows'):
            if hasattr(self, field):
                delattr(self, field)

    def sync_search_scope(self):
        for value, button in getattr(self, 'search_scope_buttons', {}).items():
            self.host.tab_style(button, self.search_mode.value == value)

    def style_panel_tab(self, name, selected):
        button = self.panel_tabs[name]
        self.host.tab_style(button, selected)
        self.host.presentation.surface(button, radius=0, background='transparent',
            foreground='text' if selected else 'muted', outlined=False)
        self.host.presentation.surface(self.panel_tab_indicators[name], radius=0,
            background='accent' if selected else 'transparent', outlined=False)

    def install_panel_actions(self):
        """Reuse the library's existing commands, keeping the tree viewport clear."""
        presentation = self.host.presentation
        actions = [('edit', 'New document', self.new_note, 'create'),
                   ('folder_add', 'New folder', lambda widget=None, **kw: self.manage_entry(folder=True), 'create'),
                   ('collapse', 'Collapse all folders', self.collapse_folders, None)]
        for icon, label, callback, capability in actions:
            if capability is None or self.library.supports(capability):
                button = presentation.icon_button(icon, label, on_press=callback)
                presentation.surface(button, radius=0, background='transparent', foreground='muted', outlined=False)
                self.panel_actions.add(button)
        self.panel_actions.add(toga.Box(style=Pack(flex=1)))

    async def browse_library_root(self, widget=None, **kwargs):
        if not self.valid():
            return
        await self.reveal_folder(self.root)

    def collapse_folders(self, widget=None, **kwargs):
        if not self.valid():
            return
        self.expanded = {self.root}
        self.render_tree()

    def select_panel_tab(self, name):
        if not self.valid() or name not in self.panel_tabs:
            return
        if name in ('Files', 'Search'):
            self.select_panel_rows(self._search_scope if name == 'Search' else name)
        self.panel_tab = name
        selected = {'Files': self.files_content, 'Search': self.search_content,
                    'Calendar': self.calendar_scroll}[name]
        if self.panel_body.children != [selected]:
            self.panel_body.clear()
            self.panel_body.add(selected)
        for key, button in self.panel_tabs.items():
            self.style_panel_tab(key, key == name)
        if name != 'Search':
            self.search_generation += 1
            if self.search_task is not None:
                if not self.search_task.done():
                    self.search_paused = True
                    self.search_task.cancel()
                self.search_task = None
        if name == 'Calendar':
            self.render_tree()  # Cancel unfinished work for the unmounted tab.
            self.refresh_calendar()
        else:
            self.calendar_generation += 1
            if self.calendar_task is not None:
                self.calendar_task.cancel()
            self.render_tree()
            if name == 'Search':
                self.resume_search_interface()
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
                    if not selected:
                        self.host.presentation.surface(row, radius=0, background='transparent',
                            outlined=False, eink_outlined=False)
                        self.host.presentation.surface(button, radius=0, background='transparent',
                            foreground='text', outlined=False, eink_outlined=False)
                    row._notes_selected = selected

    def bind_file_hold(self, button, path, *, directory=False):
        def show():
            if self.valid():
                self.host.loop.create_task(self.file_actions(path))
        button.notes_file_actions = show
        if hasattr(self, 'file_drag') and self.library.supports('rename'):
            self.file_drag.bind(button, path, source=False, target=directory)
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
            icon = getattr(button, '_notes_drag_icon', None)
            if icon is not None:
                self.file_drag.unbind(icon)
                button._notes_drag_icon = None
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
            choices.extend([('Rename…', 'rename'), ('Move…', 'move')])
        if all(self.library.supports(action) for action in ('create', 'rename', 'delete')):
            choices.append(('Copy…', 'copy'))
        if self.library.supports('delete'):
            choices.append(('Delete…', 'delete'))
        if not choices:
            return
        dialog = DocumentTypeDialog(choices=choices)
        dialog.title, dialog.message = PurePosixPath(path).name, 'Choose a file action.'
        request = self.file_action_request = getattr(self, 'file_action_request', 0) + 1
        side, epoch, destination = self.sidebar.side, self.epoch, self.host.destination()
        if side is not None:
            # The floating panel lives above the controller's alert layer.
            # Retire it before presenting the same menu for … and long press.
            self.sidebar.show_detail()
            self.sidebar.finish_dismissals()
        action = await self.view.window.dialog(dialog)
        if (not self.valid() or self.epoch != epoch or self.file_action_request != request
                or self.host.destination() != destination):
            return
        # Native alerts can dismiss the floating drawer. Its origin still owns
        # cancellation and the return from any form opened by this decision.
        if action == 'rename':
            self.selected_path = path
            self.manage_entry(move=True, return_side=side)
        elif action == 'move':
            await self.move_picker(path, return_side=side)
        elif action == 'copy':
            self.copy_entry_form(path, return_side=side)
        elif action == 'delete':
            await self.delete_entry(path)
            if (self.valid() and self.epoch == epoch and self.file_action_request == request
                    and self.host.destination() == destination and side is not None):
                self.sidebar.show(side)
        elif side is not None:
            self.sidebar.show(side)

    def show_file_action(self, view, *, route, title, return_side=None):
        if not self.valid() or self.file_command_busy:
            return False
        self.clear_file_action()
        self.file_action_side = self.sidebar.side if return_side is None else return_side
        self.file_action_view = view
        self.file_action_destination = self.destination
        self.sidebar.show_detail()
        return self.host.show_view(view, destination=self.destination, route=route, title=title)

    def file_action_current(self, view=None):
        current = getattr(self, 'file_action_view', None)
        return (self.valid() and current is not None and (view is None or view is current)
                and self.host.destination() == self.file_action_destination)

    def return_from_file_action(self, widget=None, *, view=None, **kwargs):
        if self.file_command_busy or not self.file_action_current(view):
            return
        side = getattr(self, 'file_action_side', None)
        self.clear_file_action()
        self.present()
        if side is not None:
            self.sidebar.show(side)

    def clear_file_action(self):
        view = getattr(self, 'file_action_view', None)
        browser = getattr(view, '_folder_browser', None)
        if browser is not None:
            self.host.loop.create_task(browser.close())
            view._folder_browser = None
        self.file_action_request = getattr(self, 'file_action_request', 0) + 1
        self.file_action_view = None
        self.file_action_side = None
        self.file_action_destination = None

    async def move_selected(self, widget=None, **kwargs):
        if self.selected_path is not None:
            await self.move_picker(self.selected_path)

    async def move_picker(self, source, *, return_side=None):
        if not self.valid() or self.file_command_busy or not self.library.supports('rename'):
            return False
        projection = library_files.LibraryFolderProvider(self.library, exclude=source)
        folder = ''
        generation = 0
        status = toga.Label('Links are not rewritten.')
        location = toga.Label('Library root')
        up = toga.Button('Parent folder', style=Pack(height=48))
        choose = toga.Button('Move here', enabled=False, style=Pack(height=48))

        async def navigate(path):
            nonlocal folder, generation
            if not self.file_action_current(form) or self.file_command_busy:
                return
            generation += 1
            request = generation
            choose.enabled = False
            try:
                path = projection.relative(path)
                rows = await asyncio.to_thread(projection.list, path,
                    cancelled=lambda: not self.file_action_current(form) or generation != request)
                if not self.file_action_current(form) or generation != request:
                    return
                folder = path
                browser.set_entries(projection, path, rows, location=('Notes Library', path))
                location.text = path or 'Library root'
                up.enabled = bool(path)
                choose.enabled = projection.library_path(path) != posixpath.dirname(source)
                status.text = 'Links are not rewritten.'
            except (OSError, ValueError) as error:
                if self.file_action_current(form) and generation == request:
                    status.text = str(error)

        async def enter(row):
            await navigate(row['path'])
        async def retrace(location):
            await navigate(location[1])
        browser = self.host.folder_browser(open_folder=enter, navigate=retrace)
        async def parent(widget=None, **kwargs):
            await navigate(posixpath.dirname(folder))
        up.on_press = parent
        async def submit(widget=None, **kwargs):
            if not choose.enabled or not self.file_action_current(form):
                return
            choose.enabled = False
            target = posixpath.join(projection.library_path(folder), PurePosixPath(source).name)
            if await self.move_entry_to(source, target):
                self.return_from_file_action(view=form)
            elif self.file_action_current(form):
                status.text = self.notice.text
                choose.enabled = True
        choose.on_press = submit
        form = toga.Box(children=[toga.Label('Move ' + PurePosixPath(source).name), location, up,
            browser.scroll_container(), status, choose,
            toga.Button('Cancel', on_press=lambda widget: self.return_from_file_action(view=form), style=Pack(height=48))],
            style=Pack(direction=COLUMN, flex=1, margin=12))
        form._folder_browser = browser
        self.show_file_action(form, route='notes-move', title='Move', return_side=return_side)
        await navigate('')
        return form

    def copy_entry_form(self, path, *, return_side=None):
        from services.documents.mutations import copy_path
        default = posixpath.relpath(copy_path(path, directory=self.library.provider.entry(path)['directory']), self.root or '.')
        name = toga.TextInput(value=default, style=Pack(height=48))
        status = toga.Label('Copy beside the source, or choose another path. Existing files are kept.')
        button = toga.Button('Copy', style=Pack(height=48))
        async def submit(widget=None, **kw):
            if self.file_command_busy or not self.file_action_current(form):
                return
            self.file_command_busy = True
            button.enabled = False
            try:
                target = await asyncio.to_thread(library_files.copy, self.library, path,
                    None if name.value == default else posixpath.join(self.root, name.value),
                    cancelled=lambda: not self.valid())
                if self.valid():
                    await self.load_folder(posixpath.dirname(target))
                    self.refresh_library_indexes()
                    self.file_command_busy = False
                    self.return_from_file_action(view=form)
            except (OSError, ValueError) as error:
                status.text = str(error)[:180]
            finally:
                self.file_command_busy = False
                button.enabled = True
        button.on_press = submit
        form = toga.Box(children=[toga.Label('Copy ' + PurePosixPath(path).name), name, status, button,
            toga.Button('Cancel', on_press=lambda w: self.return_from_file_action(view=form), style=Pack(height=48))],
            style=Pack(direction=COLUMN, margin=16))
        self.show_file_action(form, route='notes-copy', title='Copy', return_side=return_side)

    async def delete_entry(self, path):
        if not self.valid() or self.file_command_busy:
            return
        epoch, request, destination = self.epoch, getattr(self, 'file_action_request', 0), self.host.destination()
        def current():
            return (self.valid() and not self.file_command_busy and self.epoch == epoch
                    and getattr(self, 'file_action_request', 0) == request and self.host.destination() == destination)
        change = PathChange(deleted=path)
        removed = change.removes
        if self.path and removed(self.path) and not await self.prepare_leave():
            return
        if not current():
            return
        if not await self.view.window.dialog(toga.ConfirmDialog('Delete ' + PurePosixPath(path).name + '?',
                'Permanently delete this item and its contents? Links are not rewritten.')) or not current():
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
            self.history, retained_index = change.history(self.history, self.history_index)
            self.search_rows = [row for row in self.search_rows if not removed(row['path'])]
            self.positions = change.positions(self.positions)
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
        self.search_mode.on_change = None
        for state in self._search_interfaces.values():
            state['control'].on_change = None
            state['control'].value = ''
            state['search_rows'].clear()
            state['search_status'] = ''
        self.clear_file_action()
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
