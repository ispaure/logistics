"""Alpha preservation in shared image compression and explicit Comics opt-out."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image
from features.comics import cbz
from features.images import processing


class ImageAlphaTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def assert_preserved(self, image):
        source = self.root / 'source.png'
        destination = self.root / 'result.webp'
        image.save(source)
        with Image.open(source) as loaded:
            expected_alpha = loaded.convert('RGBA').getchannel('A').tobytes()
        self.assertTrue(processing.ImageFile(source).compress(destination, 35, 60))
        with Image.open(destination) as converted:
            self.assertIn('A', converted.getbands())
            self.assertEqual(converted.getchannel('A').tobytes(), expected_alpha)

    def rgba_image(self):
        image = Image.new('RGBA', (32, 32))
        image.putdata([(255, 64, 32, (index * 37) % 256) for index in range(32 * 32)])
        return image

    def test_rgba_alpha_values_are_preserved_by_default(self):
        self.assert_preserved(self.rgba_image())

    def test_grayscale_alpha_values_are_preserved(self):
        image = Image.new('LA', (32, 32))
        image.putdata([(120, (index * 37) % 256) for index in range(32 * 32)])
        self.assert_preserved(image)

    def test_palette_transparency_is_preserved(self):
        image = Image.new('P', (32, 32))
        image.putpalette([255, 0, 0, 0, 0, 255] + [0] * 762)
        image.putdata([index % 2 for index in range(32 * 32)])
        image.info['transparency'] = bytes([0, 128] + [255] * 254)
        self.assert_preserved(image)

    def test_rgb_transparency_key_is_preserved(self):
        image = Image.new('RGB', (32, 32), 'red')
        image.info['transparency'] = (255, 0, 0)
        self.assert_preserved(image)

    def test_explicit_opt_out_strips_alpha(self):
        source = self.root / 'source.png'
        self.rgba_image().save(source)
        destination = self.root / 'result.webp'
        self.assertTrue(processing.ImageFile(source).compress(destination, 35, 60, preserve_alpha=False))
        with Image.open(destination) as converted:
            self.assertNotIn('A', converted.getbands())

    def test_jpeg_export_remains_opaque(self):
        source = self.root / 'source.png'
        self.rgba_image().save(source)
        destination = self.root / 'result.jpg'
        self.assertTrue(processing.ImageFile(source).compress(destination, 35, 60))
        with Image.open(destination) as converted:
            self.assertEqual(converted.mode, 'RGB')

    def test_standalone_batch_preserves_alpha(self):
        source = self.root / 'source.png'
        image = self.rgba_image()
        image.save(source)
        processing.batch_compress_image(self.root, False, True, 60, 35, None, None)
        with Image.open(source.with_suffix('.webp')) as converted:
            self.assertEqual(converted.getchannel('A').tobytes(), image.getchannel('A').tobytes())

    def comic(self):
        output = BytesIO()
        self.rgba_image().save(output, 'PNG')
        path = self.root / 'comic.cbz'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('01.png', output.getvalue())
        return path, output.getvalue()

    def test_comics_explicitly_strip_alpha_from_encoded_pages(self):
        path, _ = self.comic()
        self.assertTrue(cbz.CBZFile(path).compress_to_webp(always_keep_compressed=True))
        with zipfile.ZipFile(path) as archive:
            with Image.open(BytesIO(archive.read('01.webp'))) as converted:
                self.assertNotIn('A', converted.getbands())

    def test_comics_retained_original_keeps_alpha_and_original_bytes(self):
        path, original = self.comic()
        with patch.object(cbz, 'cbz_img_min_allowed_compression_percentage', 0):
            self.assertTrue(cbz.CBZFile(path).compress_to_webp())
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.read('01.png'), original)
            with Image.open(BytesIO(archive.read('01.png'))) as retained:
                self.assertIn('A', retained.getbands())


if __name__ == '__main__':
    unittest.main()
