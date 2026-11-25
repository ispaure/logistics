"""Portable template backgrounds remain separate from live native ink."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from base64 import b64decode
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pypdf import PdfReader
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.testing.stages import TestStage
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook, read_archive
from features.notebooks.remarkable_export import PDF_SCALE, backgrounds_pdf, export_rmdoc, page_size, save_rmdoc
from features.notebooks.storage import NotebookDocument
from features.notebooks.templates import CATALOG, settings

TEST_STAGE = TestStage.REGRESSION
FIXTURES = Path(__file__).with_name('fixtures')


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

    def test_pdf_background_cache_reuses_neighbor_rasters_with_a_byte_limit(self):
        from pypdf import PdfWriter
        from features.pdf.annotation import notebook_from_pdf

        writer = PdfWriter()
        for _ in range(4):
            writer.add_blank_page(width=300, height=400)
        output = BytesIO()
        writer.write(output)
        editor = Editor(notebook_from_pdf(output.getvalue(), 'Four pages'))
        with patch.object(editor, 'render_background', side_effect=lambda key: str(key[1]) * 3) as render, \
                patch('features.notebooks.editor.PDF_BACKGROUND_BYTES', 9):
            editor.index = 1
            self.assertEqual(editor.background(), '111')
            current = editor.background_key(1)
            editor.cache_background(editor.background_key(0), '000', keep=current)
            editor.cache_background(editor.background_key(2), '222', keep=current)
            editor.cache_background(editor.background_key(3), '3333333', keep=current)
            editor.index = 2
            self.assertEqual(editor.background(), '222')
            editor.index = 1
            self.assertEqual(editor.background(), '111')
            editor.index = 0
            self.assertEqual(editor.background(), '000')
            self.assertEqual(render.call_count, 1)
            self.assertIsNone(editor.cached_background(editor.background_key(3)))

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
            self.assertIn('What I ordered', page.extract_text())
            # No raster images or annotations carry template artwork or ink.
            self.assertEqual(len(page.images), 0)
            self.assertNotIn('/Annots', page)
        self.assertIn('Highlights', pdf.pages[0].extract_text())
        self.assertNotIn('Highlights', pdf.pages[1].extract_text())

    def test_reopened_reviews_use_the_saved_layout_instead_of_the_current_preset(self):
        book, _ = self.fixture()
        for page, paper in zip(book.pages, ('pro', 'move')):
            book.members[page.template + '.template'] = (FIXTURES / f'restaurant-review-legacy-{paper}.template').read_bytes()
        asset_path = book.pages[0].template + '.template'
        asset = json.loads(book.members[asset_path])
        asset['items'][0].update(data=['M', 100, 300, 'L', 600, 300], strokeColor='#102040', strokeWidth=3)
        label = next(item for item in asset['items'] if item.get('text') == 'Restaurant / location')
        label['text'] = 'Saved café (location) & notes'
        book.members[asset_path] = json.dumps(asset).encode()
        data = book.to_bytes()
        reopened = Notebook.read(data)
        document = NotebookDocument(reopened)
        editor = Editor(reopened, document.checkpoint)
        state = editor.state()
        artwork = b64decode(state['background'].split(',', 1)[1]).decode()
        self.assertTrue(state['template_available'])
        self.assertIn('Saved café (location) &amp; notes', artwork)
        self.assertIn('M 100 300 L 600 300', artwork)
        self.assertIn('stroke="#102040" stroke-width="3"', artwork)
        self.assertEqual(editor.page_previews(0)[0]['background'], state['background'])
        self.assertFalse(reopened.structure_dirty)
        self.assertFalse(reopened.metadata_dirty)
        self.assertFalse(document.dirty)
        self.assertEqual(read_archive(reopened.to_bytes()), read_archive(data))

        exported = Notebook.read(export_rmdoc(reopened))
        pdf = PdfReader(BytesIO(exported.members[exported.id + '.pdf']))
        self.assertIn(label['text'], pdf.pages[0].extract_text())
        self.assertNotIn('Restaurant / location', pdf.pages[0].extract_text())
        self.assertIn(b'3 w 100 300 m 600 300 l S', pdf.pages[0].get_contents().get_data())
        self.assertIn('Restaurant / location', pdf.pages[1].extract_text())
        self.assertEqual(exported.page(0).to_bytes(), reopened.page(0).to_bytes())
        self.assertFalse(document.dirty)
        self.assertEqual(read_archive(reopened.to_bytes()), read_archive(data))
        working = Notebook.read(save_rmdoc(reopened), restore_templates=False)
        baked = PdfReader(BytesIO(working.members[working.id + '.pdf']))
        self.assertIn(label['text'], baked.pages[0].extract_text())

        editor.apply(dict(op='template', name='Logistics Restaurant review', format='pro', visible=False))
        self.assertTrue(document.dirty)
        self.assertIsNone(editor.state()['background'])
        self.assertEqual(editor.state()['hidden_template_preview'], state['background'])
        self.assertEqual(reopened.members[asset_path], book.members[asset_path])
        new_book = Notebook.new(template='Logistics Restaurant review')
        self.assertNotEqual(Editor(new_book).state()['background'], state['background'])
        self.assertEqual(editor.state()['template_update_pages'], 2)
        ink = [reopened.page(i).to_bytes() for i in range(2)]
        references = [page.template for page in reopened.pages]
        editor.apply(dict(op='update-template', page_id=reopened.pages[0].id))
        self.assertEqual(editor.state()['template_update_pages'], 0)
        self.assertEqual([page.template for page in reopened.pages], references)
        self.assertEqual([reopened.page(i).to_bytes() for i in range(2)], ink)
        self.assertFalse(editor.state()['template_settings']['visible'])
        updated = Notebook.read(save_rmdoc(reopened), restore_templates=False)
        baked = PdfReader(BytesIO(updated.members[updated.id + '.pdf']))
        self.assertIn('What I ordered', baked.pages[1].extract_text())
        self.assertEqual(len(baked.pages[1].images), 0)
        editor.apply(dict(op='undo'))
        self.assertEqual(editor.state()['template_update_pages'], 2)
        self.assertEqual(reopened.members[asset_path], book.members[asset_path])

    def test_embedded_artwork_can_export_without_a_catalog_entry(self):
        book = Notebook.new(template='Logistics Restaurant review')
        page = book.pages[0]
        old = page.template
        page.template = 'Archived restaurant review'
        book.members[page.template + '.template'] = book.members.pop(old + '.template')
        reopened = Notebook.read(book.to_bytes())
        state = Editor(reopened).state()
        self.assertTrue(state['template_available'])
        self.assertTrue(state['template_requires_pdf'])
        exported = Notebook.read(export_rmdoc(reopened))
        self.assertEqual(exported.pages[0].template, 'Blank')
        pdf = PdfReader(BytesIO(exported.members[exported.id + '.pdf']))
        self.assertIn('What I ordered', pdf.pages[0].extract_text())

    def test_regular_save_embeds_the_pdf_and_reopens_as_an_editable_notebook(self):
        book, _ = self.fixture()
        saved = Mock()
        resource = SimpleNamespace(save=saved)
        document = NotebookDocument(book, resource=resource)
        document.save()
        data = saved.call_args.args[0]
        portable = Notebook.read(data, restore_templates=False)
        self.assertEqual(portable.content['fileType'], 'pdf')
        self.assertEqual([page.template for page in portable.pages], ['Blank', 'Blank'])
        pdf = PdfReader(BytesIO(portable.members[portable.id + '.pdf']))
        self.assertIn('What I ordered', pdf.pages[1].extract_text())
        self.assertEqual(portable.page(1).to_bytes(), book.page(1).to_bytes())

        reopened = Notebook.read(data)
        editor = Editor(reopened)
        editor.index = 1
        self.assertTrue(editor.state()['template_editable'])
        self.assertEqual(reopened.pages[1].template, book.pages[1].template)
        self.assertFalse(reopened.structure_dirty)
        editor.apply(dict(op='add-page'))
        self.assertEqual(reopened.pages[2].template, book.pages[1].template)
        editor.apply(dict(op='template', name='Logistics Meeting notes', format='move', visible=True))
        again = Notebook.read(save_rmdoc(reopened), restore_templates=False)
        baked = PdfReader(BytesIO(again.members[again.id + '.pdf']))
        self.assertIn('Meeting notes', baked.pages[2].extract_text())
        self.assertEqual(again.page(1).to_bytes(), portable.page(1).to_bytes())

    def test_working_file_keeps_the_pdf_if_the_editable_template_assets_are_missing(self):
        book, _ = self.fixture()
        portable = Notebook.read(save_rmdoc(book), restore_templates=False)
        del portable.members[book.pages[0].template + '.template']
        reopened = Notebook.read(portable.to_bytes())
        self.assertEqual(reopened.content['fileType'], 'pdf')
        self.assertEqual(reopened.members[book.id + '.pdf'], portable.members[book.id + '.pdf'])

    def test_regular_save_preserves_ink_that_cannot_be_baked(self):
        book, _ = self.fixture()
        book.page(0).strokes[0].points[0][1] = -100
        saved = Notebook.read(save_rmdoc(book), restore_templates=False)
        self.assertEqual(saved.content['fileType'], 'notebook')
        self.assertEqual(saved.page(0).to_bytes(), book.page(0).to_bytes())

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
        self.assertGreater(state['eraser_scale'] * 16, 40)
        editor.apply(dict(op='erase', kind='whole', points=[[100, 4870, .5]], radius=16))
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

    def test_native_best_fit_uses_each_pdf_crop_box_with_ink_in_native_units(self):
        from pypdf import PdfWriter
        from pypdf.generic import RectangleObject

        writer = PdfWriter()
        first = writer.add_blank_page(width=320, height=570)
        first.cropbox = RectangleObject((5, 6, 310.5748, 560.4567))
        writer.add_blank_page(width=510, height=680)
        output = BytesIO()
        writer.write(output)
        book = Notebook.new('Native best-fit PDF')
        book.content.update(fileType='pdf', formatVersion=2, zoomMode='bestFit',
                            customZoomPageWidth=1404, customZoomPageHeight=1872, cPages={'pages': []})
        book.members[book.id + '.pdf'] = output.getvalue()
        book.add_page()
        for index, page in enumerate(book.pages):
            page.record['redir'] = dict(value=index)
            book.page(index).add([[702, 532, .5], [712, 532, .5]])

        loaded = Notebook.read(book.to_bytes())
        editor = Editor(loaded)
        for index, (width, height) in enumerate(((305.5748, 554.4567), (510, 680))):
            with self.subTest(index=index), patch.object(editor, 'background', return_value=None):
                editor.index = index
                state = editor.state()
                paper = state['pdf_paper']
                self.assertTrue(state['fit_pdf_page'])
                self.assertAlmostEqual(paper['width'], width * 226 / 72)
                self.assertAlmostEqual(paper['height'], height * 226 / 72)
                self.assertAlmostEqual(state['strokes'][0]['points'][0][0] - paper['x'], paper['width'] / 2)
                self.assertEqual(state['strokes'][0]['points'][0][1], 532)
                self.assertEqual(state['eraser_scale'], 1)
                self.assertEqual(loaded.page(index).to_bytes(), book.page(index).to_bytes())

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
            elif name == 'Logistics Restaurant review':
                self.assertIn('What I ordered', page.extract_text())
                self.assertEqual(len(page.images), 0)
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
        working = Notebook.read(save_rmdoc(book))
        self.assertEqual(working.content['fileType'], 'notebook')
        for original, reopened in zip(book.pages, working.pages):
            self.assertEqual(reopened.template, original.template)
            self.assertEqual(reopened.record['opaque'], original.record['opaque'])
            self.assertNotIn('redir', reopened.record)

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
