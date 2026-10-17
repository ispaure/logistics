"""Phone live preview, shared syntax controls and retained source ownership."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from logisticsmobile.app import LogisticsMobile
from commonUtils.ui.native.code_input import CodeInput
from toga.style.pack import COLUMN, ROW


class SourceEditorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.temporary.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')

    def tearDown(self):
        for owner in self.app.text_views.values():
            owner.dispose()
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.temporary.cleanup()

    def open(self, name):
        document = self.app.store.create(name)
        self.app.refresh_documents()
        self.app.open_document(document.id)
        self.app.show_documents()
        return self.app.editor_view

    def test_markdown_live_preview_at_phone_and_wide_widths(self):
        owner = self.open('Live.md')
        self.assertIsInstance(owner.editor, CodeInput)
        owner.apply_split(390)
        self.assertIn(owner.split_preview, owner.editor_area.children)
        self.assertEqual(owner.editor_area.style.direction, COLUMN)
        with patch.object(owner.split_preview, 'set_content') as render:
            source = '# Title\n\n| A | B |\n| --- | --- |\n| 1 | 2 |'
            owner.editor.value = source
            self.app.loop.run_until_complete(asyncio.sleep(.4))
            self.assertIn('<table>', render.call_args.args[1])
            self.assertEqual(owner.document.text, source)
            self.assertEqual(owner.editor.value, source)
        with patch('features.text_editor.mobile.ui.allocated_width', return_value=1000):
            owner.apply_split(1000)
        self.assertEqual(owner.editor_area.style.direction, ROW)
        owner.toggle_split()
        self.assertNotIn(owner.split_preview, owner.editor_area.children)
        self.assertIsNone(owner.preview_pending)
        owner.toggle_split()
        self.assertIn(owner.split_preview, owner.editor_area.children)

    def test_source_language_and_line_count_do_not_modify_text(self):
        owner = self.open('sample.py')
        self.assertIsNone(owner.split_preview)
        source = 'def hello():\n    return "😀"\n'
        owner.editor.value = source
        self.assertEqual(owner.editor.language, 'python')
        self.assertEqual(owner.line_count.text, '3 lines')
        owner.language_choice.value = 'JSON'
        self.assertEqual(owner.editor.language, 'json')
        self.assertEqual(owner.editor.value, source)
        owner.language_choice.value = 'Automatic'
        self.assertEqual(owner.editor.language, 'python')
        owner.dispose()
        self.assertIsNone(owner.editor.pending)
        self.assertTrue(owner.editor.closed)
