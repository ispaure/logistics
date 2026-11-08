"""Portable template backgrounds remain separate from live native ink."""
from copy import deepcopy
from io import BytesIO
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pypdf import PdfReader
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.testing.stages import TestStage
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from features.notebooks.remarkable_export import PDF_SCALE, backgrounds_pdf, export_rmdoc, page_size
from features.notebooks.templates import CATALOG, settings

TEST_STAGE = TestStage.REGRESSION


class RemarkableExportTests(unittest.TestCase):
    def test_desktop_export_action_uses_portable_copy_encoder(self):
        from features.notebooks.ui.workspace import NotebookWorkspace
        book, editor = self.fixture()
        owner = SimpleNamespace(confirm_export=lambda: True, editor=editor,
                                bridge=object(), operation=Mock(), busy=False)
        owner.operation.start.side_effect = lambda work, **kw: work(Mock(), lambda: False)
        with patch('features.notebooks.ui.workspace.qt.QFileDialog.getSaveFileName',
                   return_value=('/synthetic/QA.rmdoc', '')), \
                patch('features.notebooks.ui.workspace.export_local_document') as publish:
            NotebookWorkspace.export_document(owner)
        exported = Notebook.read(publish.call_args.args[1])
        self.assertEqual(exported.content['fileType'], 'pdf')
        self.assertIn(exported.id + '.pdf', exported.members)
        self.assertEqual(book.content['fileType'], 'notebook')

    def fixture(self):
        book = Notebook.new('Portable templates')
        editor = Editor(book)
        for index, paper_format in enumerate(('pro', 'move')):
            if index:
                editor.apply(dict(op='add-page'))
            editor.apply(dict(op='template', name='Logistics Restaurant review', format=paper_format, visible=True))
            editor.apply(dict(op='stroke', points=[[700, 180, .5], [850, 180, .5]], tool=17, width=2, color=0))
        return book, editor

    def test_custom_backgrounds_export_with_native_ink_and_source_preserved(self):
        book, editor = self.fixture()
        ink = [book.page(i).to_bytes() for i in range(2)]
        members, content = dict(book.members), deepcopy(book.content)
        templates = [p.template for p in book.pages]
        result = Notebook.read(export_rmdoc(book))
        self.assertEqual(result.content['fileType'], 'pdf')
        self.assertEqual(result.content['originalPageCount'], 2)
        self.assertEqual(result.content['redirectionPageMap'], [0, 1])
        self.assertEqual([p.template for p in result.pages], ['Blank', 'Blank'])
        self.assertEqual([result.page(i).to_bytes() for i in range(2)], ink)
        self.assertEqual(book.members, members)
        self.assertEqual(book.content, content)
        self.assertEqual([p.template for p in book.pages], templates)
        self.assertTrue(editor.state()['template_editable'])
        self.assertNotIn(book.id + '.pdf', book.members)
        pdf = PdfReader(BytesIO(result.members[result.id + '.pdf']))
        self.assertEqual(len(pdf.pages), 2)
        for page, size in zip(pdf.pages, [(1404, 1872), (821, 1460)]):
            self.assertAlmostEqual(float(page.mediabox.width), size[0] * PDF_SCALE, places=5)
            self.assertAlmostEqual(float(page.mediabox.height), size[1] * PDF_SCALE, places=5)
            self.assertIn('Restaurant review', page.extract_text())
            self.assertIn('Food / service / atmosphere / value', page.extract_text())
            # No raster images or annotations carry template artwork or ink.
            self.assertNotIn('/XObject', page['/Resources'])
            self.assertNotIn('/Annots', page)
        first, second = [page.get_contents().get_data() for page in pdf.pages]
        self.assertIn(b'40 64 Tm (Restaurant review)', first)
        self.assertIn(b'331.5 64 Tm (Restaurant review)', second)

    def test_pdf_paper_geometry_retains_native_ink_coordinates(self):
        book, editor = self.fixture()
        exported = Notebook.read(export_rmdoc(book))
        editor = Editor(exported)
        editor.index = 1
        bounds = editor.state()['pdf_paper']
        self.assertAlmostEqual(bounds['x'], 291.5, places=4)
        self.assertAlmostEqual(bounds['width'], 821, places=4)
        self.assertAlmostEqual(bounds['height'], 1460, places=4)
        self.assertEqual(exported.page(1).strokes[0].points[0][:2], [700, 180])
        # A blank inserted notebook page has no PDF geometry.
        editor.apply(dict(op='add-page'))
        self.assertIsNone(editor.state()['pdf_paper'])

    def test_tall_pdf_export_retains_lower_ink_and_accepts_lower_edits(self):
        book, editor = self.fixture()
        book.page(0).strokes[0].points[0][1] = 2200
        exported = Notebook.read(export_rmdoc(book))
        editor = Editor(exported)
        height = editor.state()['height']
        self.assertGreater(height, 2200)
        editor.apply(dict(op='stroke', points=[[700, 2100, .5], [710, 2100, .5]]))
        editor.apply(dict(op='erase', points=[[700, 2100, .5]], radius=16))
        with self.assertRaises(ValueError):
            editor.apply(dict(op='stroke', points=[[700, height + 1, .5]]))
        with self.assertRaises(ValueError):
            editor.apply(dict(op='erase', points=[[700, height + 1, .5]], radius=16))

    def test_native_pdf_fit_to_height_uses_the_pdf_ink_coordinate_space(self):
        from pypdf import PdfWriter
        from features.notebooks.protocol import ink_patch_script, stroke_script
        from features.pdf.annotation import notebook_from_pdf
        writer = PdfWriter()
        writer.add_blank_page(width=954, height=1696)
        output = BytesIO()
        writer.write(output)
        book = notebook_from_pdf(output.getvalue(), 'Native PDF')
        book.content.update(formatVersion=2, zoomMode='fitToHeight')
        editor = Editor(book)

        # Existing scene coordinates are centered on the legacy 1404-unit
        # origin, including points outside its former editable bounds.
        points = [[-400, 4800, .5], [-390, 4810, .5]]
        book.page(0).add(points, page_height=5500, x_bounds=(-800, 2200))
        with patch.object(editor, 'background', return_value=None):
            state = editor.state()
        self.assertAlmostEqual(state['width'], 954 / PDF_SCALE)
        self.assertAlmostEqual(state['height'], 1696 / PDF_SCALE)
        self.assertEqual(state['pdf_paper']['x'], 0)
        self.assertEqual(state['brushes'][17]['widths'][1], 12.5)
        left = (1404 - state['width']) / 2
        self.assertAlmostEqual(state['strokes'][0]['points'][0][0], points[0][0] - left)
        self.assertEqual(state['strokes'][0]['points'][0][1], 4800)
        self.assertEqual(book.page(0).strokes[0].points[0][:2], points[0][:2])
        preview, = editor.page_previews(0)
        self.assertEqual((preview['width'], preview['height']), (state['width'], state['height']))
        self.assertEqual(preview['pdf_paper'], state['pdf_paper'])
        from base64 import b64decode
        from struct import unpack
        png = b64decode(preview['background'].split(',', 1)[1])
        self.assertEqual(max(unpack('>II', png[16:24])), 288)
        self.assertAlmostEqual(preview['items'][0]['points'][0][0], points[0][0] - left, places=2)

        editor.apply(dict(op='stroke', points=[[100, 4910, .5], [110, 4920, .5]]))
        saved = book.page(0).strokes[-1]
        self.assertAlmostEqual(saved.points[0][0], 100 + left)
        self.assertEqual(saved.points[0][3], 12.5)
        self.assertAlmostEqual(saved.scale, 2 * 227 / 72)
        self.assertEqual(book.page(0).strokes[0].points[0][3], 3.5)
        self.assertAlmostEqual(editor.canvas_stroke(saved)['points'][0][0], 100)
        stroke_data = json.JSONDecoder().raw_decode(stroke_script(editor, None).split('(', 1)[1])[0]
        self.assertAlmostEqual(stroke_data['points'][0][0], 100)
        patch_data = json.loads(ink_patch_script(editor, None, book.page(0).strokes[:-1]).split('(', 1)[1][:-1])
        self.assertAlmostEqual(patch_data['strokes'][0]['points'][0][0], 100)
        with self.assertRaisesRegex(ValueError, 'outside the page'):
            editor.apply(dict(op='erase', points=[[state['width'] + 1, 4910, .5]], radius=16))
        editor.apply(dict(op='erase', kind='whole', points=[[100, 4910, .5]], radius=16))
        self.assertEqual(len(book.page(0).strokes), 1)

        reopened = Notebook.read(book.to_bytes())
        self.assertEqual(reopened.page(0).strokes[0].points[0][:2], points[0][:2])
        self.assertEqual(reopened.members[reopened.id + '.pdf'], output.getvalue())

    def test_existing_pdf_view_is_not_reinterpreted_as_a_template_export(self):
        from pypdf import PdfWriter
        book = Notebook.new()
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        output = BytesIO()
        writer.write(output)
        book.members[book.id + '.pdf'] = output.getvalue()
        book.content['fileType'] = 'pdf'
        book.pages[0].record['redir'] = dict(value=0)
        self.assertIsNone(Editor(book).pdf_bounds())
        result = Notebook.read(export_rmdoc(book))
        self.assertEqual(result.members[result.id + '.pdf'], output.getvalue())

    def test_move_page_extends_for_hidden_ink_without_scaling_it(self):
        book, editor = self.fixture()
        editor.apply(dict(op='stroke', points=[[30, 1800, .5], [40, 1810, .5]]))
        ink = book.page(1)
        key = ink.layers[0][0]
        editor.apply(dict(op='layer-visible', layer=key, visible=False))
        width, height = page_size(book, 1)
        self.assertGreater(width, 1344)
        self.assertGreater(height, 1810)
        result = Notebook.read(export_rmdoc(book))
        self.assertEqual(result.page(1).to_bytes(), ink.to_bytes())
        self.assertEqual(result.page(1).layers, ink.layers)

    def test_move_repeating_paper_keeps_shared_page_size(self):
        book = Notebook.new()
        editor = Editor(book)
        for name in ['Logistics Grid', 'Logistics Dots', 'Logistics Lined medium']:
            editor.apply(dict(op='template', name=name, format='move', visible=True))
            self.assertEqual(page_size(book, 0), (1404, 1872))

    def test_unsupported_ink_objects_block_background_conversion(self):
        book, editor = self.fixture()
        book.page(0).warning = 'Unsupported native object'
        with self.assertRaisesRegex(ValueError, 'unsupported native objects'):
            export_rmdoc(book)

    def test_every_catalog_template_exports_as_vector_artwork(self):
        book = Notebook.new()
        editor = Editor(book)
        for i, name in enumerate(CATALOG):
            if i:
                editor.apply(dict(op='add-page'))
            editor.apply(dict(op='template', name=name, format='pro', visible=True))
        pdf = PdfReader(BytesIO(backgrounds_pdf(book)))
        self.assertEqual(len(pdf.pages), len(CATALOG))
        for name, page in zip(CATALOG, pdf.pages):
            data = page.get_contents().get_data()
            if name == 'Blank':
                self.assertNotIn(b' l S', data)
            else:
                self.assertIn(b' l S', data)
        for name, count in [('P Lines small', 41), ('P Lines medium', 25),
                            ('P Lines large', 21), ('Logistics Lined medium', 31)]:
            page = pdf.pages[list(CATALOG).index(name)]
            self.assertEqual(page.get_contents().get_data().count(b' l S'), count)

    def test_native_stock_exports_stay_notebooks_and_hidden_rules_stay_hidden(self):
        book = Notebook.new()
        editor = Editor(book)
        editor.apply(dict(op='template', name='P Lines small', format='pro', visible=True))
        native = Notebook.read(export_rmdoc(book))
        self.assertEqual(native.content['fileType'], 'notebook')
        self.assertEqual(native.pages[0].template, 'P Lines small')
        self.assertNotIn(native.id + '.pdf', native.members)
        editor.apply(dict(op='template', name='P Lines small', format='pro', visible=False))
        hidden = Notebook.read(export_rmdoc(book))
        pdf = PdfReader(BytesIO(hidden.members[hidden.id + '.pdf']))
        self.assertNotIn(b' l S', pdf.pages[0].get_contents().get_data())
        self.assertEqual(hidden.content['fileType'], 'pdf')
        self.assertFalse(settings(book, book.pages[0])['visible'])

    def test_unavailable_backgrounds_do_not_silently_export_as_blank(self):
        book, editor = self.fixture()
        asset = book.pages[0].template + '.template'
        book.members[asset] = b'{"imported":"different artwork"}'
        before = dict(book.members)
        with self.assertRaisesRegex(ValueError, 'artwork unavailable'):
            export_rmdoc(book)
        self.assertEqual(book.members, before)
        sidecar = f'{book.id}/{book.pages[0].id}.logistics-template.json'
        book.members[sidecar] = json.dumps(dict(format='pro', visible=False)).encode()
        result = Notebook.read(export_rmdoc(book))
        pdf = PdfReader(BytesIO(result.members[result.id + '.pdf']))
        self.assertNotIn('Restaurant review', pdf.pages[0].extract_text())
        self.assertIn('Restaurant review', pdf.pages[1].extract_text())
        self.assertEqual(book.members[asset], before[asset])

    def test_modern_redirects_and_opaque_page_fields_survive_export(self):
        book, editor = self.fixture()
        book.content['cPages'] = dict(pages=[])
        for i, page in enumerate(book.pages):
            page.record.update(id=page.id, opaque=dict(keep=i), idx=dict(timestamp='1:1', value='b' + chr(97 + i)))
            book.content['cPages']['pages'].append(deepcopy(page.record))
        modern = Notebook.read(export_rmdoc(book))
        for i, page in enumerate(modern.pages):
            self.assertEqual(page.record['redir']['value'], i)
            self.assertEqual(page.record['opaque'], dict(keep=i))
            self.assertEqual(page.template, 'Blank')

    def test_export_copy_can_be_reopened_edited_and_saved_without_rebaking(self):
        book, editor = self.fixture()
        result = Notebook.read(export_rmdoc(book))
        pdf = result.members[result.id + '.pdf']
        edited = Editor(result)
        edited.apply(dict(op='stroke', points=[[30, 40, .5], [60, 70, .5]]))
        again = Notebook.read(export_rmdoc(result))
        self.assertEqual(again.members[again.id + '.pdf'], pdf)
        self.assertEqual(len(again.page(0).strokes), 2)
        self.assertFalse(edited.state()['template_editable'])

    def test_cancellation_stops_export_before_mutating_source(self):
        book, editor = self.fixture()
        members = dict(book.members)
        with self.assertRaises(OperationCancelled):
            export_rmdoc(book, cancelled=lambda: True)
        self.assertEqual(book.members, members)
