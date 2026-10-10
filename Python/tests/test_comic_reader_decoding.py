"""Reader decoding when a platform's Qt image codecs are unavailable."""

import gc
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
import zipfile

from PIL import Image, ImageCms, features
from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages
from features.comics.ui import reader_pages


class MissingQtDecoder:
    def __init__(self, device):
        pass

    def setAutoTransform(self, value):
        pass

    def size(self):
        return qt.QSize()

    def read(self):
        return qt.QImage()

    def errorString(self):
        return 'Unsupported image format'

    @staticmethod
    def supportedImageFormats():
        return [qt.QByteArray(b'png'), qt.QByteArray(b'jpeg')]


class ReaderDecodingTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'sample.cbz'

    def pages(self, data, entry='pages/01.png'):
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr(entry, data)
        return ComicPages(self.path)

    def encoded(self, image, format='PNG', **options):
        stream = BytesIO()
        image.save(stream, format=format, **options)
        return stream.getvalue()

    def fallback(self, pages):
        with patch.object(qt, 'QImageReader', MissingQtDecoder):
            return reader_pages.read_image(pages, 0)

    @unittest.skipUnless(features.check('webp'), 'Pillow WebP decoder unavailable')
    def test_webp_reads_without_qt_plugin_and_keeps_alpha_and_owned_pixels(self):
        data = self.encoded(Image.new('RGBA', (11, 17), (20, 100, 200, 64)), 'WEBP', lossless=True)
        pages = self.pages(data, 'pages/01.webp')
        before = self.path.read_bytes()
        image = self.fallback(pages)
        gc.collect()
        self.assertEqual((image.width(), image.height()), (11, 17))
        self.assertEqual(image.pixelColor(3, 4).getRgb(), (20, 100, 200, 64))
        self.assertEqual(self.path.read_bytes(), before)

    def test_fallback_applies_exif_orientation_and_retains_valid_rgb_profile(self):
        exif = Image.Exif()
        exif[274] = 6
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        data = self.encoded(Image.new('RGB', (12, 20), 'red'), 'JPEG', exif=exif, icc_profile=profile)
        image = self.fallback(self.pages(data, '01.jpg'))
        self.assertEqual((image.width(), image.height()), (20, 12))
        self.assertTrue(image.colorSpace().isValid())

    def test_bad_icc_profile_does_not_block_valid_pixels(self):
        data = self.encoded(Image.new('RGB', (12, 20), 'blue'), icc_profile=b'not an ICC profile')
        image = self.fallback(self.pages(data))
        self.assertEqual(image.pixelColor(0, 0).getRgb(), (0, 0, 255, 255))
        self.assertFalse(image.colorSpace().isValid())

    def test_fallback_bounds_large_pages_without_changing_archive(self):
        pages = self.pages(self.encoded(Image.new('RGB', (20, 10), 'blue')))
        before = self.path.read_bytes()
        with patch.object(reader_pages, 'MAX_DISPLAY_PIXELS', 16), patch.object(reader_pages, 'MAX_DISPLAY_SIDE', 8):
            image = self.fallback(pages)
        self.assertEqual((image.width(), image.height()), (8, 4))
        self.assertEqual(self.path.read_bytes(), before)

    def test_qt_success_does_not_invoke_fallback(self):
        pages = self.pages(self.encoded(Image.new('RGB', (12, 20), 'blue')))
        with patch.object(reader_pages, '_pillow_image', side_effect=AssertionError('Unexpected fallback')):
            image = reader_pages.read_image(pages, 0)
        self.assertFalse(image.isNull())

    def test_corrupt_page_identifies_entry_archive_bytes_and_both_decoders(self):
        pages = self.pages(b'not an image', 'pages/01.webp')
        with self.assertRaises(ValueError) as caught:
            self.fallback(pages)
        text = str(caught.exception)
        for detail in ['sample.cbz', 'pages/01.webp', 'page 1', '12 bytes', 'image/webp',
                       'Qt: Unsupported image format', 'Pillow:', 'Qt image formats: jpeg, png',
                       'Pillow WebP support:']:
            self.assertIn(detail, text)

    def test_archive_read_failure_is_distinct_from_decoder_failure(self):
        pages = self.pages(self.encoded(Image.new('RGB', (12, 20), 'blue')))
        with patch.object(pages, 'read_page', side_effect=OSError('Remote storage unavailable')):
            with self.assertRaises(ValueError) as caught:
                reader_pages.read_image(pages, 0)
        text = str(caught.exception)
        self.assertIn('Could not load page 1 (pages/01.png) in sample.cbz from the archive', text)
        self.assertIn('Remote storage unavailable', text)
        self.assertNotIn('Qt image formats', text)

    def test_missing_pillow_decoder_is_reported_alongside_qt_failure(self):
        pages = self.pages(b'not an image', '01.webp')
        with patch.object(reader_pages.Image, 'open', side_effect=OSError('WebP decoder is unavailable')):
            with self.assertRaises(ValueError) as caught:
                self.fallback(pages)
        self.assertIn('Pillow: WebP decoder is unavailable', str(caught.exception))
