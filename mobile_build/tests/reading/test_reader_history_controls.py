"""Global clears cover unloaded windows and fence already-open writers."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from mobile.library import LibraryStore
from mobile.workspace import Workspace, Session
from services.documents.history_controls import clear_saved_positions, clear_recent_files


class ReaderHistoryControlsTests(unittest.TestCase):
    def test_clear_positions_resets_unloaded_and_loaded_views_without_resurrection(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            library = LibraryStore(root / 'Library')
            key = uuid4().hex
            record = dict(schema=1, id=key, name='Book.epub', kind='epub',
                          revision=0, position=17, bookmarks=[2], digest='a' * 64)
            library.path(key, '.json').write_text(json.dumps(record))
            library.items()  # Populate the old cache too.
            workspace = Workspace(root)
            session = Session(uuid4().hex, 'library', key, 'epub',
                              view=dict(position=17, markdown_mode='preview'))
            workspace.sessions[session.id] = session
            workspace.active = session.id
            workspace.save()
            unloaded = root / 'Windows' / 'other'
            unloaded.mkdir(parents=True)
            other = unloaded / 'workspace.json'
            other.write_bytes(workspace.path.read_bytes())
            clear_saved_positions(root, mobile=True)
            self.assertEqual(library.read_record(key)[0]['position'], 0)
            self.assertEqual(library.read_record(key)[0]['bookmarks'], [2])
            self.assertEqual(json.loads(other.read_text())['sessions'][0]['view'],
                             dict(markdown_mode='preview'))
            session.view['position'] = 30
            workspace.save()
            self.assertNotIn('position', json.loads(workspace.path.read_text())['sessions'][0]['view'])
            library.progress(record, 30)
            self.assertEqual(library.read_record(key)[0]['position'], 0)
            reopened = LibraryStore(root / 'Library')
            reopened.progress(reopened.read_record(key)[0], 4)
            self.assertEqual(reopened.read_record(key)[0]['position'], 4)

    def test_recent_clear_reaches_locked_packages_and_unloaded_windows_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / 'recent-documents.json',
                     root / 'Windows' / 'other' / 'recent-documents.json']
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('[{"synthetic": "history"}]')
            cache = root / 'CredentialDocumentLists' / ('a' * 64)
            cache.mkdir(parents=True)
            (cache / ('b' * 64 + '.zip')).write_bytes(b'locked ciphertext')
            position = root / 'ReaderPositions' / ('c' * 64 + '.zip')
            position.parent.mkdir()
            position.write_bytes(b'position ciphertext')
            clear_recent_files(root, mobile=True)
            self.assertTrue(all(json.loads(path.read_text()) == [] for path in paths))
            self.assertFalse(list(cache.parent.glob('*/*.zip')))
            self.assertEqual(position.read_bytes(), b'position ciphertext')
