"""Decoder fixture setup does not invoke an encoder during ordinary tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
from commonUtils.testing.stages import TestStage
from tests.readers.video_fixtures import codec_matrix, chapter_movie, layout_evidence

TEST_STAGE = TestStage.REGRESSION


class VideoFixtureTests(TestCase):
    def test_screenshot_failure_preserves_original_layout_assertion(self):
        for failure in (OSError('Disk full'), False):
            with self.subTest(capture=failure), TemporaryDirectory() as directory:
                window = Mock()
                save = window.grab.return_value.save
                if isinstance(failure, Exception):
                    save.side_effect = failure
                else:
                    save.return_value = failure
                original = AssertionError('Controls overlap the picture')
                with self.assertRaises(AssertionError) as caught:
                    with layout_evidence(window, Path(directory) / 'layout.png'):
                        raise original
                self.assertIs(caught.exception, original)
                self.assertIn('Layout screenshot capture failed', original.__notes__[0])

    def test_default_fixtures_use_verified_clips_even_with_ffmpeg_installed(self):
        with TemporaryDirectory() as directory, patch(
                'tests.readers.video_fixtures.subprocess.run', side_effect=AssertionError('Unexpected encoding')):
            root = Path(directory)
            rows = codec_matrix(root)
            self.assertEqual(len(rows), 13)
            self.assertTrue(all(path.is_file() and path.stat().st_size for _, _, _, path in rows))
            self.assertTrue(chapter_movie(root).is_file())

    def test_regeneration_is_explicit_and_keeps_custom_duration(self):
        with TemporaryDirectory() as directory, patch('tests.readers.video_fixtures.subprocess.run') as encode:
            rows = codec_matrix(directory, duration=3, regenerate=True)
            self.assertEqual(len(rows), 13)
            self.assertEqual(encode.call_count, 13)
            for call in encode.call_args_list:
                command = call.args[0]
                self.assertEqual(command[command.index('-t') + 1], '3')
