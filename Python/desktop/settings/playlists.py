"""Confirmed playlist cleanup across libraries, without touching source notes."""

from commonUtils.filesystem.storage import cache_directory
from commonUtils.ui import pyside as qt
from desktop.document_catalog import unlocked_ciphers
from features.notes_library.playlists import PlaylistStore


class PlaylistSettingsPanel(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        heading = qt.QLabel('Notes Library playlists')
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        for title, handler, description in (
            ('Delete a playlist…', self.delete,
             'Choose a playlist to delete along with its saved playback position. Source notes are kept. '
             'Unlock protected storage to list its playlists.'),
            ('Clear locked playlists…', self.clear_locked,
             'Delete playlist records whose credentials are locked or unreadable. '
             'Source notes and currently readable playlists are kept.'),
        ):
            button = qt.QPushButton(title)
            button.clicked.connect(handler)
            layout.addWidget(button)
            note = qt.QLabel(description)
            note.setWordWrap(True)
            layout.addWidget(note)

    def failed(self):
        qt.QMessageBox.warning(self, 'Could not update playlists', 'Check storage access and try again.')

    def delete(self):
        try:
            store = PlaylistStore(cache_directory(create=False))
            records = store.all(ciphers=tuple(unlocked_ciphers()))
            if not records:
                qt.QMessageBox.information(self, 'Delete playlist',
                    'There are no available playlists. Unlock protected storage to see its saved playlists.')
                return
            names = [f'{index + 1}. {record.name}' + (' · This session' if record.session_only else '')
                     for index, record in enumerate(records)]
            name, accepted = qt.QInputDialog.getItem(self, 'Delete playlist',
                'Choose a playlist to review before deleting.', names, editable=False)
            if not accepted:
                return
            record = records[names.index(name)]
            # Credentials may have locked while the picker was open.
            if not any(row.id == record.id for row in store.all(ciphers=tuple(unlocked_ciphers()))):
                self.failed()
                return
            if qt.QMessageBox.question(self, 'Delete playlist?',
                'Delete the selected playlist and its saved position? The source notes will be kept.',
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel) == qt.QMessageBox.StandardButton.Yes:
                store.delete_record(record, ciphers=tuple(unlocked_ciphers()))
        except (OSError, ValueError):
            self.failed()

    def clear_locked(self):
        try:
            store = PlaylistStore(cache_directory(create=False))
            if not store.locked_count(ciphers=tuple(unlocked_ciphers())):
                qt.QMessageBox.information(self, 'Clear locked playlists', 'There are no locked playlist records.')
                return
            if qt.QMessageBox.question(self, 'Clear locked playlists?',
                'Delete playlist records whose credentials are locked or unreadable? The source notes will be kept.',
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel) == qt.QMessageBox.StandardButton.Yes:
                store.clear_locked(ciphers=tuple(unlocked_ciphers()))
        except (OSError, ValueError):
            self.failed()
