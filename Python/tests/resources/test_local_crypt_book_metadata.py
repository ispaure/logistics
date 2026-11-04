"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from tests.local_crypt_fixture import crypt_fixture


from tests.resources.localcrypt_cases import LocalCryptCase


class LocalCryptBookMetadataTests(LocalCryptCase):
    def test_private_epub_metadata_preserves_resources_and_inner_password(self):
        from io import BytesIO
        from zipfile import ZipFile
        from tests.books_fixture import make_book
        from commonUtils.archives.zip_access import open_archive, archive_manifest, is_encrypted
        from features.books.epub import EPUBBook
        from features.books.metadata import save_metadata
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            original = BytesIO()
            make_book(original)
            for password in (None, 'synthetic-archive-password'):
                source = BytesIO()
                with ZipFile(BytesIO(original.getvalue())) as incoming, open_archive(source, 'w', password=password) as outgoing:
                    outgoing.comment = incoming.comment
                    for member in incoming.infolist():
                        outgoing.writestr(member.filename, incoming.read(member))
                f.provider.command('rcat', 'book.epub', input_data=source.getvalue(), limit=0)
                book = EPUBBook(f.item.data / 'book.epub', source=f.provider)
                before = archive_manifest(BytesIO(source.getvalue()), password=password)
                saved, backup = save_metadata(book, {'title': ['Encrypted title sentinel']})
                self.assertIsNone(backup)
                self.assertEqual(saved.values('title'), ['Encrypted title sentinel'])
                with f.provider.open(saved.path) as stream:
                    self.assertEqual(is_encrypted(stream), password is not None)
                    stream.seek(0)
                    after = archive_manifest(stream, password=password)
                before.pop(book.package_path); after.pop(book.package_path)
                self.assertEqual(after, before)
                with self.assertRaises(ValueError):
                    save_metadata(book, {'title': ['stale']})
                ciphertext = f.provider.encrypted_path('book.epub').read_bytes()
                with self.assertRaises(Exception):
                    save_metadata(saved, {'title': ['cancelled']}, cancelled=lambda: True)
                self.assertEqual(f.provider.encrypted_path('book.epub').read_bytes(), ciphertext)
                self.assertNotIn(b'Encrypted title sentinel', ciphertext)
                self.assertEqual(list(f.item.data.glob('*.bak*')), [])

    def test_private_epub_picker_reads_and_saves_metadata_without_persistent_state(self):
        from io import BytesIO
        from tests.books_fixture import make_book
        from commonUtils.runtime.resources.selection import ResourceChoice
        from commonUtils.ui.readers.reader_menus import RecentFiles
        from features.books.epub import EPUBBook
        from services.documents.ui.readers import open_reader_choice
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            data = BytesIO(); make_book(data)
            f.provider.command('rcat', 'book.epub', input_data=data.getvalue(), limit=0)
            released = []
            lease = f.provider.acquire()
            def release():
                released.append(True)
                lease()
            choice = ResourceChoice(f.provider, 'book.epub', release)
            with patch.object(RecentFiles, 'add', side_effect=AssertionError('Private reader wrote recents')), \
                 patch('features.books.ui.reader.ReadingState', side_effect=AssertionError('Private reader created state')):
                window = open_reader_choice(choice, None, 'epub')
                self.assertIsNotNone(window)
                try:
                    self.wait(lambda: not window.reader._loading)
                    self.assertTrue(window.reader.private)
                    self.assertTrue(window.windowTitle().startswith('🕵️ Private - '))
                    from services.documents.credential_state import CredentialState
                    self.assertIsInstance(window.reader._state, CredentialState)
                    with self.assertRaises(PermissionError):
                        _ = window.reader._state.cipher.identity
                    with patch('commonUtils.persistence.atomic_write_bytes', side_effect=AssertionError('Passwordless checkpoint wrote disk')):
                        window.reader._state.save({'position': .5})
                    self.assertEqual(window.reader._state.memory, {'position': .5})
                    self.assertFalse(window.reader.menus.recent.isEnabled())
                    self.assertTrue(window.reader.text.toPlainText())
                    self.assertEqual(released, [])
                    with patch('features.books.ui.reader.MetadataEditor.exec', return_value=qt.QDialog.DialogCode.Accepted), \
                         patch('features.books.ui.reader.MetadataEditor.changes', return_value={'title': ['Private reader metadata']}):
                        window.reader.edit_metadata()
                    self.wait(lambda: window.reader.worker is None)
                    self.assertEqual(EPUBBook(f.item.data / 'book.epub', source=f.provider).title, 'Private reader metadata')
                    self.assertEqual(window.reader.status.text(), 'Metadata saved.')
                    self.assertEqual(window.windowTitle(), '🕵️ Private - book.epub')
                finally:
                    self.wait(window.prepare_close)
                    window.close()
                    self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
                    self.app.processEvents()
                self.assertEqual(released, [True])

    def test_private_epub_metadata_window_uses_provider(self):
        from io import BytesIO
        from tests.books_fixture import make_book
        from features.books.ui.metadata_window import MetadataWindow
        from features.books.epub import EPUBBook
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            data = BytesIO(); make_book(data)
            f.provider.command('rcat', 'book.epub', input_data=data.getvalue(), limit=0)
            window = MetadataWindow(f.item.data / 'book.epub', source=f.provider)
            self.wait(lambda: window.worker is None)
            self.assertIsNotNone(window.editor, window.status.text())
            self.assertIs(window.book.source, f.provider)
            self.assertEqual(window.windowTitle(), '🕵️ Private - Edit EPUB metadata')
            window.editor.fields['title'].setText('Edited through private EPUB UI')
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(window.prepare_credential_lock())
            window.editor._accept()
            self.wait(lambda: window.worker is None)
            book = EPUBBook(f.item.data / 'book.epub', source=f.provider)
            self.assertEqual(book.values('title'), ['Edited through private EPUB UI'])

    def test_private_epub_metadata_prompts_for_inner_password(self):
        from io import BytesIO
        from zipfile import ZipFile
        from tests.books_fixture import make_book
        from commonUtils.archives.zip_access import open_archive
        from features.books.ui.metadata_window import MetadataWindow
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            data = BytesIO(); make_book(data)
            protected = BytesIO()
            with ZipFile(BytesIO(data.getvalue())) as source, open_archive(protected, 'w', password='different-inner-password') as target:
                for member in source.infolist():
                    target.writestr(member.filename, source.read(member))
            f.provider.command('rcat', 'book.epub', input_data=protected.getvalue(), limit=0)
            with patch('desktop.dialogs.archive_password.ask_password', return_value='different-inner-password') as prompt:
                window = MetadataWindow(f.item.data / 'book.epub', source=f.provider)
                self.wait(lambda: window.editor is not None)
                self.assertEqual(window.book.password, 'different-inner-password')
                prompt.assert_called_once()
                window.close()
