"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from commonUtils.filesystem.native_paths import native_path
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.rclone import executable
from features.rclone.localcrypt import backend as local_crypt
from features.rclone.localcrypt import mapping as copy_mapping
from features.rclone.localcrypt import transport
from features.rclone import actions
from features.rclone import session
from features.comics.library import ComicDocument
from features.comics.pages import ComicPages
from tests.local_crypt_fixture import crypt_fixture


class LocalCryptTests(QtTestCase):
    def test_service_open_views_close_independently_and_lock_together(self):
        from features.rclone.desktop_service import service
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f, patch.object(
                executable, 'get_rclone_path', return_value=self.binary):
            first = service.localcrypt.open(f.item)
            second = service.localcrypt.open(f.item)
            self.addCleanup(first.close)
            self.addCleanup(second.close)
            browser_release = first.acquire()
            reader_release = first.acquire()
            browser_release()
            self.assertFalse(first.closed)
            self.assertEqual(first.read_bytes('note.md'), f.original)
            reader_release()
            self.assertTrue(first.closed)
            self.assertEqual(second.read_bytes('note.md'), f.original)
            service.credentials.lock(f.context)
            self.assertTrue(second.closed)
            with self.assertRaisesRegex(ValueError, 'locked'):
                second.read_bytes('note.md')

    def test_recursive_search_uses_one_listing_and_opens_nested_results(self):
        from commonUtils.search.providers import search_resources
        from io import BytesIO
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            f.provider.mkdir('nested')
            f.provider.mkdir('nested/deep')
            f.provider.create_file('nested/deep/Needle.txt', BytesIO(b'found'))
            with patch.object(f.provider, 'command', wraps=f.provider.command) as command:
                result = search_resources(f.provider, '', 'NEEDLE')
            self.assertTrue(result.complete)
            self.assertEqual([row['path'] for row in result.rows], ['nested/deep/Needle.txt'])
            self.assertEqual(command.call_count, 1)
            self.assertIn('--recursive', command.call_args.args)
            with f.provider.open(result.rows[0]['path']) as stream:
                self.assertEqual(stream.read(), b'found')
            scoped = search_resources(f.provider, 'nested', 'needle')
            self.assertEqual(scoped.rows[0]['name'], 'deep/Needle.txt')
            self.assertTrue(scoped.complete)

    def test_open_stream_cached_bytes_reject_revocation_and_replacement(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            f.provider.list()
            with f.provider.open('note.md') as stream:
                self.assertEqual(stream.read(), f.original)
                stream.seek(0)
                session.forget(f.context)
                self.assertTrue(f.provider.closed)
                self.assertFalse(f.provider._cache._blocks)
                with self.assertRaisesRegex(ValueError, 'locked'):
                    stream.read(1)
                session.remember(f.context, {'Secret': {'type': 'crypt'}}, package_path=f.package)
                with self.assertRaisesRegex(ValueError, 'locked'):
                    stream.seek(0)

    def test_revocation_retires_private_window_and_blocks_reshow(self):
        from services.documents.ui.private_views import protect_private_view
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            window = qt.QMainWindow()
            window.setWindowTitle('Secret document sentinel')
            protect_private_view(window, f.provider)
            window.show()
            self.app.processEvents()
            session.forget(f.context)
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            self.assertFalse(window.isEnabled())
            self.assertNotIn('sentinel', window.windowTitle())
            window.show()
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            window.close()

    def test_private_view_guard_follows_save_as_provider(self):
        from types import SimpleNamespace
        from services.documents.ui.private_views import protect_private_view
        with TemporaryDirectory() as directory:
            first = SimpleNamespace(private=True, context=Path(directory) / 'first.session')
            second = SimpleNamespace(private=True, context=Path(directory) / 'second.session')
            for provider in (first, second):
                session.remember(provider.context, {'view': {'type': 'local'}})
                self.addCleanup(session.forget, provider.context)
            window = qt.QMainWindow()
            window.choice = SimpleNamespace(provider=first)
            protect_private_view(window, first)
            window.show()
            # ResourceTextWindow releases the old choice before publishing the
            # new choice. Its pending Save As destination owns the displayed draft.
            window.pending_choice = SimpleNamespace(provider=second)
            session.forget(first.context)
            self.app.processEvents()
            self.assertTrue(window.isVisible())
            window.choice, window.pending_choice = window.pending_choice, None
            session.forget(second.context)
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            window.close()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = qt.QApplication.instance() or qt.QApplication([])
        cls.binary = executable.get_rclone_path()
        if not cls.binary.is_file():
            if os.environ.get('LOGISTICS_REQUIRE_LOCALCRYPT_TESTS'):
                raise RuntimeError('Required pinned rclone is missing.')
            raise unittest.SkipTest('Pinned rclone executable not installed')

    def test_archive_reads_reuse_revision_checked_memory_and_nested_listing(self):
        from io import BytesIO
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            f.provider.list()
            with patch.object(transport, 'run_bytes', wraps=transport.run_bytes) as commands:
                for name in ('plain.cbz', 'encrypted.cbz'):
                    document = ComicDocument(f.item.data / name, source=f.provider)
                    self.assertEqual(ComicPages(document.path, document).read_page(0)[0], f.image)
                self.assertEqual(commands.call_count, 3)
                commands.reset_mock()
                document = ComicDocument(f.item.data / 'plain.cbz', source=f.provider)
                self.assertEqual(ComicPages(document.path, document).read_page(0)[0], f.image)
                self.assertEqual(commands.call_count, 0)
            with f.provider.open('note.md') as stream:
                self.assertEqual(stream.read(), f.original)
            changed = b'# Changed revision\n'
            f.provider.write_bytes('note.md', changed, expected=f.original)
            with f.provider.open('note.md') as stream:
                self.assertEqual(stream.read(), changed)
            f.provider.mkdir('nested')
            f.provider.create_file('nested/child.md', BytesIO(changed))
            f.provider.list()
            rows = f.provider.list('nested')
            self.assertEqual(rows[0]['path'], 'nested/child.md')
            self.assertEqual(f.provider.read_bytes('nested/child.md'), changed)
            session.forget(f.context)
            with self.assertRaisesRegex(ValueError, 'locked'):
                with f.provider.open('note.md'):
                    pass
            f.provider.close()
            self.assertFalse(f.provider._cache._blocks)
            self.assertFalse(f.provider._cache._sizes)

    def test_decrypted_pull_remembers_package_after_session_restart(self):
        from features.rclone.localcrypt import connections as local_connections
        from features.rclone import ui_contributions
        from models.local_folder import LocalFolder
        from services.folders.entries import get_folder_entries
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            self.assertTrue(actions.pull_remote('Secret', f.context))
            item, = local_connections.connections()
            self.assertEqual(item.package, f.package)
            self.assertEqual(item.data.joinpath('note.md').read_bytes(), f.original)
            self.assertEqual(set(json.loads(item.record.read_text())), {'schema', 'package', 'remote'})
            self.assertNotIn(item.record, list(item.data.rglob('*')))
            session.forget(f.context)
            with patch.dict(session.registry._known_packages, {}, clear=True), \
                 patch.object(ui_contributions.credentials, 'get_loaded_credential_config_paths', return_value=[]):
                sources = ui_contributions._get_remote_sources()
                source, = [source for source in sources if source.name.endswith('— Local')]
                entry, = get_folder_entries(source.get_remote_names(), remote_source='rclone',
                                            remote_context=source.context, local_folders=source.get_local_folders(),
                                            include_local_only=False)
                self.assertEqual([action.name for action in ui_contributions._get_actions(entry)], ['Push...', 'Pull'])
                with patch.object(actions, 'pull_remote', return_value=True) as pull:
                    next(action for action in ui_contributions._get_actions(entry) if action.name == 'Pull').callback()
                pull.assert_called_once_with('Secret', item.context, package=f.package, review=True)
                with patch('features.rclone.localcrypt.ui.views.ensure_session', return_value=False) as unlock:
                    self.assertFalse(actions.push_to_cloud(LocalFolder(item.data), f.context))
                    unlock.assert_called_once_with(item.context, package=f.package)
                with patch('features.rclone.localcrypt.ui.views.ensure_session', return_value=True), \
                     patch('features.rclone.transfers.workflow.sync_transfer', return_value=True) as push:
                    self.assertTrue(actions.push_to_cloud(LocalFolder(item.data), f.context))
                    self.assertEqual(push.call_args.args, (item.data, 'Secret:'))
                    self.assertEqual(push.call_args.kwargs['config_path'], item.context)
            other = local_connections.LocalConnection(f.root / 'Other.zip', 'Secret', item.root)
            with self.assertRaisesRegex(ValueError, 'another credential package'):
                other.publish()

    def test_unaccepted_decrypted_pull_does_not_publish_association(self):
        from features.rclone.localcrypt import connections as local_connections
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f, \
             patch('features.rclone.transfers.sync.rclone_sync', return_value=False):
            self.assertFalse(actions.pull_remote('Secret', f.context))
            self.assertEqual(local_connections.connections(include_missing=True), [])

    def test_bulk_metadata_action_keeps_selected_encrypted_zip_comics(self):
        from io import BytesIO
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        from features.comics.ui.metadata_editor import MetadataEditor
        from commonUtils.archives.zip_access import is_encrypted
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f, \
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
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
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
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
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
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f, \
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
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f, \
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
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            f.provider.create_file('second.zip', BytesIO(f.provider.read_bytes('encrypted.cbz')))
            paths = [f.item.data / name for name in ('encrypted.cbz', 'second.zip')]
            before = [f.provider.encrypted_path(path).read_bytes() for path in paths]
            ini = f.provider.entry('remoteConfig.ini')
            f.provider.remove_empty('remoteConfig.ini', ini['revision'])
            with self.assertRaisesRegex(ValueError, 'No selected comics could be unlocked'):
                ComicSelection(paths, source=f.provider)
            self.assertEqual([f.provider.encrypted_path(path).read_bytes() for path in paths], before)

    def test_unloaded_accounts_need_an_existing_local_copy_to_show(self):
        import shutil
        from features.rclone import ui_contributions
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            self.assertTrue(actions.pull_remote('Secret', f.context))
            values = session.credentials(f.context)
            f.provider.close()
            session.forget(f.context)
            with patch.object(ui_contributions.credentials, 'get_loaded_credential_config_paths', return_value=[]):
                self.assertEqual(len(ui_contributions._get_remote_sources()), 2)
                shutil.rmtree(f.item.data)
                shutil.rmtree(f.root / 'Server/Local/Secret')
                self.assertEqual(ui_contributions._get_remote_sources(), [])
            session.remember(f.context, values, package_path=f.package)
            with patch.object(ui_contributions.credentials, 'get_loaded_credential_config_paths', return_value=[f.context]):
                source, = ui_contributions._get_remote_sources()
                self.assertIn('Secret', source.get_remote_names())
                self.assertEqual(source.get_local_folders(), [])

    def test_ciphertext_mirror_and_both_comic_layers_survive_edits_without_plaintext_files(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            self.assertEqual({row['name'] for row in f.provider.list()}, {'note.md', 'plain.cbz', 'encrypted.cbz', 'remoteConfig.ini', 'page.png'})
            self.assertEqual(f.provider.read_bytes('note.md'), f.original)
            f.provider.write_bytes('note.md', b'# Private fixture\n\nEdited locally.\n', expected=f.original)
            for name in ('plain.cbz', 'encrypted.cbz'):
                doc = ComicDocument(f.item.data / name, source=f.provider)
                self.assertEqual(ComicPages(doc.path, doc).read_page(0)[0], f.image)
                doc.save({'Title': 'Private metadata sentinel'})
                reopened = ComicDocument(doc.path, source=f.provider)
                self.assertEqual(reopened.info.get_field('Title'), 'Private metadata sentinel')
                self.assertEqual(ComicPages(doc.path, reopened).read_page(0)[0], f.image)
                self.assertEqual(reopened.password is not None, name == 'encrypted.cbz')
            for file in f.item.data.rglob('*'):
                if file.is_file():
                    data = file.read_bytes()
                    self.assertNotIn(b'Edited locally.', data)
                    self.assertNotIn(b'Private metadata sentinel', data)
                    self.assertNotIn(f.image, data)
            before = {str(path.relative_to(f.item.data)): path.read_bytes() for path in f.item.data.rglob('*') if path.is_file()}
            self.assertTrue(actions.push_to_cloud(local_crypt.LocalCryptFolder(f.item), f.context))
            after = {str(path.relative_to(f.cloud)): path.read_bytes() for path in f.cloud.rglob('*') if path.is_file()}
            self.assertEqual(before, after)  # No double encryption on upload.
            record = json.loads(f.item.record.read_text())
            self.assertEqual(set(record), {'schema', 'package', 'remote'})
            self.assertEqual(record['schema'], 2)
            self.assertEqual(f.item.data, f.root / 'Application Support' / 'Logistics' / 'LocalCrypt' / 'Secret')
            self.assertEqual(copy_mapping.for_path(f.item.data), f.item)
            self.assertNotIn('password', f.item.record.read_text())

    def test_stale_failed_and_linked_saves_preserve_ciphertext_and_session_expiry_requires_zip(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            target = f.provider.encrypted_path('note.md')
            prior = target.read_bytes()
            with self.assertRaisesRegex(ValueError, 'changed'):
                f.provider.write_bytes('note.md', b'# stale', expected=b'wrong original')
            self.assertEqual(target.read_bytes(), prior)
            with patch.object(f.provider, 'command', side_effect=OSError('Synthetic failure')):
                with self.assertRaises(OSError):
                    f.provider.write_bytes('note.md', b'# failed', expected=f.original)
            self.assertEqual(target.read_bytes(), prior)
            self.assertEqual(copy_mapping.push_target(f.item.data, f.context), 'Cloud:' + str(f.cloud))
            with self.assertRaises(ValueError):
                copy_mapping.push_target(f.item.data, f.root / 'Different.session')
            session.forget(f.context)
            with self.assertRaises(ValueError):
                f.provider.read_bytes('note.md')
            from commonUtils.archives.zip_access import ArchivePasswordError
            with self.assertRaises(ArchivePasswordError):
                copy_mapping.unlock(f.item, 'wrong package password')
            self.assertIsNone(session.credentials(f.context))
            self.assertEqual(copy_mapping.unlock(f.item, 'synthetic-package-password')['Secret']['type'], 'crypt')

    def test_regular_browser_routes_navigation_and_reuses_private_tab(self):
        from desktop.file_browser import FileBrowserPage, _browser_view, _new_browser_tab, _crypt_location
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f, \
             patch('features.application.registry.get_browser_extensions', return_value=[]), \
             patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary):
            page = FileBrowserPage(root_path=f.root)
            original = page.workspace.active_view
            browser = original.file_browser
            try:
                browser.navigate(f.item.data)
                self.wait(lambda: isinstance(page.workspace.active_view, CryptBrowserView))
                private = page.workspace.active_view
                self.wait(lambda: not private.file_browser.operation.busy)
                self.assertTrue(private.view_title.startswith('🕵️ Private - '))
                self.assertEqual(private.file_browser.tree.topLevelItemCount(), 5)
                self.assertIn('note.md', [private.file_browser.tree.topLevelItem(i).text(0) for i in range(5)])
                self.assertEqual(browser.navigation.directory, f.root)
                with patch('desktop.file_browser.time.monotonic', return_value=123), \
                     patch('desktop.file_browser._crypt_location', return_value=(f.item, True)) as resolve, \
                     patch.object(copy_mapping, 'storage_root', return_value=f.item.root) as root_lookup:
                    for _ in range(1000):
                        self.assertTrue(original._directory_boundary(f.item.data))
                    resolve.assert_called_once()
                    root_lookup.assert_called_once()
                # Ciphertext I/O paths may carry Windows' extended prefix.
                # Both spellings must route privately before any OS activation.
                for raw in (f.item.data, native_path(f.item.data), f.provider.encrypted_path('note.md')):
                    self.assertEqual(_crypt_location(raw), (f.item, True))
                index = browser.model.index(str(f.item.data))
                self.assertTrue(index.isValid())
                self.assertEqual(browser.model.rowCount(index), 0)
                self.assertFalse(browser.model.canFetchMore(index))
                browser.set_directory(f.item.data)
                self.wait(lambda: not original._crypt_route_pending)
                self.assertEqual(len(page.workspace.docks), 2)
                # Breadcrumb, tree expansion, columns and direct view roots all route.
                for invoke in (lambda: browser.navigation.requested.emit(f.item.data),
                               lambda: browser.views.set_root(f.item.data),
                               lambda: browser.views._expanded(browser.sort_model.mapFromSource(index)),
                               lambda: browser._activate_path(f.provider.encrypted_path('note.md'))):
                    invoke()
                    self.wait(lambda: not original._crypt_route_pending)
                    self.assertEqual(browser.navigation.directory, f.root)
                    self.assertEqual(len(page.workspace.docks), 2)
                browser.views.set_mode(2)
                browser.views.select_source(index)
                self.wait(lambda: not browser.views._column_selection_pending and not original._crypt_route_pending)
                self.assertEqual(browser.navigation.directory, f.root)
                self.assertEqual(len(page.workspace.docks), 2)
                alias = f.root / 'alias'
                alias.symlink_to(f.item.data, target_is_directory=True)
                aliased = _browser_view(alias)
                try:
                    self.assertIsInstance(aliased, CryptBrowserView)
                    self.wait(lambda: not aliased.file_browser.operation.busy)
                    self.assertEqual(aliased.file_browser.navigation.directory, f.item.data)
                finally:
                    self.wait(aliased.prepare_close)
                    aliased.close()
                # A private new tab keeps a logical path, never a ciphertext path.
                f.provider.mkdir('Readable folder')
                private.file_browser.navigate(f.item.data / 'Readable folder')
                self.wait(lambda: not private.file_browser.operation.busy)
                page.workspace._activate(next(dock for dock in page.workspace.docks if dock.widget() is private))
                cloned = _new_browser_tab(page.workspace)
                self.wait(lambda: not cloned.file_browser.operation.busy)
                self.assertEqual(cloned.file_browser.navigation.directory, f.item.data / 'Readable folder')
                unmapped = f.item.root / 'unmapped'
                unmapped.mkdir()
                with patch.object(qt.QMessageBox, 'warning') as warning:
                    browser.navigate(unmapped)
                    self.wait(lambda: not original._crypt_route_pending)
                    warning.assert_called_once()
            finally:
                self.wait(page.prepare_close)
                page.close()

    def test_hub_refresh_reads_local_and_crypt_folders_once_for_many_accounts(self):
        from features.rclone.ui_contributions import _get_remote_sources
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f, \
             patch('features.rclone.credentials.get_loaded_credential_config_paths',
                   return_value=[f.context, *(f.root / f'account{i}.session' for i in range(7))]), \
             patch('models.folder_discovery.get_local_folders', return_value=[]) as ordinary, \
             patch.object(copy_mapping, 'connections', wraps=copy_mapping.connections) as copies:
            sources = _get_remote_sources()
            for source in sources:
                source.get_local_folders()
            ordinary.assert_called_once()
            copies.assert_called_once()

    def test_folder_sources_do_not_duplicate_the_same_encrypted_copy(self):
        from features.rclone.ui_contributions import _get_remote_sources, CopyContext
        from types import SimpleNamespace
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f, \
             patch('features.rclone.credentials.get_loaded_credential_config_paths', return_value=[f.context]), \
             patch('models.folder_discovery.get_local_folders', return_value=[]) as local:
            sources = _get_remote_sources()
            self.assertEqual(len(sources), 1)
            self.assertIsInstance(sources[0].get_local_folders()[0], local_crypt.LocalCryptFolder)
            local.return_value = [SimpleNamespace(name='Secret', path=f.root / 'Local' / 'Secret')]
            sources = _get_remote_sources()
            self.assertEqual(len(sources), 2)
            self.assertIsInstance(sources[1].context, CopyContext)
            with patch('features.rclone.credentials.get_loaded_credential_config_paths', return_value=[]):
                self.assertEqual(len(_get_remote_sources()), 1)

    def wait(self, predicate, seconds=30):
        deadline = time.monotonic() + seconds
        while not predicate():
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()

    def test_linked_root_is_supported_but_inner_links_name_the_offending_path(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            actual = f.root / 'relocated-ciphertext'
            f.item.data.rename(actual)
            f.item.data.symlink_to(actual, target_is_directory=True)
            copy_mapping.validate_ciphertext_tree(f.item)
            self.assertEqual(copy_mapping.for_path(f.item.data), f.item)
            provider = local_crypt.CryptResources(f.item, binary=self.binary)
            try:
                self.assertEqual(provider.read_bytes('note.md'), f.original)
                self.assertEqual(copy_mapping.push_target(f.item.data, f.context), 'Cloud:' + str(f.cloud))
                self.assertTrue(actions.push_to_cloud(local_crypt.LocalCryptFolder(f.item), f.context))
                self.assertTrue(actions.pull_encrypted_copy('Secret', f.context))
                self.assertTrue(f.item.data.is_symlink())
                linked = f.item.data / 'bad-link'
                linked.symlink_to(f.root / 'plain', target_is_directory=True)
                with self.assertRaises(ValueError) as error:
                    copy_mapping.validate_ciphertext_tree(f.item)
                self.assertIn(str(linked), str(error.exception))
                with self.assertRaises(ValueError):
                    provider.list()
                with self.assertRaises(ValueError):
                    copy_mapping.push_target(f.item.data, f.context)
                linked.unlink()
                linked = f.item.data / 'bad-hard-link'
                os.link(provider.encrypted_path('note.md'), linked)
                with self.assertRaises(ValueError) as error:
                    copy_mapping.validate_ciphertext_tree(f.item)
                self.assertIn('independent regular files:', str(error.exception))
                linked.unlink()
                f.item.record.unlink()
                with self.assertRaisesRegex(ValueError, 'no valid credential mapping'):
                    copy_mapping.push_target(f.item.data, f.context)
            finally:
                provider.close()

    def test_private_browser_shared_views_render_comic_covers_in_memory(self):
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        from commonUtils.ui.file_browser.views import BrowserViews
        from commonUtils.ui.readers.reader_menus import RecentFiles
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f, \
             patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary), \
             patch.object(RecentFiles, 'add', side_effect=AssertionError('Private thumbnails wrote recents')):
            view = CryptBrowserView(f.item)
            view.resize(1100, 750)
            view.show()
            browser = view.file_browser
            try:
                self.wait(lambda: not browser.busy)
                self.assertIsInstance(browser.views, BrowserViews)
                self.assertIsNone(browser.views.storage)
                self.assertEqual(set(browser.view_selector.buttons), {0, 1, 2})
                document = ComicDocument(f.item.data / 'plain.cbz', source=f.provider)
                document.save({'Title': 'Private panel metadata'})
                browser.refresh()
                self.wait(lambda: not browser.busy)
                browser.views.select_source(browser.model.browse_index(f.item.data / 'plain.cbz'))
                self.wait(lambda: browser.tabs.count() == 2 and not browser.busy)
                self.assertIn('Private panel metadata', browser.tabs.widget(1).toPlainText())
                self.assertEqual(browser.tabs.tabText(1), 'Comic Metadata')
                self.assertTrue(browser.preview_panel.isVisible())
                browser.views.select_source(browser.model.browse_index(f.item.data / 'page.png'))
                self.wait(lambda: browser.tabs.count() == 2 and browser.tabs.tabText(1) == 'Image Information' and not browser.busy)
                self.assertIn('Width: 24', browser.tabs.widget(1).toPlainText())
                self.assertIn('Height: 32', browser.tabs.widget(1).toPlainText())
                browser.view_selector.setCurrentIndex(1)
                paths = [f.item.data / name for name in ('plain.cbz', 'encrypted.cbz', 'page.png')]
                self.wait(lambda: all(path in browser.views.covers.icons for path in paths) and not browser.busy)
                self.assertTrue(all(not browser.views.covers.icons[path].isNull() for path in paths))
                self.assertFalse(browser.persistent_index)
                f.provider.mkdir('Readable folder')
                browser.refresh()
                self.wait(lambda: not browser.busy)
                browser.view_selector.setCurrentIndex(2)
                browser.views.select_source(browser.model.browse_index(f.item.data / 'Readable folder'))
                self.wait(lambda: browser.navigation.directory == f.item.data / 'Readable folder' and not browser.busy)
            finally:
                self.wait(view.prepare_close)
                self.assertEqual(len(browser.views.covers.icons), 0)
                view.close()

    def test_regular_and_private_file_passwords_retry_in_the_same_prompt(self):
        from PySide6.QtTest import QTest
        from desktop.dialogs.archive_password import ask_password, ValidatedPasswordDialog
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            for source, path in ((None, f.plain / 'encrypted.cbz'), (f.provider, f.item.data / 'encrypted.cbz')):
                state = {'phase': 0, 'checks': [], 'timeout': time.monotonic() + 10}
                timer = qt.QTimer()
                def drive():
                    dialogs = [widget for widget in self.app.topLevelWidgets()
                               if isinstance(widget, ValidatedPasswordDialog) and widget.isVisible()]
                    if not dialogs:
                        return
                    dialog = dialogs[0]
                    if time.monotonic() > state['timeout']:
                        dialog.reject()
                    elif state['phase'] == 0:
                        state['phase'] = 1
                        dialog.password.setText('wrong password')
                        QTest.keyClick(dialog.password, qt.Qt.Key.Key_Return)
                    elif state['phase'] == 1 and dialog.error.text() and not dialog.operation.busy:
                        state['checks'] = [dialog.password.text() == '', dialog.password.hasFocus(),
                                           'Incorrect password' in dialog.error.text()]
                        state['phase'] = 2
                        dialog.password.setText('synthetic-archive-password')
                        QTest.keyClick(dialog.password, qt.Qt.Key.Key_Enter)
                timer.timeout.connect(drive)
                timer.start(10)
                try:
                    self.assertEqual(ask_password(path, 'Unlock this file.', source=source), 'synthetic-archive-password')
                    self.assertEqual(state['checks'], [True, True, True])
                finally:
                    timer.stop()
                    timer.deleteLater()

    def test_browser_markdown_and_metadata_use_memory_only_hosts(self):
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        from features.comics.ui.metadata_editor import MetadataEditor
        from commonUtils.ui.readers.reader_menus import RecentFiles
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            with patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary), \
                 patch.object(RecentFiles, 'add', side_effect=AssertionError('Private reader must not persist a recent filename')):
                view = CryptBrowserView(f.item)
                self.wait(lambda: not view.file_browser.operation.busy)
                self.assertFalse(view.file_browser.persistent_index)
                self.assertEqual(view.file_browser.tree.topLevelItemCount(), 5)
                self.assertFalse(hasattr(view.file_browser, 'index_search'))
                with patch('features.rclone.localcrypt.ui.views.show_document') as present:
                    view.open_document(f.item.data / 'note.md')
                    self.wait(lambda: not view.open_operation.busy)
                window = present.call_args.args[0]
                try:
                    self.assertEqual(window.viewer.editor.toPlainText(), f.original.decode())
                    self.assertIs(window.viewer.pages.currentWidget(), window.viewer.browser)
                    self.assertFalse(window.viewer.edit_button.isChecked())
                    self.assertTrue(window.viewer.save_as_action.isEnabled())
                    self.assertTrue(window.viewer.open_action.isEnabled())
                    image = window.viewer.browser.loadResource(qt.QTextDocument.ResourceType.ImageResource,
                                                               qt.QUrl.fromLocalFile(str(f.item.data / 'page.png')))
                    self.assertFalse(image.isNull())
                    window.viewer.set_edit_mode('source')
                    window.viewer.editor.setPlainText('# Changed through private Markdown UI')
                    window.viewer.editor.document().setModified(True)
                    self.assertFalse(window.viewer.save_document())
                    self.wait(lambda: not window.viewer.storage.operation.busy)
                    self.assertEqual(f.provider.read_bytes('note.md'), b'# Changed through private Markdown UI')
                    self.assertFalse(window.viewer.is_modified)
                finally:
                    window.close()
                editor = MetadataEditor(f.item.data / 'encrypted.cbz', source=f.provider)
                try:
                    self.wait(lambda: not editor.busy)
                    self.assertIsNotNone(editor.document, editor.message.text())
                    self.assertTrue(editor.document.private)
                finally:
                    editor.close()
                    view.prepare_close()
                    self.wait(lambda: not view.open_operation.busy and not view.file_browser.operation.busy)
                    view.close()

    def test_forgetting_parent_removes_private_keys_and_reunlock_requires_new_provider(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            private_context = f.provider.context
            self.assertIsNotNone(session.credentials(private_context))
            session.forget(f.context)
            self.assertIsNone(session.credentials(private_context))
            copy_mapping.unlock(f.item, 'synthetic-package-password')
            with self.assertRaisesRegex(ValueError, 'Reopen'):
                f.provider.read_bytes('note.md')
            with_provider = local_crypt.CryptResources(f.item, binary=self.binary)
            try:
                self.assertEqual(with_provider.read_bytes('note.md'), f.original)
            finally:
                with_provider.close()

    def test_provider_owners_release_keys_only_after_last_document(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            browser = f.provider.acquire()
            document = f.provider.acquire()
            browser()
            browser()  # Closing plus destruction is safe.
            self.assertEqual(f.provider.read_bytes('note.md'), f.original)
            document()
            self.assertIsNone(session.credentials(f.provider.context))
            self.assertTrue(f.provider.closed)

    def test_cancel_before_publication_preserves_original_and_cleans_staging(self):
        from threading import Event
        from commonUtils.runtime.operations import OperationCancelled
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            before = {str(p): p.read_bytes() for p in f.item.data.rglob('*') if p.is_file()}
            cancelled = Event()
            with f.provider.operation(cancelled.is_set):
                with self.assertRaises(OperationCancelled):
                    f.provider.replace_stream('note.md', lambda stream: stream.write(b'# cancelled'),
                        expected_revision=f.provider.version('note.md'), verify=lambda path: cancelled.set())
            self.assertEqual(before, {str(p): p.read_bytes() for p in f.item.data.rglob('*') if p.is_file()})
            with self.assertRaises(OperationCancelled):
                with f.provider.operation(lambda: True):
                    f.provider.read_bytes('note.md')
            self.assertEqual(f.provider.read_bytes('note.md'), f.original)

    def test_malformed_records_and_specific_push_never_fall_back_inside_localcrypt(self):
        from types import SimpleNamespace
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            bad = f.item.record.parent / 'malformed.json'
            for text in ('[]', 'null', '123', '"text"', '{broken'):
                bad.write_text(text)
                self.assertEqual(copy_mapping.connections(), [f.item])
            folder = SimpleNamespace(name='Secret')
            with patch('features.rclone.transfers.workflow.sync_transfer', return_value=True) as transfer:
                actions.push_specific_directory(folder, f.context, str(f.item.data))
                self.assertEqual(transfer.call_args.args[1], copy_mapping.push_target(f.item.data, f.context, folder.name, specific=True))
                self.assertFalse(transfer.call_args.kwargs['copy_links'])
                f.item.record.unlink()
                transfer.reset_mock()
                with self.assertRaisesRegex(ValueError, 'no valid credential mapping'):
                    actions.push_specific_directory(folder, f.context, str(f.item.data))
                transfer.assert_not_called()

    def test_cancelled_open_never_presents_a_document(self):
        from threading import Event
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        with self.temporary_directory() as directory, crypt_fixture(directory, self.binary) as f:
            with patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary):
                view = CryptBrowserView(f.item)
                self.wait_until(lambda: not view.file_browser.operation.busy)
                entered, finish = Event(), Event()
                def prepare(provider, path):
                    entered.set()
                    finish.wait(5)
                    return f.original, {}
                with patch('features.rclone.localcrypt.ui.views.prepare_markdown', side_effect=prepare), \
                     patch('features.rclone.localcrypt.ui.views.show_document') as show:
                    view.open_document(f.item.data / 'note.md')
                    self.wait_until(entered.is_set)
                    view.open_operation.request_cancel()
                    finish.set()
                    self.wait_until(lambda: not view.open_operation.busy)
                    show.assert_not_called()
                context = view.provider.context
                # Closing may be deferred while an owned preview/listing worker
                # retires. Exercise that state deliberately instead of racing
                # the machine's completion speed and assuming close succeeded.
                pending, cancelled = Event(), Event()
                pending.set()
                view.file_browser.operations.own(pending, busy=pending.is_set, cancel=cancelled.set)
                try:
                    self.assertFalse(view.close())
                    self.assertTrue(cancelled.is_set())
                    self.assertIsNotNone(session.credentials(context))
                finally:
                    pending.clear()
                self.wait_until(view.close, message='Private browser did not finish cooperative close')
                self.assertIsNone(session.credentials(context))

    def test_specific_push_preview_matches_execution_and_reports_lost_mapping(self):
        from types import SimpleNamespace
        from features.rclone.transfers.ui.push_dialog import RclonePushDialog
        with self.temporary_directory() as directory, crypt_fixture(directory, self.binary) as f:
            entry = SimpleNamespace(name='Secret', local=SimpleNamespace(path=f.plain, name='Secret'),
                                    remote_source='rclone', remote_context=f.context, remote_name='Secret')
            dialog = RclonePushDialog(entry)
            dialog.specific_radio.setChecked(True)
            dialog.specific_path.setText(str(f.item.data))
            self.assertEqual(dialog.result_destination.text(), 'Cloud:' + str(f.cloud))
            f.item.record.unlink()
            with patch('features.rclone.transfers.ui.push_dialog.ui.display_msg_box_ok') as message, \
                 patch('features.rclone.transfers.workflow.sync_transfer') as transfer:
                dialog._push()
                transfer.assert_not_called()
                self.assertIn('no valid credential mapping', message.call_args.args[1])
                self.assertIn('no valid credential mapping', dialog.result_destination.text())
            dialog.close()

    def test_pull_choices_follow_selected_copy(self):
        from features.rclone.ui_contributions import _get_actions, _matching_local_folders
        from models.folder_entry import FolderEntry
        from types import SimpleNamespace
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            entry = FolderEntry('Secret', remote_name='Secret', remote_source='rclone', remote_context=f.context)
            self.assertEqual([a.name for a in _get_actions(entry)], ['Pull'])
            entry.local = SimpleNamespace(name='Secret')
            names = [a.name for a in _get_actions(entry)]
            self.assertIn('Pull', names)
            self.assertEqual(names, ['Push...', 'Pull'])
            with patch.object(actions, 'pull_remote') as plain:
                next(action for action in _get_actions(entry) if action.name == 'Pull').callback()
                plain.assert_called_once_with('Secret', f.context, review=True)
            entry.local = local_crypt.LocalCryptFolder(f.item)
            with patch.object(actions, 'pull_encrypted_copy') as encrypted, patch.object(actions, 'pull_remote') as plain:
                choices = {a.name: a for a in _get_actions(entry)}
                choices['Pull'].callback()
                encrypted.assert_called_once_with('Secret', f.context, item=f.item, review=True)
                plain.assert_not_called()
                self.assertEqual(set(choices), {'Push...', 'Pull'})
            with patch('models.folder_discovery.get_local_folders', return_value=[]):
                self.assertIsInstance(_matching_local_folders(f.context)[0], local_crypt.LocalCryptFolder)
            ordinary = SimpleNamespace(name='Secret')
            with patch('models.folder_discovery.get_local_folders', return_value=[ordinary]):
                self.assertEqual(_matching_local_folders(f.context), [ordinary])

    def test_private_epub_metadata_preserves_resources_and_inner_password(self):
        from io import BytesIO
        from zipfile import ZipFile
        from tests.books_fixture import make_book
        from commonUtils.archives.zip_access import open_archive, archive_manifest, is_encrypted
        from features.books.epub import EPUBBook
        from features.books.metadata import save_metadata
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
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

    def test_private_comic_picker_owns_provider_and_reused_reader_releases_extra_choice(self):
        from commonUtils.runtime.resources.selection import ResourceChoice
        from commonUtils.ui.readers.reader_menus import RecentFiles
        from services.documents.ui.readers import open_reader_choice
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            released = []
            def choice(label):
                lease = f.provider.acquire()
                def release():
                    released.append(label)
                    lease()
                return ResourceChoice(f.provider, 'encrypted.cbz', release)
            with patch.object(RecentFiles, 'add', side_effect=AssertionError('Private comic wrote recents')):
                window = open_reader_choice(choice('original'), None, 'comic')
                self.assertIsNotNone(window)
                try:
                    self.wait(lambda: not window.busy and not window.page_cache.busy)
                    self.assertTrue(window.pages.document.private)
                    self.assertTrue(window.windowTitle().startswith('🕵️ Private - '))
                    from services.documents.reader_positions import PrivateComicState
                    self.assertIsInstance(window._state, PrivateComicState)
                    with self.assertRaises(PermissionError):
                        _ = window._state.state.cipher.identity
                    with patch('commonUtils.persistence.atomic_write_bytes', side_effect=AssertionError('Passwordless checkpoint wrote disk')):
                        window._state.save(0, window.pages.pages)
                    self.assertEqual(window._state.state.memory['page'], 0)
                    self.assertTrue(window.menus.shared.open_action.isEnabled())
                    self.assertEqual(released, [])
                    reused = open_reader_choice(choice('extra'), None, 'comic')
                    self.assertIs(reused, window)
                    self.assertEqual(released, ['extra'])
                finally:
                    self.wait(lambda: not window.busy and not window.page_cache.busy)
                    window.shutdown()
                    window.close()
                    self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
                    self.app.processEvents()
                self.assertEqual(released, ['extra', 'original'])

    def test_private_epub_picker_reads_and_saves_metadata_without_persistent_state(self):
        from io import BytesIO
        from tests.books_fixture import make_book
        from commonUtils.runtime.resources.selection import ResourceChoice
        from commonUtils.ui.readers.reader_menus import RecentFiles
        from features.books.epub import EPUBBook
        from services.documents.ui.readers import open_reader_choice
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
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
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
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
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
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

    def test_private_markdown_save_as_retargets_local_and_crypt_without_overwrite(self):
        from features.rclone.localcrypt.ui.views import MarkdownStorage, PrivateMarkdownWindow
        from commonUtils.runtime.resources.local import LocalFiles
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            path = f.item.data / 'note.md'
            storage = MarkdownStorage(f.provider, path, f.original, {}, lambda *_: None)
            window = PrivateMarkdownWindow(path, storage)
            window.viewer.edit_mode.setCurrentIndex(window.viewer.edit_mode.findData('source'))
            try:
                local_root = Path(directory) / 'save-as-local'
                local_root.mkdir()
                local = LocalFiles(local_root)
                window.viewer.editor.setPlainText('# Save As draft')
                window.viewer.editor.document().setModified(True)
                self.assertTrue(window.viewer.save_as_action.isEnabled())
                with patch('services.documents.ui.markdown.choose_destination', return_value=(local, 'exported.md', lambda: None)), \
                        patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
                    window.viewer.save_as_dialog()
                self.wait(lambda: not storage.operation.busy)
                self.assertEqual((local_root / 'exported.md').read_bytes(), b'# Save As draft')
                self.assertEqual(window.windowTitle(), '🕵️ Private - exported.md — Markdown')
                with patch('services.documents.ui.editors.open_editor_choice') as linked:
                    window.viewer.storage.open_link(local_root / 'linked.md', 'anchor')
                    selected = linked.call_args.args[0]
                    self.assertIs(selected.provider, local)
                    self.assertEqual(selected.path, 'linked.md')
                    self.assertEqual(linked.call_args.kwargs['fragment'], 'anchor')
                    selected.close()

                self.assertEqual(f.provider.read_bytes('note.md'), f.original)
                window.viewer.editor.setPlainText('# Saved locally again')
                window.viewer.editor.document().setModified(True)
                window.viewer.save_document()
                self.wait(lambda: not storage.operation.busy)
                self.assertEqual((local_root / 'exported.md').read_bytes(), b'# Saved locally again')
                with patch('services.documents.ui.markdown.choose_destination', return_value=(f.provider, 'another.md', lambda: None)):
                    window.viewer.save_as_dialog()
                self.wait(lambda: not storage.operation.busy)
                self.assertEqual(f.provider.read_bytes('another.md'), b'# Saved locally again')
                window.viewer.editor.setPlainText('# Collision must retain draft')
                window.viewer.editor.document().setModified(True)
                with patch('services.documents.ui.markdown.choose_destination', return_value=(f.provider, 'note.md', lambda: None)):
                    window.viewer.save_as_dialog()
                self.wait(lambda: not storage.operation.busy)
                self.assertEqual(f.provider.read_bytes('note.md'), f.original)
                self.assertTrue(window.viewer.is_modified)
            finally:
                window.viewer.editor.document().setModified(False)
                window.viewer.formatted_editor.document().setModified(False)
                window.close()


class LocalCryptNamingTests(unittest.TestCase):
    def test_browser_recognizes_relocated_copy_and_external_aliases(self):
        from desktop.file_browser import _crypt_location
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            item = copy_mapping.Connection(root / 'one.zip', 'Secret', root / 'LocalCrypt')
            with patch('services.local_storage.install_local_storage_policy'), \
                 patch.object(copy_mapping, 'storage_root', return_value=item.root):
                item.publish()
                target = root / 'relocated'
                item.data.rename(target)
                item.data.symlink_to(target, target_is_directory=True)
                alias = root / 'shortcut'
                alias.symlink_to(target, target_is_directory=True)
                for path in (item.data, target, alias, alias / 'opaque-subfolder'):
                    self.assertEqual(_crypt_location(path), (item, True))
                self.assertEqual(_crypt_location(root), (None, False))

    def test_clean_name_repeat_publish_and_conflicts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'LocalCrypt'
            first = copy_mapping.Connection(Path(directory) / 'one.zip', 'Legacy-ComicRack', root)
            with patch('services.local_storage.install_local_storage_policy'):
                first.publish()
                self.assertEqual(first.data, root / 'Legacy-ComicRack')
                (first.data / 'sentinel').write_bytes(b'ciphertext')
                first.publish()
                self.assertEqual(copy_mapping.connections(root), [first])
                self.assertEqual(copy_mapping.for_path(first.data / 'sentinel', root), first)
                for name in ('Legacy-ComicRack', 'legacy-comicrack'):
                    other = copy_mapping.Connection(Path(directory) / 'two.zip', name, root)
                    with self.assertRaisesRegex(ValueError, 'another credential package'):
                        other.publish()
                    self.assertFalse(other.record.exists())
                self.assertEqual((first.data / 'sentinel').read_bytes(), b'ciphertext')
                first.record.unlink()
                with self.assertRaisesRegex(ValueError, 'without this credential mapping'):
                    first.publish()

    def test_unsupported_mapping_is_preserved_and_invalid_names_are_refused(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'LocalCrypt'
            current = copy_mapping.Connection(Path(directory) / 'one.zip', 'Secret', root)
            current.record.parent.mkdir(parents=True)
            original = json.dumps({'schema': 1, 'package': str(current.package), 'remote': current.remote}).encode()
            current.record.write_bytes(original)
            old_data = root / 'old-package-hash' / 'Secret-oldhash'
            old_data.mkdir(parents=True)
            (old_data / 'sentinel').write_bytes(b'preserve old ciphertext')
            with patch('services.local_storage.install_local_storage_policy'):
                self.assertEqual(copy_mapping.connections(root), [])
                with self.assertRaisesRegex(ValueError, 'existing LocalCrypt credential mapping is invalid'):
                    current.publish()
                self.assertFalse(current.data.exists())
                self.assertEqual(current.record.read_bytes(), original)
                self.assertEqual((old_data / 'sentinel').read_bytes(), b'preserve old ciphertext')
                for name in ('../escape', '.connections', 'a/b', 'a\\b', 'CON', 'trailing.', 'trailing '):
                    with self.assertRaises(ValueError):
                        copy_mapping.Connection(current.package, name, root).publish()
