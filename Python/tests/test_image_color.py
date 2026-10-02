"""Color-quality selection for the shared Images/Comics compressor."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
from features.images.processing import ImageFile


class ImageColorTests(unittest.TestCase):
    def setUp(self):
        self.workspace = TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)

    def assert_quality(self, image, expected_quality, expected_color):
        source = self.root / 'source.png'
        image.save(source)
        file = ImageFile(source)
        original_save = Image.Image.save
        qualities = []
        def capture_save(image, destination, *args, **kwargs):
            qualities.append(kwargs.get('quality'))
            return original_save(image, destination, *args, **kwargs)
        with patch.object(Image.Image, 'save', capture_save):
            self.assertTrue(file.compress(self.root / 'result.webp', 35, 60))
        self.assertEqual(qualities, [expected_quality])
        self.assertEqual(file.color, expected_color)
        self.assertEqual(file.compressed_image.color, expected_color)

    def test_uniform_colors_receive_color_quality(self):
        for color in ('red', 'green', 'blue', 'yellow', 'cyan', 'magenta', '#805030'):
            with self.subTest(color=color):
                self.assert_quality(Image.new('RGB', (64, 64), color), 60, True)

    def test_uniform_rgb_grays_receive_grayscale_quality(self):
        for level in (0, 32, 127, 128, 200, 255):
            with self.subTest(level=level):
                self.assert_quality(Image.new('RGB', (64, 64), (level, level, level)), 35, False)

    def test_rgb_grayscale_gradient_stays_grayscale(self):
        image = Image.new('RGB', (256, 16))
        image.putdata([(x, x, x) for _ in range(16) for x in range(256)])
        self.assert_quality(image, 35, False)

    def test_neutral_quantization_tolerance_is_preserved(self):
        self.assert_quality(Image.new('RGB', (64, 64), (128, 129, 128)), 35, False)

    def test_visible_uniform_tint_receives_color_quality(self):
        self.assert_quality(Image.new('RGB', (64, 64), (150, 128, 128)), 60, True)

    def test_grayscale_modes_stay_grayscale(self):
        for mode in ('1', 'L', 'LA'):
            with self.subTest(mode=mode):
                self.assert_quality(Image.new(mode, (64, 64)), 35, False)

    def test_palette_color_is_detected(self):
        image = Image.new('RGB', (64, 64), 'red').convert('P')
        self.assert_quality(image, 60, True)

    def test_rgba_color_is_detected(self):
        self.assert_quality(Image.new('RGBA', (64, 64), (255, 0, 0, 255)), 60, True)

    def test_large_uniform_color_is_detected_after_sampling(self):
        self.assert_quality(Image.new('RGB', (1024, 16), 'blue'), 60, True)

    def test_varying_color_remains_color(self):
        image = Image.new('RGB', (64, 64))
        image.putdata([(255, 0, 0) if x % 2 else (0, 0, 255) for x in range(64 * 64)])
        self.assert_quality(image, 60, True)


if __name__ == '__main__':
    unittest.main()
