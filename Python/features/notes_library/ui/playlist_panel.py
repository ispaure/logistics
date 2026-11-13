"""Desktop Notes Library playlist navigation and queue editing."""

from pathlib import PurePosixPath

from commonUtils.ui import pyside as qt


class PlaylistRows(qt.QListWidget):
    reorder = qt.Signal(object, int)

    def dropEvent(self, event):
        event.ignore()
        if event.source() is not self or self.currentItem() is None:
            return
        source = self.currentRow()
        point = event.position().toPoint()
        item = self.itemAt(point)
        slot = self.count() if item is None else self.row(item) + (
            point.y() > self.visualItemRect(item).center().y())
        target = slot - (slot > source)
        if source != target:
            self.reorder.emit(self.currentItem().data(qt.Qt.ItemDataRole.UserRole), target)
            event.acceptProposedAction()


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
        self.spoken = qt.QLabel()
        for label in (self.header, self.notice, self.spoken):
            label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.spoken.setWordWrap(True)
        self.spoken.hide()
        self.rows = PlaylistRows()
        self.rows.setAccessibleName('Saved playlists')
        self.rows.itemActivated.connect(self.activate)
        self.rows.currentItemChanged.connect(self.select)
        self.rows.reorder.connect(self.move)
        self.catalog_changed.connect(self.refresh, qt.Qt.ConnectionType.QueuedConnection)
        self.list_actions = qt.QWidget()
        list_layout = qt.QHBoxLayout(self.list_actions)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self.new_button = self.button('New playlist…', self.create, list_layout)
        self.open_button = self.button('Open', self.open_current, list_layout)
        self.detail_actions = qt.QWidget()
        detail = qt.QGridLayout(self.detail_actions)
        detail.setContentsMargins(0, 0, 0, 0)
        for row, labels in enumerate((
            (('All playlists', self.back), ('Rename…', self.rename)),
            (('Add Markdown…', self.pick), ('Delete playlist…', self.delete)),
            (('Move up', lambda: self.move_selected(-1)), ('Move down', lambda: self.move_selected(1))),
            (('Repair reference…', lambda: self.pick(replace=True)), ('Remove entry', self.remove)),
        )):
            for column, (label, handler) in enumerate(labels):
                button = qt.QPushButton(label)
                button.clicked.connect(lambda checked=False, handler=handler: handler())
                detail.addWidget(button, row, column)
        self.up_button, self.down_button, self.repair_button, self.remove_button = (
            detail.itemAtPosition(row, column).widget() for row, column in ((2, 0), (2, 1), (3, 0), (3, 1)))
        self.play_button = qt.QPushButton('Read aloud…')
        self.play_button.clicked.connect(self.play)
        self.selected_play_button = qt.QPushButton('Play selected')
        self.selected_play_button.clicked.connect(self.play_selected)
        self.play_actions = qt.QWidget()
        play_layout = qt.QHBoxLayout(self.play_actions)
        play_layout.setContentsMargins(0, 0, 0, 0)
        play_layout.addWidget(self.play_button)
        play_layout.addWidget(self.selected_play_button)
        layout = qt.QVBoxLayout(self)
        layout.addWidget(self.header)
        layout.addWidget(self.notice)
        layout.addWidget(self.spoken)
        layout.addWidget(self.rows, 1)
        layout.addWidget(self.list_actions)
        layout.addWidget(self.detail_actions)
        layout.addWidget(self.play_actions)
        self.detail_actions.hide()
        self.play_actions.hide()
        self.new_button.setEnabled(False)
        self.open_button.setEnabled(False)

    @staticmethod
    def button(label, handler, layout):
        button = qt.QPushButton(label)
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
        self.rows.clear()
        self.header.clear()
        self.notice.clear()
        self.spoken.clear()
        self.spoken.hide()

    def read(self):
        if self.usable():
            try:
                return self.catalog.list()
            except (OSError, ValueError):
                self.notice.setText('Playlists could not be opened. Unlock the library or try again.')
        return None

    def refresh(self):
        records = self.read()
        if records is None:
            self.playlist = self.selected = None
            self.rows.clear()
            self.header.clear()
            self.spoken.clear()
            self.spoken.hide()
            self.list_actions.show()
            self.detail_actions.hide()
            self.play_actions.hide()
            self.new_button.setEnabled(False)
            return
        identity = self.playlist.id if self.playlist else None
        self.playlist = next((record for record in records if record.id == identity), None)
        playlist = self.playlist
        self.header.setText(playlist.name if playlist else '')
        self.header.setVisible(playlist is not None)
        self.list_actions.setVisible(playlist is None)
        self.detail_actions.setVisible(playlist is not None)
        self.play_actions.setVisible(playlist is not None)
        self.new_button.setEnabled(True)
        self.rows.setAccessibleName('Playlist entries' if playlist else 'Saved playlists')
        self.rows.setDragDropMode(qt.QAbstractItemView.DragDropMode.InternalMove if playlist
                                  else qt.QAbstractItemView.DragDropMode.NoDragDrop)
        self.rows.setDefaultDropAction(qt.Qt.DropAction.MoveAction)
        with qt.QSignalBlocker(self.rows):
            self.rows.clear()
            for record in playlist.entries if playlist else records:
                item = qt.QListWidgetItem(self.rows)
                item.setData(qt.Qt.ItemDataRole.UserRole, record.id)
                if playlist:
                    item.setFlags(item.flags() | qt.Qt.ItemFlag.ItemIsDragEnabled)
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
        self.refresh_state()

    def refresh_state(self):
        playlist, speech = self.playlist, self.speech
        if playlist is None or not self.usable():
            self.spoken.clear()
            self.spoken.hide()
            return
        state = speech.state if speech.playlist_id == playlist.id else 'stopped'
        active = (speech.active_id if speech.playlist_id == playlist.id else None) or playlist.active_id
        status = {'speaking': 'Playing', 'paused': 'Paused', 'stopped': 'Ready',
                  'unavailable': 'Read-aloud unavailable'}.get(state, state.capitalize())
        for row, entry in enumerate(playlist.entries):
            parts = [entry.path]
            if entry.id == active:
                parts.append(status)
            if entry.id in speech.unavailable:
                parts.append('Missing or inaccessible')
            item = self.rows.item(row)
            if item is not None and item.text() != ' · '.join(parts):
                item.setText(' · '.join(parts))
        detail = status if playlist.entries else 'Add Markdown notes to start listening.'
        if playlist.session_only:
            detail += ' This playlist lasts for the current session.'
        if self.notice.text() != detail:
            self.notice.setText(detail)
        line = getattr(speech, 'spoken_line', '') if speech.playlist_id == playlist.id else ''
        if self.spoken.text() != line:
            self.spoken.setText(line)
            self.spoken.setVisible(bool(line))

    def select(self, item, previous=None):
        self.selected = item.data(qt.Qt.ItemDataRole.UserRole) if item is not None else None
        row = self.rows.currentRow()
        self.open_button.setEnabled(item is not None)
        self.play_button.setEnabled(self.playlist is not None and self.rows.count() > 0)
        self.selected_play_button.setEnabled(self.playlist is not None and item is not None)
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < self.rows.count() - 1)
        self.repair_button.setEnabled(row >= 0)
        self.remove_button.setEnabled(row >= 0)

    def activate(self, item):
        identity = item.data(qt.Qt.ItemDataRole.UserRole)
        if self.playlist is None:
            self.open_playlist(identity)
        else:
            self.speech.play(self.playlist.id, identity, anchor=self.play_button)

    def open_current(self):
        if self.selected:
            self.open_playlist(self.selected)

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

    def pick(self, *, replace=False):
        if not self.usable() or self.playlist is None:
            return
        from commonUtils.ui.resources.picker import choose_resource

        identity, entry = self.playlist.id, self.selected
        if replace and entry is None:
            return
        provider = self.owner.library.provider
        choice = choose_resource(
            [('Current library', lambda: (provider, provider.acquire() if hasattr(provider, 'acquire') else lambda: None))],
            parent=self, extensions=('.md', '.markdown'), directory=self.owner.library.root)
        if choice:
            try:
                if replace:
                    self.change('replace', identity, entry, choice.path)
                else:
                    self.change('add', identity, choice.path)
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

    def play_selected(self):
        if self.usable() and self.playlist is not None and self.selected is not None:
            self.speech.play(self.playlist.id, self.selected, anchor=self.play_button)
