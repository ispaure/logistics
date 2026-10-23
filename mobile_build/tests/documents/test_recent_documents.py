"""Recent history retains ordinary identities and excludes private sessions."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from mobile.recent_documents import RecentDocuments
from mobile.workspace import Session


class RecentDocumentTests(unittest.TestCase):
    def test_bound_order_restore_and_private_removal(self):
        with TemporaryDirectory() as directory:
            history = RecentDocuments(Path(directory))
            for index in range(12):
                session = Session(str(index), 'managed-text', f'{index:032x}', 'text', title='Not stored')
                history.remember(session)
            self.assertEqual(len(history.items), 10)
            self.assertEqual(history.items[0]['resource'], f'{11:032x}')
            self.assertNotIn('Not stored', history.path.read_text())
            restored = RecentDocuments(Path(directory))
            self.assertEqual(restored.items, history.items)
            session.transient = True
            restored.remember(session)
            self.assertNotIn(session.resource, [item['resource'] for item in restored.items])
            private = Session('private', 'provider-session', 'secret/path', 'text', transient=True)
            restored.remember(private)
            self.assertNotIn('secret', restored.path.read_text())

    def test_corrupt_history_is_preserved(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'recent-documents.json'
            path.write_text('invalid')
            history = RecentDocuments(root)
            self.assertTrue(history.error)
            history.remember(Session('a', 'managed-text', 'a' * 32, 'text'))
            self.assertEqual(path.read_text(), 'invalid')
