"""Settings playlist deletion preserves source notes and unavailable credentials."""

from pathlib import Path
from unittest.mock import Mock, patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from desktop.settings.playlists import PlaylistSettingsPanel
from desktop.settings.reader_history import ReaderHistoryPanel
from features.notes_library.notes import NotesLibrary
from features.notes_library.playlists import PlaylistStore
from features.rclone import session
from services.documents.credential_state import DesktopCredentialCipher

TEST_STAGE = TestStage.REGRESSION


class PlaylistSettingsTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.root = Path(self.temporary_directory().name)
        self.notes = self.root / 'notes'
        self.notes.mkdir()
        self.source = self.notes / 'Keep.md'
        self.source.write_text('Keep this source note.')
        self.store = PlaylistStore(self.root / 'settings')
        library = NotesLibrary(LocalFiles(self.notes))
        self.addCleanup(library.close)
        self.catalog = self.store.for_library(library)
        self.ciphers = []
        self.enterContext(patch('desktop.settings.playlists.cache_directory', return_value=self.root / 'settings'))
        self.enterContext(patch('desktop.settings.playlists.unlocked_ciphers', side_effect=lambda: self.ciphers))
        self.warning = self.enterContext(patch.object(qt.QMessageBox, 'warning'))
        self.info = self.enterContext(patch.object(qt.QMessageBox, 'information'))
        self.history = ReaderHistoryPanel()
        self.panel = self.history.findChild(PlaylistSettingsPanel)

    def create(self, name='Morning', catalog=None):
        catalog = catalog or self.catalog
        record = catalog.create(name)
        return catalog.add(record.id, self.source.name)

    def protected(self, identity='a', *, password='password'):
        context = self.root / (identity + '.session')
        def unlock():
            session.remember(context, {'Remote': {'type': 'local'}},
                             state_identity=identity * 64, state_password=password)
        unlock()
        self.addCleanup(session.forget, context)
        provider = LocalFiles(self.notes)
        provider.private, provider.context = True, context
        library = NotesLibrary(provider)
        self.addCleanup(library.close)
        catalog = self.store.for_library(library)
        self.ciphers.append(DesktopCredentialCipher(provider))
        return catalog, context, unlock

    def click(self, title):
        next(button for button in self.panel.findChildren(qt.QPushButton) if button.text() == title).click()

    def test_delete_duplicate_name_keeps_other_playlist_and_source(self):
        self.create()
        self.create()
        first, second = self.store.all()
        changed = Mock()
        self.addCleanup(self.catalog.subscribe(changed))

        def choose(parent, title, message, names, **kwargs):
            self.assertEqual(names, ['1. Morning', '2. Morning'])
            return names[1], True

        with patch.object(qt.QInputDialog, 'getItem', side_effect=choose), \
                patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
            self.click('Delete a playlist…')
        self.assertIsNotNone(self.catalog.get(first.id))
        self.assertIsNone(self.catalog.get(second.id))
        self.assertEqual(self.source.read_text(), 'Keep this source note.')
        changed.assert_called_once()
        self.warning.assert_not_called()

    def test_picker_and_confirmation_cancel_preserve_playlist(self):
        self.create()
        before = self.store.buckets.path().read_bytes()
        with patch.object(qt.QInputDialog, 'getItem', return_value=('', False)), \
                patch.object(qt.QMessageBox, 'question') as confirm:
            self.click('Delete a playlist…')
        confirm.assert_not_called()
        with patch.object(qt.QInputDialog, 'getItem', return_value=('1. Morning', True)), \
                patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel) as confirm:
            self.click('Delete a playlist…')
        self.assertEqual(confirm.call_args.args[-1], qt.QMessageBox.StandardButton.Cancel)
        self.assertEqual(self.store.buckets.path().read_bytes(), before)

    def test_locked_clear_preserves_readable_playlists_and_rechecks_unlock(self):
        self.create()
        catalog, context, unlock = self.protected()
        self.create('Private', catalog)
        path = self.store.root / ('a' * 64 + '.zip')
        before = path.read_bytes()
        session.forget(context)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.click('Clear locked playlists…')
        self.assertEqual(path.read_bytes(), before)

        def confirm(*args):
            self.assertIn('locked or unreadable', args[2])
            self.assertNotIn('Private', args[2])
            unlock()
            return qt.QMessageBox.StandardButton.Yes

        with patch.object(qt.QMessageBox, 'question', side_effect=confirm):
            self.click('Clear locked playlists…')
        self.assertEqual(path.read_bytes(), before)
        unreadable = self.store.root / ('b' * 64 + '.zip')
        unreadable.write_bytes(b'unreadable encrypted record')
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
            self.click('Clear locked playlists…')
        self.assertFalse(unreadable.exists())
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.catalog.list()), 1)
        self.assertTrue(self.source.is_file())
        self.warning.assert_not_called()

    def test_credential_lock_during_confirmation_preserves_encrypted_playlist(self):
        catalog, context, _ = self.protected()
        self.create('Private', catalog)
        path = self.store.root / ('a' * 64 + '.zip')
        before = path.read_bytes()

        def lock(*args):
            session.forget(context)
            return qt.QMessageBox.StandardButton.Yes

        with patch.object(qt.QInputDialog, 'getItem', return_value=('1. Private', True)), \
                patch.object(qt.QMessageBox, 'question', side_effect=lock):
            self.click('Delete a playlist…')
        self.assertEqual(path.read_bytes(), before)
        self.warning.assert_called_once()

    def test_session_playlist_deletion_and_empty_state(self):
        catalog, _, _ = self.protected(password=None)
        record = self.create('Temporary', catalog)
        self.assertTrue(record.session_only)
        with patch.object(qt.QInputDialog, 'getItem', return_value=('1. Temporary · This session', True)), \
                patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
            self.click('Delete a playlist…')
        self.assertEqual(catalog.list(), ())
        self.assertTrue(self.source.is_file())
        with patch.object(qt.QInputDialog, 'getItem') as picker:
            self.click('Delete a playlist…')
        picker.assert_not_called()
        self.info.assert_called_once()
        self.warning.assert_not_called()
