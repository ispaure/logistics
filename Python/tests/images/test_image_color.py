"""Color-quality selection for the shared Images/Comics compressor."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

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

    def test_color_and_grayscale_select_configured_quality(self):
        for color, quality, is_color in [('red', 60, True), ('gray', 35, False)]:
            with self.subTest(color=color):
                self.assert_quality(Image.new('RGB', (32, 32), color), quality, is_color)


if __name__ == '__main__':
    unittest.main()
