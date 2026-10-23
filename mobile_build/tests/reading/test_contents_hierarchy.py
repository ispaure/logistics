"""Contents destinations, disclosure independence and failure fallbacks."""
import asyncio
from io import BytesIO
from types import SimpleNamespace as NS
import unittest
from pypdf import PdfWriter
from commonUtils.ui.native.presentation import HierarchyList
from features.pdf.contents import contents
from features.pdf.mobile.contents import PDFContents
from features.books.mobile.navigation import ChapterList
from mobile.appearance import hierarchy_row_style


def fixture(outline=True):
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=100, height=100)
    if outline:
        parent = writer.add_outline_item('Getting started', 0)
        writer.add_outline_item('Installation', 1, parent=parent)
        writer.add_outline_item('Reference', 2)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class ContentsTests(unittest.TestCase):
    def test_pdf_destinations_keep_depth_and_zero_based_page(self):
        entries = contents(fixture())
        self.assertEqual([(e.label, e.depth, e.index) for e in entries],
                         [('Getting started', 0, 0), ('Installation', 1, 1), ('Reference', 0, 2)])
        self.assertEqual(contents(fixture(False)), ())

    def test_expand_never_activates_and_restores_hidden_descendants(self):
        selected = []
        tree = HierarchyList(contents(fixture()), selected.append, row_style=hierarchy_row_style)
        tree.rows.children[0].disclosure.on_press()
        self.assertEqual(len(tree.rows.children), 2)
        self.assertEqual(selected, [])
        tree.rows.children[0].title_button.on_press()
        self.assertEqual(selected[0].index, 0)
        tree.rows.children[0].disclosure.on_press()
        self.assertEqual(len(tree.rows.children), 3)
        tree.rows.children[1].title_button.on_press()
        self.assertEqual(selected[-1].index, 1)
        self.assertEqual(tree.rows.children[1].children[0].style.width, 20)

    def test_only_one_chapter_destination_is_current_for_shared_spine(self):
        entries = [NS(label='Part', depth=0, index=0), NS(label='Section', depth=1, index=0)]
        tree = ChapterList(entries, lambda entry: None, row_style=hierarchy_row_style, current=0)
        self.assertEqual([row.title_button.hierarchy_selected for row in tree.rows.children], [True, False])
        self.assertEqual(tree.rows.children[0]._impl._surface_roles, ('hover', None, False))
        self.assertEqual(tree.rows.children[0].title_button._impl._surface_roles, ('transparent', 'text', False))

    def test_pdf_empty_contents_and_closed_reader_do_not_jump(self):
        async def check():
            jumps = []
            alive = True
            panel = PDFContents(NS(data=fixture(False)), on_page=jumps.append, alive=lambda: alive)
            await panel.toggle()
            self.assertIn('no contents', panel.notice.text)
            self.assertIsNone(panel.tree)
            panel.document.data = fixture()
            await panel.toggle()
            self.assertIsNotNone(panel.tree)
            alive = False
            panel.choose(panel.tree.entries[0])
            self.assertEqual(jumps, [])
            panel.dispose()
            self.assertEqual(panel.tree.entries, [])
            self.assertEqual(panel.tree.rows.children, [])
            self.assertIsNone(panel.document)
        asyncio.run(check())
