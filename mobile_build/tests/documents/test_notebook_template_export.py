"""The native export command publishes portable backgrounds with live ink."""
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pypdf import PdfReader
from commonUtils.testing.stages import TestStage
from features.notebooks.bridge import Bridge
from features.notebooks.editor import Editor
from features.notebooks.mobile.panel import NotebookPanel
from features.notebooks.notebook import Notebook

TEST_STAGE = TestStage.REGRESSION


class NotebookTemplateExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_export_contains_the_background_and_unchanged_ink(self):
        book = Notebook.new('Mobile portable export')
        editor = Editor(book)
        editor.apply(dict(op='template', name='Logistics Restaurant review', format='move', visible=True))
        editor.apply(dict(op='stroke', points=[[700, 180, .5], [850, 180, .5]]))
        original = book.page(0).to_bytes()
        owner = SimpleNamespace(bridge=Bridge(), web=object(), editor=editor,
                                document=None, view=SimpleNamespace(children=[]),
                                confirm_export=AsyncMock(return_value=True),
                                closed=False, busy=False, app=SimpleNamespace(active_host=True))
        copies = []
        async def save(app, name, open_stream):
            self.assertIs(app, owner.app)
            self.assertTrue(name.endswith('.rmdoc'))
            with open_stream() as stream:
                copies.append(stream.read())
            return True
        with patch('commonUtils.ui.native.documents.export_stream', side_effect=save):
            await NotebookPanel.perform(owner, dict(op='export'))
        self.assertEqual(len(copies), 1)
        exported = Notebook.read(copies[0])
        self.assertEqual(exported.content['fileType'], 'pdf')
        self.assertEqual(exported.page(0).to_bytes(), original)
        pdf = PdfReader(BytesIO(exported.members[exported.id + '.pdf']))
        self.assertIn('Restaurant review', pdf.pages[0].extract_text())
        self.assertEqual(book.content['fileType'], 'notebook')
        self.assertFalse(owner.busy)
