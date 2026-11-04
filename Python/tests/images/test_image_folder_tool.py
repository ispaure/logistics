"""Current folder compression preserves inputs and reports per-image outcomes."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
from commonUtils.testing.stages import TestStage
from features.images import actions, processing

TEST_STAGE = TestStage.REGRESSION


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

        def report(done, total, message):
            nonlocal stop
            progress.append((done, total))
            if done == 1:
                stop = True

        result, outcomes = self.compress(report=report, cancelled=lambda: stop)
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
