"""Remote service lifetimes and publication races without network access."""
import base64
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest
from unittest.mock import patch

from features.rclone.mobile.service import native_service
from features.rclone.mobile.remote_readers import RemoteSource
from features.rclone.remote_access import NativeRemoteLocation


class Client:
    generation = 1

    def __init__(self):
        self.cached = {}
        self.before_list = lambda: None

    def connection_identity(self, remote):
        return remote + '-identity'

    def entries(self, remote, path=''):
        self.before_list()
        return [dict(path='note.txt', directory=False, size=4)]

    def request(self, action, **values):
        if action == 'remote_stat':
            return dict(size=4, revision='one')
        if action == 'remote_range':
            data = b'note'[values['offset']:values['offset'] + values['count']]
            return dict(data=base64.b64encode(data).decode())
        if action == 'remote_cache_open':
            self.cached[values['run']] = b'note'
            return {}
        if action == 'remote_cache_close':
            self.cached.pop(values['run'], None)
            return {}
        raise AssertionError(action)

    def lock(self):
        self.generation += 1


class RemoteServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.service = native_service(self.client)

    def open(self, remote='Files'):
        return self.service.remotes.open(NativeRemoteLocation(remote))

    def test_browser_closure_keeps_readers_independent_but_lock_revokes_all(self):
        browser = self.open()
        readers = browser.readers()
        first, second = readers.open('note.txt'), readers.open('note.txt')
        browser.close()
        first.source.close()
        second.source.check()
        third = readers.open('note.txt')
        self.service.credentials.lock()
        for source in (second.source, third.source):
            with self.assertRaises(ValueError):
                source.check()
        with self.assertRaises(ValueError):
            readers.open('note.txt')
        self.assertFalse(self.open().closed)
        # Reloading identical settings does not revive the captured reader store.
        with self.assertRaises(ValueError):
            readers.open('note.txt')

    def test_identity_and_expected_generation_refuse_rebinding(self):
        with self.assertRaisesRegex(ValueError, 'connection changed'):
            self.service.remotes.open(NativeRemoteLocation('Files', identity='Other-identity'))
        with self.assertRaisesRegex(ValueError, 'Credentials changed'):
            self.service.remotes.open(NativeRemoteLocation('Files', generation=0))

    def test_generation_change_during_open_cannot_capture_replacement_access(self):
        identity = self.client.connection_identity
        def changed(remote):
            self.client.lock()
            return identity(remote)
        self.client.connection_identity = changed
        with self.assertRaises(ValueError):
            self.open()

    def test_reader_store_rejects_another_clients_resource(self):
        from features.rclone.mobile.remote_readers import RemoteReaders
        with self.assertRaisesRegex(ValueError, 'another connection'):
            RemoteReaders(Client(), 'Files', resource=self.open())

    def test_late_listing_is_rejected_after_credential_change(self):
        resource = self.open()
        self.client.before_list = self.client.lock
        with self.assertRaises(ValueError):
            resource.list()
        self.assertTrue(resource.closed)

    def test_open_stream_checks_original_grant_on_cached_reads(self):
        resource = self.open()
        with resource.open('note.txt') as stream:
            self.assertEqual(stream.read(1), b'n')
            self.client.lock()
            with self.assertRaises(ValueError):
                stream.read(1)

    def test_close_during_native_cache_creation_retires_late_snapshot(self):
        started, release = Event(), Event()
        request = self.client.request
        def paused(action, **values):
            if action == 'remote_cache_open':
                started.set()
                if not release.wait(5):
                    raise TimeoutError('Fixture was not released')
            return request(action, **values)
        self.client.request = paused
        source = RemoteSource(self.client, 'Files', 'note.txt')
        with ThreadPoolExecutor() as workers:
            pending = workers.submit(source.cache_archive)
            try:
                self.assertTrue(started.wait(5))
                source.close()
            finally:
                release.set()
            with self.assertRaises(ValueError):
                pending.result(5)
        self.assertEqual(self.client.cached, {})
        self.assertIsNone(source.cache_token)

    def test_failed_progress_clears_cache_state(self):
        source = RemoteSource(self.client, 'Files', 'note.txt')
        def failed(message):
            raise RuntimeError('Presentation closed')
        source.progress = failed
        with self.assertRaises(RuntimeError):
            source.cache_archive()
        self.assertTrue(source.closed)
        self.assertEqual(self.client.cached, {})
        self.assertIsNone(source.cache_token)

    def test_cancelled_reader_setup_closes_its_independent_resource(self):
        readers = self.open().readers()
        opened = readers.resource.reopen()
        with patch.object(readers.resource, 'reopen', return_value=opened), patch(
                'features.rclone.mobile.remote_readers.direct_kind', side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                readers.open('note.txt')
        self.assertTrue(opened.closed)
        self.assertFalse(readers.resource.closed)
