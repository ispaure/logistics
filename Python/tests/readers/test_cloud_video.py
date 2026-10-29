"""Cloud video ranges use real rclone and credential-bound native resources."""
import base64
from http.client import HTTPConnection, RemoteDisconnected
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from features.video.playback import VideoContent
from services.documents.video_progress import VideoProgress
from features.video.transport import VideoTransport


class CloudVideoTests(unittest.TestCase):
    def ranges(self, content, raw):
        transport = VideoTransport(content)
        self.addCleanup(transport.close)
        url = urlsplit(transport.url)

        def request(start, end):
            connection = HTTPConnection(url.hostname, url.port, timeout=30)
            try:
                connection.request('GET', url.path, headers={'Range': f'bytes={start}-{end}'})
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()

        for start, end in ((0, 15), (len(raw) - 32, len(raw) - 1), (1024 * 1024 - 8, 1024 * 1024 + 9)):
            self.assertEqual(request(start, end), (206, raw[start:end + 1]))
        return request

    def test_real_rclone_plain_and_crypt_ranges_and_session_revocation(self):
        from features.rclone import executable, session
        from features.rclone.remote_resources import RemoteResources
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is unavailable')
        raw = bytes(range(256)) * 9000
        with TemporaryDirectory() as directory, crypt_fixture(directory, binary, state_password='synthetic-package-password') as fixture, patch.object(
                executable, 'get_rclone_path', return_value=binary):
            # Publish through the actual crypt remote, not the offline LocalCrypt copy.
            from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
            path = fixture.plain / 'movie.mkv'
            path.write_bytes(raw)
            environment, source, destination = session.launch(fixture.context, path, 'Secret:movie.mkv')
            run_bytes([str(binary), '--config', session.NULL_CONFIG, 'copyto', str(source), str(destination)],
                      environment=environment, max_output=0)
            values = session.credentials(fixture.context)
            session.remember(fixture.context, dict(values, Plain=dict(type='alias', remote=str(fixture.plain))),
                             state_password='synthetic-package-password', state_identity='a'*64)
            for remote, key in [('Plain', 'movie.mkv'), ('Secret', 'movie.mkv')]:
                with self.subTest(remote=remote):
                    provider = RemoteResources(fixture.context, remote, binary=binary)
                    content = VideoContent(provider, key)
                    try:
                        self.assertTrue(content.remote)
                        self.assertEqual(content.size, len(raw))
                        self.ranges(content, raw)
                        progress = VideoProgress(content, fixture.root / 'forbidden-cache')
                        progress.save(12345)
                        self.assertEqual(progress.load(), 12345)
                        self.assertEqual(VideoProgress(content, fixture.root / 'forbidden-cache').load(), 12345)
                        state_path = progress.credential_state.root / (progress.credential_state.binding() + '.zip')
                        state = state_path.read_bytes()
                        self.assertNotIn(b'position', state)
                        self.assertNotIn(b'movie.mkv', state)
                        progress.save(1, completed=True)
                        self.assertEqual(progress.load(), 0)
                        self.assertTrue(state_path.exists())
                        self.assertTrue(content.restricted)
                        with self.assertRaises(PermissionError):
                            content.require_external()
                    finally:
                        content.close()
                        provider.close()
            provider = RemoteResources(fixture.context, 'Secret', binary=binary)
            content = VideoContent(provider, 'movie.mkv')
            try:
                request = self.ranges(content, raw)
                session.forget(fixture.context)
                with self.assertRaises((ValueError, PermissionError)):
                    content.check()
                with self.assertRaises(RemoteDisconnected):
                    request(0, 15)
            finally:
                content.close()
                provider.close()

    def test_native_remote_ranges_revision_and_credential_generation(self):
        from features.rclone.mobile.service import native_service
        from features.rclone.remote_access import NativeRemoteLocation
        raw = bytes(range(256)) * 9000

        class Client:
            generation = 1
            revision = 'original'
            package_records = [dict(remotes=['Secret'], saved=False, crypt_identities={'Secret': 'crypt'})]
            calls = []

            def connection_identity(self, remote):
                return 'connection'

            def request(self, action, **values):
                self.calls.append((action, values))
                if action == 'remote_stat':
                    return dict(size=len(raw), revision=self.revision)
                if action == 'remote_range':
                    if values['expected'] != self.revision:
                        raise ValueError('The remote file changed.')
                    start, count = values['offset'], values['count']
                    return dict(data=base64.b64encode(raw[start:start + count]).decode())
                raise AssertionError(action)

        client = Client()
        provider = native_service(client).remotes.open(NativeRemoteLocation('Secret'))
        content = VideoContent(provider, 'movie.mp4')
        try:
            provider.close()  # Independent content grant survives browser closure.
            self.ranges(content, raw)
            self.assertTrue(content.restricted)
            requests = [values for action, values in client.calls if action == 'remote_range']
            self.assertTrue(requests)
            self.assertTrue(all(values['count'] <= 4 * 1024 * 1024 for values in requests))
            client.revision = 'replacement'
            with self.assertRaisesRegex(ValueError, 'changed'):
                content.check()
            client.revision = 'original'
            client.generation += 1
            with self.assertRaises(ValueError):
                content.check()
        finally:
            content.close()

    def test_mobile_feature_migrates_previous_video_switch(self):
        from services.mobile_features import disabled_features, document_feature
        self.assertEqual(disabled_features('["media"]'), {'video'})
        self.assertEqual(document_feature('movie.MKV'), 'video')
        self.assertEqual(document_feature('movie.mp4'), 'video')

    def test_transport_cancellation_closes_connection_without_server_traceback(self):
        from commonUtils.runtime.operations import OperationCancelled
        from types import SimpleNamespace
        from unittest.mock import Mock
        content = SimpleNamespace(path='movie.mp4', size=10,
            check=Mock(side_effect=OperationCancelled('cancelled')))
        transport = VideoTransport(content)
        try:
            url = urlsplit(transport.url)
            with patch.object(transport.server, 'handle_error') as error:
                connection = HTTPConnection(url.hostname, url.port, timeout=2)
                try:
                    connection.request('GET', url.path)
                    with self.assertRaises(RemoteDisconnected):
                        connection.getresponse()
                finally:
                    connection.close()
                error.assert_not_called()
        finally:
            transport.close()
