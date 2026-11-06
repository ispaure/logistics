
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tests.local_crypt_fixture import crypt_fixture, require_pinned_rclone


class LocalCryptBatchChecks:
    @classmethod
    def setUpClass(cls):
        cls.binary = require_pinned_rclone()


    def check_dataview_discovery_batches_names_across_folders(self, settings):
        from unittest.mock import patch
        from features.notes_library.dataview import ViewFiles
        from features.notes_library.notes import NotesLibrary
        from logistics_build.build_retention import scratch
        with self.subTest(settings=settings), scratch(Path.cwd()) as directory, crypt_fixture(
                directory, self.binary, crypt_settings=settings) as fixture:
            provider = fixture.provider
            paths = [f'Topics/Folder{i}/Common/Note.md' for i in range(24)]
            paths[0] = paths[0].removesuffix('.md') + '.markdown'
            for name, encoded in zip(paths + ['.hidden/Secret.md'],
                                     provider._commands.encode_many(paths + ['.hidden/Secret.md'])):
                from commonUtils.filesystem.native_paths import native_path
                target = native_path(provider.root / encoded)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(provider.encrypted_path('note.md').read_bytes())
            with patch.object(provider, 'list', side_effect=AssertionError('No per-folder listing')), patch.object(
                    provider, 'open', side_effect=AssertionError('No content reads')), patch.object(
                    provider._commands, '_run', wraps=provider._commands._run) as commands:
                index = ViewFiles(NotesLibrary(provider), 'Home.md').page_index(lambda: False)
            self.assertEqual({page['file']['path'] for page in index['pages']}, {'note.md', *paths})
            self.assertLessEqual(commands.call_count, 8)
            self.assertEqual(set(provider.note_file_paths('Topics/Folder0')), {paths[0]})
            with patch.object(provider, 'list', side_effect=AssertionError('No per-folder listing')), patch.object(
                    provider, 'open', side_effect=AssertionError('No content reads')), patch.object(
                    provider._commands, '_run', wraps=provider._commands._run) as commands:
                metadata = ViewFiles(NotesLibrary(provider), 'note.md').page_index(lambda: False, metadata=True)
            self.assertEqual({page['file']['path'] for page in metadata['pages']}, {'note.md', *paths})
            self.assertTrue(all(page['file']['size'] == len(fixture.original) for page in metadata['pages']))
            self.assertLessEqual(commands.call_count, 8)
            with patch.object(provider, 'command', return_value=b'[]'):
                with self.assertRaisesRegex(ValueError, 'changed during discovery'):
                    provider.note_file_entries()
            from commonUtils.runtime.operations import OperationCancelled
            with self.assertRaises(OperationCancelled):
                provider.note_file_paths(cancelled=lambda: True)
            decode = provider._note_decode
            def revoke(entries):
                result = decode(entries)
                provider.close()
                return result
            with patch.object(provider, '_note_decode', side_effect=revoke):
                with self.assertRaises(ValueError):
                    provider.note_file_paths()

    def check_notes_link_lookup_shares_ciphertext_scan_and_bounded_fallback(self, settings):
        from unittest.mock import patch
        from features.notes_library.notes import NotesLibrary
        from logistics_build.build_retention import scratch
        with self.subTest(settings=settings), scratch(Path.cwd()) as directory, crypt_fixture(
                directory, self.binary, crypt_settings=settings) as fixture:
            provider = fixture.provider
            # Ciphertext-only fixture entries: lookup must never read bodies.
            for folder in ('Topics', 'Other', '.hidden', 'Topics/Nested'):
                provider._physical(folder, directory=True).mkdir(parents=True, exist_ok=True)
            for name in ('Topics/Art.md', '.hidden/Art.md', 'Topics/Nested/Deep.md', 'Other/Unrelated.md',
                         'Topics/Nested/Smoke_Color_04.mp4', '.hidden/Smoke_Color_04.mp4'):
                provider.encrypted_path(name).write_bytes(b'opaque fixture')
            library = NotesLibrary(provider)
            with patch.object(provider, 'find_note_paths', side_effect=AssertionError('No global scan')), patch.object(
                    provider, 'list', side_effect=AssertionError('No folder listing')):
                self.assertEqual(library.link('Welcome.md', 'Topics/Art'), ('Topics/Art.md', ''))
            for fallback in (False, True):
                with self.subTest(fallback=fallback), patch.object(
                        provider, 'list', side_effect=AssertionError('No folder listings')), patch.object(
                        provider, 'open', side_effect=AssertionError('No content reads')), patch.object(
                        provider, '_ciphertext_note_paths', **({'return_value': None} if fallback else {
                            'wraps': provider._ciphertext_note_paths})), patch.object(
                        provider._commands, 'decode_many', wraps=provider._commands.decode_many) as decode:
                    self.assertEqual(library.link('Welcome.md', 'Art#heading'), ('Topics/Art.md', 'heading'))
                    self.assertEqual(library.link('Welcome.md', 'Nested/Deep'), ('Topics/Nested/Deep.md', ''))
                    self.assertEqual(library.link('Welcome.md', 'Smoke_Color_04.mp4'),
                                     ('Topics/Nested/Smoke_Color_04.mp4', ''))
                    self.assertEqual(library.link('Welcome.md', 'Nested/Smoke_Color_04.mp4'),
                                     ('Topics/Nested/Smoke_Color_04.mp4', ''))
                    self.assertTrue(decode.called)
                    self.assertEqual(provider.find_note_paths('Art.md', root='Other'), [])
            provider.encrypted_path('Other/Art.md').write_bytes(b'duplicate')
            with self.assertRaisesRegex(ValueError, 'Several notes'):
                library.link('Welcome.md', 'Art')
            provider.encrypted_path('Other/Smoke_Color_04.mp4').write_bytes(b'duplicate')
            with self.assertRaisesRegex(ValueError, 'Several notes'):
                library.link('Welcome.md', 'Smoke_Color_04.mp4')
            with self.assertRaisesRegex(ValueError, 'not found'):
                library.link('Welcome.md', 'Missing')
            from commonUtils.runtime.operations import OperationCancelled
            with self.assertRaises(OperationCancelled):
                library.link('Welcome.md', 'Art', cancelled=lambda: True)
            decode = provider._commands.decode_many
            def revoke(paths):
                result = decode(paths)
                provider.close()
                return result
            with patch.object(provider._commands, 'decode_many', side_effect=revoke):
                with self.assertRaises(ValueError):
                    provider.find_note_paths('Art.md')
            self.assertEqual(len(provider._cache._paths), 0)
            library.close()
