"""Real internal annotations, rotated hit regions and notebook page redirects."""
from io import BytesIO
import unittest
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from features.pdf.links import page_links, safe_page_links

TEST_STAGE = TestStage.REGRESSION


def linked_pdf(rotation=0):
    from pypdf import PdfWriter
    from pypdf.annotations import Link
    from pypdf.generic import NameObject, TextStringObject, DictionaryObject
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(300, 600)
    writer.pages[0].rotate(rotation)
    writer.add_annotation(0, Link(rect=(30, 420, 150, 540), target_page_index=2))
    writer.add_named_destination('chapter', 1)
    writer.add_annotation(0, DictionaryObject({NameObject('/Subtype'): NameObject('/Link'),
        NameObject('/Rect'): writer.pages[0]['/Annots'][0].get_object()['/Rect'],
        NameObject('/Dest'): TextStringObject('chapter')}))
    writer.add_annotation(0, Link(rect=(10, 10, 20, 20), url='https://example.com'))
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


class PDFLinkTests(unittest.TestCase):
    def test_notebook_background_uses_one_native_pdf_open(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from features.notebooks.editor import Editor
        from features.pdf.document import PDFDocument

        render = Mock(return_value=b'synthetic raster')
        data = linked_pdf()
        with patch.object(PDFDocument, 'backend', return_value=nullcontext(
                SimpleNamespace(count=3, render=render))) as open_renderer:
            self.assertTrue(Editor.render_background((data, 2)).startswith('data:image/png;base64,'))
        open_renderer.assert_called_once_with(data)
        render.assert_called_once_with(2)

    def test_explicit_named_and_rotation(self):
        expected = {0: [.1,.1,.5,.3], 90: [.7,.1,.9,.5], 180: [.5,.7,.9,.9], 270: [.1,.5,.3,.9]}
        for rotation, rect in expected.items():
            links = page_links(linked_pdf(rotation), 0)
            self.assertEqual([link['index'] for link in links], [2, 1])
            for actual, value in zip(links[0]['rect'], rect):
                self.assertAlmostEqual(actual, value)
        self.assertEqual(safe_page_links(b'broken', 0), [])
        self.assertEqual(page_links(linked_pdf(), 2), [])

    def test_crop_hidden_invalid_and_protected_annotations(self):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import NameObject, NumberObject, RectangleObject
        writer = PdfWriter(clone_from=PdfReader(BytesIO(linked_pdf())))
        page = writer.pages[0]
        page.cropbox = RectangleObject((30, 300, 270, 600))
        out = BytesIO(); writer.write(out)
        link = page_links(out.getvalue(), 0)[0]
        for actual, expected in zip(link['rect'], [0, .2, .5, .6]):
            self.assertAlmostEqual(actual, expected)
        for annotation in page['/Annots']:
            annotation.get_object()[NameObject('/F')] = NumberObject(32)
        out = BytesIO(); writer.write(out)
        self.assertEqual(page_links(out.getvalue(), 0), [])
        writer.encrypt('protected')
        out = BytesIO(); writer.write(out)
        self.assertEqual(page_links(out.getvalue(), 0), [])

    def test_notebook_redirects_after_insertion_move_and_deletion(self):
        from features.pdf.annotation import notebook_from_pdf
        from features.notebooks.editor import Editor
        book = notebook_from_pdf(linked_pdf(), 'Linked')
        editor = Editor(book)
        original = book.to_bytes()
        self.assertEqual([p['index'] for p in editor.page_links()], [2, 1])
        editor.apply(dict(op='add-page'))
        editor.apply(dict(op='page', index=0))
        self.assertEqual([p['index'] for p in editor.page_links()], [3, 2])
        book.move_page(3, 1)
        self.assertEqual([p['index'] for p in editor.page_links()], [1, 3])
        book.delete_page(1)
        self.assertEqual([p['index'] for p in editor.page_links()], [2])
        self.assertEqual(len(editor.undo), 1)  # link inspection/navigation never edits ink history
        self.assertTrue(original)

    def test_notebook_page_jumps_reuse_link_index_and_invalidate_on_pdf_change(self):
        from unittest.mock import patch
        from pypdf import PdfReader
        from features.pdf.annotation import notebook_from_pdf
        from features.notebooks.editor import Editor

        book = notebook_from_pdf(linked_pdf(), 'Linked')
        editor = Editor(book)
        editor.pdf_data()
        with patch('pypdf.PdfReader', wraps=PdfReader) as parse:
            self.assertEqual([link['index'] for link in editor.page_links()], [2, 1])
            editor.apply(dict(op='page', index=2))
            self.assertEqual(editor.page_links(), [])
            editor.apply(dict(op='page', index=0))
            self.assertEqual([link['index'] for link in editor.page_links()], [2, 1])
            self.assertEqual(parse.call_count, 1)

        book.members[book.id + '.pdf'] = linked_pdf(90)
        rotated = editor.page_links()[0]['rect']
        for actual, expected in zip(rotated, [.7, .1, .9, .5]):
            self.assertAlmostEqual(actual, expected)


class PDFDesktopLinkTests(QtTestCase):
    def test_desktop_real_plain_click_and_undo(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest
        from commonUtils.ui import pyside as qt
        from features.pdf.ui.reader import PDFWindow
        window = PDFWindow('linked.pdf', linked_pdf())
        self.addCleanup(window.close)
        window.show()
        QTest.qWait(100)
        view = window.view.viewport()
        # First link's center at (90,480), top-down (90,120).
        scale = min((view.width()-12)/300, (view.height()-12)/600)
        center = QPoint(round(view.width()/2 + (90-150)*scale), round(view.height()/2 + (120-300)*scale))
        QTest.mouseClick(view, qt.Qt.MouseButton.LeftButton, pos=center)
        QTest.qWait(30)
        self.assertEqual(window.index, 2)
        self.assertFalse(window.undo_jump.isHidden())
        window.undo_jump.click()
        self.assertEqual(window.index, 0)
        self.assertTrue(window.undo_jump.isHidden())
        window.offer_link_return(1)
        self.assertEqual(window.link_timer.interval(), 3000)
        window.go(1)
        self.assertIsNone(window.link_return)
