"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from features.rclone import actions
from features.rclone import session
from features.comics.library import ComicDocument
from features.comics.pages import ComicPages
from tests.local_crypt_fixture import crypt_fixture


from tests.resources.localcrypt_cases import LocalCryptCase


class LocalCryptComicMetadataTests(LocalCryptCase):
    def test_bulk_metadata_action_keeps_selected_encrypted_zip_comics(self):
        from io import BytesIO
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        from commonUtils.archives.zip_access import is_encrypted
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f, \
             patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary):
            f.provider.create_file('second.zip', BytesIO(f.provider.read_bytes('encrypted.cbz')))
            f.provider.rename('encrypted.cbz', 'first.zip')
            paths = [f.item.data / name for name in ('first.zip', 'second.zip')]
            for n, path in enumerate(paths):
                ComicDocument(path, source=f.provider).save({'Title': f'Untouched title {n}'})
            view = CryptBrowserView(f.item)
            browser = view.file_browser
            self.wait(lambda: not browser.busy)
            selection = browser.tree.selectionModel()
            for n, path in enumerate(paths):
                index = browser.sort_model.mapFromSource(browser.model.browse_index(path))
                flags = qt.QItemSelectionModel.SelectionFlag.ClearAndSelect if n == 0 else qt.QItemSelectionModel.SelectionFlag.Select
                selection.select(index, flags | qt.QItemSelectionModel.SelectionFlag.Rows)
            self.assertEqual({row['path'] for row in browser.selected_rows()}, {'first.zip', 'second.zip'})
            editor = view.edit_metadata(paths[0])
            try:
                self.wait(lambda: not editor.busy)
                self.assertIsNotNone(editor.selection, editor.message.text())
                self.assertEqual(set(editor.targets), set(paths))
                self.assertEqual(len(editor.selection.documents), 2)
                self.assertTrue(editor.is_bulk)
                editor.tabs.apply_pending({'Series': 'Encrypted ZIP batch sentinel'})
                editor._save()
                self.wait(lambda: not editor.busy)
                self.assertIsNone(editor.last_save_error)
                for n, path in enumerate(paths):
                    document = ComicDocument(path, source=f.provider)
                    self.assertEqual(document.info.get_field('Series'), 'Encrypted ZIP batch sentinel')
                    self.assertEqual(document.info.get_field('Title'), f'Untouched title {n}')
                    self.assertEqual(ComicPages(path, document).read_page(0)[0], f.image)
                    with f.provider.open(path) as stream:
                        self.assertTrue(is_encrypted(stream))
                    self.assertNotIn(b'Encrypted ZIP batch sentinel', f.provider.encrypted_path(path).read_bytes())
                self.assertTrue(editor.windowTitle().startswith('🕵️ Private -'))
            finally:
                self.wait(lambda: not editor.busy)
                editor.close()
                self.wait(view.prepare_close)
                view.close()

    def test_private_folder_metadata_selection_uses_provider_and_deduplicates_zip_cbz(self):
        from io import BytesIO
        from features.comics.selection import ComicSelection
        from features.comics.ui.metadata_editor import MetadataEditor
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            f.provider.mkdir('Comics')
            f.provider.mkdir('Comics/Nested')
            f.provider.create_file('Comics/a.zip', BytesIO(f.provider.read_bytes('encrypted.cbz')))
            f.provider.create_file('Comics/Nested/b.cbz', BytesIO(f.provider.read_bytes('encrypted.cbz')))
            f.provider.create_file('Comics/Nested/readme.txt', BytesIO(b'Not a comic'))
            from commonUtils.archives.zip_access import open_archive
            unrelated = BytesIO()
            with open_archive(unrelated, 'w', password='unrelated password') as archive:
                archive.writestr('document.txt', b'Unrelated ZIP must not receive ComicInfo')
            f.provider.create_file('Comics/unrelated.zip', BytesIO(unrelated.getvalue()))
            folder = f.item.data / 'Comics'
            selected = ComicSelection([folder, folder / 'Nested', folder / 'a.zip'], source=f.provider)
            self.assertEqual({document.path for document in selected.documents}, {folder / 'a.zip', folder / 'Nested/b.cbz'})
            self.assertFalse(selected.load_failures)
            result = selected.save({'Publisher': 'Private folder batch'})
            self.assertEqual(len(result.saved), 2)
            self.assertFalse(result.failed)
            self.assertEqual(f.provider.read_bytes('Comics/unrelated.zip'), unrelated.getvalue())
            editor = MetadataEditor(folder, source=f.provider)
            try:
                self.wait(lambda: not editor.busy)
                self.assertTrue(editor.is_bulk)
                self.assertEqual(len(editor.selection.documents), 2)
                self.assertEqual({document.info.get_field('Publisher') for document in editor.selection.documents}, {'Private folder batch'})
            finally:
                self.wait(lambda: not editor.busy)
                editor.close()

    def test_bulk_metadata_user_input_persists_all_fields_in_localcrypt(self):
        from io import BytesIO
        from PySide6.QtTest import QTest
        from features.comics.comicinfo import ComicInfoXML
        from features.comics.ui.metadata_editor import MetadataEditor
        from commonUtils.archives.zip_access import is_encrypted
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            f.provider.create_file('second.cbz', BytesIO(f.provider.read_bytes('encrypted.cbz')))
            paths = [f.item.data / name for name in ('encrypted.cbz', 'second.cbz')]
            ComicDocument(paths[1], source=f.provider).save({
                field: '3' if field in ComicInfoXML.INTEGER_FIELDS else
                ComicInfoXML.ENUMS[field][0] if field in ComicInfoXML.ENUMS else 'Existing ' + field
                for field in ComicInfoXML.FIELDS if field != 'PageCount'})
            editor = MetadataEditor(paths, source=f.provider)
            editor.show()
            try:
                self.wait(lambda: not editor.busy)
                self.assertIsNotNone(editor.selection, editor.message.text())
                self.assertTrue(all(entry.mixed for entry in editor.tabs.state.fields.values()))
                expected = {}
                for field, control in editor.editors.items():
                    if field in ComicInfoXML.ENUMS or field == 'LanguageISO':
                        value = 'fr' if field == 'LanguageISO' else ComicInfoXML.ENUMS[field][-1]
                        control.setCurrentIndex(control.findData(value))
                    else:
                        value = '7' if field in ComicInfoXML.INTEGER_FIELDS else (
                            '1A' if field in ('Number', 'AlternateNumber') else 'Private ' + field)
                        widget = control.lineEdit() if isinstance(control, (qt.QAbstractSpinBox, qt.QComboBox)) else control
                        widget.setFocus()
                        widget.selectAll()
                        QTest.keyClicks(widget, value)
                    expected[field] = value
                self.assertEqual(editor._changes(), expected)
                for changes in (expected, {'Writer': 'Second apply', 'Count': '9'}):
                    if changes is not expected:
                        for field, value in changes.items():
                            control = editor.editors[field]
                            widget = control.lineEdit() if isinstance(control, qt.QAbstractSpinBox) else control
                            widget.setFocus()
                            widget.selectAll()
                            QTest.keyClicks(widget, value)
                        expected.update(changes)
                    QTest.mouseClick(editor.apply_button, qt.Qt.MouseButton.LeftButton)
                    self.wait(lambda: not editor.busy)
                    self.assertIsNone(editor.last_save_error, editor.message.text())
                    self.assertEqual(editor._changes(), {})
                    for path in paths:
                        document = ComicDocument(path, source=f.provider)
                        self.assertEqual({name: document.info.get_field(name) for name in expected}, expected)
                        self.assertEqual(ComicPages(path, document).read_page(0)[0], f.image)
                        with f.provider.open(path) as stream:
                            self.assertTrue(is_encrypted(stream))
                        self.assertNotIn(b'Private Writer', f.provider.encrypted_path(path).read_bytes())
            finally:
                self.wait(lambda: not editor.busy)
                editor.close()

    def test_bulk_metadata_save_refreshes_localcrypt_browser_information(self):
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f, \
             patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary):
            view = CryptBrowserView(f.item)
            view.show()
            browser = view.file_browser
            self.wait(lambda: not browser.busy)
            path = f.item.data / 'plain.cbz'
            browser.views.select_source(browser.model.browse_index(path))
            self.wait(lambda: not browser.busy and browser.tabs.count() == 2)
            self.assertNotIn('Updated from bulk editor', browser.tabs.widget(1).toPlainText())
            editor = view.edit_metadata(f.item.data)
            try:
                self.wait(lambda: not editor.busy)
                self.assertEqual(len(editor.selection.documents), 2)
                editor.editors['Writer'].setText('Updated from bulk editor')
                editor.apply_button.click()
                self.wait(lambda: not editor.busy and not browser.busy
                          and not browser.preview.pending and not browser.preview.queued)
                self.assertIsNone(editor.last_save_error)
                self.assertEqual(ComicDocument(path, source=f.provider).info.writer, 'Updated from bulk editor')
                self.assertIn('Updated from bulk editor', browser.tabs.widget(1).toPlainText())
            finally:
                self.wait(lambda: not editor.busy)
                editor.close()
                self.wait(view.prepare_close)
                view.close()

    def test_pulled_comic_metadata_is_fresh_after_browser_refresh_and_editor_reopen(self):
        from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f, \
             patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary):
            view = CryptBrowserView(f.item)
            view.show()
            browser = view.file_browser
            self.wait(lambda: not browser.busy)
            path = f.item.data / 'plain.cbz'
            browser.views.select_source(browser.model.browse_index(path))
            self.wait(lambda: not browser.busy and browser.tabs.count() == 2)
            # Populate provider caches before a real ciphertext pull replaces it.
            ComicDocument(path, source=view.provider)
            ComicDocument(f.plain / 'plain.cbz').save({'Writer': 'Writer from remote pull'})
            environment, source, destination = session.launch(f.context, f.plain, 'Secret:')
            run_bytes([str(self.binary), '--config', session.NULL_CONFIG, 'copy', str(source), str(destination)],
                      environment=environment, max_output=0)
            editor = None
            try:
                self.assertTrue(actions.pull_encrypted_copy('Secret', f.context, item=f.item))
                self.assertEqual(ComicDocument(path, source=view.provider).info.writer, 'Writer from remote pull')
                browser.refresh()
                self.wait(lambda: not browser.busy and not browser.preview.pending and not browser.preview.queued)
                self.assertIn('Writer from remote pull', browser.tabs.widget(1).toPlainText())
                editor = view.edit_metadata(path)
                self.wait(lambda: not editor.busy)
                self.assertEqual(editor.editors['Writer'].text(), 'Writer from remote pull')
            finally:
                if editor is not None:
                    self.wait(lambda: not editor.busy)
                    editor.close()
                self.wait(view.prepare_close)
                view.close()

    def test_private_batch_reports_missing_inner_password_without_modifying_archives(self):
        from io import BytesIO
        from features.comics.selection import ComicSelection
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            f.provider.create_file('second.zip', BytesIO(f.provider.read_bytes('encrypted.cbz')))
            paths = [f.item.data / name for name in ('encrypted.cbz', 'second.zip')]
            before = [f.provider.encrypted_path(path).read_bytes() for path in paths]
            ini = f.provider.entry('remoteConfig.ini')
            f.provider.remove_empty('remoteConfig.ini', ini['revision'])
            with self.assertRaisesRegex(ValueError, 'No selected comics could be unlocked'):
                ComicSelection(paths, source=f.provider)
            self.assertEqual([f.provider.encrypted_path(path).read_bytes() for path in paths], before)
