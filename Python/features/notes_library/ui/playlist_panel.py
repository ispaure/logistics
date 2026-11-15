"""Desktop Notes Library playlist navigation and queue editing."""

from pathlib import PurePosixPath

from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.icons import set_painted_icon
from commonUtils.ui.readers.reader_chrome import ReaderIcon


class PlaylistRows(qt.QListWidget):
    reorder = qt.Signal(object, int)
    drop_slot = None

    def __init__(self):
        super().__init__()
        self.drop_indicator = qt.QWidget(self.viewport())
        self.drop_indicator.setAttribute(qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.drop_indicator.setAutoFillBackground(True)
        self.drop_indicator.setBackgroundRole(qt.QPalette.ColorRole.Window)
        self.drop_indicator.hide()

    def slot_at(self, point):
        item = self.itemAt(point)
        return self.count() if item is None else self.row(item) + int(
            point.y() >= self.visualItemRect(item).center().y())

    def dragMoveEvent(self, event):
        super().dragMoveEvent(event)
        slot = self.slot_at(event.position().toPoint())
        source = self.currentRow()
        self.drop_slot = slot if event.source() is self and slot - int(slot > source) != source else None
        self.viewport().update()

    def dragLeaveEvent(self, event):
        self.drop_slot = None
        self.viewport().update()
        super().dragLeaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.drop_slot is not None and self.count():
            slot = self.drop_slot
            rect = self.visualItemRect(self.item(min(slot, self.count() - 1)))
            y = rect.top() if slot < self.count() else rect.bottom()
            palette = self.palette()
            palette.setColor(qt.QPalette.ColorRole.Window, palette.color(qt.QPalette.ColorRole.Text))
            self.drop_indicator.setPalette(palette)
            self.drop_indicator.setGeometry(2, max(0, y - 1), self.viewport().width() - 4, 2)
            self.drop_indicator.show()
            self.drop_indicator.raise_()
        else:
            self.drop_indicator.hide()

    def dropEvent(self, event):
        event.ignore()
        self.drop_slot = None
        self.viewport().update()
        if event.source() is not self or self.currentItem() is None:
            return
        source = self.currentRow()
        point = event.position().toPoint()
        slot = self.slot_at(point)
        target = slot - (slot > source)
        if source != target:
            self.reorder.emit(self.currentItem().data(qt.Qt.ItemDataRole.UserRole), target)
            event.acceptProposedAction()


class PlaylistRowDelegate(qt.QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(qt.Qt.ItemDataRole.UserRole + 1):
            option.text = ''  # The row widget owns the filename and trailing menu.


class PlaylistPanel(qt.QWidget):
    catalog_changed = qt.Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.catalog = self.speech = None
        self.playlist = self.selected = None
        self.unsubscribe = lambda: None
        self.header = qt.QLabel()
        self.header.setWordWrap(True)
        self.notice = qt.QLabel('Open a library to manage playlists.')
        self.notice.setWordWrap(True)
        for label in (self.header, self.notice):
            label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.rows = PlaylistRows()
        self.rows.setItemDelegate(PlaylistRowDelegate(self.rows))
        self.rows.setDropIndicatorShown(False)
        self.row_labels = {}
        self.entry_buttons = {}
        self.rows.setAccessibleName('Saved playlists')
        self.rows.itemClicked.connect(self.activate)
        self.rows.itemActivated.connect(self.activate)
        self.rows.currentItemChanged.connect(self.select)
        self.rows.reorder.connect(self.move)
        self.catalog_changed.connect(self.refresh, qt.Qt.ConnectionType.QueuedConnection)
        self.list_actions = qt.QWidget()
        list_layout = qt.QHBoxLayout(self.list_actions)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self.new_button = self.button('edit', 'New playlist…', self.create, list_layout)
        list_layout.addStretch()
        self.detail_actions = qt.QWidget()
        detail = qt.QHBoxLayout(self.detail_actions)
        detail.setContentsMargins(0, 0, 0, 0)
        self.button('previous', 'All playlists', self.back, detail)
        detail.addStretch()
        self.play_button = self.button('speaker', 'Read aloud playlist', self.play, detail)
        self.more_button = self.button(None, 'Playlist actions', None, detail)
        self.more_button.setText('…')
        menu = qt.QMenu(self.more_button)
        menu.addAction('Rename playlist…', self.rename)
        menu.addSeparator()
        menu.addAction('Delete playlist…', self.delete)
        self.more_button.setMenu(menu)
        self.more_button.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        layout = qt.QVBoxLayout(self)
        layout.addWidget(self.list_actions)
        layout.addWidget(self.detail_actions)
        layout.addWidget(self.header)
        layout.addWidget(self.notice)
        layout.addWidget(self.rows, 1)
        self.detail_actions.hide()
        self.new_button.setEnabled(False)

    @staticmethod
    def button(icon, label, handler, layout):
        button = qt.QToolButton()
        button.setAutoRaise(True)
        button.setStyleSheet('QToolButton::menu-indicator { image: none; width: 0px; }')
        if icon:
            set_painted_icon(button, ReaderIcon, icon)
        button.setAccessibleName(label)
        button.setToolTip(label)
        if handler:
            button.clicked.connect(handler)
        layout.addWidget(button)
        return button

    def connect_library(self):
        from commonUtils.filesystem.storage import cache_directory
        from ..playlists import PlaylistStore
        from .playlist_speech import PlaylistSpeech

        self.catalog = PlaylistStore(cache_directory(create=False)).for_library(self.owner.library)
        self.unsubscribe = self.catalog.subscribe(self.catalog_changed.emit)
        self.speech = PlaylistSpeech(self.owner, self.catalog, self.refresh_state)
        if self.owner.panel_tabs.currentWidget() is self:
            self.refresh()

    def usable(self):
        return self.catalog is not None and not self.owner.locked and not self.owner.closing

    def close_library(self):
        self.unsubscribe()
        self.unsubscribe = lambda: None
        self.playlist = self.selected = None
        if self.speech is not None:
            self.speech.close()
        self.speech = self.catalog = None
        self.row_labels.clear()
        self.entry_buttons.clear()
        self.rows.clear()
        self.header.clear()
        self.notice.clear()

    def read(self):
        if self.usable():
            try:
                return self.catalog.list()
            except (OSError, ValueError):
                self.notice.setText('Playlists could not be opened. Unlock the library or try again.')
                self.notice.show()
        return None

    def refresh(self):
        records = self.read()
        if records is None:
            self.playlist = self.selected = None
            self.row_labels.clear()
            self.entry_buttons.clear()
            self.rows.clear()
            self.header.clear()
            self.list_actions.show()
            self.detail_actions.hide()
            self.new_button.setEnabled(False)
            return
        identity = self.playlist.id if self.playlist else None
        self.playlist = next((record for record in records if record.id == identity), None)
        playlist = self.playlist
        self.header.setText(playlist.name if playlist else '')
        self.header.setVisible(playlist is not None)
        self.list_actions.setVisible(playlist is None)
        self.detail_actions.setVisible(playlist is not None)
        self.new_button.setEnabled(True)
        self.rows.setAccessibleName('Playlist entries' if playlist else 'Saved playlists')
        self.rows.setDragDropMode(qt.QAbstractItemView.DragDropMode.InternalMove if playlist
                                  else qt.QAbstractItemView.DragDropMode.NoDragDrop)
        self.rows.setDefaultDropAction(qt.Qt.DropAction.MoveAction)
        with qt.QSignalBlocker(self.rows):
            self.rows.drop_slot = None
            self.row_labels.clear()
            self.entry_buttons.clear()
            self.rows.clear()
            for record in playlist.entries if playlist else records:
                item = qt.QListWidgetItem(self.rows)
                item.setData(qt.Qt.ItemDataRole.UserRole, record.id)
                if playlist:
                    item.setFlags(item.flags() | qt.Qt.ItemFlag.ItemIsDragEnabled)
                    item.setData(qt.Qt.ItemDataRole.UserRole + 1, True)
                    item.setToolTip(record.path)
                    row = qt.QWidget()
                    line = qt.QHBoxLayout(row)
                    line.setContentsMargins(6, 0, 2, 0)
                    label = qt.QLabel()
                    label.setTextFormat(qt.Qt.TextFormat.PlainText)
                    label.setAttribute(qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                    label.setMinimumWidth(0)
                    line.addWidget(label, 1)
                    more = self.button(None, 'Actions for ' + PurePosixPath(record.path).name, None, line)
                    more.setText('…')
                    more.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
                    menu = qt.QMenu(more)
                    menu.aboutToShow.connect(lambda identity=record.id, menu=menu: self.entry_menu(identity, menu))
                    more.setMenu(menu)
                    self.row_labels[record.id] = label
                    self.entry_buttons[record.id] = more
                    item.setSizeHint(qt.QSize(0, max(36, row.sizeHint().height())))
                    self.rows.setItemWidget(item, row)
                else:
                    item.setText(record.name + (' · This session' if record.session_only else ''))
                if record.id == self.selected:
                    self.rows.setCurrentItem(item)
            if playlist and self.rows.currentRow() < 0:
                for row, entry in enumerate(playlist.entries):
                    if entry.id == playlist.active_id:
                        self.rows.setCurrentRow(row)
                        break
        self.select(self.rows.currentItem())
        if playlist is None:
            self.notice.setText('' if records else 'Create a playlist to arrange notes for read-aloud.')
        self.notice.setVisible(bool(self.notice.text()))
        self.refresh_state()

    def refresh_state(self):
        playlist, speech = self.playlist, self.speech
        if playlist is None or not self.usable():
            return
        for row, entry in enumerate(playlist.entries):
            parts = [PurePosixPath(entry.path).name]
            if entry.id in speech.unavailable:
                parts.append('Missing or inaccessible')
            item = self.rows.item(row)
            if item is not None and item.text() != ' · '.join(parts):
                item.setText(' · '.join(parts))
                self.row_labels[entry.id].setText(item.text())
        detail = '' if playlist.entries else 'Use a note’s or folder note’s actions to add it to this playlist.'
        if playlist.session_only:
            detail += ' This playlist lasts for the current session.'
        if self.notice.text() != detail:
            self.notice.setText(detail)
        self.notice.setVisible(bool(detail))

    def select(self, item, previous=None):
        self.selected = item.data(qt.Qt.ItemDataRole.UserRole) if item is not None else None
        self.play_button.setEnabled(self.playlist is not None and self.rows.count() > 0)
        for identity, label in self.row_labels.items():
            role = qt.QPalette.ColorRole.HighlightedText if identity == self.selected else qt.QPalette.ColorRole.Text
            label.setForegroundRole(role)
            palette = self.rows.palette()
            palette.setColor(qt.QPalette.ColorRole.ButtonText, palette.color(role))
            self.entry_buttons[identity].setPalette(palette)

    def entry_menu(self, identity, menu):
        menu.clear()
        if not self.usable() or self.playlist is None:
            return
        index = next((i for i, entry in enumerate(self.playlist.entries) if entry.id == identity), None)
        if index is None:
            return
        self.rows.setCurrentRow(index)
        menu.addAction('Move up', lambda: self.move_selected(-1)).setEnabled(index > 0)
        menu.addAction('Move down', lambda: self.move_selected(1)).setEnabled(index < self.rows.count() - 1)
        menu.addAction('Repair reference…', self.repair)
        menu.addAction('Remove entry', self.remove)

    def activate(self, item):
        if not self.usable():
            return
        identity = item.data(qt.Qt.ItemDataRole.UserRole)
        if self.playlist is None:
            self.open_playlist(identity)
        else:
            entry = next((entry for entry in self.playlist.entries if entry.id == identity), None)
            if entry is not None:
                self.owner.open_note(entry.path)

    def open_playlist(self, identity):
        records = self.read()
        self.playlist = next((record for record in records or () if record.id == identity), None)
        self.selected = None
        self.refresh()

    def back(self):
        self.playlist = self.selected = None
        self.refresh()

    def change(self, method, *args):
        if not self.usable():
            return None
        try:
            return getattr(self.catalog, method)(*args)
        except (OSError, ValueError):
            self.notice.setText('Could not update the playlist. Check the selection and library access.')
            self.notice.show()
            return None

    def create(self):
        if not self.usable():
            return
        name, accepted = qt.QInputDialog.getText(self, 'New playlist', 'Name')
        if accepted:
            playlist = self.change('create', name)
            if playlist:
                self.open_playlist(playlist.id)

    def rename(self):
        if not self.usable() or self.playlist is None:
            return
        playlist = self.playlist
        name, accepted = qt.QInputDialog.getText(self, 'Rename playlist', 'Name', text=playlist.name)
        if accepted:
            self.change('rename', playlist.id, name)

    def delete(self):
        if not self.usable() or self.playlist is None:
            return
        playlist = self.playlist
        choice = qt.QMessageBox.question(self, 'Delete playlist?',
            'Delete this playlist and its saved position? The source notes will be kept.',
            qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
            qt.QMessageBox.StandardButton.Cancel)
        if choice == qt.QMessageBox.StandardButton.Yes:
            self.change('delete', playlist.id)

    def repair(self):
        if not self.usable() or self.playlist is None:
            return
        from commonUtils.ui.resources.picker import choose_resource

        identity, entry = self.playlist.id, self.selected
        if entry is None:
            return
        provider = self.owner.library.provider
        choice = choose_resource(
            [('Current library', lambda: (provider, provider.acquire() if hasattr(provider, 'acquire') else lambda: None))],
            parent=self, extensions=('.md', '.markdown'), directory=self.owner.library.root)
        if choice:
            try:
                self.change('replace', identity, entry, choice.path)
            finally:
                choice.close()

    def add_note(self, path):
        records = self.read()
        if records is None:
            return
        if not records:
            name, accepted = qt.QInputDialog.getText(self, 'New playlist', 'Name')
            record = self.change('create', name) if accepted else None
        else:
            names = [f'{index + 1}. {record.name}' for index, record in enumerate(records)]
            name, accepted = qt.QInputDialog.getItem(self, 'Add to playlist',
                PurePosixPath(path).name, names, editable=False)
            record = records[names.index(name)] if accepted else None
        if record and self.change('add', record.id, path):
            self.owner.panel_tabs.setCurrentWidget(self)
            self.open_playlist(record.id)

    def remove(self):
        if self.selected is not None:
            self.change('remove', self.playlist.id, self.selected)

    def move(self, entry, index):
        if self.playlist is not None:
            self.change('move', self.playlist.id, entry, index)

    def move_selected(self, distance):
        index = self.rows.currentRow() + distance
        if self.selected is not None and 0 <= index < self.rows.count():
            self.move(self.selected, index)

    def play(self):
        if self.usable() and self.playlist is not None:
            self.speech.play(self.playlist.id, anchor=self.play_button)
