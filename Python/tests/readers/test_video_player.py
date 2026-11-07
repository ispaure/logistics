"""Video range, grant, resume and subtitle contracts without native decoders."""

from commonUtils.testing.stages import TestStage, stage

TEST_STAGE = TestStage.REGRESSION
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
    def test_selected_sidecar_is_restored_after_video_folder_move(self):
        from features.video.sidecars import discover_sidecars
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'renamed.mp4').write_bytes(b'movie')
            (root / 'captions.srt').write_text('1\n00:00:01,000 --> 00:00:02,000\nHi\n')
            content = VideoContent(LocalFiles(root), 'renamed.mp4')
            try:
                subtitles = discover_sidecars(content, preferred='oldfolder/captions.srt')
                try:
                    self.assertEqual([item.path for item in subtitles], ['captions.srt'])
                finally:
                    for item in subtitles:
                        item.close()
            finally:
                content.close()

    def test_legacy_local_position_and_defaults_migrate_to_content_record(self):
        from dataclasses import asdict
        from hashlib import sha256
        import json
        from features.video.session import PlaybackSettings
        from services.documents.video_settings import SettingsStore, VideoSettingsStore
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'movie.mp4').write_bytes(b'legacy movie')
            provider = LocalFiles(root)
            content = VideoContent(provider, 'movie.mp4')
            self.addCleanup(content.close)
            cache = root / 'state'
            cache.mkdir()
            key = sha256(json.dumps([provider.storage_id, provider.storage_namespace, content.path]).encode()).hexdigest()
            (cache / (key + '.json')).write_text(json.dumps(dict(schema=1,
                revision=json.dumps(content.source.expected), position=1234, generation='')))
            SettingsStore(cache).save(asdict(PlaybackSettings(rate=1.5)))
            progress = VideoProgress(content, cache)
            self.assertEqual(progress.load(), 1234)
            self.assertEqual(VideoSettingsStore(progress, cache).load().rate, 1.5)
            progress.save(5678)
            restored = VideoProgress(content, cache)
            self.assertEqual(restored.load(), 5678)
            self.assertEqual(restored.settings.rate, 1.5)

    def test_local_settings_and_position_follow_moves_survive_completion_and_isolate_copies(self):
        from dataclasses import asdict
        from features.video.session import PlaybackSettings
        from services.documents.video_settings import VideoSettingsStore
        with TemporaryDirectory() as directory:
            root = Path(directory)
            movie = root / 'movie.mp4'
            movie.write_bytes(b'video data' * 100)
            content = VideoContent(LocalFiles(root), movie.name)
            progress = VideoProgress(content, root / 'state')
            progress.load()
            preferences = PlaybackSettings(rate=1.5, aspect='fill', audio_track=2, subtitle_track=-1)
            VideoSettingsStore(progress, root / 'state').save(asdict(preferences))
            progress.save(12345)
            content.close()
            target = root / 'subfolder'
            target.mkdir()
            shutil.copyfile(movie, target / 'copied.mp4')
            movie.rename(target / 'renamed.mp4')
            copied = VideoContent(LocalFiles(target), 'copied.mp4')
            original = VideoContent(LocalFiles(target), 'renamed.mp4')
            try:
                self.assertEqual(VideoProgress(copied, root / 'state').load(), 0)
                restored = VideoProgress(original, root / 'state')
                self.assertEqual(restored.load(), 12345)
                self.assertEqual(restored.settings, preferences)
                restored.save(99999, completed=True)
                reopened = VideoProgress(original, root / 'state')
                self.assertEqual(reopened.load(), 0)
                self.assertEqual(reopened.settings, preferences)
                self.assertFalse((root / 'state' / 'playback-settings.json').exists())
            finally:
                copied.close()
                original.close()


    @stage(TestStage.EXTENDED)
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
                from features.video.session import PlaybackSettings
                state.settings = PlaybackSettings(rate=1.25, aspect='fill', subtitle_track=-1)
                state.duration = 90000
                state.save(24680)
                self.assertEqual(state.load(), 24680)
                self.assertEqual(state.duration, 90000)
                self.assertEqual(state.settings.rate, 1.25)
                state.save(13579)
                self.assertEqual(state.load(), 13579)
                encrypted, = (Path(directory) / 'ReaderPositions').glob('*.zip')
                self.assertNotIn(b'position', encrypted.read_bytes())
                self.assertFalse((Path(directory) / 'public-cache').exists())
                reopened = VideoProgress(content, Path(directory) / 'public-cache')
                self.assertEqual(reopened.load(), 13579)
                self.assertEqual(reopened.duration, 90000)
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

    def test_loopback_start_does_not_wait_for_reverse_dns(self):
        from threading import Event, Thread
        entered, release, completed = Event(), Event(), Event()
        transports, errors = [], []
        def resolve(address):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Resolver fixture was not released')
            return 'localhost', [], [address]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'movie.mp4').write_bytes(b'movie')
            content = VideoContent(LocalFiles(root), 'movie.mp4')
            def start():
                try:
                    transports.append(VideoTransport(content))
                except Exception as error:
                    errors.append(error)
                finally:
                    completed.set()
            worker = Thread(target=start)
            try:
                with patch('socket.gethostbyaddr', side_effect=resolve) as lookup:
                    worker.start()
                    try:
                        self.assertTrue(completed.wait(2), 'Loopback startup waited for reverse DNS')
                        self.assertFalse(entered.is_set())
                        self.assertEqual(errors, [])
                        lookup.assert_not_called()
                    finally:
                        release.set()
                        worker.join(3)
                    self.assertFalse(worker.is_alive())
            finally:
                for transport in transports:
                    transport.close()
                content.close()

    def test_loopback_start_ignores_unavailable_or_raising_reverse_dns(self):
        from socket import herror
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'movie.mp4').write_bytes(b'movie')
            content = VideoContent(LocalFiles(root), 'movie.mp4')
            try:
                for error in (herror('No reverse DNS'), RuntimeError('Resolver unavailable')):
                    with self.subTest(error=type(error).__name__), patch('socket.gethostbyaddr', side_effect=error) as lookup:
                        transport = VideoTransport(content)
                        try:
                            self.assertEqual(transport.server.server_address[0], '127.0.0.1')
                            self.assertEqual(transport.server.server_name, '127.0.0.1')
                            self.assertEqual(transport.server.server_port, transport.server.server_address[1])
                            lookup.assert_not_called()
                        finally:
                            transport.close()
                            transport.close()
                        self.assertFalse(transport.thread.is_alive())
                        self.assertEqual(transport.server.socket.fileno(), -1)
            finally:
                content.close()

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
