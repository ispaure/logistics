"""Browser and Notes Library renames retain references across real crypt modes."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION

from contextlib import nullcontext
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from services.documents.catalog import DocumentCatalog
from desktop.document_catalog import source_reference
from features.rclone import executable
from tests.local_crypt_fixture import crypt_fixture


class RenameReferenceTests(QtTestCase):
    def test_desktop_recent_rename_is_independent_of_a_failed_favourites_catalog(self):
        from desktop.document_catalog import relocate
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            stores = {recent: DocumentCatalog(root / 'lists', recent=recent) for recent in (False, True)}
            stores[True].remember(dict(type='local', path=str(root / 'Before.md')),
                                  'Before.md', dict(editor='markdown'))
            with patch('desktop.document_catalog.catalog', side_effect=lambda recent=False: stores[recent]), \
                    patch.object(stores[False], 'relocate', side_effect=OSError('Unreadable favourites')):
                with self.assertRaises(OSError):
                    relocate(LocalFiles(root), 'Before.md', 'After.md')
            row = stores[True].entries('recent')[0]
            self.assertEqual(row['source']['path'], str(root / 'After.md'))
            self.assertEqual(row['title'], 'After.md')

    def test_committed_rename_notifies_host_even_when_refresh_fails(self):
        from commonUtils.ui.resources.browser import ResourceBrowser
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Before.md').write_bytes(b'keep bytes')
            provider = LocalFiles(root)
            browser = ResourceBrowser(provider, preview=False)
            browser.show()
            self.wait_until(lambda: not browser.busy)
            committed = []
            browser.renamed.connect(lambda source, target: committed.append((source, target)))
            with patch.object(qt.QInputDialog, 'getText', return_value=('After.md', True)), \
                    patch.object(provider, 'list', side_effect=OSError('Refresh unavailable')):
                browser._rename(dict(path='Before.md', name='Before.md', directory=False))
                self.wait_until(lambda: not browser.busy)
            self.assertEqual(committed, [('Before.md', 'After.md')])
            self.assertEqual((root / 'After.md').read_bytes(), b'keep bytes')
            browser.close()

    def exercise_renames(self, root, *, fixture=None, notes=False):
        root = root.resolve()
        from desktop.file_browser import BrowserView
        from features.notes_library.ui.notes_library import NotesLibraryWindow
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        from features.rclone.localcrypt.backend import CryptResources
        provider = fixture.provider if fixture else LocalFiles(root)
        provider.mkdir('Folder Ω')
        provider.create_file('Folder Ω/Private note.md', BytesIO(b'# Original bytes\n'))
        stores = {recent: DocumentCatalog(root / 'lists', recent=recent) for recent in (False, True)}
        source, cipher = source_reference(provider.root / 'Folder Ω/Private note.md', provider)
        opener = dict(editor='notes', root='Folder Ω' if fixture else str(root / 'Folder Ω'))
        for recent, store in stores.items():
            store.remember(source, 'Private note.md', opener, favourite=not recent, cipher=cipher)
        factory = (lambda: CryptResources(fixture.item, binary=provider.binary)) if fixture else lambda: LocalFiles(root)
        with patch('desktop.document_catalog.catalog', side_effect=lambda recent=False: stores[recent]), \
                patch('features.application.registry.get_browser_extensions', return_value=[]), \
                (patch('features.rclone.executable.get_rclone_path', return_value=provider.binary) if fixture else nullcontext()):
            view = (NotesLibraryWindow(factory, 'Rename test') if notes else
                    CryptBrowserView(fixture.item) if fixture else BrowserView(root_path=root))
            self.addCleanup(lambda: view.close() if __import__('shiboken6').isValid(view) else None)
            view.show()
            browser = None if notes else view.file_browser
            def settled():
                self.wait_until(lambda: not view.progress.busy if notes else not browser.busy,
                                timeout=20 if fixture else 5)
            settled()
            if notes:
                self.assertIsNotNone(view.library, view.progress.message.text())
                view.open_note('Folder Ω/Private note.md')
                settled()
            for before, after in [('Folder Ω/Private note.md', 'Folder Ω/Renamed café.md'),
                                  ('Folder Ω', 'Moved Ω')]:
                if notes:
                    view.rename_tree_entry(before, Path(after).name)
                    settled()
                elif fixture:
                    with patch.object(qt.QInputDialog, 'getText', return_value=(Path(after).name, True)):
                        browser._rename(dict(path=before, name=Path(before).name, directory='/' not in before))
                    settled()
                else:
                    index = browser.model.index(str(root / before))
                    self.wait_until(index.isValid)
                    self.assertTrue(browser.model.setData(index, Path(after).name))
                    qt.QApplication.processEvents()
                expected = ('Folder Ω/Renamed café.md' if '/' in before else 'Moved Ω/Renamed café.md')
                with provider.open(expected) as stream:
                    self.assertEqual(stream.read(), b'# Original bytes\n')
                if notes:
                    self.assertEqual(view.history[view.index], expected)
                    self.assertEqual(view.storage.path, (provider.root / expected).resolve())
                for recent, store in stores.items():
                    rows = store.entries('recent' if recent else 'favourites', ciphers=[cipher] if cipher else [])
                    self.assertEqual(len(rows), 1)
                    row = rows[0]
                    self.assertEqual(row['source'], source_reference(provider.root / expected, provider)[0])
                    self.assertEqual(row['title'], 'Renamed café.md')
                    self.assertEqual(row['id'], store.identity(row['source']))
                    folder = expected.rpartition('/')[0]
                    self.assertEqual(row['opener']['root'], folder if fixture else str(root / folder))
                    if cipher:
                        self.assertNotIn(b'Renamed', store.path(cipher).read_bytes())
            # A collision must preserve both files and all saved references.
            provider.create_file('Moved Ω/Taken.md', BytesIO(b'# Keep destination'))
            original_lists = {recent: store.path(cipher).read_bytes() for recent, store in stores.items()}
            if notes:
                view.rename_tree_entry('Moved Ω/Renamed café.md', 'Taken.md')
                settled()
            elif fixture:
                with patch.object(qt.QInputDialog, 'getText', return_value=('Taken.md', True)):
                    browser._rename(dict(path='Moved Ω/Renamed café.md', name='Renamed café.md', directory=False))
                settled()
            else:
                with patch.object(qt.QMessageBox, 'warning'):
                    self.assertFalse(browser.model.setData(browser.model.index(str(root / 'Moved Ω/Renamed café.md')), 'Taken.md'))
            for path, data in [('Moved Ω/Renamed café.md', b'# Original bytes\n'), ('Moved Ω/Taken.md', b'# Keep destination')]:
                with provider.open(path) as stream:
                    self.assertEqual(stream.read(), data)
            for recent, store in stores.items():
                self.assertEqual(store.path(cipher).read_bytes(), original_lists[recent])
            if notes:
                view.open_note('Moved Ω/Renamed café.md')
                settled()
                view.viewer.set_edit_mode('source')
                view.viewer.active_editor().insertPlainText('Edited after renames. ')
                view.viewer.save_document()
                settled()
                self.assertFalse(view.viewer.is_modified, view.viewer.status.text())
                with provider.open('Moved Ω/Renamed café.md') as stream:
                    self.assertIn(b'Edited after renames.', stream.read())
            else:
                settled()
            view.close()

    def test_local_browser_and_notes_file_folder_renames(self):
        for notes in (False, True):
            with self.subTest(notes=notes), self.temporary_directory() as directory:
                self.exercise_renames(Path(directory), notes=notes)

    def test_localcrypt_browser_and_notes_name_encryption_modes(self):
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone executable not installed')
        for mode, directory_names in [(mode, encrypted) for mode in ('standard', 'obfuscate', 'off')
                                      for encrypted in (True, False)]:
            for notes in (False, True):
                with self.subTest(mode=mode, directory_names=directory_names, notes=notes), self.temporary_directory() as directory:
                    settings = dict(filename_encryption=mode, directory_name_encryption=str(directory_names).lower())
                    with crypt_fixture(directory, binary, crypt_settings=settings, state_password='fixture-password') as fixture:
                        self.exercise_renames(Path(directory), fixture=fixture, notes=notes)

    def test_remote_plain_and_encrypted_renames_are_unavailable(self):
        from commonUtils.runtime.resources.provider import capabilities
        from commonUtils.runtime.resources.mutations import rename_resource
        from commonUtils.ui.resources.browser import ResourceBrowser
        from features.rclone.remote_resources import RemoteResources
        from features.rclone.mobile.remote_resources import NativeRemoteResources
        for provider_type in (RemoteResources, NativeRemoteResources):
            provider = object.__new__(provider_type)
            provider.root = Path('/synthetic-remote')
            provider.storage_id = 'remote'
            provider.storage_namespace = 'fixture'
            self.assertFalse(capabilities(provider).rename)
            for path in ('Note.md', 'Folder'):
                with self.assertRaises((PermissionError, ValueError)):
                    rename_resource(provider, path, 'Renamed')
        host = type('Host', (), dict(busy=False, closing=False, provider=provider))()
        with patch.object(qt.QInputDialog, 'getText', side_effect=AssertionError('Read-only rename prompt')):
            ResourceBrowser._rename(host, dict(path='Note.md', name='Note.md'))
