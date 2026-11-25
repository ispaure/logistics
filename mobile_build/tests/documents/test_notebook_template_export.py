"""The native export command publishes portable backgrounds with live ink."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from base64 import b64decode
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pypdf import PdfReader
from commonUtils.testing.stages import TestStage
from features.notebooks.bridge import Bridge
from features.notebooks.editor import Editor
from features.notebooks.images import image_data
from features.notebooks.mobile.panel import NotebookPanel
from features.notebooks.notebook import Notebook
from Python.tests.notebooks.image_fixtures import png_source

TEST_STAGE = TestStage.REGRESSION


class NotebookTemplateExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_export_contains_the_background_and_unchanged_ink(self):
        book = Notebook.new('Mobile portable export')
        editor = Editor(book)
        editor.apply(dict(op='template', name='Logistics Restaurant review', format='move', visible=True))
        editor.apply(dict(op='stroke', points=[[700, 180, .5], [850, 180, .5]]))
        book = Notebook.read(book.to_bytes())
        editor = Editor(book)
        owner = NotebookPanel.__new__(NotebookPanel)
        owner.__dict__.update(bridge=Bridge(), web=object(), editor=editor,
                              document=None, progress=None, view=SimpleNamespace(children=[]),
                              confirm_export=AsyncMock(return_value=True),
                              closed=False, busy=False, pen_input=None,
                              app=SimpleNamespace(active_host=True))
        data = b64decode(png_source().split(',', 1)[1])
        selection = dict(op='insert-photo', source='photos', page_id=book.pages[0].id,
                         layer=book.page(0).layers[0][0], bounds=[291.5, 0, 821, 1460])
        with patch('features.notebooks.mobile.ios_photos.choose_photo', new=AsyncMock(return_value=data)) as pick:
            await owner.perform(selection)
            pick.assert_awaited_once_with(owner.web, 'photos')
        picture, asset = next(image_data(book, 0))
        self.assertEqual(asset, data)
        self.assertGreater(picture.corners[0][0], 291.5)
        self.assertLess(picture.corners[2][0], 1112.5)
        with patch('features.notebooks.mobile.ios_photos.choose_photo', new=AsyncMock(return_value=None)):
            await owner.perform(dict(selection, source='camera'))
        self.assertEqual(len(book.page(0).images), 1)
        original = book.page(0).to_bytes()
        copies = []
        async def save(app, name, open_stream):
            self.assertIs(app, owner.app)
            self.assertTrue(name.endswith('.rmdoc'))
            with open_stream() as stream:
                copies.append(stream.read())
            return True
        with patch('commonUtils.ui.native.documents.export_stream', side_effect=save):
            await owner.perform(dict(op='export'))
        owner.confirm_export.assert_awaited_once_with()
        self.assertEqual(len(copies), 1)
        exported = Notebook.read(copies[0])
        self.assertEqual(exported.content['fileType'], 'pdf')
        self.assertEqual(exported.page(0).to_bytes(), original)
        self.assertEqual(next(image_data(exported, 0))[1], data)
        pdf = PdfReader(BytesIO(exported.members[exported.id + '.pdf']))
        self.assertIn('Restaurant review', pdf.pages[0].extract_text())
        self.assertIn('What I ordered', pdf.pages[0].extract_text())
        self.assertEqual(len(pdf.pages[0].images), 0)
        self.assertEqual(book.content['fileType'], 'notebook')
        self.assertFalse(owner.busy)
