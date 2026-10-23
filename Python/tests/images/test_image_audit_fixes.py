"""Regression coverage for source changes, multiframe defaults, and metadata."""

from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image, ImageCms
from features.images import processing, actions
from features.comics import cbz


class ImageAuditFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        redirect = redirect_stdout(StringIO())
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)

    def source(self, name='page.png', metadata=False):
        path = self.root / name
        kwargs = {}
        if metadata:
            kwargs['icc_profile'] = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
            exif = Image.Exif()
            exif[270] = 'Description to preserve'
            exif[274] = 6
            exif[34665] = {40962: 64, 40963: 80, 36867: '2026:10:02 12:00:00'}
            kwargs['exif'] = exif
        Image.new('RGB', (64, 80), 'red').save(path, **kwargs)
        return path

    def batch(self, force=False, preserve=None):
        return actions.batch_compress_to_webp(self.root, False, force, 60, 35, None, None, preserve)

    def test_shared_encoder_rejects_source_changed_during_encoding(self):
        source = self.source()
        image = processing.ImageFile(source)
        actual_save = Image.Image.save
        edit = b'externally edited source'
        def editing_save(image, destination, *args, **kwargs):
            result = actual_save(image, destination, *args, **kwargs)
            source.write_bytes(edit)
            return result
        with patch.object(Image.Image, 'save', editing_save):
            self.assertFalse(image.compress(source.with_suffix('.webp'), 35, 60))
        self.assertEqual(source.read_bytes(), edit)
        self.assertFalse(source.with_suffix('.webp').exists())
        self.assertFalse((self.root / '.page.webp').exists())

    def test_batch_rejects_edit_after_encoding_before_deletion(self):
        source = self.source()
        actual_compress = processing.ImageFile.compress
        edit = b'externally edited source'
        def editing_compress(image, *args, **kwargs):
            result = actual_compress(image, *args, **kwargs)
            source.write_bytes(edit)
            return result
        with patch.object(processing.ImageFile, 'compress', editing_compress):
            self.assertFalse(self.batch(True))
        self.assertEqual(source.read_bytes(), edit)
        self.assertFalse(source.with_suffix('.webp').exists())
        self.assertFalse((self.root / '.page.webp').exists())

    def test_shared_encoder_rejects_source_changed_before_call(self):
        source = self.source()
        image = processing.ImageFile(source)
        source.write_bytes(b'changed since inspection')
        self.assertFalse(image.compress(source.with_suffix('.webp'), 35, 60))
        self.assertEqual(source.read_bytes(), b'changed since inspection')

    def test_batch_rejects_edit_before_same_path_replacement(self):
        source = self.source('page.webp')
        actual_compress = processing.ImageFile.compress
        def editing_compress(image, *args, **kwargs):
            result = actual_compress(image, *args, **kwargs)
            source.write_bytes(b'new webp edit')
            return result
        with patch.object(processing.ImageFile, 'compress', editing_compress):
            self.assertFalse(self.batch(True))
        self.assertEqual(source.read_bytes(), b'new webp edit')

    def test_uppercase_webp_recompresses_at_its_original_path(self):
        source = self.source('page.WEBP')
        self.assertTrue(self.batch(True))
        self.assertTrue(source.exists())
        self.assertEqual([path.name for path in self.root.iterdir()], ['page.WEBP'])

    def multiframe(self, format):
        output = BytesIO()
        Image.new('RGB', (128,128), 'red').save(output, format=format, save_all=True,
            append_images=[Image.new('RGB', (128,128), 'blue')])
        return output.getvalue()

    def test_standalone_preserves_multiframe_originals_by_default(self):
        for format, ext in [('GIF', 'gif'), ('TIFF', 'tiff'), ('WEBP', 'webp'), ('PNG', 'png')]:
            with self.subTest(format=format):
                source = self.root / f'page.{ext}'
                original = self.multiframe(format)
                source.write_bytes(original)
                self.assertTrue(self.batch())
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(list(self.root.iterdir()), [source])
                source.unlink()

    def test_comics_preserve_animation_by_default(self):
        original = self.multiframe('GIF')
        source = self.root / 'comic.cbz'
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('01.gif', original)
        self.assertTrue(cbz.CBZFile(source).compress_to_webp())
        with zipfile.ZipFile(source) as archive:
            self.assertEqual(archive.read('01.gif'), original)

    def test_explicit_opt_out_allows_flattening(self):
        source = self.root / 'page.gif'
        source.write_bytes(self.multiframe('GIF'))
        self.assertTrue(self.batch(False, False))
        self.assertFalse(source.exists())
        with Image.open(source.with_suffix('.webp')) as converted:
            self.assertEqual(getattr(converted, 'n_frames', 1), 1)

    def test_conflicting_standalone_options_fail_before_encoding(self):
        source = self.source()
        original = source.read_bytes()
        with patch.object(processing, 'log') as log, patch.object(processing.ImageFile, 'compress') as encode:
            self.assertFalse(self.batch(True, True))
            encode.assert_not_called()
            self.assertEqual(log.call_args.args[0], processing.Severity.ERROR)
        self.assertEqual(source.read_bytes(), original)

    def test_shared_encoding_preserves_icc_exif_and_normalizes_orientation(self):
        source = self.source('photo.jpg', metadata=True)
        with Image.open(source) as original:
            icc = original.info['icc_profile']
        output = self.root / 'photo.webp'
        self.assertTrue(processing.ImageFile(source).compress(output, 35, 60, max_height=32))
        with Image.open(output) as converted:
            self.assertEqual(converted.info['icc_profile'], icc)
            exif = converted.getexif()
            self.assertEqual(exif[270], 'Description to preserve')
            self.assertIsNone(exif.get(274))
            self.assertEqual(converted.size, (40, 32))
            nested = exif.get_ifd(34665)
            self.assertEqual((nested[40962], nested[40963]), (40,32))
            self.assertEqual(nested[36867], '2026:10:02 12:00:00')

    def test_standalone_batch_preserves_icc_exif(self):
        source = self.source('photo.jpg', metadata=True)
        self.assertTrue(self.batch(True))
        with Image.open(source.with_suffix('.webp')) as converted:
            self.assertTrue(converted.info['icc_profile'])
            self.assertEqual(converted.getexif()[270], 'Description to preserve')

    def test_comic_encoding_preserves_icc_exif(self):
        image_path = self.source('photo.jpg', metadata=True)
        source = self.root / 'comic.cbz'
        with zipfile.ZipFile(source,'w') as archive:
            archive.writestr('01.jpg', image_path.read_bytes())
        self.assertTrue(cbz.CBZFile(source).compress_to_webp(True))
        with zipfile.ZipFile(source) as archive:
            with Image.open(BytesIO(archive.read('01.webp'))) as converted:
                self.assertTrue(converted.info['icc_profile'])
                self.assertEqual(converted.getexif()[270], 'Description to preserve')

    def test_unreadable_image_returns_failure_before_batch_mutation(self):
        source = self.source()
        original = source.read_bytes()
        (self.root / 'bad.png').write_bytes(b'bad image')
        self.assertFalse(self.batch(True))
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(source.with_suffix('.webp').exists())

    def test_jpeg_output_preserves_icc_and_exif(self):
        source = self.source('photo.png', metadata=True)
        output = self.root / 'photo.jpg'
        self.assertTrue(processing.ImageFile(source).compress(output, 35,60))
        with Image.open(output) as converted:
            self.assertTrue(converted.info['icc_profile'])
            self.assertEqual(converted.getexif()[270], 'Description to preserve')
            self.assertIsNone(converted.getexif().get(274))

    def test_non_rgb_profiles_are_converted_to_matching_rgb_profile(self):
        for mode, profile_name in [('CMYK', 'Generic CMYK Profile.icc'),
                                   ('L', 'Generic Gray Profile.icc')]:
            with self.subTest(mode=mode):
                profile_path = Path('/System/Library/ColorSync/Profiles') / profile_name
                if not profile_path.exists():
                    self.skipTest('System CMYK/gray profiles unavailable on this platform')
                source = self.root / f'{mode}.tiff'
                Image.new(mode, (32,32)).save(source, icc_profile=profile_path.read_bytes())
                output = source.with_suffix('.webp')
                self.assertTrue(processing.ImageFile(source).compress(output,35,60))
                with Image.open(output) as converted:
                    profile = ImageCms.ImageCmsProfile(BytesIO(converted.info['icc_profile']))
                    self.assertEqual(profile.profile.xcolor_space.strip(), 'RGB')
                    self.assertEqual(converted.mode, 'RGB')

    def test_jpeg_gray_alpha_converts_pixels_and_profile_together(self):
        profile_path = Path('/System/Library/ColorSync/Profiles/Generic Gray Profile.icc')
        if not profile_path.exists():
            self.skipTest('System gray profile unavailable on this platform')
        icc = profile_path.read_bytes()
        source = self.root / 'gray-alpha.png'
        exif = Image.Exif()
        exif[270] = 'Gray alpha description'
        Image.new('LA', (32,32), (100,120)).save(source, icc_profile=icc, exif=exif)
        original = source.read_bytes()
        expected = ImageCms.profileToProfile(Image.new('L', (32,32), 100),
            ImageCms.ImageCmsProfile(BytesIO(icc)), ImageCms.createProfile('sRGB'),
            outputMode='RGB').getpixel((0,0))
        for extension in ('.jpg', '.jpeg'):
            with self.subTest(extension=extension):
                output = self.root / f'converted{extension}'
                self.assertTrue(processing.ImageFile(source).compress(output,95,95))
                with Image.open(output) as converted:
                    profile = ImageCms.ImageCmsProfile(BytesIO(converted.info['icc_profile']))
                    self.assertEqual(profile.profile.xcolor_space.strip(), 'RGB')
                    self.assertEqual(converted.mode, 'RGB')
                    self.assertEqual(converted.getexif()[270], 'Gray alpha description')
                    for actual, target in zip(converted.getpixel((0,0)), expected):
                        self.assertLessEqual(abs(actual - target), 2)
                self.assertEqual(source.read_bytes(), original)

    def test_jpeg_retains_native_gray_and_cmyk_profiles(self):
        for mode, profile_name in [('L', 'Generic Gray Profile.icc'),
                                   ('CMYK', 'Generic CMYK Profile.icc')]:
            with self.subTest(mode=mode):
                profile_path = Path('/System/Library/ColorSync/Profiles') / profile_name
                if not profile_path.exists():
                    self.skipTest('System CMYK/gray profiles unavailable on this platform')
                icc = profile_path.read_bytes()
                source = self.root / f'{mode}.tiff'
                Image.new(mode, (32,32)).save(source, icc_profile=icc)
                output = source.with_suffix('.jpg')
                self.assertTrue(processing.ImageFile(source).compress(output,35,60))
                with Image.open(output) as converted:
                    self.assertEqual(converted.mode, mode)
                    self.assertEqual(converted.info['icc_profile'], icc)

    def test_invalid_profile_fails_without_losing_original(self):
        source = self.root / 'invalid-profile.png'
        Image.new('RGB', (64,80), 'red').save(source, icc_profile=b'invalid profile')
        original = source.read_bytes()
        self.assertFalse(self.batch(True))
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(source.with_suffix('.webp').exists())

    def test_source_change_after_publication_keeps_edited_source(self):
        source = self.source()
        actual_link = processing.os.link
        def editing_link(staged, destination):
            result = actual_link(staged, destination)
            source.write_bytes(b'edit made just after output publication')
            return result
        with patch.object(processing.os, 'link', editing_link):
            self.assertFalse(self.batch(True))
        self.assertEqual(source.read_bytes(), b'edit made just after output publication')
        self.assertTrue(source.with_suffix('.webp').exists())


if __name__ == '__main__':
    unittest.main()
