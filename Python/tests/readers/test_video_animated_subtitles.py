"""Verify that the compatibility decoder composites changing ASS frames."""
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from PIL import Image

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.video.ui.player import VideoWindow
from logistics_build.build_retention import scratch
from tests.readers.decoder_fixtures import headless_vlc_playback

TEST_STAGE = TestStage.EXTENDED


def make_movie(root):
    source = Path(__file__).with_name('fixtures') / 'video' / 'animated.ass'
    # Encode the video frame number in the first row of blocks so delayed Qt
    # callbacks and coarse decoder clocks cannot shift a subtitle comparison.
    clock = root / 'clock.gray'
    with clock.open('wb') as frames:
        for index in range(250):
            blocks = b''.join(bytes([150 if index & (1 << bit) else 20]) * 8 for bit in range(8))
            frames.write((blocks + bytes(256)) * 12 + bytes(320 * 168))
    movie = root / 'fixture.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pixel_format', 'gray',
        '-video_size', '320x180', '-framerate', '25', '-i', str(clock), '-f', 'lavfi', '-i',
        'sine=frequency=440:sample_rate=48000:duration=10', '-i', str(source), '-map', '0:v',
        '-map', '1:a', '-map', '2:s', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt',
        'yuv420p', '-c:a', 'aac', '-c:s', 'copy', '-disposition:s:0', 'default', str(movie)],
        check=True, timeout=30, capture_output=True)
    return movie


class AnimatedSubtitleTests(QtTestCase):
    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg synthetic fixture generator required')
    def test_vlc_composites_current_ass_state_with_each_video_frame(self):
        with scratch() as root:
            movie = make_movie(root)
            with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'cache'):
                window = VideoWindow(ResourceChoice(LocalFiles(root), movie.name),
                                     backend_factory=headless_vlc_playback)
            observations = {}
            end = -1

            def observe(frame):
                nonlocal end
                if not frame.isValid():
                    return
                image = frame.toImage().convertToFormat(qt.QImage.Format.Format_RGB888)
                index = sum(1 << bit for bit in range(8) if image.pixelColor(4 + bit * 8, 4).red() > 80)
                end = index
                pixels = Image.frombytes('RGB', (image.width(), image.height()), image.constBits(),
                                        'raw', 'RGB', image.bytesPerLine())
                region = pixels.crop((0, 30, 320, 180))
                box = region.convert('L').point(lambda value: 255 if value > 65 else 0).getbbox()
                observations[index] = (box, region.getpixel((box[0] + 8, box[1] + 8))[2] if box else None)

            window.player.videoSink().videoFrameChanged.connect(observe)
            try:
                window.show()
                self.wait_until(lambda: end >= 235, timeout=22)
                # ASS moves 220 px over five seconds, then holds its final
                # position for one second before the static cue replaces it.
                # Use short frame ranges so missing callbacks under host load
                # do not require a particular frame to arrive.
                for first, last in ((12, 24), (30, 43), (60, 73), (94, 107), (126, 139),
                                    (153, 169), (180, 193), (208, 222), (228, 235)):
                    with self.subTest(frames=(first, last)):
                        matches = {index: data for index, data in observations.items() if first <= index <= last}
                        self.assertTrue(matches, 'No decoded picture in this part of the timeline')
                        for index, (box, blue) in matches.items():
                            if index < 25 or index >= 225:
                                self.assertIsNone(box)
                                continue
                            x = min(244, round(24 + (index - 25) * 220 / 125)) if index < 175 else 120
                            self.assertIsNotNone(box)
                            self.assertAlmostEqual(box[0], x, delta=2)
                            self.assertAlmostEqual(box[2] - box[0], 24, delta=2)
                            if index >= 175 or index < 43:
                                self.assertLess(blue, 80)
                            elif index >= 153:
                                self.assertGreater(blue, 220)
                self.assertGreater(window.player.stats.played_abuffers, 0)
            finally:
                window.close()
                self.wait_until(lambda: window.content.closed, drain_deferred=True)
