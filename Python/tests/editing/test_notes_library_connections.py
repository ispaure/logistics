"""Connection reuse validates external revisions and keeps library lifetimes scoped."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from features.notes_library.notes import NotesLibrary
from features.notes_library.notes_links import connections

TEST_STAGE = TestStage.REGRESSION


class ConnectionIndexTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        (self.root / 'A.md').write_text('[B](B.md)')
        (self.root / 'B.md').write_text('# B')
        self.library = NotesLibrary(LocalFiles(self.root))
        self.addCleanup(self.library.close)

    def test_shared_tabs_reuse_parsed_notes_and_external_edits_invalidate(self):
        sibling = NotesLibrary(self.library.provider, connection_index=self.library.connection_index)
        self.assertEqual(connections(self.library, 'B.md')['incoming'], ['A.md'])
        with patch.object(sibling, 'read', wraps=sibling.read) as read:
            self.assertEqual(connections(sibling, 'A.md')['outgoing'], ['B.md'])
            read.assert_not_called()
            (self.root / 'A.md').write_text('No links')
            self.assertEqual(connections(sibling, 'B.md')['incoming'], [])
            self.assertEqual([call.args[0] for call in read.call_args_list], ['A.md'])
        sibling.close()
        self.assertEqual(connections(self.library, 'B.md')['words'], 2)
        self.library.close()
        self.assertFalse(self.library.connection_index._rows)

    def test_concurrent_scans_read_each_unchanged_body_once(self):
        with patch.object(self.library, 'read', wraps=self.library.read) as read:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(connections, self.library, path) for path in ('A.md', 'B.md')]
                self.assertEqual(futures[0].result()['outgoing'], ['B.md'])
                self.assertEqual(futures[1].result()['incoming'], ['A.md'])
            self.assertEqual(read.call_count, 2)


if __name__ == '__main__':
    unittest.main()
