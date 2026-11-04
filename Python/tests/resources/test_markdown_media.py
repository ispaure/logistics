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
    def test_cancelled_render_lookup_does_not_poison_later_render(self):
        from features.notes_library.notes import NotesLibrary
        from commonUtils.runtime.operations import OperationCancelled
        from threading import Event
        library = NotesLibrary(self.provider)
        self.addCleanup(library.close)
        stopped = Event()
        source = library.image_source('Home.md', cancelled=stopped.is_set)
        stopped.set()
        with self.assertRaises(OperationCancelled):
            source('clip.mp4')
        self.assertFalse(library._media['Home.md'].videos)
        self.assertIsNotNone(library.image_source('Home.md')('clip.mp4'))

    def test_library_resolution_failure_retires_deleted_cached_video(self):
        from features.notes_library.notes import NotesLibrary
        library = NotesLibrary(self.provider)
        self.addCleanup(library.close)
        source = library.image_source('Home.md')
        self.assertIsNotNone(source('clip.mp4'))
        content, transport = library._media['Home.md'].videos['clip.mp4']
        self.video.unlink()
        with self.assertRaisesRegex(ValueError, 'not found'):
            source('clip.mp4')
        self.assertTrue(content.closed)
        self.assertTrue(transport.closed.is_set())

    def test_video_url_decoding_tries_literal_spelling_after_missing_decoded_name(self):
        literal = self.root / 'two%20words.mp4'
        literal.write_bytes(b'literal video')
        source = self.media.render_source()
        self.assertIsNotNone(source(literal.name))
        self.assertIn(literal.name, self.media.videos)
        (self.root / 'two words.mp4').write_bytes(b'decoded video')
        self.assertIsNotNone(source(literal.name))
        self.assertIn('two words.mp4', self.media.videos)

    def test_file_video_preview_retires_stream_when_final_validation_or_cancellation_fails(self):
        from contextlib import contextmanager
        from services.documents.file_preview import FilePreview
        from features.video.transport import VideoTransport
        from commonUtils.runtime.operations import OperationCancelled
        transports = []
        def transport(content):
            result = VideoTransport(content)
            transports.append(result)
            return result
        @contextmanager
        def invalid(*args):
            yield
            raise PermissionError('Access changed at publication')
        with patch('features.video.transport.VideoTransport', side_effect=transport):
            with patch('services.documents.file_preview.document_operation', invalid):
                with self.assertRaises(PermissionError):
                    FilePreview.open(self.provider, 'clip.mp4')
            self.assertEqual(len(transports), 1)
            self.assertTrue(transports[0].closed.is_set())
            self.assertTrue(transports[0].content.closed)
            with self.assertRaises(OperationCancelled):
                FilePreview.open(self.provider, 'clip.mp4', cancelled=lambda: len(transports) > 1)
        self.assertEqual(len(transports), 2)
        self.assertTrue(transports[1].closed.is_set())
        self.assertTrue(transports[1].content.closed)

    def test_rasters_reuse_bytes_but_refresh_after_changes_and_deletion(self):
        from PIL import Image
        image = self.root / 'pic.png'
        Image.new('RGB', (2, 2), 'red').save(image)
        with patch.object(self.provider, 'open', wraps=self.provider.open) as opened:
            first = self.media.render_source()('pic.png')
            self.assertEqual(self.media.render_source()('pic.png'), first)
            self.assertEqual(opened.call_count, 1)
            Image.new('RGB', (3, 3), 'blue').save(image)
            self.assertNotEqual(self.media.render_source()('pic.png'), first)
            self.assertEqual(opened.call_count, 2)
            image.unlink()
            self.assertIsNone(self.media.render_source()('pic.png'))
        self.media.close()
        self.assertFalse(self.media.rasters)

    def test_editing_media_references_reuses_only_the_current_targets(self):
        from PIL import Image
        from commonUtils.ui.native.markdown_preview import markdown_body
        for name, color in (('old.png', 'red'), ('new.png', 'blue')):
            Image.new('RGB', (2, 2), color).save(self.root / name)
        def render(text):
            return markdown_body(text, image_source=self.media.render_source())
        with patch.object(self.provider, 'open', wraps=self.provider.open) as opened:
            first = render('![Old](old.png)')
            self.assertEqual(render('![Old](old.png)'), first)
            self.assertEqual(opened.call_count, 1)
            changed = render('![New](new.png)')
            self.assertNotEqual(changed, first)
            self.assertEqual(opened.call_count, 2)
            self.assertNotIn('<img', render('Image deleted'))
            self.assertEqual(opened.call_count, 2)

    def test_link_resolution_reused_until_directory_changes(self):
        from features.notes_library.notes import NotesLibrary
        from features.notes_library.link_policy import resolve_link
        (self.root / 'Home.md').write_text('[[Target]]')
        (self.root / 'nested').mkdir()
        (self.root / 'nested/Target.md').write_text('target')
        library = NotesLibrary(self.provider)
        self.addCleanup(library.close)
        with patch('features.notes_library.link_policy.resolve_link', wraps=resolve_link) as resolve:
            self.assertEqual(library.link('Home.md', 'Target')[0], 'nested/Target.md')
            self.assertEqual(library.link('Home.md', 'Target')[0], 'nested/Target.md')
            self.assertEqual(resolve.call_count, 1)
            (self.root / 'Target.md').write_text('closer target')
            self.assertEqual(library.link('Home.md', 'Target')[0], 'Target.md')
            self.assertEqual(resolve.call_count, 2)
            (self.root / 'Target.md').unlink()
            self.assertEqual(library.link('Home.md', 'Target')[0], 'nested/Target.md')
            with self.assertRaises(ValueError):
                library.link('Home.md', 'Removed')

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.provider = LocalFiles(self.root)
        self.video = self.root / 'clip.mp4'
        self.video.write_bytes(b'first video bytes')
        self.media = MarkdownMedia(self.provider, 'Home.md', root='')
        self.addCleanup(self.media.close)

    def test_mobile_markdown_embeds_are_lazy_paused_and_start_at_zero(self):
        from commonUtils.ui.native.markdown_preview import markdown_body
        source = self.media.render_source()
        markdown = '![Movie](clip.mp4)'
        for html in (markdown_body(markdown, image_source=source),):
            self.assertIn('<video controls playsinline preload="none"', html)
            self.assertNotIn('autoplay', html)
            self.assertNotIn('#t=', html)
            self.assertNotIn('currentTime', html)

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
