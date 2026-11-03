"""Recent history retains ordinary identities and excludes private sessions."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from mobile.recent_documents import RecentDocuments
from mobile.workspace import Session


class RecentDocumentTests(unittest.TestCase):
    def test_note_reference_preserves_library_context_after_reload_and_folder_move(self):
        with TemporaryDirectory() as directory:
            history = RecentDocuments(Path(directory))
            source = dict(type='local', path='/files/Vault/Projects/Plan.md')
            session = Session('', 'file-reference', '', 'markdown', title='Plan.md')
            history.remember_file(session, source, opener=dict(kind='notes', root='/files/Vault'))
            restored = RecentDocuments(Path(directory))
            self.assertFalse(restored.error)
            self.assertEqual(restored.sessions()[0].history_opener,
                             dict(kind='notes', root='/files/Vault'))
            restored.relocate(dict(type='local', path='/files/Vault'),
                              dict(type='local', path='/files/Renamed'))
            again = RecentDocuments(Path(directory))
            self.assertFalse(again.error)
            self.assertEqual(again.sessions()[0].source['path'], '/files/Renamed/Projects/Plan.md')
            self.assertEqual(again.sessions()[0].history_opener['root'], '/files/Renamed')

    def test_invalid_note_references_fail_closed(self):
        for source, root in [(dict(type='local', path=7), '/files/Vault'),
                             (dict(type='local', path='/files/Other.md'), '/files/Vault'),
                             (dict(type='crypt', remote='r', identity='a'*64, namespace='b'*64,
                                   key='Vault/Note.md'), '../Vault')]:
            item = dict(provider='file-reference', resource=RecentDocuments.reference_id(source),
                        kind='markdown', title='Note.md', source=source,
                        opener=dict(kind='notes', root=root))
            with self.subTest(source=source), self.assertRaises(ValueError):
                RecentDocuments.validate_reference(item)

    def test_video_reference_restores_without_becoming_a_workspace_kind(self):
        from mobile.workspace import KINDS
        with TemporaryDirectory() as directory:
            history = RecentDocuments(Path(directory))
            source = dict(type='local', path='/files/Movie.mkv')
            session = Session('', 'file-reference', history.reference_id(source), 'video', title='Movie.mkv')
            history.remember_file(session, source)
            history.remember_file(session, source)
            restored = RecentDocuments(Path(directory))
            self.assertFalse(restored.error)
            self.assertEqual(len(restored.sessions()), 1)
            self.assertEqual(restored.sessions()[0].kind, 'video')
            self.assertEqual(restored.sessions()[0].source, source)
            self.assertNotIn('video', KINDS)

    def test_relocated_ios_history_merges_only_the_same_existing_document(self):
        import json
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            root = Path(directory)
            documents = root / 'Documents'
            documents.mkdir()
            (documents / 'Movie.mkv').touch()
            old = '/var/mobile/Containers/Data/Application/OLD/Documents/'
            sources = [dict(type='local', path=old + 'Movie.mkv'),
                       dict(type='local', path=str(documents / 'Movie.mkv')),
                       dict(type='local', path='/other/Movie.mkv'),
                       dict(type='local', path=old + 'Missing.mkv')]
            items = [dict(provider='file-reference', resource=RecentDocuments.reference_id(source),
                          kind='video', title='Movie.mkv', source=source, opened=i + 1)
                     for i, source in enumerate(sources)]
            (root / 'recent-documents.json').write_text(json.dumps(items))
            with patch('services.documents.locations.shared_documents_path', return_value=documents):
                history = RecentDocuments(root)
                self.assertFalse(history.error)
                self.assertEqual(len(history.items), 3)
                self.assertEqual({i['source']['path'] for i in history.items},
                                 {sources[1]['path'], sources[2]['path'], sources[3]['path']})
                session = Session('', 'file-reference', '', 'video', title='Movie.mkv')
                history.remember_file(session, sources[0])
                self.assertEqual(len(history.items), 3)
                self.assertEqual(history.items[0]['source'], sources[1])
                self.assertEqual(RecentDocuments(root).items, history.items)

    def test_secondary_window_resolves_against_app_storage_not_window_storage(self):
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            root = Path(directory)
            window = root / 'Windows' / 'secondary'
            window.mkdir(parents=True)
            documents = root / 'Public'
            documents.mkdir()
            (documents / 'Movie.mkv').touch()
            source = dict(type='local', path='/var/mobile/Containers/Data/Application/OLD/Documents/Movie.mkv')
            session = Session('', 'file-reference', '', 'video', title='Movie.mkv')
            with patch('services.documents.locations.shared_documents_path',
                       side_effect=lambda private: documents if private == root else None):
                history = RecentDocuments(window, private_root=root)
                history.remember_file(session, source)
                self.assertEqual(history.items[0]['source']['path'], str(documents / 'Movie.mkv'))
                self.assertEqual(history.path.parent, window)

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
