"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from tempfile import TemporaryDirectory
from unittest.mock import patch
from features.rclone.localcrypt import backend as local_crypt
from features.rclone.localcrypt import mapping as copy_mapping
from features.rclone.localcrypt import transport
from features.rclone import actions
from features.rclone import session
from features.comics.library import ComicDocument
from features.comics.pages import ComicPages
from tests.local_crypt_fixture import crypt_fixture


from tests.resources.localcrypt_cases import LocalCryptCase


class LocalCryptStorageTests(LocalCryptCase):
    def test_recursive_search_uses_one_listing_and_opens_nested_results(self):
        from commonUtils.search.providers import search_resources
        from io import BytesIO
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            f.provider.mkdir('nested')
            f.provider.mkdir('nested/deep')
            f.provider.create_file('nested/deep/Needle.txt', BytesIO(b'found'))
            with patch.object(f.provider, 'command', wraps=f.provider.command) as command:
                result = search_resources(f.provider, '', 'NEEDLE')
            self.assertTrue(result.complete)
            self.assertEqual([row['path'] for row in result.rows], ['nested/deep/Needle.txt'])
            self.assertEqual(command.call_count, 1)
            self.assertIn('--recursive', command.call_args.args)
            with f.provider.open(result.rows[0]['path']) as stream:
                self.assertEqual(stream.read(), b'found')
            scoped = search_resources(f.provider, 'nested', 'needle')
            self.assertEqual(scoped.rows[0]['name'], 'deep/Needle.txt')
            self.assertTrue(scoped.complete)

    def test_open_stream_cached_bytes_reject_revocation_and_replacement(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            f.provider.list()
            with f.provider.open('note.md') as stream:
                self.assertEqual(stream.read(), f.original)
                stream.seek(0)
                session.forget(f.context)
                self.assertTrue(f.provider.closed)
                self.assertFalse(f.provider._cache._blocks)
                with self.assertRaisesRegex(ValueError, 'locked'):
                    stream.read(1)
                session.remember(f.context, {'Secret': {'type': 'crypt'}}, package_path=f.package)
                with self.assertRaisesRegex(ValueError, 'locked'):
                    stream.seek(0)

    def test_archive_reads_reuse_revision_checked_memory_and_nested_listing(self):
        from io import BytesIO
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            f.provider.list()
            with patch.object(transport, 'run_bytes', wraps=transport.run_bytes) as commands:
                for name in ('plain.cbz', 'encrypted.cbz'):
                    document = ComicDocument(f.item.data / name, source=f.provider)
                    self.assertEqual(ComicPages(document.path, document).read_page(0)[0], f.image)
                self.assertEqual(commands.call_count, 3)
                commands.reset_mock()
                document = ComicDocument(f.item.data / 'plain.cbz', source=f.provider)
                self.assertEqual(ComicPages(document.path, document).read_page(0)[0], f.image)
                self.assertEqual(commands.call_count, 0)
            with f.provider.open('note.md') as stream:
                self.assertEqual(stream.read(), f.original)
            changed = b'# Changed revision\n'
            f.provider.write_bytes('note.md', changed, expected=f.original)
            with f.provider.open('note.md') as stream:
                self.assertEqual(stream.read(), changed)
            f.provider.mkdir('nested')
            f.provider.create_file('nested/child.md', BytesIO(changed))
            f.provider.list()
            rows = f.provider.list('nested')
            self.assertEqual(rows[0]['path'], 'nested/child.md')
            self.assertEqual(f.provider.read_bytes('nested/child.md'), changed)
            session.forget(f.context)
            with self.assertRaisesRegex(ValueError, 'locked'):
                with f.provider.open('note.md'):
                    pass
            f.provider.close()
            self.assertFalse(f.provider._cache._blocks)
            self.assertFalse(f.provider._cache._sizes)

    def test_stale_failed_and_linked_saves_preserve_ciphertext_and_session_expiry_requires_zip(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            target = f.provider.encrypted_path('note.md')
            prior = target.read_bytes()
            with self.assertRaisesRegex(ValueError, 'changed'):
                f.provider.write_bytes('note.md', b'# stale', expected=b'wrong original')
            self.assertEqual(target.read_bytes(), prior)
            with patch.object(f.provider, 'command', side_effect=OSError('Synthetic failure')):
                with self.assertRaises(OSError):
                    f.provider.write_bytes('note.md', b'# failed', expected=f.original)
            self.assertEqual(target.read_bytes(), prior)
            self.assertEqual(copy_mapping.push_target(f.item.data, f.context), 'Cloud:' + str(f.cloud))
            with self.assertRaises(ValueError):
                copy_mapping.push_target(f.item.data, f.root / 'Different.session')
            session.forget(f.context)
            with self.assertRaises(ValueError):
                f.provider.read_bytes('note.md')
            from commonUtils.archives.zip_access import ArchivePasswordError
            with self.assertRaises(ArchivePasswordError):
                copy_mapping.unlock(f.item, 'wrong package password')
            self.assertIsNone(session.credentials(f.context))
            self.assertEqual(copy_mapping.unlock(f.item, 'synthetic-package-password')['Secret']['type'], 'crypt')

    def test_linked_root_is_supported_but_inner_links_name_the_offending_path(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            actual = f.root / 'relocated-ciphertext'
            f.item.data.rename(actual)
            f.item.data.symlink_to(actual, target_is_directory=True)
            copy_mapping.validate_ciphertext_tree(f.item)
            self.assertEqual(copy_mapping.for_path(f.item.data), f.item)
            provider = local_crypt.CryptResources(f.item, binary=self.binary)
            try:
                self.assertEqual(provider.read_bytes('note.md'), f.original)
                self.assertEqual(copy_mapping.push_target(f.item.data, f.context), 'Cloud:' + str(f.cloud))
                self.assertTrue(actions.push_to_cloud(local_crypt.LocalCryptFolder(f.item), f.context))
                self.assertTrue(actions.pull_encrypted_copy('Secret', f.context))
                self.assertTrue(f.item.data.is_symlink())
                linked = f.item.data / 'bad-link'
                linked.symlink_to(f.root / 'plain', target_is_directory=True)
                with self.assertRaises(ValueError) as error:
                    copy_mapping.validate_ciphertext_tree(f.item)
                self.assertIn(str(linked), str(error.exception))
                with self.assertRaises(ValueError):
                    provider.list()
                with self.assertRaises(ValueError):
                    copy_mapping.push_target(f.item.data, f.context)
                linked.unlink()
                linked = f.item.data / 'bad-hard-link'
                os.link(provider.encrypted_path('note.md'), linked)
                with self.assertRaises(ValueError) as error:
                    copy_mapping.validate_ciphertext_tree(f.item)
                self.assertIn('independent regular files:', str(error.exception))
                linked.unlink()
                f.item.record.unlink()
                with self.assertRaisesRegex(ValueError, 'no valid credential mapping'):
                    copy_mapping.push_target(f.item.data, f.context)
            finally:
                provider.close()

    def test_cancel_before_publication_preserves_original_and_cleans_staging(self):
        from threading import Event
        from commonUtils.runtime.operations import OperationCancelled
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            before = {str(p): p.read_bytes() for p in f.item.data.rglob('*') if p.is_file()}
            cancelled = Event()
            with f.provider.operation(cancelled.is_set):
                with self.assertRaises(OperationCancelled):
                    f.provider.replace_stream('note.md', lambda stream: stream.write(b'# cancelled'),
                        expected_revision=f.provider.version('note.md'), verify=lambda path: cancelled.set())
            self.assertEqual(before, {str(p): p.read_bytes() for p in f.item.data.rglob('*') if p.is_file()})
            with self.assertRaises(OperationCancelled):
                with f.provider.operation(lambda: True):
                    f.provider.read_bytes('note.md')
            self.assertEqual(f.provider.read_bytes('note.md'), f.original)
