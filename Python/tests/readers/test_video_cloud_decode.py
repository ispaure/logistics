"""Real rclone plain/crypt decoding over revocable loopback ranges."""
from unittest.mock import patch
from collections import deque
from contextlib import ExitStack
from time import monotonic
from shiboken6 import isValid
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt

TEST_STAGE = TestStage.EXTENDED


class CloudVideoDecodeTests(QtTestCase):
    def test_rclone_plain_and_crypt_cloud_streams_decode_frames_and_audio(self):
        from PySide6.QtMultimedia import QAudioBufferOutput, QMediaPlayer, QVideoSink
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import bundled_movie
        from tests.local_crypt_fixture import crypt_fixture
        from features.rclone import executable, session
        from features.rclone.remote_resources import RemoteResources
        from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
        from features.video.playback import VideoContent
        from features.video.transport import VideoTransport
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is unavailable')
        with scratch() as root, crypt_fixture(root, binary) as fixture, patch.object(
                executable, 'get_rclone_path', return_value=binary):
            movies = [bundled_movie(name, root) for name in ('h264-aac.mp4', 'mpeg4-mp3.avi')]
            for movie in movies:
                environment, source, destination = session.launch(fixture.context, movie, 'Secret:' + movie.name)
                run_bytes([str(binary), '--config', session.NULL_CONFIG, 'copyto', str(source), str(destination)],
                          environment=environment, max_output=0)
            values = session.credentials(fixture.context)
            session.remember(fixture.context, dict(values, Plain=dict(type='alias', remote=str(movie.parent))))
            for remote, key in [(remote, movie.name) for movie in movies for remote in ('Plain', 'Secret')]:
                with self.subTest(remote=remote, file=key), ExitStack() as cleanup:
                    started = monotonic()
                    def checkpoint(phase):
                        print(f'Cloud decode {remote}/{key}: {phase} at {monotonic() - started:.3f}s', flush=True)
                    provider = RemoteResources(fixture.context, remote, binary=binary)
                    cleanup.callback(provider.close)
                    content = VideoContent(provider, key)
                    cleanup.callback(content.close)
                    checkpoint('admitted')
                    transport_errors = []
                    transport = VideoTransport(content, failed=transport_errors.append)
                    def close_transport():
                        transport.close()
                        checkpoint('transport closed')
                    cleanup.callback(close_transport)
                    player = QMediaPlayer()
                    def retire_player():
                        try:
                            player.stop()
                            player.setSource(qt.QUrl())
                        finally:
                            player.deleteLater()
                            self.wait_until(lambda: not isValid(player), drain_deferred=True)
                            checkpoint('native retired')
                    cleanup.callback(retire_player)
                    sink, output = QVideoSink(player), QAudioBufferOutput(player)
                    player.setVideoSink(sink)
                    player.setAudioBufferOutput(output)
                    frames, samples, errors = deque(maxlen=1), deque(maxlen=1), []
                    sink.videoFrameChanged.connect(lambda frame, frames=frames: frames.append(frame.startTime()) if frame.isValid() else None)
                    output.audioBufferReceived.connect(lambda buffer, samples=samples: samples.append(buffer.frameCount()) if buffer.isValid() else None)
                    player.errorOccurred.connect(lambda error, message, errors=errors: errors.append(message))
                    player.setSource(qt.QUrl(transport.url))
                    player.play()
                    checkpoint('playing requested')
                    self.wait_until(lambda: (frames and samples) or errors or transport_errors, timeout=30,
                        message=lambda: repr(dict(remote=remote, file=key, frames=len(frames),
                            samples=len(samples), errors=errors, transport=transport_errors,
                            status=str(player.mediaStatus()), state=str(player.playbackState()),
                            position=player.position(), duration=player.duration())))
                    self.assertFalse(transport_errors, transport_errors)
                    self.assertFalse(errors, errors)
                    self.assertTrue(frames, 'No cloud video frames')
                    self.assertTrue(samples, 'No cloud audio samples')
                    checkpoint('decoded')
                    player.pause()
                    frames.clear()
                    player.setPosition(1000)
                    self.assertTrue(player.isSeekable())
                    # A setter updates Qt's logical position before the
                    # demuxer finishes its HTTP seek. Verify the decoded
                    # result before retiring this player and its provider.
                    self.wait_until(lambda: (frames and frames[-1] >= 900000) or errors or transport_errors,
                        timeout=10, message=lambda: repr(dict(remote=remote, file=key, phase='seek',
                            frames=list(frames), errors=errors, transport=transport_errors)))
                    self.assertFalse(errors, errors)
                    self.assertFalse(transport_errors, transport_errors)
                    checkpoint('seek decoded')
