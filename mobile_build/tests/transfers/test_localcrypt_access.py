"""LocalCrypt resource sessions close independently and never revive old grants."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

import base64
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from features.rclone.localcrypt.mobile.locations import LocalCryptLocation
from features.rclone.mobile.service import native_service
from features.rclone.localcrypt.mobile.resources import encrypted_copies

TEST_STAGE = TestStage.REGRESSION


class NativeArchiveLifetimeTests(unittest.TestCase):
    """Exercise only synthetic ciphertext and fake native plaintext responses."""

    def source(self, root):
        from features.rclone.localcrypt.mobile.archive_source import NativeSource
        path = Path(root) / 'ciphertext'
        path.write_bytes(b'opaque synthetic ciphertext')
        calls = []

        def request(action, **values):
            calls.append(action)
            if action == 'crypt_stat':
                return dict(name='fixture.cbz', size=7)
            if action == 'crypt_archive' and 'member' not in values:
                return [dict(name='page.txt', size=7, crc=0, flags=0, directory=False)]
            return dict(data=base64.b64encode(b'fixture').decode())

        client = SimpleNamespace(generation=1, request=request)
        source = NativeSource(client, dict(remote='Fixture', identity='synthetic',
                                          encrypted_path='ciphertext'), path,
                              password='synthetic-inner-password')
        self.addCleanup(source.close)
        return source, calls

    def test_close_retires_cached_and_direct_native_access(self):
        with TemporaryDirectory() as root:
            source, calls = self.source(root)
            with source.open(source.path) as stream:
                self.assertEqual(stream.read(3), b'fix')
                stream.seek(0)
                self.assertEqual(stream.read(3), b'fix')
                source.read_member('page.txt')
                source.close()
                source.close()
                before = list(calls)
                for action in (lambda: stream.seek(0), lambda: stream.read(1),
                               lambda: source.request('crypt_stat'),
                               lambda: source.read_member('page.txt')):
                    with self.subTest(action=action), self.assertRaises(ValueError):
                        action()
                self.assertEqual(calls, before)
                self.assertIsNone(source.password)
                self.assertIsNone(source.headers)
                self.assertFalse(source.cache)

    def test_close_during_native_request_rejects_late_archive_headers(self):
        with TemporaryDirectory() as root:
            source, calls = self.source(root)
            request = source.client.request

            def close_during_request(action, **values):
                result = request(action, **values)
                source.close()
                return result

            source.client.request = close_during_request
            with self.assertRaises(ValueError):
                source.request('crypt_archive')
            self.assertIsNone(source.headers)
            self.assertFalse(source.cache)

    def test_close_during_member_decode_cannot_restore_plaintext_cache(self):
        with TemporaryDirectory() as root:
            source, calls = self.source(root)
            decode = base64.b64decode

            def close_during_decode(*args, **kwargs):
                data = decode(*args, **kwargs)
                source.close()
                return data

            with patch('services.documents.archive_access.base64.b64decode',
                       side_effect=close_during_decode), self.assertRaises(ValueError):
                source.read_member('page.txt')
            self.assertFalse(source.cache)
            self.assertEqual(source.cache_bytes, 0)

    def test_credential_expiry_retires_password_and_archive_metadata(self):
        with TemporaryDirectory() as root:
            source, calls = self.source(root)
            source.request('crypt_archive')
            source.read_member('page.txt')
            source.client.generation += 1
            with self.assertRaisesRegex(ValueError, 'Credentials'):
                source.request('crypt_stat')
            self.assertIsNone(source.password)
            self.assertIsNone(source.headers)
            self.assertFalse(source.cache)

    def test_cancellation_callback_cannot_close_then_release_cached_bytes(self):
        with TemporaryDirectory() as root:
            source, calls = self.source(root)
            with source.open(source.path) as stream:
                self.assertEqual(stream.read(1), b'f')
                source.cancelled = lambda: source.close() or False
                with self.assertRaises(ValueError):
                    stream.read(1)

    def test_concurrent_member_reads_count_the_cached_block_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        with TemporaryDirectory() as root:
            source, calls = self.source(root)
            request, ready = source.client.request, Barrier(2)

            def read_together(action, **values):
                result = request(action, **values)
                ready.wait(5)
                return result

            source.client.request = read_together
            with ThreadPoolExecutor(max_workers=2) as workers:
                reads = [workers.submit(source.read_member, 'page.txt') for _ in range(2)]
                self.assertEqual([read.result(5) for read in reads], [b'fixture', b'fixture'])
            self.assertEqual(len(source.cache), 1)
            self.assertEqual(source.cache_bytes, len(b'fixture'))

    def test_password_change_and_restore_rejects_the_in_flight_member(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        with TemporaryDirectory() as root:
            source, calls = self.source(root)
            entered, dispatch, returned, release = Event(), Event(), Event(), Event()
            transport, native = source._request, source.client.request
            native_passwords = []

            def record_password(action, **values):
                if 'member' in values:
                    native_passwords.append(values['password'])
                return native(action, **values)

            def paused_transport(action, **values):
                if 'member' not in values:
                    return transport(action, **values)
                entered.set()
                if not dispatch.wait(5):
                    raise TimeoutError('Synthetic dispatch was not released')
                result = transport(action, **values)
                returned.set()
                if not release.wait(5):
                    raise TimeoutError('Synthetic result was not released')
                return result

            source.client.request = record_password
            source._request = paused_transport
            with ThreadPoolExecutor(max_workers=1) as workers:
                pending = workers.submit(source.read_member, 'page.txt')
                try:
                    self.assertTrue(entered.wait(5))
                    with source.open_archive(source.path, password='synthetic-replacement'):
                        pass
                    dispatch.set()
                    self.assertTrue(returned.wait(5))
                    with source.open_archive(source.path, password='synthetic-inner-password'):
                        pass
                finally:
                    dispatch.set()
                    release.set()
                with self.assertRaisesRegex(ValueError, 'password changed'):
                    pending.result(5)
            self.assertEqual(native_passwords, ['synthetic-inner-password'])
            self.assertFalse(source.cache)
            self.assertEqual(source.cache_bytes, 0)


class Client:
    generation = 0

    def request(self, action, **values):
        if action == 'crypt_describe':
            return 'note.txt'
        if action == 'crypt_path':
            return dict(identity='a' * 64, path=values['path'])
        if action == 'crypt_paths':
            return [item['path'] for item in values['entries']]
        if action == 'crypt_sizes':
            return values['sizes']
        if action == 'crypt_raw_read':
            return dict(data=base64.b64encode(b'fixture content').decode())
        if action == 'crypt_decode':
            return dict(name='note.txt', data=base64.b64encode(b'fixture content').decode())
        raise AssertionError(action)

    def lock(self):
        self.generation += 1


class LocalCryptAccessTests(unittest.TestCase):
    def test_native_write_progress_reports_bytes_and_cancels_without_reading_plaintext(self):
        from threading import Event
        from features.rclone.localcrypt.mobile.resources import write_progress
        cancelled, reported, stopped = Event(), Event(), Event()
        client = SimpleNamespace(cancel=lambda: stopped.set())
        values = []
        def progress(done):
            values.append(done)
            reported.set()
        stream = SimpleNamespace(transfer_progress=progress)
        with TemporaryDirectory() as root:
            with (Path(root) / 'encrypted-stage').open('wb') as output:
                output.write(b'ciphertext')
                output.flush()
                with write_progress(client, output, stream, cancelled.is_set):
                    self.assertTrue(reported.wait(3))
                    cancelled.set()
                    self.assertTrue(stopped.wait(3))
                self.assertTrue(values)
                self.assertEqual(values[0], len(b'ciphertext'))
    def test_note_metadata_converts_distinct_sizes_in_bounded_guarded_batches(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            for size in range(300):
                (provider.root / f'Note{size}.md').write_bytes(b'x' * (size + 48))
            (provider.root / 'Duplicate.md').write_bytes(b'x' * 48)
            original = client.request
            batches = []
            def request(action, **values):
                if action == 'crypt_sizes':
                    batches.append(values['sizes'])
                    self.assertEqual(values['identity'], provider.identity)
                    return [size - 48 for size in values['sizes']]
                return original(action, **values)
            with patch.object(client, 'request', side_effect=request), patch.object(
                    provider, 'open', side_effect=AssertionError('No document reads')):
                rows = provider.note_file_entries()
            self.assertEqual({row['size'] for row in rows}, set(range(300)))
            self.assertEqual(len(rows), 301)
            self.assertEqual(len(batches), 2)
            self.assertTrue(all(len(batch) <= 256 for batch in batches))
            self.assertEqual(sum(map(len, batches)), 300)
            for invalid in (None, [], [True] * 256, [-1] * 256):
                def malformed(action, **values):
                    return invalid if action == 'crypt_sizes' else original(action, **values)
                with patch.object(client, 'request', side_effect=malformed), self.assertRaisesRegex(ValueError, 'sizes'):
                    provider.note_file_entries()
            def revoke(action, **values):
                result = request(action, **values)
                if action == 'crypt_sizes':
                    client.lock()
                return result
            with patch.object(client, 'request', side_effect=revoke), self.assertRaises(ValueError):
                provider.note_file_entries()

    def test_duplicate_note_lookup_does_not_remap_each_candidate(self):
        if not hasattr(os, 'fwalk'):
            self.skipTest('Descriptor-relative lookup is POSIX-specific')
        with TemporaryDirectory() as root:
            provider = self.provider(root, Client())
            for i in range(300):
                folder = provider.root / f'Folder{i}'
                folder.mkdir()
                (folder / 'Common.md').write_bytes(b'fixture')
            with patch.object(provider, 'entry', side_effect=AssertionError('No per-candidate remapping')), patch.object(
                    provider.client, 'request', wraps=provider.client.request) as requests:
                self.assertEqual(len(provider.find_note_paths('Common.md')), 300)
            mappings = [call for call in requests.call_args_list if call.args[0] == 'crypt_path']
            self.assertLessEqual(len(mappings), 3)

    def test_discovery_rejects_a_queued_directory_replaced_before_descent(self):
        with TemporaryDirectory() as root:
            provider = self.provider(root, Client())
            folder = provider.root / 'Moving'
            folder.mkdir()
            (folder / 'Original.md').write_bytes(b'fixture')
            check = provider._check_note_directory
            def replace(path, before):
                if path == folder:
                    path.rename(provider.root / 'Retired')
                    path.mkdir()
                    (path / 'Replacement.md').write_bytes(b'fixture')
                check(path, before)
            with patch.object(provider, '_check_note_directory', side_effect=replace):
                with self.assertRaisesRegex(ValueError, 'changed during discovery'):
                    provider.note_file_paths()

    def test_dataview_discovery_batches_sibling_folders_and_refreshes(self):
        from features.notes_library.dataview import ViewFiles
        from features.notes_library.notes import NotesLibrary
        from commonUtils.runtime.operations import OperationCancelled
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            for i in range(300):
                folder = provider.root / 'Topics' / f'Folder{i}'
                folder.mkdir(parents=True)
                (folder / 'Note.md').write_bytes(b'opaque fixture')
            (provider.root / '.hidden').mkdir()
            (provider.root / '.hidden/Secret.md').write_bytes(b'opaque fixture')
            library = NotesLibrary(provider)
            with patch.object(provider, 'list', side_effect=AssertionError('No per-folder listing')), patch.object(
                    provider, 'open', side_effect=AssertionError('No content reads')), patch.object(
                    client, 'request', wraps=client.request) as requests:
                index = ViewFiles(library, 'Topics/Home.md').page_index(lambda: False)
            self.assertEqual(len(index['pages']), 300)
            batches = [call.kwargs['entries'] for call in requests.call_args_list if call.args[0] == 'crypt_paths']
            self.assertEqual(len(batches), 4)
            self.assertTrue(all(len(batch) <= 256 for batch in batches))
            self.assertEqual(sum(entry['path'] == 'Note.md' for batch in batches for entry in batch), 1)
            self.assertFalse(any(entry['path'] == 'Secret.md' for batch in batches for entry in batch))
            with patch.object(provider, 'list', side_effect=AssertionError('No per-folder listing')):
                metadata = ViewFiles(library, 'Topics/Home.md').page_index(lambda: False, metadata=True)
            self.assertEqual(len(metadata['pages']), 300)
            self.assertTrue(all(page['file']['size'] == len(b'opaque fixture') for page in metadata['pages']))
            path = provider.root / 'Topics/Folder0/Note.md'
            path.rename(path.with_name('Renamed.md'))
            pages = provider.note_file_paths('Topics/Folder0')
            self.assertEqual(pages, ['Topics/Folder0/Renamed.md'])
            with self.assertRaises(OperationCancelled):
                provider.note_file_paths(cancelled=lambda: True)
            decode = provider._note_decode
            def revoke(entries):
                result = decode(entries)
                client.lock()
                return result
            with patch.object(provider, '_note_decode', side_effect=revoke):
                with self.assertRaises(ValueError):
                    provider.note_file_paths()

    def test_dataview_discovery_rejects_links_and_incomplete_batches(self):
        with TemporaryDirectory() as root:
            provider = self.provider(root, Client())
            (provider.root / 'Note.md').write_bytes(b'opaque fixture')
            with patch.object(provider, '_note_decode', return_value=[]):
                with self.assertRaisesRegex(ValueError, 'Incomplete'):
                    provider.note_file_paths()
            (provider.root / 'Link.md').symlink_to(provider.root / 'Note.md')
            with self.assertRaisesRegex(ValueError, 'Linked storage'):
                provider.note_file_paths()

    def test_note_lookup_decodes_only_candidate_paths_and_preserves_matching_rules(self):
        from features.notes_library.notes import NotesLibrary
        from commonUtils.runtime.operations import OperationCancelled
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            for folder in ('Topics', 'Other', '.hidden', 'Topics/Nested'):
                (provider.root / folder).mkdir(parents=True)
            for name in ('Topics/Unique.md', '.hidden/Unique.md', 'Other/Unrelated.md', 'Topics/Nested/Deep.md',
                         'Topics/Nested/Smoke_Color_04.mp4', '.hidden/Smoke_Color_04.mp4'):
                (provider.root / name).write_bytes(b'opaque fixture')
            library = NotesLibrary(provider)
            with patch.object(provider, 'list', side_effect=AssertionError('Full folder listing')), patch.object(
                    client, 'request', wraps=client.request) as requests:
                self.assertEqual(library.link('Start.md', 'Unique#section'), ('Topics/Unique.md', 'section'))
                self.assertEqual(library.link('Start.md', 'Nested/Deep'), ('Topics/Nested/Deep.md', ''))
                self.assertEqual(library.link('Start.md', 'Smoke_Color_04.mp4'),
                                 ('Topics/Nested/Smoke_Color_04.mp4', ''))
                decoded = [entry for call in requests.call_args_list if call.args[0] == 'crypt_paths'
                           for entry in call.kwargs['entries']]
                self.assertTrue(decoded)
                if hasattr(os, 'fwalk'):
                    self.assertTrue(all(not entry['directory'] for entry in decoded))
                    self.assertTrue(all(Path(entry['path']).name in {'Unique.md', 'Deep.md', 'Smoke_Color_04.mp4'}
                                        for entry in decoded))
                else:
                    self.assertTrue(all(entry['directory'] for entry in decoded))
            self.assertEqual(provider.find_note_paths('Unique.md', root='Other'), [])
            (provider.root / 'Other/Unique.md').write_bytes(b'opaque duplicate')
            with self.assertRaisesRegex(ValueError, 'Several notes'):
                library.link('Start.md', 'Unique')
            (provider.root / 'Other/Smoke_Color_04.mp4').write_bytes(b'opaque duplicate')
            with self.assertRaisesRegex(ValueError, 'Several notes'):
                library.link('Start.md', 'Smoke_Color_04.mp4')
            with self.assertRaisesRegex(ValueError, 'not found'):
                library.link('Start.md', 'Missing')
            with self.assertRaises(OperationCancelled):
                library.link('Start.md', 'Unique', cancelled=lambda: True)
            (provider.root / 'Other/Linked.md').symlink_to(provider.root / 'Topics/Unique.md')
            with self.assertRaisesRegex(ValueError, 'Linked storage'):
                library.link('Start.md', 'Unique')
            provider.close()

    def test_note_lookup_cannot_publish_after_revocation_during_decode(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            (provider.root / 'Folder').mkdir()
            (provider.root / 'Folder/Unique.md').write_bytes(b'opaque fixture')
            original = client.request
            def revoke(action, **values):
                result = original(action, **values)
                if action == 'crypt_paths':
                    client.lock()
                return result
            with patch.object(client, 'request', side_effect=revoke):
                with self.assertRaises(ValueError):
                    provider.find_note_paths('Unique.md')

    def test_note_lookup_rechecks_collection_selection_before_publishing(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            (provider.root / 'Folder').mkdir()
            (provider.root / 'Folder/Unique.md').write_bytes(b'opaque fixture')
            provider.collection_storage_root = Path(root) / 'app'
            selected = [provider.root.parent]
            original = client.request
            def relocate(action, **values):
                result = original(action, **values)
                if action == 'crypt_paths':
                    selected[0] = provider.root.parent / 'Changed'
                return result
            with patch('features.rclone.localcrypt.mobile.resources.collection_path', side_effect=lambda *a: selected[0]), patch.object(
                    client, 'request', side_effect=relocate):
                with self.assertRaisesRegex(ValueError, 'Collection location changed'):
                    provider.find_note_paths('Unique.md')

    def test_ciphertext_scan_falls_back_for_hidden_heavy_trees(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            hidden = provider.root / '.hidden'
            hidden.mkdir()
            for index in range(10001):
                (hidden / str(index)).touch()
            (provider.root / 'Folder').mkdir()
            (provider.root / 'Folder/Unique.md').write_bytes(b'opaque fixture')
            self.assertEqual(provider.find_note_paths('Unique.md'), ['Folder/Unique.md'])

    def test_candidate_replacement_during_decode_is_rejected(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            (provider.root / 'Folder').mkdir()
            candidate = provider.root / 'Folder/Unique.md'
            candidate.write_bytes(b'original opaque fixture')
            original = client.request
            def replace(action, **values):
                result = original(action, **values)
                if action == 'crypt_paths':
                    candidate.write_bytes(b'replacement opaque fixture with another revision')
                return result
            with patch.object(client, 'request', side_effect=replace):
                with self.assertRaisesRegex(ValueError, 'changed during lookup'):
                    provider.find_note_paths('Unique.md')

    def test_fallback_rejects_a_directory_moved_during_decode(self):
        from logistics_build.build_retention import scratch
        with scratch(Path.cwd()) as root:
            client = Client()
            provider = self.provider(root, client)
            for folder in ('Stable', 'Moving'):
                (provider.root / folder).mkdir()
                (provider.root / folder / 'Unique.md').write_bytes(b'opaque fixture')
            original = client.request
            def move(action, **values):
                result = original(action, **values)
                if action == 'crypt_paths' and (provider.root / 'Moving').exists():
                    (provider.root / 'Moving').rename(provider.root / 'Moved')
                return result
            with patch.object(provider, '_ciphertext_note_paths', return_value=None), patch.object(
                    client, 'request', side_effect=move):
                with self.assertRaisesRegex(ValueError, 'changed during lookup'):
                    provider.find_note_paths('Unique.md')
            provider.close()

    def test_failed_archive_construction_releases_its_native_source(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.provider_documents import ProviderDocuments
        with TemporaryDirectory() as root:
            provider = LocalFiles(root)
            Path(root, 'broken.cbz').write_bytes(b'ciphertext')
            source = SimpleNamespace(close=Mock())
            provider.content_source = Mock(return_value=source)
            with patch('services.documents.readers.PrivateReader', side_effect=ValueError('Invalid archive')):
                with self.assertRaisesRegex(ValueError, 'Invalid archive'):
                    ProviderDocuments(provider).open('broken.cbz')
            source.close.assert_called_once_with()

    def test_password_retry_keeps_the_explicit_read_provider(self):
        from commonUtils.archives.zip_access import ArchivePasswordError
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.provider_documents import ProviderDocuments
        with TemporaryDirectory() as root:
            Path(root, 'fixture.cbz').write_bytes(b'opaque synthetic ciphertext')
            original, selected = LocalFiles(root), LocalFiles(root)
            original.archive_password = Mock(side_effect=AssertionError('Read provider was replaced'))
            selected.archive_password = Mock(return_value='synthetic-inner-password')
            sources = [SimpleNamespace(close=Mock()), SimpleNamespace(close=Mock())]
            selected.content_source = Mock(side_effect=sources)
            prepared = SimpleNamespace()
            with patch('services.documents.readers.PrivateReader',
                       side_effect=[ArchivePasswordError('Synthetic locked archive'), prepared]):
                reader = ProviderDocuments(original).open('fixture.cbz', read_provider=selected)
            self.addCleanup(reader.source.close)
            self.assertIs(reader.source.provider, selected)
            self.assertEqual(reader.password, 'synthetic-inner-password')
            selected.archive_password.assert_called_once_with('fixture.cbz', cancelled=reader.source.cancelled)
            sources[0].close.assert_called_once_with()
            sources[1].close.assert_not_called()

    def test_revocation_after_loading_releases_the_unpublished_reader(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.provider_documents import ProviderDocuments
        with TemporaryDirectory() as root:
            provider = LocalFiles(root)
            Path(root, 'note.txt').write_bytes(b'original')
            source = SimpleNamespace(close=Mock())
            provider.content_source = Mock(return_value=source)
            provider.check = Mock(side_effect=[None, ValueError('Credentials locked')])
            with self.assertRaisesRegex(ValueError, 'Credentials locked'):
                ProviderDocuments(provider).open('note.txt')
            source.close.assert_called_once_with()

    def provider(self, root, client):
        return native_service(client).localcrypt.open(LocalCryptLocation(Path(root), 'Secret'))

    def test_mobile_browser_stop_releases_only_its_own_access(self):
        from mobile.app import LogisticsMobile
        from mobile.browser_ui import FileBrowser
        with TemporaryDirectory() as root:
            LogisticsMobile.storage_root = Path(root)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            provider = self.provider(Path(root) / 'encrypted', Client())
            (provider.root / 'note.txt').write_bytes(b'ciphertext fixture')
            reader = encrypted_copies(provider)
            document = reader.open('note.txt')
            self.addCleanup(document.source.close)
            browser = FileBrowser()
            try:
                browser.set_entries(provider, '', provider.list())
                app.loop.run_until_complete(browser.close())
                self.assertTrue(provider.closed)
                self.assertEqual(document.text, 'fixture content')
                document.source.check_access()
            finally:
                app.loop.run_until_complete(browser.close())
                app.main_window.close()
                close_loop(app.loop)

    def test_browser_close_preserves_independent_reader_and_other_browser(self):
        with TemporaryDirectory() as root:
            client = Client()
            browser = self.provider(root, client)
            other = self.provider(root, client)
            (browser.root / 'note.txt').write_bytes(b'ciphertext fixture')
            reader = encrypted_copies(browser)
            document = reader.open('note.txt')
            self.addCleanup(document.source.close)
            release = browser.acquire()
            release()
            release()  # GUI close and destruction can both release their lease.
            with self.assertRaisesRegex(ValueError, 'closed'):
                browser.list()
            self.assertEqual(other.list()[0]['name'], 'note.txt')
            self.assertEqual(document.text, 'fixture content')
            document.source.check_access()
            self.assertFalse(document.source.provider.closed)

    def test_lock_and_identical_reunlock_never_revive_old_provider_or_buffer(self):
        with TemporaryDirectory() as root:
            client = Client()
            service = native_service(client)
            provider = self.provider(root, client)
            (provider.root / 'note.txt').write_bytes(b'ciphertext fixture')
            with provider.open('note.txt') as stream:
                self.assertEqual(stream.read(), b'fixture content')
                service.credentials.lock()
                with self.assertRaisesRegex(ValueError, 'locked'):
                    stream.seek(0)
                with self.assertRaises(ValueError):
                    stream.readline()
            client.generation += 1  # The same crypt key can be unlocked again.
            with self.assertRaises(ValueError):
                provider.reopen()
            self.assertEqual(self.provider(root, client).list()[0]['name'], 'note.txt')

    def test_revocation_during_listing_cannot_publish_plaintext_names(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            (provider.root / 'private-name.txt').write_bytes(b'ciphertext fixture')
            original = client.request
            def request(action, **values):
                result = original(action, **values)
                if action == 'crypt_paths':
                    client.lock()
                return result
            client.request = request
            with self.assertRaisesRegex(ValueError, 'locked'):
                provider.list()

    def test_generation_change_while_opening_does_not_create_storage(self):
        with TemporaryDirectory() as root:
            client = Client()
            original = client.request
            def request(action, **values):
                result = original(action, **values)
                client.lock()
                return result
            client.request = request
            with self.assertRaises(ValueError):
                self.provider(root, client)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_native_lock_scope_is_explicit_and_saved_material_is_untouched(self):
        client = Client()
        client.vault = SimpleNamespace(forget=lambda: self.fail('Lock must not forget saved credentials'))
        service = native_service(client)
        self.assertIs(service, native_service(client))
        self.assertEqual(service.credentials.lock_scope, 'all')
        with self.assertRaisesRegex(ValueError, 'all loaded packages'):
            service.credentials.lock('Personal')
        self.assertEqual(client.generation, 0)

    def test_worker_cancellation_does_not_revoke_the_view_or_a_completed_operation(self):
        from commonUtils.runtime.operations import OperationCancelled
        with TemporaryDirectory() as root:
            provider = self.provider(root, Client())
            cancelled = [False]
            with provider.operation(lambda: cancelled[0]):
                self.assertEqual(provider.list(), [])
                cancelled[0] = True  # Publication/operation already completed.
            self.assertFalse(provider.closed)
            with self.assertRaises(OperationCancelled), provider.operation(lambda: True):
                self.fail('Cancelled work was admitted')
            self.assertEqual(provider.list(), [])

    def test_offline_reader_cannot_save_after_lock_and_identical_reunlock(self):
        from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
        with TemporaryDirectory() as root:
            client = Client()
            copies = LocalCryptCopies(Path(root), client)
            key = 'b' * 32
            folder = Path(root) / key
            folder.mkdir()
            (folder / 'data').write_bytes(b'ciphertext fixture')
            (folder / 'record.json').write_text(json.dumps(dict(
                remote='Secret', encrypted_path='encoded-name', identity='a' * 64)))
            reader = copies.open(key)
            client.lock()
            client.generation += 1
            with self.assertRaisesRegex(ValueError, 'locked'):
                copies.save(reader, 'old reader must not publish')
            self.assertEqual((folder / 'data').read_bytes(), b'ciphertext fixture')
            self.assertEqual(copies.open(key).text, 'fixture content')
