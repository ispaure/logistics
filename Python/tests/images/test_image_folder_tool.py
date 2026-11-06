"""Image folder workflows preserve inputs and report per-image outcomes."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
import piexif
from commonUtils.integrations.wrappers import piexifWrapper
from commonUtils.testing.stages import TestStage
from features.images import actions, processing

TEST_STAGE = TestStage.REGRESSION


class ExifCommentsBatchTests(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(TemporaryDirectory())
        self.root = Path(temp).resolve()

    def jpeg(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (8, 8), 'red').save(path)
        return path

    def test_changed_and_noop_keep_original_backup(self):
        path = self.jpeg('photo.JPEG')
        original = path.read_bytes()
        self.assertIsNone(actions.set_jpg_exif_comments(self.root, False, 'Old comment'))
        backup = self.root / 'photo.JPEG.before-comments'
        self.assertEqual(backup.read_bytes(), original)

        result, changed = actions.set_jpg_exif_comments_batch(self.root, False, 'Café')
        self.assertEqual(result.completed, [path])
        self.assertEqual(result.failed, {})
        self.assertEqual(changed, {path: True})
        edited = path.read_bytes()
        metadata = piexif.load(edited)
        self.assertEqual(bytes(metadata['0th'][piexifWrapper.COMMENTS_TAG_ADDRESS]), 'Café\0'.encode('utf-16-le'))
        self.assertEqual(backup.read_bytes(), original)

        with patch.object(piexifWrapper, 'atomic_write_bytes', wraps=piexifWrapper.atomic_write_bytes) as write:
            result, changed = actions.set_jpg_exif_comments_batch(self.root, False, 'Café')
        write.assert_not_called()
        self.assertEqual(result.completed, [path])
        self.assertEqual(result.failed, {})
        self.assertEqual(changed, {path: False})
        self.assertEqual(path.read_bytes(), edited)
        self.assertEqual(backup.read_bytes(), original)

    def test_scan_skips_hidden_files_and_symlinks_and_respects_recursion(self):
        source = self.jpeg('visible/photo.jpg')
        skipped = [self.jpeg(name) for name in ('outside.jpg', 'input/.hidden.jpg', 'input/.hidden/photo.jpg')]
        folder = self.root / 'input'
        nested = self.jpeg('input/nested/photo.jpg')
        links = (folder / 'linked.jpg', folder / 'linked-folder')
        links[0].symlink_to(skipped[0])
        links[1].symlink_to(source.parent, target_is_directory=True)
        untouched = {path: path.read_bytes() for path in [source, *skipped, nested]}

        result, _ = actions.set_jpg_exif_comments_batch(folder, False, 'New comment')
        self.assertEqual(result.completed, [])
        self.assertEqual(result.failed, {})
        result, changed = actions.set_jpg_exif_comments_batch(folder, True, 'New comment')
        self.assertEqual(result.completed, [nested])
        self.assertEqual(result.failed, {})
        self.assertEqual(changed, {nested: True})
        self.assertNotEqual(nested.read_bytes(), untouched.pop(nested))
        for path, original in untouched.items():
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(path.with_name(path.name + '.before-comments').exists())
        for link in links:
            self.assertTrue(link.is_symlink())
            self.assertFalse(link.with_name(link.name + '.before-comments').exists())

    def test_cancellation_during_scan_leaves_all_jpegs_untouched(self):
        source = self.jpeg('photo.jpg')
        original = source.read_bytes()
        result, changed = actions.set_jpg_exif_comments_batch(
            self.root, True, 'New comment', cancelled=lambda: True)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.completed, [])
        self.assertEqual(result.failed, {})
        self.assertEqual(changed, {})
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_concurrent_source_edit_is_reported_as_failure(self):
        source = self.jpeg('photo.jpg')
        original = source.read_bytes()
        write = piexifWrapper.atomic_write_bytes

        def edit_before_publication(path, *args, **kwargs):
            if path == source:
                source.write_bytes(b'external edit')
            return write(path, *args, **kwargs)

        with patch.object(piexifWrapper, 'atomic_write_bytes', side_effect=edit_before_publication):
            result, changed = actions.set_jpg_exif_comments_batch(self.root, False, 'New comment')
        self.assertEqual(result.completed, [])
        self.assertIn('JPEG changed during metadata editing', result.failed[source])
        self.assertEqual(changed, {})
        self.assertEqual(source.read_bytes(), b'external edit')
        self.assertEqual((self.root / 'photo.jpg.before-comments').read_bytes(), original)
        self.assertCountEqual(self.root.iterdir(), [source, self.root / 'photo.jpg.before-comments'])


class ImageFolderToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.image('sample.png')
        self.enterContext(redirect_stdout(StringIO()))

    def image(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (32, 32), 'red').save(path)
        return path

    def compress(self, targets=None, **kwargs):
        options = dict(always_keep_compressed=True,
                       preserve_animated_and_multipage_originals=False)
        options.update(kwargs)
        return actions.compress_folders(self.root if targets is None else targets, **options)

    def test_batch_continues_after_bad_image_and_preserves_unrelated_outputs(self):
        bad = self.root / 'broken.png'
        bad.write_bytes(b'not an image')
        unrelated = self.root / 'unrelated.webp'
        unrelated.write_bytes(b'preexisting output')
        result, outcomes = self.compress()
        self.assertEqual(result.completed, [self.source])
        self.assertEqual(set(result.failed), {bad})
        self.assertEqual(outcomes, {self.source: 'Converted to WEBP'})
        self.assertFalse(result.cancelled)
        self.assertEqual(result.remaining, [])
        self.assertFalse(self.source.exists())
        with Image.open(self.source.with_suffix('.webp')) as image:
            self.assertEqual(image.size, (32, 32))
        self.assertEqual(bad.read_bytes(), b'not an image')
        self.assertEqual(unrelated.read_bytes(), b'preexisting output')

    def test_encoder_failure_preserves_source_cleans_stage_and_continues(self):
        second = self.image('second.png')
        original = self.source.read_bytes()
        save = Image.Image.save

        def fail_first_save(image, destination, *args, **kwargs):
            if Path(destination).name == '.sample.webp':
                Path(destination).write_bytes(b'partial encoding')
                raise OSError('encoder failed')
            return save(image, destination, *args, **kwargs)

        with patch.object(Image.Image, 'save', fail_first_save):
            result, outcomes = self.compress()
        self.assertEqual(result.completed, [second])
        self.assertEqual(set(result.failed), {self.source})
        self.assertEqual(result.remaining, [])
        self.assertFalse(result.cancelled)
        self.assertEqual(outcomes, {second: 'Converted to WEBP'})
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.source.with_suffix('.webp').exists())
        self.assertFalse(list(self.root.glob('.*.webp')))
        self.assertFalse(second.exists())
        with Image.open(second.with_suffix('.webp')) as converted:
            self.assertEqual(converted.size, (32, 32))

    def test_blocked_folder_never_calls_encoder(self):
        with patch('services.folders.safety.require_safe_folder', side_effect=ValueError('Protected')), \
                patch.object(processing.ImageFile, 'compress') as encode:
            with self.assertRaisesRegex(ValueError, 'Protected'):
                self.compress()
        encode.assert_not_called()
        self.assertTrue(self.source.exists())

    def test_conflicting_options_fail_before_any_mutation(self):
        original = self.source.read_bytes()
        with patch.object(processing.ImageFile, 'compress') as encode:
            with self.assertRaises(ValueError):
                self.compress(preserve_animated_and_multipage_originals=True)
        encode.assert_not_called()
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.source.with_suffix('.webp').exists())

    def test_all_roots_are_validated_before_processing_any_images(self):
        from services.folders.safety import require_safe_folder

        blocked = self.root / 'protected'
        blocked.mkdir()
        original = self.source.read_bytes()

        def check_folder(path, **kwargs):
            if Path(path) == blocked:
                raise ValueError('Protected')
            return require_safe_folder(path, **kwargs)

        with patch('services.folders.safety.require_safe_folder', side_effect=check_folder), \
                patch.object(processing.ImageFile, 'compress') as encode:
            with self.assertRaisesRegex(ValueError, 'Protected'):
                self.compress([self.root, blocked])
        encode.assert_not_called()
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.source.with_suffix('.webp').exists())
        self.assertFalse(list(self.root.glob('.*.webp')))

    def test_default_policy_keeps_animated_original_bytes(self):
        self.source.unlink()
        animated = self.root / 'animated.gif'
        Image.new('RGB', (32, 32), 'red').save(
            animated, save_all=True, append_images=[Image.new('RGB', (32, 32), 'blue')])
        original = animated.read_bytes()
        with patch.object(processing.ImageFile, 'compress') as encode:
            result, outcomes = actions.compress_folders(self.root)
        encode.assert_not_called()
        self.assertEqual(result.completed, [animated])
        self.assertEqual(outcomes, {animated: 'Kept original (animated/multipage)'})
        self.assertEqual(animated.read_bytes(), original)
        self.assertFalse(animated.with_suffix('.webp').exists())

    def test_cancellation_finishes_current_image_and_reports_remaining_inputs(self):
        second = self.image('second.png')
        original = second.read_bytes()
        progress = []
        stop = False
        encoder = processing.ImageFile.compress

        def report(done, total, message):
            progress.append((done, total))

        def cancel_during_encoding(image, *args, **kwargs):
            nonlocal stop
            stop = True
            return encoder(image, *args, **kwargs)

        with patch.object(processing.ImageFile, 'compress', autospec=True,
                          side_effect=cancel_during_encoding) as encode:
            result, outcomes = self.compress(report=report, cancelled=lambda: stop)
        self.assertEqual(encode.call_count, 1)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.completed, [self.source])
        self.assertEqual(result.remaining, [second])
        self.assertEqual(result.failed, {})
        self.assertEqual(outcomes, {self.source: 'Converted to WEBP'})
        self.assertEqual(progress, [(0, 2), (1, 2)])
        self.assertFalse(self.source.exists())
        self.assertTrue(self.source.with_suffix('.webp').exists())
        self.assertEqual(second.read_bytes(), original)
        self.assertFalse(second.with_suffix('.webp').exists())
        self.assertFalse(list(self.root.glob('.*.webp')))

    def test_default_webp_exclusion_skips_existing_and_new_outputs_on_repeat_runs(self):
        existing = self.image('existing.WEBP')
        invalid = self.root / 'invalid.webp'
        invalid.write_bytes(b'not an image')
        nested = self.image('nested/incoming.png')
        original = existing.read_bytes()
        first, _ = self.compress()
        self.assertEqual(set(first.completed), {self.source, nested})
        self.assertEqual(first.failed, {})
        outputs = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(processing, 'ImageFile') as inspect:
            second, outcomes = self.compress()
        inspect.assert_not_called()
        self.assertEqual(second.completed, [])
        self.assertEqual(second.failed, {})
        self.assertEqual(outcomes, {})
        self.assertEqual(existing.read_bytes(), original)
        self.assertEqual(invalid.read_bytes(), b'not an image')
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, outputs)

    def test_disabling_exclusion_recompresses_existing_uppercase_webp(self):
        self.source.unlink()
        source = self.image('page.WEBP')
        encoder = processing.ImageFile.compress
        with patch.object(processing.ImageFile, 'compress', autospec=True,
                          side_effect=encoder) as encode:
            result, outcomes = self.compress(exclude_webp=False)
        self.assertEqual(encode.call_count, 1)
        self.assertEqual(result.completed, [source])
        self.assertEqual(outcomes, {source: 'Converted to WEBP'})
        self.assertEqual(list(self.root.iterdir()), [source])
        with Image.open(source) as image:
            self.assertEqual(image.size, (32, 32))

    def test_overlapping_roots_process_each_image_once_in_natural_order(self):
        second = self.image('nested/page2.png')
        tenth = self.image('nested/page10.png')
        encoder = processing.ImageFile.compress
        with patch.object(processing.ImageFile, 'compress', autospec=True,
                          side_effect=encoder) as encode:
            result, outcomes = self.compress([self.root, second.parent, self.root])
        self.assertEqual(result.completed, [second, tenth, self.source])
        self.assertEqual(result.failed, {})
        self.assertEqual(encode.call_count, 3)
        self.assertEqual(set(outcomes), {self.source, second, tenth})

    def test_nonrecursive_selection_leaves_nested_images_untouched(self):
        nested = self.image('nested/page.png')
        original = nested.read_bytes()
        result, outcomes = self.compress(recursive=False)
        self.assertEqual(result.completed, [self.source])
        self.assertEqual(set(outcomes), {self.source})
        self.assertEqual(nested.read_bytes(), original)
        self.assertFalse(nested.with_suffix('.webp').exists())

    def test_current_folder_workflow_does_not_follow_file_or_directory_links(self):
        folder = self.root / 'input'
        folder.mkdir()
        original = self.source.read_bytes()
        (folder / 'linked-directory').symlink_to(self.root, target_is_directory=True)
        (folder / 'linked.png').symlink_to(self.source)
        with patch.object(processing.ImageFile, 'compress') as encode:
            result, outcomes = self.compress(folder)
        encode.assert_not_called()
        self.assertEqual(result.completed, [])
        self.assertEqual(result.failed, {})
        self.assertEqual(outcomes, {})
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.source.with_suffix('.webp').exists())

    def test_legacy_batch_does_not_follow_folder_or_file_links(self):
        folder = self.root / 'input'
        folder.mkdir()
        (folder / 'linked-directory').symlink_to(self.root, target_is_directory=True)
        (folder / 'linked.png').symlink_to(self.source)
        with patch.object(processing.ImageFile, 'compress') as encode:
            self.assertTrue(processing.batch_compress_image(folder, True, True, 80, 45, None, None))
        encode.assert_not_called()
        self.assertTrue(self.source.exists())
