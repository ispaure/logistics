"""Browser and Notes Library renames retain references across real crypt modes."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION

from pathlib import Path
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from services.documents.catalog import DocumentCatalog


from tests.resources.rename_cases import RenameCase


class RenameReferenceTests(RenameCase):
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

    def test_local_browser_and_notes_file_folder_renames(self):
        for notes in (False, True):
            with self.subTest(notes=notes), self.temporary_directory() as directory:
                self.exercise_renames(Path(directory), notes=notes)

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
