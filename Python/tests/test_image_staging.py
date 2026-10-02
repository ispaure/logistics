"""Standalone WebP recompression uses dot-prefixed sibling candidates."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import errno
from unittest.mock import patch

from PIL import Image
from features.images import processing


class ImageStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        redirect = redirect_stdout(StringIO())
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)

    def source(self, name='page.webp'):
        path = self.root / name
        Image.new('RGBA', (32, 32), (255, 0, 0, 128)).save(path)
        return path

    def run_batch(self, forced=False):
        return processing.batch_compress_image(self.root, False, forced, 60, 35, None, None)

    def fake_encoder(self, source, original_bytes, compressed_size, candidate_name=None):
        def encode(image, dest_path, **kwargs):
            self.assertEqual(dest_path, source.with_suffix('.webp'))
            self.assertTrue(kwargs['defer_replace'])
            staged_path = dest_path.with_name(candidate_name or f'.{dest_path.name}')
            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertEqual(dest_path.parent, source.parent)
            staged_path.write_bytes(b'compressed output')
            image.size = 100
            image.compressed_image = processing.fileUtils.File(staged_path)
            image.compressed_image.size = compressed_size
            return True
        return encode

    def test_webp_source_is_retained_at_or_above_threshold(self):
        for size in (75, 90):
            with self.subTest(size=size):
                source = self.source()
                original = source.read_bytes()
                with patch.object(processing.ImageFile, 'compress', self.fake_encoder(source, original, size)):
                    self.assertTrue(self.run_batch())
                self.assertEqual(source.read_bytes(), original)
                self.assertFalse((self.root / '.page.webp').exists())

    def test_webp_source_is_replaced_below_threshold(self):
        source = self.source()
        original = source.read_bytes()
        with patch.object(processing.ImageFile, 'compress', self.fake_encoder(source, original, 74)):
            self.assertTrue(self.run_batch())
        self.assertEqual(source.read_bytes(), b'compressed output')
        self.assertFalse((self.root / '.page.webp').exists())

    def test_forced_recompression_keeps_larger_candidate(self):
        source = self.source()
        original = source.read_bytes()
        with patch.object(processing.ImageFile, 'compress', self.fake_encoder(source, original, 110)):
            self.assertTrue(self.run_batch(True))
        self.assertEqual(source.read_bytes(), b'compressed output')

    def test_non_webp_conversion_publishes_normal_name_before_deletion(self):
        source = self.source('page.png')
        original = source.read_bytes()
        with patch.object(processing.ImageFile, 'compress', self.fake_encoder(source, original, 74)):
            self.assertTrue(self.run_batch())
        self.assertFalse(source.exists())
        self.assertEqual((self.root / 'page.webp').read_bytes(), b'compressed output')
        self.assertFalse((self.root / '.page.webp').exists())

    def test_non_webp_retained_original_leaves_no_webp(self):
        source = self.source('page.png')
        original = source.read_bytes()
        with patch.object(processing.ImageFile, 'compress', self.fake_encoder(source, original, 75)):
            self.assertTrue(self.run_batch())
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_unsupported_hard_links_use_exclusive_copy(self):
        for code in {errno.EXDEV, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EPERM}:
            with self.subTest(errno=code):
                source = self.source('page.png')
                with patch.object(processing.os, 'link', side_effect=OSError(code, 'Unavailable')):
                    self.assertTrue(self.run_batch(True))
                self.assertFalse(source.exists())
                output = self.root / 'page.webp'
                with Image.open(output) as image:
                    image.load()
                    self.assertEqual(image.size, (32,32))
                self.assertFalse((self.root / '.page.webp').exists())
                output.unlink()

    def test_copy_fallback_refuses_destination_created_during_publication(self):
        source = self.source('page.png')
        original = source.read_bytes()
        destination = self.root / 'page.webp'
        def unavailable_link(*args):
            destination.write_bytes(b'another output')
            raise OSError(errno.EOPNOTSUPP, 'Unavailable')
        with patch.object(processing.os, 'link', unavailable_link):
            self.assertFalse(self.run_batch(True))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(destination.read_bytes(), b'another output')
        self.assertFalse((self.root / '.page.webp').exists())

    def test_failed_copy_cleans_partial_output_and_preserves_source(self):
        source = self.source('page.png')
        original = source.read_bytes()
        def failed_copy(source, destination):
            destination.write(b'partial')
            raise OSError('Copy failed')
        with patch.object(processing.os, 'link', side_effect=OSError(errno.EOPNOTSUPP, 'Unavailable')), \
                patch.object(processing.shutil, 'copyfileobj', failed_copy):
            self.assertFalse(self.run_batch(True))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_failed_copy_flush_preserves_source_and_cleans_output(self):
        source = self.source('page.png')
        original = source.read_bytes()
        with patch.object(processing.os, 'link', side_effect=OSError(errno.ENOTSUP, 'Unavailable')), \
                patch.object(processing.os, 'fsync', side_effect=OSError('Flush failed')):
            self.assertFalse(self.run_batch(True))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_other_link_errors_do_not_trigger_copy_fallback(self):
        source = self.source('page.png')
        original = source.read_bytes()
        with patch.object(processing.os, 'link', side_effect=OSError(errno.EIO, 'I/O failed')), \
                patch.object(processing.shutil, 'copyfileobj') as copy:
            self.assertFalse(self.run_batch(True))
            copy.assert_not_called()
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_copy_fallback_checks_source_before_deletion(self):
        source = self.source('page.png')
        actual_copy = processing.shutil.copyfileobj
        def editing_copy(input_file, output_file):
            actual_copy(input_file, output_file)
            source.write_bytes(b'edited during copy')
        with patch.object(processing.os, 'link', side_effect=OSError(errno.EOPNOTSUPP, 'Unavailable')), \
                patch.object(processing.shutil, 'copyfileobj', editing_copy):
            self.assertFalse(self.run_batch(True))
        self.assertEqual(source.read_bytes(), b'edited during copy')
        self.assertTrue((self.root / 'page.webp').exists())
        self.assertFalse((self.root / '.page.webp').exists())

    def test_failed_encoder_cleans_partial_stage_and_keeps_original(self):
        source = self.source()
        original = source.read_bytes()
        def fail(image, dest_path, *args, **kwargs):
            Path(dest_path).write_bytes(b'partial encoding')
            raise OSError('encoder failed')
        with patch.object(Image.Image, 'save', fail):
            self.assertFalse(self.run_batch(True))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_existing_stage_is_never_overwritten_or_deleted(self):
        source = self.source()
        original = source.read_bytes()
        stage = self.source('.page.webp')
        stage_original = stage.read_bytes()
        self.assertFalse(self.run_batch(True))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(stage.read_bytes(), stage_original)

    def test_existing_webp_destination_is_not_overwritten(self):
        source = self.source('page.png')
        destination = self.source('page.webp')
        original, existing = source.read_bytes(), destination.read_bytes()
        self.assertFalse(self.run_batch(True))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(destination.read_bytes(), existing)

    def test_failed_replacement_keeps_source_and_cleans_stage(self):
        source = self.source()
        original = source.read_bytes()
        with patch.object(processing.ImageFile, 'compress', self.fake_encoder(source, original, 74)), \
                patch.object(processing.os, 'replace', side_effect=OSError('replace failed')):
            self.assertFalse(self.run_batch())
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse((self.root / '.page.webp').exists())

    def test_real_webp_recompression_preserves_alpha(self):
        source = self.source()
        self.assertTrue(self.run_batch(True))
        with Image.open(source) as converted:
            self.assertEqual(converted.getchannel('A').getextrema(), (128, 128))
        self.assertFalse((self.root / '.page.webp').exists())

    def test_shared_compress_stages_before_replacing_same_path(self):
        source = self.source()
        original = source.read_bytes()
        actual_save = Image.Image.save
        destinations = []
        def observe_save(image, destination, *args, **kwargs):
            destinations.append(Path(destination))
            self.assertEqual(source.read_bytes(), original)
            return actual_save(image, destination, *args, **kwargs)
        image = processing.ImageFile(source)
        with patch.object(Image.Image, 'save', observe_save):
            self.assertTrue(image.compress(source, 35, 60))
        self.assertEqual(destinations, [self.root / '.page.webp'])
        self.assertEqual(image.compressed_image.path, source)
        self.assertFalse((self.root / '.page.webp').exists())

    def test_shared_compress_failure_preserves_existing_destination(self):
        source = self.source('page.png')
        destination = self.source('page.webp')
        original, existing = source.read_bytes(), destination.read_bytes()
        def fail_save(image, destination, *args, **kwargs):
            Path(destination).write_bytes(b'partial')
            raise OSError('encoder failed')
        with patch.object(Image.Image, 'save', fail_save):
            self.assertFalse(processing.ImageFile(source).compress(destination, 35, 60))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(destination.read_bytes(), existing)
        self.assertFalse((self.root / '.page.webp').exists())

    def test_shared_compress_refuses_existing_dot_file(self):
        source = self.source('page.png')
        stage = self.source('.page.webp')
        existing = stage.read_bytes()
        self.assertFalse(processing.ImageFile(source).compress(self.root / 'page.webp', 35, 60))
        self.assertEqual(stage.read_bytes(), existing)
        self.assertFalse((self.root / 'page.webp').exists())

    def test_deferred_shared_compress_leaves_candidate_for_comparison(self):
        source = self.source()
        original = source.read_bytes()
        image = processing.ImageFile(source)
        self.assertTrue(image.compress(source, 35, 60, defer_replace=True))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(image.compressed_image.path, self.root / '.page.webp')
        self.assertTrue(image.compressed_image.path.exists())

    def test_batch_uses_returned_candidate_path_for_publication_and_cleanup(self):
        for size in (74, 75):
            with self.subTest(size=size):
                source = self.source()
                original = source.read_bytes()
                candidate = self.root / '.encoder-candidate.webp'
                encoder = self.fake_encoder(source, original, size, candidate.name)
                with patch.object(processing.ImageFile, 'compress', encoder):
                    self.assertTrue(self.run_batch())
                expected = b'compressed output' if size < 75 else original
                self.assertEqual(source.read_bytes(), expected)
                self.assertFalse(candidate.exists())
                self.assertFalse((self.root / '.page.webp').exists())


if __name__ == '__main__':
    unittest.main()
