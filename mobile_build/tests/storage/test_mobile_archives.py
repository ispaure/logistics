"""Mobile archive publication preserves sources and obeys resource policy."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.provider import ResourceCapabilities
from commonUtils.testing.stages import TestStage
from mobile.archive_operations import ArchiveItem, FORMATS, create_archive, extract_archive

TEST_STAGE = TestStage.REGRESSION


class ReadOnly(LocalFiles):
    capabilities = ResourceCapabilities()


class Private(LocalFiles):
    private = True


class ArchiveOperationsTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.provider = LocalFiles(self.root)
        (self.root / 'a.txt').write_bytes(b'alpha')
        (self.root / 'nested').mkdir()
        (self.root / 'nested' / 'b.bin').write_bytes(b'\0bravo')
        self.sources = tuple(ArchiveItem.from_row(self.provider, self.provider.entry(path))
                             for path in ('a.txt', 'nested'))

    def create(self, format='zip', name='generated', cancelled=lambda: False):
        return create_archive(self.sources, self.provider, '', name, format, self.root, cancelled)

    def test_create_edit_and_extract_all_desktop_creation_formats(self):
        for format in FORMATS:
            with self.subTest(format=format):
                path = self.create(format)
                item, members = ArchiveItem(self.provider, path.name).inspect(lambda: False)
                self.assertEqual({row.name.rstrip('/') for row in members}, {'a.txt', 'nested', 'nested/b.bin'})
                if format == 'zip':
                    (self.root / 'added.txt').write_bytes(b'new')
                    item = item.edit(lambda: False, sources=(ArchiveItem(self.provider, 'added.txt'),),
                                     remove=('a.txt',))
                    _, members = item.inspect(lambda: False)
                    self.assertIn('added.txt', {row.name for row in members})
                    self.assertNotIn('a.txt', {row.name for row in members})
                destination = extract_archive(item, self.provider, '', 'output-' + format, lambda: False)
                self.assertEqual((destination / 'nested' / 'b.bin').read_bytes(), b'\0bravo')
                expected = ('added.txt', b'new') if format == 'zip' else ('a.txt', b'alpha')
                self.assertEqual((destination / expected[0]).read_bytes(), expected[1])

    def test_no_overwrite_and_no_partial_output(self):
        path = self.create()
        before = path.read_bytes()
        item, _ = ArchiveItem(self.provider, path.name).inspect(lambda: False)
        with self.assertRaises(FileExistsError):
            self.create()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            item.edit(lambda: False, sources=(self.sources[0],))
        with patch('commonUtils.archives.editing.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                item.edit(lambda: False, remove=('a.txt',))
        with self.assertRaises(OperationCancelled):
            item.edit(lambda: True, remove=('a.txt',))
        with self.assertRaises(OperationCancelled):
            self.create(name='cancelled', cancelled=lambda: True)
        with self.assertRaises(OperationCancelled):
            extract_archive(item, self.provider, '', 'cancelled', lambda: True)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(any(self.root.glob('cancelled*')))
        self.assertFalse(any(self.root.glob('.logistics-*')))

    def test_unsafe_member_and_destination_are_rejected(self):
        path = self.root / 'unsafe.zip'
        with ZipFile(path, 'w') as archive:
            archive.writestr('../outside.txt', b'fixture')
        item = ArchiveItem(self.provider, path.name)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            item.inspect(lambda: False)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            extract_archive(item, self.provider, '', 'extracted', lambda: False)
        with self.assertRaises(ValueError):
            self.create(name='../outside')
        self.assertFalse((self.root / 'extracted').exists())

    def test_destination_policy_and_stale_archive(self):
        path = self.create()
        item, _ = ArchiveItem(self.provider, path.name).inspect(lambda: False)
        for provider, error in ((ReadOnly(self.root), PermissionError), (Private(self.root), ValueError)):
            with self.assertRaises(error):
                extract_archive(item, provider, '', 'output', lambda: False)
        path.chmod(0o400)
        with self.assertRaises(PermissionError):
            ArchiveItem(self.provider, path.name).edit(lambda: False, remove=('a.txt',))
        with self.assertRaisesRegex(ValueError, 'changed'):
            item.inspect(lambda: False)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            item.inspect(lambda: False)

    def test_locked_zip_headers_and_password_gate(self):
        from commonUtils.archives.zip_access import ArchivePasswordError
        try:
            import pyzipper
        except ImportError:
            # A header-only ZipCrypto fixture models gated content on mobile.
            path = self.root / 'encrypted.zip'
            with ZipFile(path, 'w') as archive:
                archive.writestr('inside.txt', b'protected')
            data = bytearray(path.read_bytes())
            for signature, offset in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
                position = data.index(signature) + offset
                data[position] |= 1
            path.write_bytes(data)
        else:
            path = self.root / 'encrypted.zip'
            with pyzipper.AESZipFile(path, 'w', encryption=pyzipper.WZ_AES) as archive:
                archive.setpassword(b'generated-fixture')
                archive.writestr('inside.txt', b'protected')
        item, members = ArchiveItem(self.provider, path.name).inspect(lambda: False)
        self.assertTrue(any(member.encrypted for member in members))
        before = path.read_bytes()
        with self.assertRaises(ArchivePasswordError):
            extract_archive(item, self.provider, '', 'locked', lambda: False)
        with self.assertRaises(RuntimeError):
            item.edit(lambda: False, remove=(members[0].name,))
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / 'locked').exists())


class ArchiveWorkflowTests(unittest.TestCase):
    def test_file_browser_resource_actions(self):
        from mobile_build.native_tests.tests.logisticsmobile.archive_checks import exercise_archives
        from mobile_build.tests.support.app import mobile_app
        with mobile_app(retire_documents=True) as app:
            app.loop.run_until_complete(exercise_archives(app))
