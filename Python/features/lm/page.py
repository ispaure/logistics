"""Retained LM workspace: one editable conversation, explicit network actions."""
from commonUtils.ui.appearance.typography import point_size
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from commonUtils.ui import pyside as qt
from commonUtils.persistence import atomic_write_bytes, atomic_write_json
from .domain import build_request, conversation, defaults, message, validate_settings
from .storage import Store, export_markdown
from .transport import Client
from .icons import chat_icon, action_button
from .conversation_view import ConversationView
from .conversation_tree import ConversationTree
from commonUtils.ui.appearance.status_line import StatusLine


class SamplingSpin(qt.QDoubleSpinBox):
    """Treat server default as a choice adjacent to zero, not a negative range."""
    def stepBy(self, steps):
        if self.value() < 0 and steps > 0:
            self.setValue(0)
        elif self.value() == 0 and steps < 0:
            self.setValue(-1)
        else:
            self.setValue(max(0, self.value() + steps * self.singleStep()) if self.value() >= 0 else -1)

    def valueFromText(self, text):
        value = super().valueFromText(text)
        return -1 if value < 0 else value


class Composer(qt.QPlainTextEdit):
    send_requested = qt.Signal()

    def keyPressEvent(self, event):
        if event.key() in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter):
            # Let an input method finish composing before treating Return as Send.
            if event.modifiers() == qt.Qt.KeyboardModifier.NoModifier and not self.composing:
                event.accept()
                self.send_requested.emit()
                return
        super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        self.composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    composing = False


class ProfilesDialog(qt.QDialog):
    def __init__(self, store, parent):
        super().__init__(parent)
        self.store = store
        self.expected = store.profiles()
        self.profiles = deepcopy(self.expected)
        self.setWindowTitle('LM server profiles')
        self.resize(650, 340)
        layout = qt.QVBoxLayout(self)
        note = qt.QLabel('Enter the OpenAI-compatible API base URL, e.g. http://localhost:1234/v1. Tokens are entered on the chat page and kept only for this session.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = qt.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Name', 'API base URL'])
        self.table.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(qt.QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)
        for entry in self.profiles:
            self.add_row(entry)
        row = qt.QHBoxLayout()
        add = qt.QPushButton('Add server')
        add.clicked.connect(lambda: self.add_row(dict(id=uuid4().hex, name='New server', base_url='http://localhost:1234/v1')))
        remove = qt.QPushButton('Remove')
        remove.clicked.connect(self.remove_row)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        self.error = qt.QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Save | qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_row(self, entry):
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = qt.QTableWidgetItem(entry['name'])
        name.setData(qt.Qt.ItemDataRole.UserRole, entry['id'])
        self.table.setItem(row, 0, name)
        self.table.setItem(row, 1, qt.QTableWidgetItem(entry['base_url']))

    def remove_row(self):
        if self.table.currentRow() >= 0:
            self.table.removeRow(self.table.currentRow())

    def save(self):
        profiles = [dict(id=self.table.item(i, 0).data(qt.Qt.ItemDataRole.UserRole),
                         name=self.table.item(i, 0).text(), base_url=self.table.item(i, 1).text())
                    for i in range(self.table.rowCount())]
        try:
            self.store.save_profiles(profiles, self.expected)
        except (OSError, ValueError) as error:
            self.error.setText(str(error))
            return
        self.accept()


class LMPage(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent=None, *, store=None, client=None):
        super().__init__(parent)
        self.store = store or Store()
        self.client = client or Client(self)
        self.data = None
        self.lease = None
        self._lease_holder = [None]
        holder = self._lease_holder
        self.destroyed.connect(lambda: holder[0].unlock() if holder[0] is not None else None)
        self.active_message = None
        self.session_tokens = {}
        self.profiles = []
        self.loading = False
        self.dirty = False
        self.discard_approved = False
        self.closing = False
        self.setProperty('navigation_position', 'workspace')
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        splitter = qt.QSplitter()
        layout.addWidget(splitter, 1)
        left = self.sidebar = qt.QWidget()
        side = qt.QVBoxLayout(left)
        side.setContentsMargins(8, 8, 8, 8)
        side.setSpacing(10)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Search conversations…')
        side.addWidget(self.search)
        self.list = ConversationTree()
        self.list.move_requested.connect(self.move_tree_item)
        self.list.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.conversation_menu)
        self.list.setHeaderHidden(True)
        self.list.setAccessibleName('Conversation folders and conversations')
        self.list.setIndentation(16)
        side.addWidget(self.list, 1)
        row = qt.QHBoxLayout()
        self.new_button = self.icon_button('New conversation', self.new_conversation, 'new', row)
        self.folder_button = self.icon_button('New folder…', self.new_folder, 'folder', row)
        self.refresh_button = self.icon_button('Refresh conversations', self.refresh, 'refresh', row)
        row.addStretch()
        self.more_button = qt.QToolButton()
        self.more_button.setIcon(chat_icon('more'))
        self.more_button.setIconSize(qt.QSize(20, 20))
        self.more_button.setAutoRaise(True)
        self.more_button.setToolTip('Conversation actions')
        self.more_button.setAccessibleName('Conversation actions')
        self.more_button.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = qt.QMenu(self.more_button)
        self.rename_button = menu.addAction('Rename conversation…', self.rename)
        self.move_button = menu.addAction('Move conversation…', self.move_conversation)
        self.export_button = menu.addAction('Export conversation…', self.export)
        self.pin_action = menu.addAction('Pin conversation', self.toggle_pin)
        self.fork_action = menu.addAction('Fork conversation', self.fork_conversation)
        menu.addSeparator()
        self.delete_button = menu.addAction('Delete conversation…', self.delete)
        self.more_button.setMenu(menu)
        row.addWidget(self.more_button)
        side.insertLayout(0, row)
        self.list.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.list.setUniformRowHeights(True)
        splitter.addWidget(left)
        right = qt.QWidget()
        body = qt.QVBoxLayout(right)
        body.setContentsMargins(8, 4, 4, 4)
        body.setSpacing(6)
        self.connection_box = qt.QWidget()
        connection = qt.QFormLayout(self.connection_box)
        connection.setContentsMargins(0, 0, 0, 0)
        row = qt.QHBoxLayout()
        self.profile = qt.QComboBox()
        self.profile.setMinimumContentsLength(12)
        self.profile.setSizeAdjustPolicy(qt.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        row.addWidget(self.profile, 1)
        self.profiles_button = self.icon_button('Manage server profiles', self.edit_profiles, 'settings', row)
        connection.addRow('Server', row)
        self.token = qt.QLineEdit()
        self.token.setEchoMode(qt.QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText('Optional API token — session only')
        connection.addRow('Token', self.token)
        connection.setRowVisible(self.token, False)
        row = qt.QHBoxLayout()
        self.model = qt.QComboBox()
        self.model.setMinimumContentsLength(12)
        self.model.setSizeAdjustPolicy(qt.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.model.setEditable(True)
        self.model.setInsertPolicy(qt.QComboBox.InsertPolicy.NoInsert)
        self.model.setToolTip('Refresh models or type the exact model ID from your server.')
        row.addWidget(self.model, 1)
        self.test_button = self.icon_button('Test connection / Refresh models', self.refresh_models, 'refresh', row)
        connection.addRow('Model', row)
        body.addWidget(self.connection_box)
        options = qt.QHBoxLayout()
        self.settings_toggle = qt.QToolButton()
        self.settings_toggle.setText('Generation settings')
        self.settings_toggle.setCheckable(True)
        self.settings_toggle.setAutoRaise(True)
        self.settings_toggle.setArrowType(qt.Qt.ArrowType.RightArrow)
        self.settings_toggle.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        options.addWidget(self.settings_toggle)
        self.auth_toggle = qt.QToolButton()
        self.auth_toggle.setText('Session token')
        self.auth_toggle.setCheckable(True)
        self.auth_toggle.setAutoRaise(True)
        self.auth_toggle.toggled.connect(lambda shown: connection.setRowVisible(self.token, shown))
        options.addStretch()
        options.addWidget(self.auth_toggle)
        body.addLayout(options)
        self.settings_box = qt.QWidget()
        settings = qt.QFormLayout(self.settings_box)
        self.temperature = SamplingSpin()
        self.temperature.setRange(-1, 2)
        self.temperature.setSingleStep(.1)
        self.temperature.setSpecialValueText('Server default')
        settings.addRow('Temperature', self.temperature)
        self.top_p = SamplingSpin()
        self.top_p.setRange(-1, 1)
        self.top_p.setSingleStep(.05)
        self.top_p.setSpecialValueText('Server default')
        settings.addRow('Top-p', self.top_p)
        self.context = qt.QSpinBox()
        self.context.setRange(256, 2_000_000)
        settings.addRow('Model context size (tokens)', self.context)
        self.max_tokens = qt.QSpinBox()
        self.max_tokens.setRange(1, 131072)
        settings.addRow('Maximum response tokens', self.max_tokens)
        self.system = qt.QPlainTextEdit()
        self.system.setPlaceholderText('System instructions')
        self.system.setMaximumHeight(90)
        settings.addRow('System instructions', self.system)
        note = qt.QLabel('Context uses an approximate UTF-8 token estimate. Set the context size to match your server model. Older turns may be omitted; saved history stays intact.')
        note.setWordWrap(True)
        settings.addRow(note)
        body.addWidget(self.settings_box)
        self.settings_box.hide()
        self.settings_toggle.toggled.connect(self.settings_box.setVisible)
        self.settings_toggle.toggled.connect(lambda shown: self.settings_toggle.setArrowType(
            qt.Qt.ArrowType.DownArrow if shown else qt.Qt.ArrowType.RightArrow))
        self.transcript = ConversationView()
        self.transcript.setAccessibleName('Conversation transcript')
        self.transcript.retry_requested.connect(self.retry)
        body.addWidget(self.transcript, 1)
        self.disclaimer = qt.QLabel('Language Models can make mistakes. Check important info.')
        self.disclaimer.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.disclaimer.setWordWrap(True)
        self.disclaimer.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        body.addWidget(self.disclaimer)
        self.composer_frame = qt.QFrame()
        self.composer_frame.setObjectName('lmComposerFrame')
        row = qt.QHBoxLayout(self.composer_frame)
        row.setContentsMargins(4, 2, 6, 2)
        row.setSpacing(6)
        self.composer = Composer()
        self.composer.setPlaceholderText('Message…  Enter to send · Shift+Enter for a new line')
        self.composer.send_requested.connect(self.send)
        self.composer.setFixedHeight(72)
        self.composer.setAccessibleName('Message draft')
        row.addWidget(self.composer, 1)
        self.send_button = qt.QToolButton()
        self.send_button.setFixedSize(42, 42)
        self.send_button.setIconSize(qt.QSize(24, 24))
        self.send_button.setObjectName('lmSendStop')
        self.send_button.clicked.connect(self.send_or_stop)
        row.addWidget(self.send_button, 0, qt.Qt.AlignmentFlag.AlignVCenter)
        body.addWidget(self.composer_frame)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([245, 850])
        splitter.setHandleWidth(1)
        self.status = StatusLine('Ready.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setContentsMargins(0, 0, 0, 0)
        self.status_bar = qt.QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        content = qt.QWidget(self.status_bar)
        footer = qt.QHBoxLayout(content)
        footer.setContentsMargins(10, 8, 10, 8)
        footer.setSpacing(8)
        footer.addWidget(self.status, 1)
        self.status_bar.addWidget(content, 1)
        self.status_bar.setStyleSheet('QStatusBar::item { border: none; }')
        layout.addWidget(self.status_bar)
        self.save_error = qt.QLabel()
        self.save_error.setWordWrap(True)
        self.save_error.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.save_error)
        self.save_error.hide()
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
        from .domain import now
        fork = deepcopy(self.data)
        fork.update(id=uuid4().hex, revision=0, title=(fork['title'] + ' (fork)')[:200],
                    pinned=False, created=now(), updated=now())
        for entry in fork['messages']:
            entry['id'] = uuid4().hex
        lease = None
        try:
            lease = self.store.lease(fork['id'])
            self.store.save(fork)
        except (OSError, ValueError) as error:
            if lease is not None:
                lease.unlock()
            self.status.setText(str(error))
            return
        self.release_lease()
        self.data, self.lease = fork, lease
        self._lease_holder[0] = lease
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
        try:
            lease = self.store.lease(key)
            try:
                data = self.store.load(key)
            except BaseException:
                lease.unlock()
                raise
        except (OSError, ValueError, UnicodeError) as error:
            self.status.setText(str(error))
            self.refresh()
            return
        self.release_lease()
        self.lease, self.data = lease, data
        self._lease_holder[0] = lease
        interrupted = False
        for entry in data['messages']:
            if entry['status'] == 'streaming':
                entry['status'] = 'interrupted'
                interrupted = True
        self.restore()
        self.dirty = interrupted
        if interrupted:
            self.status.setText('An interrupted response was recovered. Retry to generate a new answer; partial text is retained.')
            self.persist()
        else:
            self.status.setText('Conversation opened.')
        self.update_controls()

    def release_lease(self):
        if self.lease is not None:
            self.lease.unlock()
            self.lease = None
            self._lease_holder[0] = None

    def restore(self):
        self.loading = True
        data = self.data
        self.profile.setCurrentIndex(self.profile.findData(data['profile_id']))
        self.token.setText(self.session_tokens.get(data['profile_id'], ''))
        self.model.setCurrentText(data['model'])
        self.composer.setPlainText(data['draft'])
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

    def persist(self):
        self.save_timer.stop()
        if self.data is None or not self.dirty:
            return True
        try:
            self.collect()
            self.store.save(self.data)
        except (OSError, ValueError, UnicodeError) as error:
            self.save_error.setText(f'Conversation not saved: {error} Use Export to keep your current copy.')
            self.save_error.show()
            return False
        self.dirty = False
        self.save_error.clear()
        self.save_error.hide()
        for item in self.tree_items():
            if item.data(0, qt.Qt.ItemDataRole.UserRole) == self.data['id']:
                item.setText(0, ('★ ' if self.data.get('pinned') else '') + self.data['title'])
        return True

    def new_conversation(self):
        if self.client.busy or not self.persist():
            return
        data = conversation(defaults(), self.profile.currentData() or '', self.model.currentText())
        data['folder'] = self.selected_folder()
        try:
            lease = self.store.lease(data['id'])
            try:
                self.store.save(data)
            except BaseException:
                lease.unlock()
                raise
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.release_lease()
        self.data, self.lease = data, lease
        self._lease_holder[0] = lease
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
        if self.data is None or not self.composer.toPlainText().strip():
            return
        if not self.persist():
            return
        self.collect()
        snapshot = deepcopy(self.data)
        text = self.composer.toPlainText()
        self.data['messages'].append(message('user', text))
        if self.data['title'] == 'New conversation':
            self.data['title'] = next(line.strip() for line in text.splitlines() if line.strip())[:80]
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
            payload, metadata = build_request(self.data)
        except ValueError as error:
            self.status.setText(str(error))
            return False
        metadata['base_url'] = profile['base_url']
        entry = message('assistant', status='streaming', request=metadata)
        self.data['messages'].append(entry)
        old_draft = self.data['draft']
        if clear_draft:
            self.data['draft'] = ''
            self.loading = True
            self.composer.clear()
            self.loading = False
        self.dirty = True
        if not self.persist():
            self.data['messages'].pop()
            self.data['draft'] = old_draft
            self.loading = True
            self.composer.setPlainText(old_draft)
            self.loading = False
            return False
        self.active_message = entry
        try:
            self.client.start(profile, self.token.text(), payload)
        except (ValueError, OSError) as error:
            entry['status'] = 'failed'
            entry['error'] = str(error)
            self.active_message = None
            self.dirty = True
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
        if self.active_message is None:
            return
        self.active_message['content'] += text
        self.dirty = True
        if not self.render_timer.isActive():
            self.render_timer.start()

    def checkpoint(self):
        if not self.persist():
            self.client.cancel()
            self.status.setText('Generation stopped because the conversation could not be saved. Partial output remains available for export.')

    def completed(self, status, error, metadata):
        self.checkpoint_timer.stop()
        if self.active_message is not None:
            entry, self.active_message = self.active_message, None
            entry['status'] = status
            entry['response'] = metadata
            if error:
                entry['error'] = error
            self.dirty = True
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
