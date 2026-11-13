"""Check encrypted desktop file operations, batched name lookup and plaintext cleanup."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.mutations import move_resource, delete_resource
from features.rclone import executable
from tests.local_crypt_fixture import crypt_fixture


from tests.resources.localcrypt_batch_cases import LocalCryptBatchChecks


class DesktopFileOperationsTests(LocalCryptBatchChecks, unittest.TestCase):
    def test_encrypted_transfer_preview_batches_cleanup_and_directory_names(self):
        from unittest.mock import patch
        from features.rclone.transfers.desktop import DesktopTransferRequest, _compare
        from features.rclone.localcrypt import transport
        from logistics_build.build_retention import scratch
        with scratch(Path.cwd()) as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            provider = fixture.provider
            leading_flags = ['--json', '-Root.md']
            self.assertEqual(provider._commands.decode_many(provider._commands.encode_many(leading_flags)), leading_flags)
            paths = [f'Folder{i}/-Note.markdown' for i in range(30)]
            for encoded in provider._commands.encode_many(paths):
                path = provider.root / encoded
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'opaque fixture')
            transfer = DesktopTransferRequest(provider.root, fixture.cloud, 'Push', fixture.context,
                                               provider.binary, crypt_item=fixture.item)
            emitted = []
            with patch.object(transport, 'run_bytes', wraps=transport.run_bytes) as commands:
                revision = _compare(transfer, fixture.context, lambda kind, name: emitted.append((kind, name)), lambda: False)
            self.assertEqual(len(revision), 64)
            self.assertTrue(set(('add', path) for path in paths) <= set(emitted))
            self.assertTrue(set(('add', f'Folder{i}/') for i in range(30)) <= set(emitted))
            self.assertLessEqual(commands.call_count, 4)


    def test_dataview_discovery_batches_names_across_folders(self):
        self.check_dataview_discovery_batches_names_across_folders(None)

    def test_notes_landing_probes_use_bounded_batches_and_no_content_reads(self):
        from io import BytesIO
        from unittest.mock import patch
        from features.notes_library.notes import NotesLibrary
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            provider = fixture.provider
            for name in ('One', 'Two', 'Empty'):
                provider.mkdir(name)
            provider.create_file('One/One.md', BytesIO(b'# Landing'))
            library = NotesLibrary(provider)
            rows = library.folders('')
            with patch.object(provider._commands, 'encode_many', wraps=provider._commands.encode_many) as encode, \
                    patch.object(provider, 'open', side_effect=AssertionError('No content reads')):
                pages = library.folder_pages(rows)
            self.assertEqual(pages['One'], 'One/One.md')
            self.assertIsNone(pages['Two'])
            self.assertIsNone(pages['Empty'])
            self.assertEqual(encode.call_count, 1)
            library.close()

    def test_notes_link_lookup_shares_ciphertext_scan_and_bounded_fallback(self):
        self.check_notes_link_lookup_shares_ciphertext_scan_and_bounded_fallback(None)

    def test_verified_save_drops_temporary_plaintext_and_keeps_original_cache_valid(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            provider = fixture.provider
            updated = b'# Verified replacement\n'
            provider.write_bytes('note.md', updated, expected=fixture.original)
            self.assertEqual(provider.read_bytes('note.md'), updated)
            cache = provider._cache
            self.assertFalse(any('.save-' in path for path in cache._paths))
            self.assertFalse(any('.save-' in path for path in cache._sizes))
            self.assertFalse(any('.save-' in key[0] for key in cache._blocks))

    def test_evicted_directory_mapping_can_be_rebuilt_without_changing_ciphertext(self):
        from io import BytesIO
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            provider = fixture.provider
            provider.mkdir('nested')
            provider.create_file('nested/note.md', BytesIO(b'original'))
            before = sorted(path.relative_to(fixture.item.data) for path in fixture.item.data.rglob('*'))
            provider._cache.forget_path('nested')
            self.assertEqual(provider.read_bytes('nested/note.md'), b'original')
            self.assertEqual(provider.list('nested')[0]['name'], 'note.md')
            after = sorted(path.relative_to(fixture.item.data) for path in fixture.item.data.rglob('*'))
            self.assertEqual(after, before)

    def test_create_file_rejects_would_block_input_without_publishing_a_prefix(self):
        from commonUtils.integrations.wrappers.cmdShellWrapper.binary import BinaryCommandError
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            crypt = fixture.provider
            before = {path.relative_to(crypt.root) for path in crypt.root.rglob('*')}
            for index, chunks in enumerate(((None,), (b'partial data', None))):
                with self.subTest(prefix=index):
                    pending = iter(chunks)
                    class WouldBlock:
                        def read(self, size):
                            return next(pending, b'')
                    with self.assertRaises(BinaryCommandError):
                        crypt.create_file(f'blocked-{index}.txt', WouldBlock())
                    self.assertEqual({path.relative_to(crypt.root) for path in crypt.root.rglob('*')}, before)
                    self.assertEqual(crypt.read_bytes('note.md'), fixture.original)

    def test_folder_round_trip_and_ciphertext_rename(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            crypt = fixture.provider
            # Ordinary editor Save As cannot publish plaintext into the backing tree.
            from commonUtils.ui.markdown.io import _write_markdown
            from commonUtils.persistence.text import write_text_file
            for save in (_write_markdown, write_text_file):
                with self.assertRaises(PermissionError):
                    save(crypt.root / 'raw-save-as.md', b'should stay out')
            self.assertFalse((crypt.root / 'raw-save-as.md').exists())
            # An authorized provider save and connection record refresh remain valid.
            fixture.item.publish()
            plain = Path(directory) / 'operations-local'
            plain.mkdir()
            local = LocalFiles(plain)
            local.mkdir('source'); local.mkdir('source/empty')
            (plain / 'source/note.txt').write_bytes(b'file-operation-private-sentinel')
            # Inner archive bytes must survive without asking for their password.
            with crypt.open('encrypted.cbz') as stream:
                original_zip = stream.read()
            (plain / 'source/book.cbz').write_bytes(original_zip)
            move_resource(local, 'source', crypt, 'imported')
            self.assertFalse((plain / 'source').exists())
            crypt.rename('imported', 'renamed')
            crypt.mkdir('destination')
            move_resource(crypt, 'renamed', crypt, 'destination/moved')
            self.assertEqual({r['name'] for r in crypt.list('destination/moved')}, {'empty', 'note.txt', 'book.cbz'})
            for file in crypt.root.rglob('*'):
                self.assertNotIn('note.txt', file.name)
                if file.is_file(): self.assertNotIn(b'file-operation-private-sentinel', file.read_bytes())
            move_resource(crypt, 'destination/moved', local, 'exported')
            self.assertEqual((plain / 'exported/book.cbz').read_bytes(), original_zip)
            self.assertEqual((plain / 'exported/note.txt').read_bytes(), b'file-operation-private-sentinel')
            from commonUtils.runtime.resources.mutations import save_resource_bytes
            save_resource_bytes(crypt, 'saved-as.md', b'# Saved As')
            self.assertEqual(crypt.read_bytes('saved-as.md'), b'# Saved As')
            crypt.encrypted_path('fake.md').write_bytes(b'plaintext masquerading as encrypted content' * 10)
            with self.assertRaises(Exception):
                move_resource(crypt, 'fake.md', local, 'should-not-exist.md')
            self.assertFalse((plain / 'should-not-exist.md').exists())
            self.assertTrue(crypt.encrypted_path('fake.md').exists())
            delete_resource(crypt, 'fake.md')
            # A future backend bug which writes plaintext under an encoded name
            # must fail verification, clean staging, and preserve the source.
            from unittest.mock import patch
            (plain / 'future-bug.txt').write_bytes(b'plaintext writer oversight')
            before_names = {p.name for p in crypt.root.iterdir()}
            def wrong_writer(path, stream, **kwargs):
                crypt.encrypted_path(path).write_bytes(stream.read())
            with patch.object(crypt, 'create_file', side_effect=wrong_writer):
                with self.assertRaises(Exception):
                    move_resource(local, 'future-bug.txt', crypt, 'must-not-publish.txt')
            self.assertTrue((plain / 'future-bug.txt').exists())
            self.assertEqual({p.name for p in crypt.root.iterdir()}, before_names)
            delete_resource(crypt, 'destination')
            self.assertFalse(crypt._locate('destination').exists())

    def test_drive_root_picker_can_move_into_and_out_of_nested_crypt(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as f:
            local = LocalFiles(f.root)  # Like the chooser: this root contains crypt storage.
            move_resource(f.provider, 'note.md', local, 'exported.md')
            self.assertEqual((f.root / 'exported.md').read_bytes(), f.original)
            move_resource(local, 'exported.md', f.provider, 'imported.md')
            self.assertEqual(f.provider.read_bytes('imported.md'), f.original)
            self.assertFalse((f.root / 'exported.md').exists())
            (f.root / 'folder').mkdir()
            (f.root / 'folder/child').mkdir()
            nested = LocalFiles(f.root / 'folder')
            with self.assertRaisesRegex(ValueError, 'Overlapping'):
                move_resource(local, 'folder', nested, 'child/nested')
            self.assertTrue((f.root / 'folder/child').is_dir())

    def test_staging_collisions_preserve_the_existing_file(self):
        from io import BytesIO
        from types import SimpleNamespace
        from unittest.mock import patch
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            crypt = fixture.provider
            token = 'collision'
            for name in ('.create-' + token, '.save-' + token + '.md'):
                crypt.encrypted_path(name).write_bytes(b'preexisting staging bytes')
            with patch('features.rclone.localcrypt.backend.uuid4', return_value=SimpleNamespace(hex=token)):
                with self.assertRaises(FileExistsError):
                    crypt.create_file('new.md', BytesIO(b'new'))
                with self.assertRaises(FileExistsError):
                    crypt.write_bytes('note.md', b'new')
            for name in ('.create-' + token, '.save-' + token + '.md'):
                self.assertEqual(crypt.encrypted_path(name).read_bytes(), b'preexisting staging bytes')
            self.assertEqual(crypt.read_bytes('note.md'), fixture.original)


@unittest.skipUnless(os.environ.get('LOGISTICS_MOBILE_BRIDGE'), 'Host native bridge required')
class MobileFileOperationsTests(unittest.TestCase):
    def test_existing_copy_managed_tree_and_plain_round_trip(self):
        from features.rclone.mobile.cloud import CloudClient
        from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
        from features.rclone.localcrypt.mobile.resources import CryptFiles, DownloadedCryptFile, ManagedCopies
        fixture = json.loads(Path('mobile_build/native_tests/tests/logisticsmobile/localcrypt_fixture.json').read_text())
        client = CloudClient(library=os.environ['LOGISTICS_MOBILE_BRIDGE'])
        client.request('import', package=fixture['package'], password='', package_name='Synthetic.zip', session_only=True)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            copies = LocalCryptCopies(root / 'copies', client)
            sample = fixture['copies']['encrypted.cbz']
            folder = copies.root / sample['key']; folder.mkdir()
            (folder / 'record.json').write_text(json.dumps(sample['record']))
            (folder / 'data').write_bytes(base64.b64decode(sample['ciphertext']))
            source = DownloadedCryptFile(copies, sample['key'])
            crypt = CryptFiles(root / 'trees', client, sample['record']['remote'])
            from io import BytesIO
            class ShortReader(BytesIO):
                def read(self, size=-1):
                    return super().read(min(size, 3))
            content = b'# Complete native short-read fixture'
            crypt.create_file('short.md', ShortReader(content))
            with crypt.open('short.md') as stream:
                self.assertEqual(stream.read(), content)
            delete_resource(crypt, 'short.md')
            crypt.mkdir('books')
            move_resource(source, source.name, crypt, 'books/comic.cbz')
            self.assertFalse(folder.exists())
            crypt.rename('books', 'comics')
            managed = ManagedCopies(crypt)
            reader = managed.open('comics/comic.cbz', password='synthetic-archive-password')
            self.assertEqual(reader.kind, '.cbz')
            local_root = root / 'plain'; local_root.mkdir()
            local = LocalFiles(local_root)
            move_resource(crypt, 'comics', local, 'exported')
            from zipfile import ZipFile
            with ZipFile(local_root / 'exported/comic.cbz') as archive:
                self.assertTrue(any(info.flag_bits & 1 for info in archive.infolist()))
            (local_root / 'exported/note.md').write_bytes(b'# Managed text')
            move_resource(local, 'exported', crypt, 'back')
            reader = managed.open('back/note.md')
            reader = managed.save(reader, '# Saved managed text')
            self.assertEqual(managed.open('back/note.md').text, '# Saved managed text')
            managed.save_metadata(managed.open('back/comic.cbz', password='synthetic-archive-password'), {'Title': 'Managed title'})
            self.assertEqual(managed.open('back/comic.cbz', password='synthetic-archive-password').comic.info.get_field('Title'), 'Managed title')
            for file in crypt.root.rglob('*'):
                if file.is_file(): self.assertNotIn(b'Saved managed text', file.read_bytes())
            delete_resource(crypt, 'back')
            self.assertFalse(crypt.list())
        client.clear()
