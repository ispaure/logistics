"""Native picker selection contracts; provider permissions need device tests."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.runtime.platform import OS
from logisticsmobile.access import AndroidDocuments, IOSDocuments, LocalDocuments
from logisticsmobile.pickers import pick_document


class PickerTests(unittest.IsolatedAsyncioTestCase):
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
        with patch('logisticsmobile.pickers.get_os', return_value=OS.ANDROID), patch.dict('sys.modules', java=java):
            provider, reference = await pick_document(app)
        self.assertIsInstance(provider, AndroidDocuments)
        self.assertIs(provider.resolver, resolver)
        self.assertEqual(reference, 'opaque content URI')
        self.assertEqual(started[0].flags, [Intent.FLAG_GRANT_READ_URI_PERMISSION])
        self.assertEqual(started[0].category, Intent.CATEGORY_OPENABLE)

    async def test_ios_and_desktop_selection_use_their_matching_providers(self):
        app = SimpleNamespace(main_window=SimpleNamespace(dialog=AsyncMock(return_value=Path('/selected.txt'))))
        selected = (IOSDocuments(), object())
        with patch('logisticsmobile.pickers.get_os', return_value=OS.IOS), \
                patch('logisticsmobile.pickers.pick_ios', new=AsyncMock(return_value=selected)) as picker:
            self.assertIs(await pick_document(app), selected)
            picker.assert_awaited_once_with(app)
        with patch('logisticsmobile.pickers.get_os', return_value=OS.MAC):
            provider, reference = await pick_document(app)
        self.assertIsInstance(provider, LocalDocuments)
        self.assertEqual(reference, Path('/selected.txt'))
