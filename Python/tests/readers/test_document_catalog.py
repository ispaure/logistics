"""Favourite opening modes, bounded history and credential-password privacy."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from services.documents.catalog import DocumentCatalog
from services.documents.credential_state import DesktopCredentialCipher
from features.rclone.credential_sessions import CredentialSessions
from unittest.mock import patch


class DocumentCatalogTests(TestCase):
    def test_moves_follow_paths_and_library_context_while_deletes_retire_references(self):
        with TemporaryDirectory() as directory:
            catalog = DocumentCatalog(directory)
            catalog.remember(dict(type='local', path='/notes/Folder/Home.md'), 'Home.md',
                             dict(editor='notes', root='/notes/Folder'), favourite=True)
            catalog.relocate(dict(type='local', path='/notes/Folder'), dict(type='local', path='/notes/Moved'))
            row = catalog.entries()[0]
            self.assertEqual(row['source']['path'], '/notes/Moved/Home.md')
            self.assertEqual(row['opener']['root'], '/notes/Moved')
            catalog.relocate(dict(type='local', path='/notes/Moved/Home.md'), dict(type='local', path='/notes/Moved/Renamed.md'))
            row = catalog.entries()[0]
            self.assertEqual(row['title'], 'Renamed.md')
            self.assertEqual(row['id'], catalog.identity(row['source']))
            catalog.relocate(dict(type='local', path='/notes/Moved'))
            self.assertEqual(catalog.entries(), [])

    def test_clearing_recent_preserves_favourites_and_locked_recent_is_removable(self):
        from services.documents.history_controls import clear_recent_files
        with TemporaryDirectory() as directory:
            favourites = DocumentCatalog(directory)
            recent = DocumentCatalog(directory, recent=True)
            source = dict(type='local', path='/notes/Home.md')
            favourites.remember(source, 'Home', {}, favourite=True)
            recent.remember(source, 'Home', {})
            (recent.root / ('a' * 64 + '.zip')).write_bytes(b'locked ciphertext')
            clear_recent_files(directory)
            self.assertEqual(recent.entries('recent'), [])
            self.assertEqual(len(favourites.entries()), 1)
            self.assertFalse(list(recent.root.iterdir()))

    def test_favourite_replaces_opening_mode_and_history_is_bounded(self):
        with TemporaryDirectory() as directory:
            catalog = DocumentCatalog(directory)
            source = dict(type='local', path='/notes/Home.md')
            catalog.remember(source, 'Home.md', dict(editor='notes', root='/notes'), favourite=True)
            catalog.remember(source, 'Home.md', dict(editor='markdown'), favourite=True)
            self.assertEqual(len(catalog.entries()), 1)
            self.assertEqual(catalog.entries()[0]['opener'], dict(editor='markdown'))
            for index in range(15):
                catalog.remember(dict(type='local', path=f'/notes/{index}.md'), str(index), {})
            self.assertEqual(len(catalog.entries('recent')), 10)
            self.assertEqual(catalog.entries('recent')[0]['title'], '14')

    def test_credential_bucket_has_no_plaintext_and_requires_matching_unlock(self):
        sessions = CredentialSessions()
        context = Path('/fixture/session')
        source = dict(type='crypt', path='private-sentinel.md')
        identity = 'a' * 64
        with TemporaryDirectory() as directory, patch('features.rclone.session.registry', sessions):
            sessions.remember(context, {}, state_password='secret', state_identity=identity)
            cipher = DesktopCredentialCipher(SimpleNamespace(context=context))
            catalog = DocumentCatalog(directory)
            catalog.remember(source, 'private-sentinel', dict(editor='notes'), favourite=True, cipher=cipher)
            catalog.remember(source, 'private-sentinel', dict(editor='notes'), cipher=cipher)
            self.assertNotIn(b'private-sentinel', catalog.path(cipher).read_bytes())
            self.assertEqual(catalog.entries(), [])
            self.assertEqual(len(catalog.entries(ciphers=[cipher])), 1)
            sessions.forget(context)
            with self.assertRaises(PermissionError):
                catalog.entries(ciphers=[cipher])
            sessions.remember(context, {}, state_password='wrong', state_identity=identity)
            before = catalog.path(cipher).read_bytes()
            with self.assertRaises((ValueError, RuntimeError)):
                catalog.remember(source, 'replacement', {}, favourite=True, cipher=cipher)
            self.assertEqual(catalog.path(cipher).read_bytes(), before)
            sessions.forget(context)

    def test_corrupt_catalog_is_preserved(self):
        with TemporaryDirectory() as directory:
            catalog = DocumentCatalog(directory)
            catalog.root.mkdir()
            catalog.path().write_text('invalid')
            with self.assertRaises(ValueError):
                catalog.remember({'path': '/note.md'}, 'Note', {}, favourite=True)
            self.assertEqual(catalog.path().read_text(), 'invalid')

    def test_swapped_credential_bucket_and_revoke_during_save_preserve_ciphertext(self):
        sessions = CredentialSessions()
        context = Path('/fixture/catalog-session')
        with TemporaryDirectory() as directory, patch('features.rclone.session.registry', sessions):
            sessions.remember(context, {}, state_password='shared password', state_identity='a' * 64)
            cipher = DesktopCredentialCipher(SimpleNamespace(context=context))
            catalog = DocumentCatalog(directory)
            source = dict(type='crypt', path='private.md')
            catalog.remember(source, 'Private', {}, favourite=True, cipher=cipher)
            original = catalog.path(cipher).read_bytes()
            sessions.remember(context, {}, state_password='shared password', state_identity='b' * 64)
            catalog.path(cipher).write_bytes(original)
            with self.assertRaisesRegex(ValueError, 'another credential'):
                catalog.read(cipher)
            self.assertEqual(catalog.entries(ciphers=[cipher], strict=False), [])
            self.assertTrue(catalog.errors)
            sessions.remember(context, {}, state_password='shared password', state_identity='a' * 64)
            transform = cipher.transform
            def revoke(data, decode=False):
                result = transform(data, decode=decode)
                if not decode:
                    sessions.forget(context)
                return result
            with patch.object(cipher, 'transform', side_effect=revoke), self.assertRaises(PermissionError):
                catalog.remember(source, 'Changed', {}, favourite=True, cipher=cipher)
            self.assertEqual((catalog.root / ('a' * 64 + '.zip')).read_bytes(), original)
