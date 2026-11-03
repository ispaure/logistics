"""Markdown media refresh and malformed-reference isolation."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.request import urlopen

from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from services.documents.markdown import prepare_markdown
from services.documents.markdown_media import MarkdownMedia

TEST_STAGE = TestStage.REGRESSION


class MarkdownMediaTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.provider = LocalFiles(self.root)
        self.video = self.root / 'clip.mp4'
        self.video.write_bytes(b'first video bytes')
        self.media = MarkdownMedia(self.provider, 'Home.md', root='')
        self.addCleanup(self.media.close)

    def test_changed_video_gets_a_new_stream_and_retires_old_revision(self):
        source = self.media.render_source()
        first = source('clip.mp4')
        old_content, old_transport = self.media.videos['clip.mp4']
        self.video.write_bytes(b'replacement video with different bytes')
        second = source('clip.mp4')
        self.assertIsNotNone(second)
        self.assertNotEqual(first[1], second[1])
        self.assertTrue(old_content.closed)
        self.assertTrue(old_transport.closed.is_set())
        self.assertEqual(self.media.videos['clip.mp4'][0].size, self.video.stat().st_size)
        with urlopen(second[1], timeout=5) as response:
            self.assertEqual(response.read(), b'replacement video with different bytes')

    def test_deleted_video_cannot_reuse_a_cached_stream(self):
        source = self.media.render_source()
        self.assertIsNotNone(source('clip.mp4'))
        old_content, old_transport = self.media.videos['clip.mp4']
        self.video.unlink()
        self.assertIsNone(source('clip.mp4'))
        self.assertTrue(old_content.closed)
        self.assertTrue(old_transport.closed.is_set())
        self.assertNotIn('clip.mp4', self.media.videos)

    def test_unchanged_video_reuses_its_stream(self):
        source = self.media.render_source()
        first = source('clip.mp4')
        content, transport = self.media.videos['clip.mp4']
        self.assertEqual(first, source('clip.mp4'))
        self.assertFalse(content.closed)
        self.assertFalse(transport.closed.is_set())

    def test_revocation_retires_cached_playback_and_refuses_a_new_stream(self):
        source = self.media.render_source()
        self.assertIsNotNone(source('clip.mp4'))
        old_content, old_transport = self.media.videos['clip.mp4']
        with patch.object(self.provider, '_check_active', create=True, side_effect=PermissionError('Locked')):
            self.assertIsNone(source('clip.mp4'))
        self.assertTrue(old_content.closed)
        self.assertTrue(old_transport.closed.is_set())

    def test_malformed_asset_url_does_not_prevent_opening_note(self):
        source = b'# Valid note\n\n![Broken](http://[broken)\n\nFollowing text.\n'
        data, resources = prepare_markdown(self.provider, self.root / 'Home.md', data=source)
        self.addCleanup(resources.close)
        self.assertEqual(data, source)
        self.assertEqual(resources, {})
