"""LM workspace presentation and navigation, backed by an owned conversation session."""
from commonUtils.ui.appearance.typography import point_size
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from commonUtils.ui import pyside as qt
from commonUtils.persistence import atomic_write_bytes, atomic_write_json
from ..domain import build_request, conversation, defaults, message, validate_settings
from ..storage import Store, export_markdown
from ..session import ConversationSession
from ..agent import AgentClient
from ..screenshots import encode_screenshot, MAX_IMAGES
from .image_view import ScreenshotView
from ..project_tools import ProjectTools, TOOLS
from .ide_context import registered_projects, editor_context
from .icons import chat_icon, action_button
from .layout import build_layout
from .composer import Composer
from .profiles import ProfilesDialog


class LMPage(qt.QWidget):
    idle = qt.Signal()

    # Existing hosts and callers can inspect these without duplicating state.
    @property
    def data(self):
        return self.session.data

    @data.setter
    def data(self, value):
        self.session.data = value

    @property
    def lease(self):
        return self.session.lease

    @property
    def dirty(self):
        return self.session.dirty

    @dirty.setter
    def dirty(self, value):
        self.session.dirty = value

    @property
    def active_message(self):
        return self.session.active_message

    def __init__(self, parent=None, *, store=None, client=None):
        super().__init__(parent)
        self.store = store or Store()
        self.client = client or AgentClient(self)
        self.projects = {}
        self.draft_images = []
        self.browser_mode = 'chat'
        self.last_conversations = {}
        self.mode_search = {}
        self.session = ConversationSession(self.store)
        session = self.session
        # Capture only the session, never the widget being destroyed.
        self.destroyed.connect(lambda: session.release_lease())
        self.session_tokens = {}
        self.profiles = []
        self.loading = False
        self.dirty = False
        self.discard_approved = False
        self.closing = False
        layout = build_layout(self)
        self.save_timer = qt.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(700)
        self.save_timer.timeout.connect(self.persist)
        self.checkpoint_timer = qt.QTimer(self)
        self.checkpoint_timer.setInterval(1000)
        self.checkpoint_timer.timeout.connect(self.checkpoint)
        self.render_timer = qt.QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(80)
        self.render_timer.timeout.connect(self.render)
        self.search_timer = qt.QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.list.currentItemChanged.connect(self.select)
        self.profile.currentIndexChanged.connect(self.profile_changed)
        self.token.textChanged.connect(self.token_changed)
        self.model.currentTextChanged.connect(self.changed)
        self.composer.textChanged.connect(self.draft_changed)
        self.composer.textChanged.connect(self.fit_composer)
        self.system.textChanged.connect(self.changed)
        for widget in (self.temperature, self.top_p, self.context, self.max_tokens):
            widget.valueChanged.connect(self.changed)
        self.client.delta.connect(self.append_delta)
        self.client.models.connect(self.models_loaded)
        self.client.completed.connect(self.completed)
        if hasattr(self.client, 'activity'):
            self.client.activity.connect(self.status.setText)
        from commonUtils.ui.appearance.styling import styling
        self.styling = styling(qt.QApplication.instance())
        self.styling.bind(self.transcript, 'reading')
        self.styling.bind(self.composer, 'reading')
        self.styling.changed.connect(self.render)
        self.create_menus(layout)
        self.apply_chrome()
        self.styling.changed.connect(self.apply_chrome)
        theme = getattr(qt.QApplication.instance(), '_commonutils_theme', None)
        if theme is not None:
            theme.changed.connect(self.apply_chrome)
        self.load_profiles()
        self.refresh()
        first = next((item for item in self.tree_items() if item.data(0, qt.Qt.ItemDataRole.UserRole)), None)
        if first is not None:
            self.list.setCurrentItem(first)
        self.update_controls()

    def create_menus(self, layout):
        self.menu_bar = qt.QMenuBar()
        self.menu_bar.setNativeMenuBar(False)
        layout.insertWidget(0, self.menu_bar)
        file = self.menu_bar.addMenu('File')
        self.idle_menu_actions = [file.addAction('New conversation', self.new_conversation),
                                  file.addAction('New folder…', self.new_folder)]
        file.addSeparator()
        for action in (self.rename_button, self.move_button, self.export_button, self.delete_button):
            file.addAction(action)
        edit = self.menu_bar.addMenu('Edit')
        self.draft_actions = []
        for label, callback in [('Undo draft', self.composer.undo), ('Redo draft', self.composer.redo),
                                ('Cut draft selection', self.composer.cut), ('Copy draft selection', self.composer.copy),
                                ('Paste into draft', self.composer.paste), ('Select draft', self.composer.selectAll)]:
            self.draft_actions.append(edit.addAction(label, callback))
        chat = self.menu_bar.addMenu('Conversation')
        chat.addAction(self.pin_action)
        chat.addAction(self.fork_action)
        view = self.menu_bar.addMenu('View')
        self.idle_menu_actions.append(view.addAction('Refresh conversations', self.refresh))
        view.addAction('Find conversations', self.search.setFocus)
        sidebar = view.addAction('Conversation sidebar')
        sidebar.setCheckable(True)
        sidebar.setChecked(True)
        sidebar.toggled.connect(self.sidebar.setVisible)
        generation = view.addAction('Generation settings')
        generation.setCheckable(True)
        generation.toggled.connect(self.settings_toggle.setChecked)
        self.settings_toggle.toggled.connect(generation.setChecked)
        server = self.menu_bar.addMenu('Server')
        self.idle_menu_actions.extend([server.addAction('Manage profiles…', self.edit_profiles),
                                      server.addAction('Test connection / Refresh models', self.refresh_models)])

    def conversation_menu(self, point):
        item = self.list.itemAt(point)
        if item is None or self.client.busy:
            return
        self.list.setCurrentItem(item)
        key = item.data(0, qt.Qt.ItemDataRole.UserRole)
        menu = qt.QMenu(self.list)
        if key:
            if self.data is None or self.data['id'] != key:
                return  # Opening may have been refused by a lease or save conflict.
            for action in (self.pin_action, self.fork_action, self.rename_button, self.move_button,
                           self.export_button, self.delete_button):
                menu.addAction(action)
        else:
            menu.addAction('New conversation here', self.new_conversation)
            menu.addAction('New folder…', self.new_folder)
        menu.exec(self.list.viewport().mapToGlobal(point))

    def toggle_pin(self):
        if self.client.busy or self.data is None or self.lease is None or not self.persist():
            return
        self.data['pinned'] = not self.data.get('pinned', False)
        self.dirty = True
        if self.persist():
            self.refresh(reveal_current=True)
        self.update_controls()

    def fork_conversation(self):
        if self.client.busy or self.data is None or self.lease is None or not self.persist():
            return
        from ..domain import now
        fork = deepcopy(self.data)
        fork.update(id=uuid4().hex, revision=0, title=(fork['title'] + ' (fork)')[:200],
                    pinned=False, created=now(), updated=now())
        for entry in fork['messages']:
            entry['id'] = uuid4().hex
        try:
            self.session.create(fork)
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.restore()
        self.search.clear()
        self.refresh(reveal_current=True)
        self.status.setText('Conversation forked. The original is unchanged.')

    def move_tree_item(self, source, destination):
        if self.client.busy or not self.persist():
            return
        key, folder = source
        try:
            if key:
                active = self.data is not None and self.data['id'] == key
                data = self.data if active else self.store.load(key)
                self.store.move(data, destination, lease=self.lease if active else None)
            else:
                moved_folder = self.store.move_folder(folder, destination, active=self.data, lease=self.lease)
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.refresh(reveal_current=True)
        if not key and moved_folder in self.folder_items:
            self.list.setCurrentItem(self.folder_items[moved_folder])
        self.status.setText('Moved to ' + (destination or '/') + '.')

    @staticmethod
    def button(title, callback, layout):
        button = qt.QPushButton(title)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def icon_button(self, title, callback, icon, layout):
        button = action_button(title, callback, icon)
        layout.addWidget(button)
        return button

    def apply_chrome(self):
        palette = qt.QApplication.palette()
        border = palette.color(qt.QPalette.ColorRole.Mid).name()
        base = palette.color(qt.QPalette.ColorRole.Base).name()
        accent = palette.color(qt.QPalette.ColorRole.Highlight).name()
        font = self.styling.font('reading')
        family = font.family().replace('\\', '\\\\').replace('"', '\\"')
        self.composer_frame.setStyleSheet(f'QFrame#lmComposerFrame {{ background: {base}; border: 1px solid {border}; border-radius: 12px; }}')
        muted = palette.color(qt.QPalette.ColorRole.PlaceholderText).name()
        self.disclaimer.setStyleSheet(f'color: {muted}; font-size: {point_size(max(6, self.styling.values["ui_font_size_int"] - .75))}pt;')
        self.composer.setStyleSheet(f'QPlainTextEdit {{ background: transparent; border: none; padding: 8px; font-family: "{family}"; font-size: {font.pointSizeF()}pt; }}')
        self.composer.document().setDefaultFont(font)
        self.send_button.setStyleSheet(f'QToolButton {{ border: 1px solid {border}; border-radius: 21px; background: {accent}; }} QToolButton:disabled {{ background: {base}; }}')
        self.transcript.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.search.setStyleSheet(f'QLineEdit {{ border: 1px solid {border}; border-radius: 8px; padding: 7px; }}')
        self.fit_composer()

    def fit_composer(self):
        lines = max(2, self.composer.document().blockCount())
        self.composer.setFixedHeight(min(150, lines * self.composer.fontMetrics().lineSpacing() + 20))

    def dragEnterEvent(self, event):
        if Composer.image_source(event.mimeData()) and (self.data is None or self.lease is not None):
            Composer.accept_image_drop(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        if Composer.image_source(event.mimeData()) and (self.data is None or self.lease is not None):
            self.composer.insertFromMimeData(event.mimeData())
            Composer.accept_image_drop(event)
        else:
            event.ignore()

    def paste_screenshot(self, image):
        if self.data is None:
            self.new_conversation()
        if self.data is None or self.lease is None:
            return
        try:
            if len(self.draft_images) >= MAX_IMAGES:
                raise ValueError('Attach at most four screenshots per message.')
            self.draft_images.append(encode_screenshot(image))
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.refresh_draft_images()
        self.changed()
        self.status.setText('Screenshot attached. Add a message or send it directly; image input requires a vision-capable model.')

    def remove_screenshot(self, key):
        self.draft_images = [image for image in self.draft_images if image['id'] != key]
        self.refresh_draft_images()
        self.changed()

    def refresh_draft_images(self):
        while self.image_draft_layout.count():
            item = self.image_draft_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for image in self.draft_images:
            card = qt.QWidget()
            layout = qt.QVBoxLayout(card)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(ScreenshotView(image, card, preview=True))
            remove = qt.QPushButton('Remove')
            remove.setAccessibleName('Remove screenshot')
            remove.clicked.connect(lambda checked=False, key=image['id']: self.remove_screenshot(key))
            layout.addWidget(remove)
            self.image_draft_layout.addWidget(card)
        self.image_draft_layout.addStretch()
        self.image_drafts.setVisible(bool(self.draft_images))

    def load_projects(self):
        key = (self.data.get('project_id', '') if self.loading and self.data
               else self.project_picker.currentData())
        try:
            self.projects = registered_projects(self)
        except (ValueError, OSError) as error:
            self.status.setText(str(error))
            self.projects = {}
        self.project_picker.blockSignals(True)
        self.project_picker.clear()
        self.project_picker.addItem('Select IDE project…', '')
        for project in sorted(self.projects.values(), key=lambda p: p.name.casefold()):
            self.project_picker.addItem(project.name, project.id)
            self.project_picker.setItemData(self.project_picker.count() - 1, str(project.root), qt.Qt.ItemDataRole.ToolTipRole)
        if key:
            if key not in self.projects:
                self.project_picker.addItem('Unavailable project — select another', key)
            self.project_picker.setCurrentIndex(self.project_picker.findData(key))
        self.project_picker.blockSignals(False)

    def mode_changed(self):
        if self.loading:
            return
        target = self.mode.currentData()
        previous = self.browser_mode
        if self.client.busy or not self.persist():
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(self.mode.findData(previous))
            self.mode.blockSignals(False)
            return
        if self.data:
            self.last_conversations[previous] = self.data['id']
        self.mode_search[previous] = self.search.text()
        self.release_lease()
        self.data = None
        self.dirty = False
        self.browser_mode = target
        self.loading = True
        self.composer.clear()
        self.draft_images = []
        self.refresh_draft_images()
        self.transcript.clear()
        self.search.setText(self.mode_search.get(target, ''))
        self.loading = False
        self.list.blockSignals(True)
        self.list.clear()
        self.folder_items = {}
        self.list.blockSignals(False)
        if target == 'code':
            self.load_projects()
        self.refresh()
        keys = [item.data(0, qt.Qt.ItemDataRole.UserRole) for item in self.tree_items()
                if item.data(0, qt.Qt.ItemDataRole.UserRole)]
        remembered = self.last_conversations.get(target)
        if remembered:
            try:
                record = self.store.load(remembered)
                if record.get('mode', 'chat') != target:
                    remembered = None
            except (OSError, ValueError):
                remembered = None
        key = remembered or (keys[0] if keys else None)
        if key:
            self.open_conversation(key)
            self.refresh(reveal_current=True)
        elif not self.search.text():
            self.new_conversation()
        self.update_controls()

    def project_changed(self):
        self.changed()
        project = self.projects.get(self.project_picker.currentData())
        if project:
            self.status.setText(f'Code mode: {project.name}. Project text may be sent to the selected server. Read-only access follows IDE exclusions.')

    def attachment_context(self):
        if self.client.busy or self.mode.currentData() != 'code':
            raise ValueError('Select Code mode to attach project context.')
        project = registered_projects(self).get(self.project_picker.currentData())
        if project is None:
            raise ValueError('Choose a registered IDE project first.')
        buffers, selections = editor_context(self, project)
        return ProjectTools(project, buffers), selections

    def append_attachment(self, text):
        draft = self.composer.toPlainText()
        if len((draft + text).encode('utf-8')) > 65536:
            raise ValueError('Attached context and draft are limited to 64 KiB. Attach a smaller selection or let the model read relevant lines.')
        self.composer.setPlainText(draft + ('\n\n' if draft else '') + text)
        self.composer.moveCursor(qt.QTextCursor.MoveOperation.End)

    def attach_files(self):
        try:
            tools, _ = self.attachment_context()
            paths, _ = qt.QFileDialog.getOpenFileNames(self, 'Attach project text files', str(tools.root))
            attachments = []
            for path in paths:
                supplied = Path(path).absolute()
                # Accept OS aliases for the project root (e.g. /var on macOS),
                # preserving every component below it for link/exclusion checks.
                anchor = next((parent for parent in reversed(supplied.parents)
                               if parent.resolve() == tools.root), None)
                if anchor is None:
                    raise ValueError('Attachments must stay inside the selected project.')
                relative = supplied.relative_to(anchor).as_posix()
                text, source = tools.text(relative)
                attachments.append(f'Project file: {relative} ({source})\n```\n{text}\n```')
            if attachments:
                self.append_attachment('\n\n'.join(attachments))
        except (ValueError, OSError, UnicodeError) as error:
            self.status.setText(str(error))

    def attach_selection(self):
        try:
            tools, selections = self.attachment_context()
            selections = [entry for entry in selections if self.selection_allowed(tools, entry[0])]
            if not selections:
                raise ValueError('Select code in an open editor in this IDE project first.')
            if len(selections) == 1:
                selected = selections[0]
            else:
                labels = [f'{path}:{line}' for path, line, _ in selections]
                label, accepted = qt.QInputDialog.getItem(self, 'Attach IDE selection', 'Selection', labels, 0, False)
                if not accepted:
                    return
                selected = selections[labels.index(label)]
            path, line, text = selected
            self.append_attachment(f'IDE selection: {path}, starting at line {line}\n```\n{text}\n```')
        except (ValueError, OSError) as error:
            self.status.setText(str(error))

    @staticmethod
    def selection_allowed(tools, path):
        try:
            tools.path(path)
            return True
        except (ValueError, OSError):
            return False

    def send_or_stop(self):
        if self.client.busy:
            self.client.cancel()
        else:
            self.send()

    def load_profiles(self):
        try:
            self.profiles = self.store.profiles()
        except (OSError, ValueError, UnicodeError) as error:
            self.profiles = []
            self.status.setText(f'Could not read server profiles: {error}')
        selected = self.data['profile_id'] if self.data else self.profile.currentData()
        self.loading = True
        self.profile.clear()
        for profile in self.profiles:
            self.profile.addItem(profile['name'], profile['id'])
        index = self.profile.findData(selected)
        self.profile.setCurrentIndex(index if selected else (0 if self.profiles else -1))
        self.token.setText(self.session_tokens.get(self.profile.currentData(), ''))
        self.loading = False

    def current_profile(self):
        return next((p for p in self.profiles if p['id'] == self.profile.currentData()), None)

    def profile_changed(self):
        if self.loading:
            return
        self.token.setText(self.session_tokens.get(self.profile.currentData(), ''))
        self.model.clear()
        self.changed()

    def token_changed(self, text):
        if not self.loading and self.profile.currentData():
            self.session_tokens[self.profile.currentData()] = text

    def refresh(self, *, reveal_current=False):
        if self.client.busy:
            return
        if self.data is not None and self.lease is None:
            # A different application page can veto closing after we retired.
            # Explicit Refresh reopens from disk and reacquires ownership.
            key = self.data['id']
            self.data = None
            self.dirty = False
            self.closing = False
            self.open_conversation(key)
        current = self.data['id'] if self.data else None
        selected = self.list.currentItem()
        selected_folder = (selected.data(0, qt.Qt.ItemDataRole.UserRole + 1)
                           if selected is not None and not selected.data(0, qt.Qt.ItemDataRole.UserRole) else None)
        expanded = {path: item.isExpanded() for path, item in getattr(self, 'folder_items', {}).items()}
        try:
            records, warnings = self.store.list(self.search.text())
            records = [record for record in records if record.get('mode', 'chat') == self.mode.currentData()]
            folders = self.store.folders()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.list.blockSignals(True)
        self.list.clear()
        root = qt.QTreeWidgetItem(self.list, ['Conversations'])
        root.setData(0, qt.Qt.ItemDataRole.UserRole + 1, '')
        self.folder_items = {'': root}
        visible_folders = set(folders) if not self.search.text() else set()
        for data in records:
            path = data['folder']
            while path:
                visible_folders.add(path)
                path = path.rpartition('/')[0]
        for path in sorted(visible_folders, key=lambda name: (name.count('/'), name.casefold())):
            parent, _, label = path.rpartition('/')
            item = qt.QTreeWidgetItem(self.folder_items[parent], [label])
            item.setData(0, qt.Qt.ItemDataRole.UserRole + 1, path)
            item.setIcon(0, self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon))
            self.folder_items[path] = item
        for data in records:
            item = qt.QTreeWidgetItem(self.folder_items[data['folder']], [('★ ' if data.get('pinned') else '') + data['title']])
            item.setData(0, qt.Qt.ItemDataRole.UserRole, data['id'])
            item.setData(0, qt.Qt.ItemDataRole.UserRole + 1, data['folder'])
            if data['id'] == current:
                self.list.setCurrentItem(item)
        if selected_folder in self.folder_items and not reveal_current:
            self.list.setCurrentItem(self.folder_items[selected_folder])
        for path, item in self.folder_items.items():
            item.setExpanded(True if self.search.text() else expanded.get(path, True))
        if reveal_current and self.list.currentItem() is not None:
            parent = self.list.currentItem().parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
        self.list.blockSignals(False)
        self.update_controls()
        if warnings:
            self.status.setText('Some conversation files could not be read and were preserved. ' + '\n'.join(warnings[:3]))

    def select(self, item, previous=None):
        if item is None or self.client.busy:
            return
        key = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if not key:
            self.update_controls()
            return
        if self.data and self.data['id'] == key:
            self.update_controls()
            return
        self.open_conversation(key)

    def tree_items(self):
        iterator = qt.QTreeWidgetItemIterator(self.list)
        while iterator.value() is not None:
            yield iterator.value()
            iterator += 1

    def selected_folder(self):
        item = self.list.currentItem()
        return item.data(0, qt.Qt.ItemDataRole.UserRole + 1) if item is not None else ''

    def new_folder(self):
        if self.client.busy:
            return
        parent = self.selected_folder()
        name, accepted = qt.QInputDialog.getText(self, 'New conversation folder',
            'Folder name (use / for multiple nested levels)')
        if not accepted or not name:
            return
        path = '/'.join(part for part in (parent, name) if part)
        try:
            self.store.create_folder(path)
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.search.clear()
        self.refresh()
        self.list.setCurrentItem(self.folder_items[path])
        self.status.setText(f'Folder created: {path}. New conversations will be saved here.')

    def move_conversation(self):
        if self.client.busy or not self.data or not self.persist():
            return
        try:
            choices = ['/', *self.store.folders()]
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        current = self.data.get('folder') or '/'
        destination, accepted = qt.QInputDialog.getItem(self, 'Move conversation',
            'Destination folder (/ for root; use / for nested levels)', choices,
            choices.index(current) if current in choices else 0, True)
        if not accepted:
            return
        try:
            self.store.move(self.data, '' if destination == '/' else destination, lease=self.lease)
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.refresh(reveal_current=True)
        self.update_controls()
        self.status.setText(f'Conversation moved to {destination or "/"}.')

    def open_conversation(self, key):
        if not self.persist():
            self.refresh()
            return
        previous_mode = self.browser_mode
        try:
            interrupted = self.session.open(key)
        except (OSError, ValueError, UnicodeError) as error:
            self.status.setText(str(error))
            self.refresh()
            return
        self.restore()
        self.dirty = interrupted
        if interrupted:
            self.status.setText('An interrupted response was recovered. Retry to generate a new answer; partial text is retained.')
            self.persist()
        else:
            self.status.setText('Conversation opened.')
        if previous_mode != self.browser_mode:
            self.refresh(reveal_current=True)
        self.update_controls()

    def release_lease(self):
        self.session.release_lease()

    def restore(self):
        self.loading = True
        data = self.data
        self.profile.setCurrentIndex(self.profile.findData(data['profile_id']))
        self.token.setText(self.session_tokens.get(data['profile_id'], ''))
        self.model.setCurrentText(data['model'])
        self.mode.setCurrentIndex(self.mode.findData(data.get('mode', 'chat')))
        self.browser_mode = data.get('mode', 'chat')
        self.last_conversations[self.browser_mode] = data['id']
        if data.get('mode') == 'code':
            self.load_projects()
        self.project_picker.setCurrentIndex(self.project_picker.findData(data.get('project_id', '')))
        self.composer.setPlainText(data['draft'])
        self.draft_images = deepcopy(data.get('draft_images', []))
        self.refresh_draft_images()
        settings = data['settings']
        self.temperature.setValue(settings['temperature'] if settings['temperature'] is not None else -1)
        self.top_p.setValue(settings['top_p'] if settings['top_p'] is not None else -1)
        self.context.setValue(settings['context_tokens'])
        self.max_tokens.setValue(settings['max_tokens'])
        self.system.setPlainText(settings['system_prompt'])
        self.loading = False
        self.dirty = False
        self.discard_approved = False
        self.save_error.clear()
        self.save_error.hide()
        self.transcript.clear()
        self.render()

    def collect(self):
        if self.data is None:
            return
        self.data['draft'] = self.composer.toPlainText()
        self.data['draft_images'] = deepcopy(self.draft_images)
        self.data['project_id'] = self.project_picker.currentData() or ''
        self.data['model'] = self.model.currentText().strip()
        self.data['profile_id'] = self.profile.currentData() or ''
        self.data['settings'] = validate_settings(dict(
            temperature=None if self.temperature.value() < 0 else self.temperature.value(),
            top_p=None if self.top_p.value() < 0 else self.top_p.value(),
            context_tokens=self.context.value(), max_tokens=self.max_tokens.value(),
            system_prompt=self.system.toPlainText()))

    def changed(self, *args):
        if self.loading or self.data is None:
            return
        self.dirty = True
        self.discard_approved = False
        self.save_timer.start()

    def draft_changed(self):
        # Font/palette updates can emit textChanged without changing draft text.
        if self.data is not None and self.composer.toPlainText() != self.data['draft']:
            self.changed()

    def show_save_error(self, error):
        self.save_error.setText(f'Conversation not saved: {error} Use Export to keep your current copy.')
        self.save_error.show()

    def persist(self):
        self.save_timer.stop()
        if self.data is None or not self.dirty:
            return True
        try:
            self.collect()
            self.session.save()
        except (OSError, ValueError, UnicodeError) as error:
            self.show_save_error(error)
            return False
        self.reflect_saved_state()
        return True

    def reflect_saved_state(self):
        """Refresh publication feedback without recollecting or resaving the draft."""
        self.save_error.clear()
        self.save_error.hide()
        for item in self.tree_items():
            if item.data(0, qt.Qt.ItemDataRole.UserRole) == self.data['id']:
                item.setText(0, ('★ ' if self.data.get('pinned') else '') + self.data['title'])

    def new_conversation(self):
        if self.client.busy or not self.persist():
            return
        data = conversation(defaults(), self.profile.currentData() or '', self.model.currentText())
        data['folder'] = self.selected_folder()
        data['mode'] = self.mode.currentData()
        data['project_id'] = self.project_picker.currentData() or ''
        try:
            self.session.create(data)
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.restore()
        self.search.clear()
        self.refresh(reveal_current=True)
        self.update_controls()
        self.composer.setFocus()

    def edit_profiles(self):
        if self.client.busy or not self.persist():
            return
        try:
            dialog = ProfilesDialog(self.store, self)
        except (OSError, ValueError, UnicodeError) as error:
            self.status.setText(str(error))
            return
        if dialog.exec() == qt.QDialog.DialogCode.Accepted:
            self.load_profiles()
            self.changed()
            self.update_controls()

    def refresh_models(self):
        profile = self.current_profile()
        if self.client.busy or profile is None:
            self.status.setText('Choose a server profile first.')
            return
        try:
            self.client.start(profile, self.token.text())
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.status.setText('Connecting and loading models…')
        self.update_controls()

    def models_loaded(self, models):
        current = self.model.currentText()
        self.loading = True
        self.model.clear()
        self.model.addItems(models)
        self.model.setCurrentText(current or (models[0] if models else ''))
        self.loading = False
        self.changed()
        self.status.setText(f'Connected. {len(models)} models available.' if models else 'Connected, but no models were listed. Load a model on the server or enter its ID.')

    def send(self):
        if self.client.busy:
            return
        if self.data is None:
            self.new_conversation()
        if self.data is None or (not self.composer.toPlainText().strip() and not self.draft_images):
            return
        if not self.persist():
            return
        self.collect()
        snapshot = deepcopy(self.data)
        text = self.composer.toPlainText()
        self.data['messages'].append(message('user', text, images=deepcopy(self.draft_images)))
        if self.data['title'] == 'New conversation':
            self.data['title'] = next((line.strip() for line in text.splitlines() if line.strip()), 'Screenshot')[:80]
        if not self.begin_generation():
            self.data = snapshot
            self.render()

    def retry(self):
        if self.client.busy or not self.data or not self.data['messages'] or not self.persist():
            return
        # Existing assistant alternatives are retained; request builder chooses the latest completed alternative for earlier turns.
        self.begin_generation(clear_draft=False)

    def begin_generation(self, *, clear_draft=True):
        profile = self.current_profile()
        if profile is None:
            self.status.setText('Choose a server profile first.')
            return False
        try:
            self.collect()
            project_tools = None
            if self.data.get('mode') == 'code':
                key = self.project_picker.currentData()
                self.projects = registered_projects(self)
                project = self.projects.get(key)
                if project is None:
                    raise ValueError('Choose a registered IDE project. Register one in IDE, then refresh projects.')
                buffers, _ = editor_context(self, project)
                project_tools = ProjectTools(project, buffers)
            payload, metadata = build_request(self.data, tools=TOOLS if project_tools else None,
                                             project_name=project_tools.name if project_tools else None)
            if project_tools:
                metadata['project_id'] = project.id
                metadata['project_name'] = project.name
                metadata['project_root'] = str(project.root)
        except ValueError as error:
            self.status.setText(str(error))
            return False
        metadata['base_url'] = profile['base_url']
        self.save_timer.stop()
        try:
            self.session.begin_response(metadata, clear_draft=clear_draft)
        except (OSError, ValueError, UnicodeError) as error:
            self.show_save_error(error)
            return False
        self.reflect_saved_state()
        if clear_draft:
            self.draft_images = []
            self.refresh_draft_images()
            self.loading = True
            self.composer.clear()
            self.loading = False
        try:
            if project_tools:
                self.client.start(profile, self.token.text(), payload, project_tools=project_tools,
                                  context_tokens=self.data['settings']['context_tokens'])
            else:
                self.client.start(profile, self.token.text(), payload)
        except (ValueError, OSError) as error:
            self.session.complete_response('failed', str(error), {})
            self.persist()
            self.status.setText(str(error))
            self.render()
            return True  # The saved user turn remains retryable.
        self.status.setText(f'Generating… Approximately {metadata["estimated_input_tokens"]} input tokens; {metadata["omitted_turns"]} earlier turns omitted.')
        self.checkpoint_timer.start()
        self.render()
        self.update_controls()
        return True

    def append_delta(self, text):
        if not self.session.append_delta(text):
            return
        if not self.render_timer.isActive():
            self.render_timer.start()

    def checkpoint(self):
        if not self.persist():
            self.client.cancel()
            self.status.setText('Generation stopped because the conversation could not be saved. Partial output remains available for export.')

    def completed(self, status, error, metadata):
        self.checkpoint_timer.stop()
        if self.session.complete_response(status, error, metadata):
            saved = self.persist() if not self.discard_approved else False
            self.render()
            if error:
                self.status.setText(error)
            elif saved:
                self.status.setText('Response saved.' if status == 'complete' else 'Stopped. Partial response saved and excluded from future context.')
            if metadata.get('finish_reason') == 'length':
                self.status.setText('Response reached the output limit. Increase maximum response tokens and regenerate if needed.')
        elif error:
            self.status.setText(error)
        elif status == 'cancelled':
            self.status.setText('Connection check stopped.')
        self.update_controls()
        self.idle.emit()

    def render(self):
        self.render_timer.stop()
        bar = self.transcript.verticalScrollBar()
        current = self.data['id'] if self.data else None
        bottom = self.transcript.key != current or bar.value() >= bar.maximum() - 12
        old = bar.value()
        self.transcript.sync(self.data)
        self.transcript.body.layout().activate()
        bar.setValue(bar.maximum() if bottom else old)

    def update_controls(self):
        busy = self.client.busy
        editable = self.data is not None and self.lease is not None
        for widget in (self.list, self.new_button, self.refresh_button, self.search, self.folder_button):
            widget.setEnabled(not busy)
        self.connection_box.setEnabled(not busy)
        self.mode.setEnabled(not busy)
        self.project_box.setVisible(self.mode.currentData() == 'code')
        self.project_box.setEnabled(editable and not busy)
        code = self.mode.currentData() == 'code'
        for widget in (self.project_picker, self.project_refresh, self.attach_button, self.selection_button):
            widget.setVisible(code)
        self.settings_box.setEnabled(editable and not busy)
        self.composer.setEnabled(editable)
        self.composer.setPlaceholderText('Draft your next message… Send after the current request finishes · Shift+Enter for a new line'
            if busy else 'Message…  Enter to send · Shift+Enter for a new line')
        self.send_button.setEnabled(busy or editable)
        action = 'Stop generation / connection check' if busy else 'Send message'
        self.send_button.setIcon(chat_icon('stop' if busy else 'send'))
        self.send_button.setToolTip(action)
        self.send_button.setAccessibleName(action)
        self.transcript.set_retry_enabled(editable and not busy)
        self.auth_toggle.setEnabled(not busy)
        selected = self.list.currentItem()
        selected_conversation = (selected is not None and self.data is not None and
            selected.data(0, qt.Qt.ItemDataRole.UserRole) == self.data['id'])
        for widget in (self.rename_button, self.delete_button):
            widget.setEnabled(editable and not busy and selected_conversation)
        self.move_button.setEnabled(editable and not busy)
        self.move_button.setToolTip('Move the open conversation to another folder')
        self.export_button.setEnabled(self.data is not None)
        self.pin_action.setEnabled(editable and not busy)
        self.pin_action.setText('Unpin conversation' if self.data and self.data.get('pinned') else 'Pin conversation')
        self.fork_action.setEnabled(editable and not busy)
        for action in getattr(self, 'draft_actions', ()):
            action.setEnabled(editable)
        for action in getattr(self, 'idle_menu_actions', ()):
            action.setEnabled(not busy)


    def rename(self):
        if self.client.busy or not self.data:
            return
        title, accepted = qt.QInputDialog.getText(self, 'Rename conversation', 'Title', text=self.data['title'])
        if accepted and title.strip():
            self.data['title'] = title.strip()[:200]
            self.dirty = True
            self.persist()

    def delete(self):
        if self.client.busy or not self.data or not self.persist():
            return
        if qt.QMessageBox.question(self, 'Delete conversation', 'Permanently delete this saved conversation?',
                                  qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                                  qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete(self.data)
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.release_lease()
        self.data = None
        self.draft_images = []
        self.refresh_draft_images()
        self.loading = True
        self.composer.clear()
        self.loading = False
        self.refresh()
        self.render()
        self.update_controls()

    def export(self):
        if not self.data:
            return
        # Export is also available after save/conflict failures, without overwriting the source.
        self.data['draft'] = self.composer.toPlainText()
        self.data['draft_images'] = deepcopy(self.draft_images)
        path, chosen = qt.QFileDialog.getSaveFileName(self, 'Export conversation', self.data['id'] + '.md',
                                                     'Markdown (*.md);;JSON (*.json)')
        if not path:
            return
        try:
            if Path(path).resolve().is_relative_to(self.store.root.resolve()):
                raise ValueError('Choose an export destination outside the LM storage folder.')
            if 'JSON' in chosen:
                atomic_write_json(path, self.data)
            else:
                atomic_write_bytes(path, export_markdown(self.data).encode('utf-8'))
        except (OSError, ValueError) as error:
            self.status.setText(f'Export failed: {error}')
            return
        self.status.setText(f'Conversation exported to {path}')

    def can_close(self):
        if self.discard_approved or self.persist():
            return True
        answer = qt.QMessageBox.question(self, 'Conversation could not be saved',
            'The current conversation has unsaved changes. Cancel to export or retry saving, or discard them and close.',
            qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel,
            qt.QMessageBox.StandardButton.Cancel)
        self.discard_approved = answer == qt.QMessageBox.StandardButton.Discard
        return self.discard_approved

    def prepare_close(self):
        self.closing = True
        self.save_timer.stop()
        if self.client.busy:
            self.client.cancel()
        if self.client.busy:
            return False
        if not self.discard_approved and not self.persist():
            return False
        self.release_lease()
        self.update_controls()
        return True
