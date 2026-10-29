"""Video range, grant, resume and subtitle contracts without native decoders."""
from contextlib import contextmanager, ExitStack
from http.client import HTTPConnection, RemoteDisconnected
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import shutil
from urllib.parse import urlsplit
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from features.video.playback import VideoContent, session_only
from services.documents.video_progress import VideoProgress
from features.video.subtitles import Subtitles
from features.video.transport import VideoTransport, byte_range


class VideoContracts(unittest.TestCase):
    def test_real_localcrypt_video_ranges_and_encrypted_resume(self):
        from features.rclone import executable, session
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is unavailable')
        with TemporaryDirectory() as directory, ExitStack() as cleanup, crypt_fixture(directory, binary, state_password='synthetic-package-password') as fixture, patch.object(
                executable, 'get_rclone_path', return_value=binary):
            from commonUtils.filesystem.native_paths import native_path
            # The normal-root fixture proves production path handling. Retire
            # its long ciphertext names before stdlib's normal-path cleanup.
            cleanup.callback(shutil.rmtree, native_path(directory))
            raw = b'video range fixture\x00' * 600000
            fixture.provider.create_file('movie.mkv', BytesIO(raw))
            content = VideoContent(fixture.provider, 'movie.mkv')
            try:
                self.assertEqual(content.size, len(raw))
                with content.open() as stream:
                    stream.seek(len(raw) - 100)
                    self.assertEqual(stream.read(100), raw[-100:])
                state = VideoProgress(content, Path(directory) / 'public-cache')
                state.save(24680)
                self.assertEqual(state.load(), 24680)
                state.save(13579)
                self.assertEqual(state.load(), 13579)
                encrypted = state.credential_state.root / (state.credential_state.binding() + '.zip')
                self.assertNotIn(b'position', encrypted.read_bytes())
                self.assertFalse((Path(directory) / 'public-cache').exists())
                self.assertEqual(VideoProgress(content, Path(directory) / 'public-cache').load(), 13579)
                session.forget(fixture.context)
                with self.assertRaises((ValueError, PermissionError)):
                    content.check()
            finally:
                content.close()

    def test_range_forms_and_invalid_ranges(self):
        for header, expected in [(None, (0, 9)), ('bytes=2-4', (2, 4)),
                                 ('bytes=2-', (2, 9)), ('bytes=-3', (7, 9)),
                                 ('bytes=8-99', (8, 9)), ('bytes=-99', (0, 9))]:
            self.assertEqual(byte_range(header, 10), expected)
        for header in ('items=0-1', 'bytes=', 'bytes=-0', 'bytes=9-2', 'bytes=10-',
                       'bytes=0-1,4-5', 'bytes=+1-2', 'bytes=one-two', 'bytes=١-٢'):
            with self.subTest(header=header), self.assertRaises(ValueError):
                byte_range(header, 10)

    def test_http_ranges_no_directory_access_and_revocation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'movie.mkv').write_bytes(b'0123456789')
            content = VideoContent(LocalFiles(root), 'movie.mkv')
            transport = VideoTransport(content)
            self.addCleanup(content.close)
            self.addCleanup(transport.close)
            url = urlsplit(transport.url)
            def request(path=url.path, method='GET', headers=None):
                connection = HTTPConnection(url.hostname, url.port, timeout=2)
                try:
                    connection.request(method, path, headers=headers or {})
                    response = connection.getresponse()
                    return response.status, dict(response.getheaders()), response.read()
                finally:
                    connection.close()
            status, headers, data = request(headers={'Range': 'bytes=3-6'})
            self.assertEqual((status, data), (206, b'3456'))
            self.assertEqual(headers['Content-Range'], 'bytes 3-6/10')
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(request(method='HEAD')[2], b'')
            self.assertEqual(request('/')[0], 404)
            self.assertEqual(request(url.path + '/../movie.mkv')[0], 404)
            self.assertEqual(request(headers={'Range': 'bytes=99-'})[0], 416)
            transport.suspend()
            with self.assertRaises(RemoteDisconnected):
                request()
            transport.resume()
            self.assertEqual(request()[2], b'0123456789')
            content.close()
            with self.assertRaises(RemoteDisconnected):
                request()

    def test_replaced_video_does_not_restore_old_progress(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / 'movie.mp4'
            video.write_bytes(b'first')
            content = VideoContent(LocalFiles(root), video.name)
            progress = VideoProgress(content, root / 'state')
            progress.save(12345)
            self.assertEqual(progress.load(), 12345)
            content.close()
            video.write_bytes(b'new revision')
            with_content = VideoContent(LocalFiles(root), video.name)
            try:
                self.assertEqual(VideoProgress(with_content, root / 'state').load(), 0)
                progress = VideoProgress(with_content, root / 'state')
                progress.save(35000, completed=True)
                self.assertEqual(progress.load(), 0)
            finally:
                with_content.close()

    def test_private_progress_uses_decoded_content_not_transfer_bytes(self):
        class PrivateFiles(LocalFiles):
            private = True
            session_only = True
            def content_source(self, path, **kwargs):
                provider = self
                class Decoded:
                    @contextmanager
                    def open(self, key):
                        with BytesIO((provider.root / key).read_bytes()[::-1]) as stream:
                            yield stream
                    def close(self):
                        pass
                return Decoded()
            def create_file(self, path, stream, **kwargs):
                return super().create_file(path, BytesIO(stream.read()[::-1]), **kwargs)
            def replace_bytes(self, path, raw, *, expected_revision):
                if self.entry(path)['revision'] != expected_revision:
                    raise ValueError('Changed')
                (self.root / path).write_bytes(raw[::-1])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'secret.mkv').write_bytes(b'fake video')
            content = VideoContent(PrivateFiles(root), 'secret.mkv')
            try:
                state = VideoProgress(content, root / 'ordinary-state')
                state.save(24680)
                self.assertEqual(state.load(), 24680)
                self.assertFalse((root / 'ordinary-state').exists())
                self.assertFalse(list(root.glob('ReaderPositions/*.zip')))  # No owning ZIP password: RAM only.
                state.save(123)
                self.assertEqual(state.load(), 123)
                with self.assertRaises(PermissionError):
                    content.require_external()
            finally:
                content.close()

    def test_cloud_wrappers_and_unknown_private_policy_fail_closed(self):
        self.assertFalse(session_only(SimpleNamespace(private=False)))
        self.assertTrue(session_only(SimpleNamespace(private=True)))
        client = SimpleNamespace(package_records=[dict(remotes=['Video'], saved=True)])
        provider = SimpleNamespace(private=True, session_only=False, client=client, remote='Video')
        self.assertFalse(session_only(provider))
        client.package_records[0]['saved'] = False
        self.assertFalse(session_only(provider))  # Consumers do not inspect credential records.
        provider.session_only = True
        self.assertTrue(session_only(provider))
        self.assertTrue(session_only(SimpleNamespace(private=False, session_only=False, provider=provider)))
        self.assertFalse(session_only(SimpleNamespace(private=True, session_only=False)))

    def test_gate_and_revision_checked_after_open(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'movie.mp4').write_bytes(b'video')
            provider = LocalFiles(root)
            provider.privacy_gate = SimpleNamespace(locked=False)
            content = VideoContent(provider, 'movie.mp4')
            try:
                provider.privacy_gate.locked = True
                with self.assertRaises(PermissionError):
                    content.check()
                provider.privacy_gate.locked = False
                (root / 'movie.mp4').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    content.check()
            finally:
                content.close()

    def test_subtitles_boundaries_overlap_markup_and_limits(self):
        subtitles = Subtitles(b'1\n00:00:01,000 --> 00:00:03,000\n<b>One</b>\n\n2\n00:00:02,000 --> 00:00:04,000\nTwo')
        self.assertEqual(subtitles.at(999), '')
        self.assertEqual(subtitles.at(1000), 'One')
        self.assertEqual(subtitles.at(2000), 'One\nTwo')
        self.assertEqual(subtitles.at(3000), 'Two')
        self.assertEqual(subtitles.at(4000), '')
        with self.assertRaises(ValueError):
            Subtitles(b'1\n00:62:01,000 --> 00:00:03,000\nInvalid')
        with self.assertRaises(ValueError):
            Subtitles(b'x' * (8 * 1024 * 1024 + 1))
