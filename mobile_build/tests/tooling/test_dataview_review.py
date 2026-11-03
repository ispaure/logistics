"""App Review sample exercises the real library parser and bounded read API."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from features.notes_library.dataview import ViewFiles, view_plan
from features.notes_library.notes import NotesLibrary, vault_root
from mobile_build.validation.dataview_review import write_archive

TEST_STAGE = TestStage.REGRESSION


class DataViewReviewTests(unittest.TestCase):
    def test_attachment_is_discoverable_and_uses_the_documented_view_and_json_paths(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            archive_path = write_archive(folder / 'review.zip')
            with ZipFile(archive_path) as archive:
                self.assertIsNone(archive.testzip())
                archive.extractall(folder / 'Local')
            provider = LocalFiles(folder / 'Local')
            root = 'Data view review'
            self.assertEqual(vault_root(provider, root, provider.list(root)), root)
            library = NotesLibrary(provider, root)
            self.addCleanup(library.close)
            source = (folder / 'Local' / root / 'Home.md').read_text()
            self.assertEqual(len(view_plan(source).scripts), 1)
            files = ViewFiles(library, root + '/Home.md')
            view = files.request(dict(id=1, kind='view', path='views/inventory'))
            self.assertIn('dv.table', view['value']['code'])
            data = files.request(dict(id=2, kind='load', path='data/items.json'))
            self.assertEqual(json.loads(data['value']), [{'name': 'Review pencils', 'quantity': 7}])
            rejected = files.request(dict(id=3, kind='load', path='../../outside.txt'))
            self.assertIn('outside this Notes Library', rejected['error'])
            # Preparing a later attachment must not overwrite the reviewed one.
            with self.assertRaises(FileExistsError):
                write_archive(archive_path)
