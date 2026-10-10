"""Verified creation/editing and transactional, traversal-safe extraction."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile
import unittest
import zipfile
from unittest.mock import patch

from commonUtils.operations import OperationCancelled
from commonUtils.zip_access import open_archive, archive_manifest, ArchivePasswordError
from features.archives import backend


class ArchiveWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'source'
        self.folder.mkdir()
        (self.folder / 'nested').mkdir()
        (self.folder / 'empty').mkdir()
        (self.folder / 'hello.txt').write_text('Hello, archive!')
        (self.folder / 'nested' / 'notes.md').write_text('# Notes\n')

    def make_zip(self, password=None):
        path = self.root / 'sample.zip'
        backend.create([self.folder], path, password=password)
        return path

    def test_round_trip_supported_formats_and_empty_directories(self):
        for format in ('zip', 'tar', 'tar.gz', 'tar.xz'):
            with self.subTest(format=format):
                archive = self.root / ('sample.' + format)
                backend.create([self.folder], archive, format=format)
                self.assertGreater(backend.test_archive(archive), 0)
                destination = self.root / ('out-' + format)
                backend.extract(archive, destination)
                self.assertEqual((destination / 'source' / 'hello.txt').read_text(), 'Hello, archive!')
                self.assertTrue((destination / 'source' / 'empty').is_dir())

    def test_encrypted_headers_can_be_browsed_and_payloads_require_password(self):
        path = self.make_zip('test-secret')
        self.assertTrue(any(entry.encrypted for entry in backend.entries(path)))
        with self.assertRaises(ArchivePasswordError):
            backend.preview(path, 'source/hello.txt')
        self.assertEqual(backend.preview(path, 'source/hello.txt', password='test-secret'), 'Hello, archive!')

    def test_selected_directory_extracts_descendants_preserving_paths(self):
        path = self.make_zip()
        out = self.root / 'selected'
        backend.extract(path, out, selected=['source/nested/'])
        self.assertEqual((out / 'source/nested/notes.md').read_text(), '# Notes\n')
        self.assertFalse((out / 'source/hello.txt').exists())

    def test_wrong_password_and_cancellation_leave_no_output(self):
        path = self.make_zip('test-secret')
        for options, error in [({'password': 'wrong'}, ArchivePasswordError),
                               ({'password': 'test-secret', 'cancelled': lambda: True}, OperationCancelled)]:
            with self.assertRaises(error):
                backend.extract(path, self.root / 'out', **options)
            self.assertFalse((self.root / 'out').exists())
        self.assertFalse(list(self.root.glob('.logistics-extract-*')))

    def test_mid_stream_cancellation_discards_staging(self):
        path = self.make_zip()
        cancel = False
        def report(*args):
            nonlocal cancel
            cancel = True
        with self.assertRaises(OperationCancelled):
            backend.extract(path, self.root / 'out', progress=report, cancelled=lambda: cancel)
        self.assertFalse((self.root / 'out').exists())

    def test_existing_destination_and_symlink_are_never_overwritten(self):
        path = self.make_zip()
        out = self.root / 'out'
        out.mkdir()
        (out / 'keep').write_text('original')
        with self.assertRaises(FileExistsError):
            backend.extract(path, out)
        self.assertEqual((out / 'keep').read_text(), 'original')
        link = self.root / 'link'
        link.symlink_to(out, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            backend.extract(path, link)

    def test_zip_and_tar_reject_traversal_links_and_collisions(self):
        for name in ('../escape', '/absolute', 'C:/escape', 'folder/../../escape'):
            for kind in ('zip', 'tar'):
                with self.subTest(name=name, kind=kind):
                    path = self.root / ('unsafe.' + kind)
                    if kind == 'zip':
                        with zipfile.ZipFile(path, 'w') as archive:
                            archive.writestr(name, b'bad')
                    else:
                        with tarfile.open(path, 'w') as archive:
                            info = tarfile.TarInfo(name)
                            info.size = 3
                            archive.addfile(info, BytesIO(b'bad'))
                    with self.assertRaises(ValueError):
                        backend.extract(path, self.root / 'out')
                    self.assertFalse((self.root / 'out').exists())
        path = self.root / 'links.tar'
        with tarfile.open(path, 'w') as archive:
            info = tarfile.TarInfo('link')
            info.type = tarfile.SYMTYPE
            info.linkname = '/tmp/escape'
            archive.addfile(info)
        with self.assertRaises(ValueError):
            backend.entries(path)
        with tarfile.open(path, 'w') as archive:
            for name in ('File', 'file'):
                info = tarfile.TarInfo(name)
                archive.addfile(info, BytesIO())
        with self.assertRaises(ValueError):
            backend.entries(path)

    def test_edit_add_remove_preserves_password_and_original_sources(self):
        path = self.make_zip('test-secret')
        extra = self.root / 'extra.txt'
        extra.write_text('new')
        backend.update_zip(path, sources=[extra], remove=['source/nested/'], password='test-secret')
        manifest = archive_manifest(path, password='test-secret')
        self.assertIn('extra.txt', manifest)
        self.assertIn('source/hello.txt', manifest)
        self.assertNotIn('source/nested/notes.md', manifest)
        self.assertTrue((self.folder / 'nested/notes.md').exists())
        with open_archive(path, password='test-secret') as archive:
            self.assertEqual(archive.read('extra.txt'), b'new')
        self.assertTrue(all(entry.encrypted for entry in backend.entries(path) if not entry.directory))

    def test_failed_edit_keeps_original_bytes(self):
        path = self.make_zip()
        before = path.read_bytes()
        for options, exception in [({'sources': [self.folder]}, ValueError),
                                   ({'remove': ['source/hello.txt'], 'cancelled': lambda: True}, OperationCancelled)]:
            with self.assertRaises(exception):
                backend.update_zip(path, **options)
            self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(self.root.glob('.logistics-edit-*')))

    def test_mixed_protection_cannot_be_silently_changed_by_edit(self):
        path = self.root / 'mixed.zip'
        with open_archive(path, 'w', password='secret') as archive:
            archive.writestr('protected', 'secret data')
        with zipfile.ZipFile(path, 'a') as archive:
            archive.writestr('public', 'public data')
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Mixed'):
            backend.update_zip(path, remove=['public'], password='secret')
        self.assertEqual(path.read_bytes(), before)

    def test_backslash_names_extract_and_remove_consistently(self):
        path = self.root / 'windows.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('folder\\file.txt', 'hello')
        backend.extract(path, self.root / 'out', selected=['folder/'])
        self.assertEqual((self.root / 'out/folder/file.txt').read_text(), 'hello')
        backend.update_zip(path, remove=['folder/'])
        self.assertEqual(backend.entries(path), ())

    def test_bounded_preview_and_binary_fallback(self):
        path = self.root / 'preview.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('large.txt', 'x' * (300 * 1024))
            archive.writestr('binary', b'\x00binary')
        self.assertIn('limited to 256 KiB', backend.preview(path, 'large.txt'))
        self.assertIn('Binary file', backend.preview(path, 'binary'))

    def test_tar_creation_rejects_collisions_and_output_inside_source(self):
        other = self.root / 'other'
        other.mkdir()
        (other / 'hello.txt').write_text('collision')
        with self.assertRaises(ValueError):
            backend.create([self.folder / 'hello.txt', other / 'hello.txt'], self.root / 'out.tar', format='tar')
        self.assertFalse((self.root / 'out.tar').exists())
        with self.assertRaises(ValueError):
            backend.create([self.folder], self.folder / 'out.tar', format='tar')

    def test_concurrent_destination_creation_is_preserved(self):
        path = self.make_zip()
        out = self.root / 'out'
        def report(*args):
            out.mkdir(exist_ok=True)
            (out / 'keep').write_text('concurrent')
        with self.assertRaises(FileExistsError):
            backend.extract(path, out, progress=report)
        self.assertEqual((out / 'keep').read_text(), 'concurrent')
        self.assertFalse((out / 'source').exists())

    def test_edit_detects_archive_changed_before_publication(self):
        path = self.make_zip()
        actual_manifest = backend.archive_manifest
        changed = None
        def manifest(candidate, **kwargs):
            nonlocal changed
            result = actual_manifest(candidate, **kwargs)
            if Path(candidate).name == 'result.zip':
                with zipfile.ZipFile(path, 'a') as archive:
                    archive.writestr('external-change', b'keep')
                changed = path.read_bytes()
            return result
        with patch.object(backend, 'archive_manifest', side_effect=manifest):
            with self.assertRaisesRegex(ValueError, 'changed during editing'):
                backend.update_zip(path, remove=['source/hello.txt'])
        self.assertEqual(path.read_bytes(), changed)

    def test_unix_executable_bits_survive_extraction(self):
        script = self.folder / 'run.sh'
        script.write_text('#!/bin/sh\necho hello\n')
        script.chmod(0o755)
        for format in ('zip', 'tar.gz'):
            archive = self.root / ('script.' + format)
            backend.create([script], archive, format=format)
            destination = self.root / ('script-' + format)
            backend.extract(archive, destination)
            self.assertEqual((destination / 'run.sh').stat().st_mode & 0o111, 0o111)

    def test_image_preview_is_bounded_and_produces_a_thumbnail(self):
        from PIL import Image
        image = BytesIO()
        Image.new('RGB', (1600, 900), 'orange').save(image, format='PNG')
        path = self.root / 'images.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('image.png', image.getvalue())
        thumbnail = backend.preview_image(path, 'image.png')
        with Image.open(BytesIO(thumbnail)) as preview:
            self.assertEqual(preview.width, 1000)
            self.assertLessEqual(abs(preview.width / preview.height - 1600 / 900), .01)
