"""Real encoded JPEG/WebP/PNG orientation and bounded malformed metadata."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from io import BytesIO
import unittest
from PIL import Image
from features.images.orientation import image_orientation
from features.images.validation import image_dimensions


class ViewerOrientationTests(unittest.TestCase):
    def test_all_exif_orientations_preserve_display_geometry(self):
        for format in ('JPEG', 'WEBP', 'PNG'):
            for orientation in range(1, 9):
                with self.subTest(format=format, orientation=orientation):
                    source = Image.new('RGB', (30, 50), 'red')
                    exif = Image.Exif()
                    exif[274] = orientation
                    data = BytesIO()
                    source.save(data, format=format, exif=exif)
                    raw = data.getvalue()
                    self.assertEqual(image_orientation(raw), orientation)
                    self.assertEqual(image_dimensions(raw), (50, 30) if orientation >= 5 else (30, 50))

    def test_missing_and_truncated_optional_metadata_is_identity(self):
        for data in (b'', b'Exif\0\0', b'\xff\xd8\xff\xe1\xff\xff', b'RIFF1234WEBPEXIF\xff\xff\xff\xff'):
            self.assertEqual(image_orientation(data), 1)

    def test_desktop_decoded_corners_for_every_rotation_and_mirror(self):
        import json
        from commonUtils.ui import pyside as qt
        from features.images.ui.decoding import read_oriented, image_thumbnail
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import orientation_fixtures
        with scratch() as root:
            orientation_fixtures(root)
            for row in json.loads((root / 'manifest.json').read_text()):
                with self.subTest(name=row['name']):
                    data = (root / (row['name'] + '.source')).read_bytes()
                    buffer = qt.QBuffer()
                    buffer.setData(data)
                    buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
                    image = read_oriented(qt.QImageReader(buffer), data)
                    width, height = image.width(), image.height()
                    self.assertEqual([width, height], row['size'])
                    points = ((2, 2), (width - 3, 2), (2, height - 3), (width - 3, height - 3))
                    for point, expected in zip(points, row['corners']):
                        actual = image.pixelColor(*point).getRgb()[:3]
                        self.assertLess(max(abs(a - b) for a, b in zip(actual, expected)), 25)
                    preview = qt.QImage.fromData(image_thumbnail(data, (30, 50)))
                    width, height = preview.width(), preview.height()
                    self.assertGreater(width, 0)
                    self.assertAlmostEqual(width / height, row['size'][0] / row['size'][1], delta=.06)
                    points = ((2, 2), (width - 3, 2), (2, height - 3), (width - 3, height - 3))
                    for point, expected in zip(points, row['corners']):
                        actual = preview.pixelColor(*point).getRgb()[:3]
                        self.assertLess(max(abs(a - b) for a, b in zip(actual, expected)), 25)

    def test_browser_thumbnail_reads_through_bounded_document_resource(self):
        from pathlib import Path
        from unittest.mock import patch
        from features.images.file_type import ImageFile
        image = ImageFile.__new__(ImageFile)
        image.path = Path('fixture.png')
        with patch('services.documents.storage.read_local_bytes', return_value=b'image') as read, \
                patch('features.images.ui.decoding.image_thumbnail', return_value=b'preview') as decode:
            self.assertEqual(image.browser_thumbnail((40, 50)), b'preview')
            read.assert_called_once_with(image.path, max_bytes=16 * 1024 * 1024)
            decode.assert_called_once_with(b'image', (40, 50))
        with patch('services.documents.storage.read_local_bytes', side_effect=ValueError('too large')), \
                patch('features.images.ui.decoding.image_thumbnail') as decode:
            self.assertEqual(image.browser_thumbnail((40, 50)), b'')
            decode.assert_not_called()
