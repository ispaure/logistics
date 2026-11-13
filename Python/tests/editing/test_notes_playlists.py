"""Playlist references, independently restored checkpoints and secure lifetime."""

import tempfile
import unittest
from pathlib import Path
from time import time_ns
from unittest.mock import Mock, patch

import pyzipper
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage

from features.notes_library.notes import NotesLibrary
from features.notes_library.playlist_queue import PlaylistQueue
from features.notes_library.playlists import PlaylistStore
from services.documents.credential_state import DesktopCredentialCipher

TEST_STAGE = TestStage.REGRESSION


class PlaylistTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.notes = root / 'notes'
        self.notes.mkdir()
        self.store = PlaylistStore(root / 'settings')
        self.library = NotesLibrary(LocalFiles(self.notes))
        self.catalog = self.store.for_library(self.library)
        self.addCleanup(self.library.close)

    def test_restore_two_positions_and_fence_deleted_playlist(self):
        first = self.catalog.create('First')
        second = self.catalog.create('Second')
        a, b = self.catalog.add(first.id, 'a.md').entries[0], self.catalog.add(second.id, 'b.md').entries[0]
        other = self.catalog.add(first.id, 'b.md').entries[1]
        self.catalog.checkpoint(first.id, a, 35, 'a' * 64, time_ns())
        self.catalog.checkpoint(second.id, b, 24, 'b' * 64, time_ns())
        self.catalog.move(first.id, a.id, 1)

        reopened = PlaylistStore(self.store.root.parent).for_library(NotesLibrary(LocalFiles(self.notes)))
        self.assertEqual([(r.name, r.active_id, r.position) for r in reopened.list()],
                         [('First', a.id, 35), ('Second', b.id, 24)])
        self.assertEqual(reopened.get(first.id).entries, (other, a))
        self.catalog.remove(first.id, a.id)
        self.assertEqual(reopened.get(first.id).active_id, other.id)
        self.assertEqual(reopened.get(first.id).position, 0)
        self.store.delete_record(reopened.get(second.id))
        self.catalog.checkpoint(second.id, b, 45, 'b' * 64, time_ns())
        self.assertIsNone(reopened.get(second.id))

    def test_encrypted_resume_locked_clear_and_memory_without_a_zip_key(self):
        provider = LocalFiles(self.notes)
        provider.private = True
        revoked = Mock(return_value=False)
        cipher = DesktopCredentialCipher(provider)
        key = lambda: ('a' * 64, bytearray(b'correct password'))
        credential = Mock(side_effect=key)
        with patch('features.notes_library.playlists._credential_revocation', return_value=revoked), \
                patch('services.documents.progress_identity.credential_authority', return_value='fixture'), \
                patch.object(DesktopCredentialCipher, 'credentials', side_effect=credential):
            catalog = self.store.for_library(NotesLibrary(provider))
            protected = catalog.create('Secret playlist')
            entry = catalog.add(protected.id, 'private.md').entries[0]
            catalog.checkpoint(protected.id, entry, 17, 'a' * 64, time_ns())
            path = self.store.root / ('a' * 64 + '.zip')
            original = path.read_bytes()
            self.assertNotIn(b'Secret playlist', original)
            self.assertNotIn(b'private.md', original)
            with pyzipper.AESZipFile(path) as archive:
                archive.setpassword(b'correct password')
                self.assertIn(b'Secret playlist', archive.read('state.json'))

            credential.side_effect = PermissionError
            self.assertFalse(catalog.list())
            self.assertEqual(self.store.locked_count(), 1)
            memory = catalog.create('This session')
            self.assertTrue(memory.session_only)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((self.store.root / 'local.json').exists())
            revoked.return_value = True
            self.assertFalse(self.store.all())

            credential.side_effect = key
            revoked.return_value = False
            restored = self.store.for_library(NotesLibrary(provider)).get(protected.id)
            self.assertEqual((restored.active_id, restored.position), (entry.id, 17))
            self.assertEqual(self.store.locked_count(ciphers=(cipher,)), 0)
            self.store.clear_locked()
            self.assertFalse(path.exists())
            catalog.checkpoint(protected.id, entry, 34, 'a' * 64, time_ns())
            self.assertFalse(path.exists())

    def test_sequence_carries_both_directions_and_skips_empty_markdown(self):
        record = self.catalog.create('Walk')
        fixtures = {'a.md': ' '.join('a' + str(i) for i in range(65)),
                    'empty.md': '![Private alt](unavailable.jpg)',
                    'b.md': ' '.join('b' + str(i) for i in range(5)),
                    'c.md': ' '.join('c' + str(i) for i in range(50))}
        for path, source in fixtures.items():
            (self.notes / path).write_text(source)
            record = self.catalog.add(record.id, path)
        queue = PlaylistQueue(self.catalog)
        queue.select(record)
        passages = {entry: queue.load(entry, lambda: False) for entry in record.entries}

        def jump(entry, target):
            scan = queue.scan(entry, target)
            current = next(scan)
            while True:
                try:
                    current = scan.send(passages[current])
                except StopIteration as done:
                    return done.value

        a, empty, b, c = record.entries
        self.assertEqual(passages[empty].words, ())
        self.assertEqual(jump(a, 100), (passages[c], passages[c].words[30]))
        self.assertEqual(jump(c, -40), (passages[a], passages[a].words[30]))
        self.assertEqual(jump(a, -100), (passages[a], passages[a].words[0]))
        self.assertEqual(jump(c, 100), (passages[c], passages[c].words[-1]))
