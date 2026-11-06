"""Folder inventories avoid document metadata while retaining provider policy."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from features.notes_library import library_files
from features.notes_library.notes import NotesLibrary

TEST_STAGE = TestStage.REGRESSION


class LibraryFolderTests(unittest.TestCase):
    def test_local_folder_snapshot_uses_names_without_entry_or_body_reads(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Folder').mkdir()
            (root / 'Folder/Folder.md').write_text('# Landing')
            (root / 'Z.md').write_text('# Z')
            (root / 'a.md').write_text('# A')
            (root / '.hidden.md').write_text('Hidden')
            provider = LocalFiles(root)
            library = NotesLibrary(provider)
            with patch.object(provider, 'open', side_effect=AssertionError('No document bodies')):
                with patch.object(provider, 'entry', side_effect=AssertionError('No per-entry metadata')):
                    rows = library.folders('')
                self.assertEqual([row['name'] for row in rows], ['Folder', 'a.md', 'Z.md'])
                self.assertEqual(library.folder_pages(rows), {'Folder': 'Folder/Folder.md'})
                self.assertEqual(rows[1]['size'], len(b'# A'))
                with self.assertRaises(OperationCancelled):
                    library.folders('', cancelled=lambda: True)
            library.close()

    def test_provider_without_names_api_keeps_its_listing(self):
        rows = [dict(name='Note.md', path='Note.md', directory=False, size=8)]
        from commonUtils.runtime.resources.paths import resource_path
        provider = SimpleNamespace(list=Mock(return_value=rows), private=False, relative=resource_path)
        library = NotesLibrary(provider)
        self.assertEqual(library.folders(''), rows)
        provider.list.assert_called_once()
        library.close()

    def test_adapted_local_listing_retains_namespace_and_filtering(self):
        class AdaptedFiles(LocalFiles):
            def list(self, path='', *, cancelled=lambda: False):
                return [dict(name='Visible.md', path='virtual/Visible.md', directory=False, size=4)]
        with TemporaryDirectory() as directory:
            library = NotesLibrary(AdaptedFiles(directory), 'virtual')
            self.assertEqual([row['path'] for row in library.folders('virtual')], ['virtual/Visible.md'])
            library.close()


class LibrarySearchTests(unittest.TestCase):
    def test_rooted_search_ranks_names_before_bodies_and_name_scope_never_reads_text(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('Vault/A', 'Vault/B', 'Vault/.hidden'):
                (root / folder).mkdir(parents=True)
            for path, body in (
                ('Outside.md', 'needle'), ('Vault/.hidden/needle.md', 'hidden'),
                ('Vault/A/needle10.md', ''), ('Vault/A/needle2.md', ''),
                ('Vault/B/needle2.md', ''), ('Vault/Body.md', 'needle')):
                (root / path).write_text(body)
            library = NotesLibrary(LocalFiles(root), 'Vault')
            self.addCleanup(library.close)
            result = library_files.search(library, 'needle', include_text=True)
            self.assertTrue(result.complete, result.errors)
            self.assertEqual([row['path'] for row in library_files.ranked_search_rows(result.rows)], [
                'Vault/A/needle2.md', 'Vault/B/needle2.md', 'Vault/A/needle10.md', 'Vault/Body.md'])
            with patch.object(library, 'read_text', side_effect=AssertionError('Filename-only search read a body')):
                names = library_files.search(library, 'needle', include_text=False)
            self.assertEqual({row['path'] for row in names.rows}, {
                'Vault/A/needle2.md', 'Vault/B/needle2.md', 'Vault/A/needle10.md'})

    def test_host_visibility_excludes_folders_before_traversal_and_body_reads(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Vault/Excluded').mkdir(parents=True)
            (root / 'Vault/Excluded/Hidden.md').write_text('needle')
            (root / 'Vault/Visible.md').write_text('needle')
            library = NotesLibrary(LocalFiles(root), 'Vault')
            self.addCleanup(library.close)
            def visible(path, *, directory):
                return path != 'Vault/Excluded'
            with patch.object(library, 'folders', wraps=library.folders) as folders, \
                    patch.object(library, 'read_text', wraps=library.read_text) as read:
                result = library_files.search(library, 'needle', include_text=True, visible=visible)
            self.assertEqual([row['path'] for row in result.rows], ['Vault/Visible.md'])
            self.assertEqual([call.args[0] for call in folders.call_args_list], ['Vault'])
            self.assertEqual([call.args[0] for call in read.call_args_list], ['Vault/Visible.md'])

    def test_listing_failures_keep_partial_matches_but_cancellation_propagates(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Vault/Broken').mkdir(parents=True)
            (root / 'Vault/needle.md').write_text('')
            library = NotesLibrary(LocalFiles(root), 'Vault')
            self.addCleanup(library.close)
            original = library.folders
            stopped = False
            cancel_on_failure = False
            def listing(folder, *, cancelled):
                nonlocal stopped
                if folder == 'Vault/Broken':
                    stopped = cancel_on_failure
                    raise ValueError('Folder cannot be listed')
                return original(folder, cancelled=cancelled)
            with patch.object(library, 'folders', side_effect=listing):
                result = library_files.search(library, 'needle', include_text=False, cancelled=lambda: stopped)
                self.assertEqual([row['path'] for row in result.rows], ['Vault/needle.md'])
                self.assertFalse(result.complete)
                self.assertEqual(result.errors, [('Vault/Broken', 'Folder cannot be listed')])
                cancel_on_failure = True
                with self.assertRaises(OperationCancelled):
                    library_files.search(library, 'needle', include_text=False, cancelled=lambda: stopped)


if __name__ == '__main__':
    unittest.main()
