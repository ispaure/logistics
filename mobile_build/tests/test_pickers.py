"""Native picker selection contracts; provider permissions need device tests."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.runtime.platform import OS
from commonUtils.runtime.document_access import AndroidDocuments, IOSDocuments, LocalDocuments
from mobile.pickers import pick_document, export_document


class PickerTests(unittest.IsolatedAsyncioTestCase):
    async def test_android_export_uses_explicit_destination_and_closes_failed_stream(self):
        class Intent:
            ACTION_CREATE_DOCUMENT = 'create'
            CATEGORY_OPENABLE = 'openable'
            FLAG_GRANT_WRITE_URI_PERMISSION = 2
            EXTRA_TITLE = 'title'
            def __init__(self, action): self.action, self.flags = action, []
            def addCategory(self, category): self.category = category
            def setType(self, mime): self.mime = mime
            def addFlags(self, flags): self.flags.append(flags)
            def putExtra(self, key, value): self.title = value
        writes, closed, started = [], [], []
        def write(data):
            writes.append(data)
            raise OSError('Provider disconnected')
        stream = SimpleNamespace(write=write, flush=lambda: None, close=lambda: closed.append(True))
        resolver = SimpleNamespace(openOutputStream=lambda uri, mode: stream)
        def start(intent, on_complete):
            started.append(intent)
            on_complete(42, SimpleNamespace(getData=lambda: 'destination URI'))
        app = SimpleNamespace(_impl=SimpleNamespace(start_activity=start,
            native=SimpleNamespace(getContentResolver=lambda: resolver)))
        java = SimpleNamespace(jclass=lambda name: Intent if name.endswith('Intent') else SimpleNamespace(RESULT_OK=42),
                               jarray=lambda dtype: list, jbyte=object())
        with patch('commonUtils.ui.native.documents.get_os', return_value=OS.ANDROID), patch.dict('sys.modules', java=java):
            with self.assertRaises(OSError):
                await export_document(app, 'Notes.md', b'\xffhello')
        self.assertEqual(closed, [True])
        self.assertEqual(writes, [[-1, 104, 101, 108, 108, 111]])
        self.assertEqual(started[0].flags, [2])
        self.assertEqual(started[0].title, 'Notes.md')
        self.assertEqual(started[0].mime, 'text/markdown')

    async def test_export_cancel_does_not_write_and_ios_staging_is_removed(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            app = SimpleNamespace(paths=SimpleNamespace(data=Path(directory)),
                                  main_window=SimpleNamespace(dialog=AsyncMock(return_value=None)))
            with patch('commonUtils.ui.native.documents.get_os', return_value=OS.MAC):
                self.assertFalse(await export_document(app, 'Notes.txt', b'copy'))
            observed = []
            async def picker(app, path):
                observed.append(path)
                self.assertEqual(path.read_bytes(), b'copy')
                return False
            with patch('commonUtils.ui.native.documents.get_os', return_value=OS.IOS), \
                    patch('commonUtils.ui.native.documents.pick_ios', side_effect=picker):
                self.assertFalse(await export_document(app, 'Notes.txt', b'copy'))
            self.assertFalse(observed[0].exists())

    async def test_android_uses_shared_detection_and_read_only_native_activity(self):
        class Intent:
            ACTION_OPEN_DOCUMENT = 'open'
            CATEGORY_OPENABLE = 'openable'
            FLAG_GRANT_READ_URI_PERMISSION = 1
            def __init__(self, action): self.action, self.flags = action, []
            def addCategory(self, category): self.category = category
            def setType(self, mime): self.mime = mime
            def addFlags(self, flags): self.flags.append(flags)
        resolver = object()
        started = []
        def start(intent, on_complete):
            started.append(intent)
            on_complete(42, SimpleNamespace(getData=lambda: 'opaque content URI'))
        app = SimpleNamespace(_impl=SimpleNamespace(start_activity=start,
            native=SimpleNamespace(getContentResolver=lambda: resolver)))
        java = SimpleNamespace(jclass=lambda name: Intent if name.endswith('Intent') else SimpleNamespace(RESULT_OK=42))
        # Host sys.platform stays unchanged; only the shared classifier is a fixture.
        with patch('commonUtils.ui.native.documents.get_os', return_value=OS.ANDROID), patch.dict('sys.modules', java=java):
            provider, reference = await pick_document(app)
        self.assertIsInstance(provider, AndroidDocuments)
        self.assertIs(provider.resolver, resolver)
        self.assertEqual(reference, 'opaque content URI')
        self.assertEqual(started[0].flags, [Intent.FLAG_GRANT_READ_URI_PERMISSION])
        self.assertEqual(started[0].category, Intent.CATEGORY_OPENABLE)

    async def test_ios_and_desktop_selection_use_their_matching_providers(self):
        app = SimpleNamespace(main_window=SimpleNamespace(dialog=AsyncMock(return_value=Path('/selected.txt'))))
        selected = (IOSDocuments(), object())
        with patch('commonUtils.ui.native.documents.get_os', return_value=OS.IOS), \
                patch('commonUtils.ui.native.documents.pick_ios', new=AsyncMock(return_value=selected)) as picker:
            self.assertIs(await pick_document(app), selected)
            picker.assert_awaited_once_with(app)
        with patch('commonUtils.ui.native.documents.get_os', return_value=OS.MAC):
            provider, reference = await pick_document(app)
        self.assertIsInstance(provider, LocalDocuments)
        self.assertEqual(reference, Path('/selected.txt'))

    async def test_large_private_copy_export_streams_without_old_size_cap(self):
        from tempfile import TemporaryDirectory
        from mobile.pickers import export_file
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'large.zip'
            with source.open('wb') as output:
                output.seek(40 * 1024 * 1024 - 1)
                output.write(b'x')
            app = SimpleNamespace(paths=SimpleNamespace(data=root))
            observed = []
            async def picker(app, path):
                observed.append(path)
                self.assertEqual(path.stat().st_size, source.stat().st_size)
                with path.open('rb') as stream:
                    stream.seek(-1, 2)
                    self.assertEqual(stream.read(1), b'x')
                return True
            with patch('commonUtils.ui.native.documents.get_os', return_value=OS.IOS), \
                    patch('commonUtils.ui.native.documents.pick_ios', side_effect=picker):
                self.assertTrue(await export_file(app, source))
            self.assertTrue(source.exists())
            self.assertFalse(observed[0].exists())
