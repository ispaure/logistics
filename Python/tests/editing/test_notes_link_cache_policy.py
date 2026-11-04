"""Document policy must see through wrappers before reusing local link metadata."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from features.notes_library.notes import NotesLibrary

TEST_STAGE = TestStage.REGRESSION


class LinkCachePolicyTests(unittest.TestCase):
    def test_wrapped_remote_lookup_stays_live_and_local_lookup_reuses_names(self):
        with TemporaryDirectory() as directory:
            for remote in (False, True):
                with self.subTest(remote=remote):
                    root = Path(directory) / str(remote)
                    (root / 'First').mkdir(parents=True)
                    (root / 'A.md').write_text('# Source')
                    (root / 'First/Target.md').write_text('# Target')
                    provider = LocalFiles(root)
                    provider.provider = SimpleNamespace(remote_storage=False)
                    library = NotesLibrary(provider)
                    # Admission is local-only. A wrapper's source may change
                    # before its owner retires this already-admitted library.
                    provider.provider.remote_storage = remote
                    self.addCleanup(library.close)
                    location = dict(side_effect=AssertionError('Remote lookup probed a physical path')) if remote else dict(wraps=provider.transfer_location)
                    with patch.object(provider, 'transfer_location', **location), \
                            patch.object(provider, 'list', wraps=provider.list) as listing:
                        self.assertEqual(library.link('A.md', 'Target'), ('First/Target.md', ''))
                        listing.reset_mock()
                        self.assertEqual(library.link('A.md', 'Target'), ('First/Target.md', ''))
                        if remote:
                            self.assertGreater(listing.call_count, 0)
                            self.assertFalse(library._link_folders)
                            self.assertFalse(library._resolved_links)
                        elif os.name != 'nt':
                            listing.assert_not_called()
                            self.assertTrue(library._resolved_links)
                        listing.reset_mock()
                        with self.assertRaises(OperationCancelled):
                            library.link('A.md', 'Target', cancelled=lambda: True)
                        listing.assert_not_called()
                        (root / 'Second').mkdir()
                        (root / 'Second/Target.md').write_text('# Ambiguous')
                        with self.assertRaisesRegex(ValueError, 'Several notes'):
                            library.link('A.md', 'Target')
                        listing.reset_mock()
                        with self.assertRaises(OperationCancelled):
                            library.link('A.md', 'Target', cancelled=lambda: True)
                        listing.assert_not_called()
