"""Folder inventories avoid document metadata while retaining provider policy."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
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


if __name__ == '__main__':
    unittest.main()
