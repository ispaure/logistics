"""Reader chrome preserves format capabilities and editing state."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.documents import LocalDocuments
from commonUtils.runtime.resources.local import LocalFiles
from features.pdf.mobile.copies import PDFCopies
from features.text_editor.resources import LocalTextCopies
from mobile.app import LogisticsMobile
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books


class ReaderCohesionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        LogisticsMobile.storage_root = self.root / 'app'
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')

    def tearDown(self):
        for owner in self.app.text_views.values():
            owner.dispose()
        self.app.loop.run_until_complete(asyncio.sleep(0))
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_epub_and_comic_offer_only_their_own_navigation(self):
        epub, comic = make_books(self.root)
        store = self.app.reader_manager().catalog.library_store
        for path, kind in ((epub, 'epub'), (comic, 'comic')):
            record = store.import_book(LocalDocuments(), path)
            self.app.loop.run_until_complete(self.app.open_book(record['id']))
            owner = self.app.readers.active
            owner.set_reading_mode(False)
            view = owner.library_view
            self.assertEqual(view._native_reader_title(), owner.session.title)
            self.assertIs(owner.reader_footer.parent, view)
            labels = [label.lower() for label, callback in owner.reader_actions.actions]
            buttons = view._native_reader_buttons()
            if kind == 'epub':
                self.assertEqual([button.control_icon for button in buttons], ['speaker', 'more'])
                self.assertTrue(any('chapters' in label for label in labels))
                self.assertNotIn(owner.previous_page, buttons)
            else:
                self.assertEqual(view.style.margin, (0, 0, 0, 0))
                self.assertIs(owner.page_footer.badge.parent, owner.reader_footer)
                self.assertNotIn(owner.book_status, view.children)
                self.assertFalse(any('chapter' in label or 'read aloud' in label for label in labels))
                self.assertTrue(any('comic pages' in label for label in labels))
                self.assertNotIn('speaker', [button.control_icon for button in buttons])
                self.assertTrue(owner.book_status.text.startswith('Page '))
                self.assertNotIn(record['name'], owner.book_status.text)
            owner.set_reading_mode(True)
            self.assertNotIn(owner.reader_footer, view.children)
            owner.set_reading_mode(False)
            self.assertIs(owner.reader_footer.parent, view)

    def test_editor_toolbar_tracks_unsaved_edits_and_leaves_rename_to_browser(self):
        self.app.create_chosen_document('md')
        owner = self.app.editor_view
        view = owner.document_view
        self.assertEqual([b.control_icon for b in view._native_reader_buttons()], ['view', 'more'])
        owner.editor.value = '# Unsaved passage\n'
        self.assertEqual([b.control_icon for b in view._native_reader_buttons()], ['save', 'more'])
        self.assertNotIn('Rename document…', [label for label, callback in owner.actions.actions])
        owner.rename_document()
        rename_view = self.app.routes.body('documents').children[0]
        rename_view.children[1].value = 'Renamed.md'
        rename_view.children[-1].on_press()
        self.assertEqual(view._native_reader_title(), 'Renamed.md')
        self.assertEqual(owner.editor.value, '# Unsaved passage\n')
        self.assertTrue(owner.document.modified)
        self.app.save_document()
        self.assertNotIn(owner.save_button, view._native_reader_buttons())

    def test_pdf_search_panel_survives_chrome_changes_without_chapter_actions(self):
        from pypdf import PdfWriter
        path = self.root / 'Guide.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=450)
        writer.write(path)
        async def exercise():
            self.assertTrue(await self.app.open_crypt(copies=PDFCopies(LocalFiles(self.root)), key=path.name), self.app.cloud_status.value)
            owner = self.app.private_sessions.active
            view = owner.crypt_view
            self.assertEqual(view._native_reader_title(), 'Guide.pdf')
            self.assertEqual([b.control_icon for b in view._native_reader_buttons()], ['find', 'more'])
            labels = [label.lower() for label, callback in owner.crypt_actions_menu.actions]
            self.assertFalse(any('chapter' in label or 'read aloud' in label or 'metadata' in label for label in labels))
            self.assertTrue(owner.reading_frame.immersive)
            owner.toggle_private_reading_mode()
            owner.pdf_tools.toggle()
            self.assertIn(owner.pdf_tools.panel, owner.pdf_tools.widget.children)
            owner.pdf_number.value = '0'
            await owner.pdf_number.on_confirm()
            self.assertTrue(owner.pdf_jump_status.text)
            self.assertIn(owner.pdf_jump_status, owner.pdf_tools.panel.children)
            owner.toggle_private_reading_mode()
            self.assertNotIn(owner.pdf_tools.widget, view.children)
            owner.toggle_private_reading_mode()
            self.assertIs(owner.pdf_tools.widget.parent, view)
            self.assertLess(view.children.index(owner.pdf_tools.widget), view.children.index(owner.pdf_body))
            self.assertEqual(owner.pdf_tools.button.control_icon, 'find')
        from mobile_build.tests.support.pdf import native_pdf
        with patch('features.pdf.document.PDFDocument.open', native_pdf):
            self.app.loop.run_until_complete(exercise())

    def test_plain_text_save_is_not_a_markdown_only_action(self):
        (self.root / 'Note.txt').write_text('Original')
        async def exercise():
            self.assertTrue(await self.app.open_crypt(copies=LocalTextCopies(LocalFiles(self.root)), key='Note.txt'))
            owner = self.app.private_sessions.active
            owner.crypt_text.value = 'Unsaved text'
            self.assertEqual([b.control_icon for b in owner.crypt_view._native_reader_buttons()][-1], 'more')
            self.assertIn(owner.crypt_save, owner.crypt_view._native_reader_buttons())
            owner.crypt_text.value = 'Original'
            self.assertNotIn(owner.crypt_save, owner.crypt_view._native_reader_buttons())
        self.app.loop.run_until_complete(exercise())

    def test_markdown_more_menu_tracks_reading_and_editing_capabilities(self):
        self.app.create_chosen_document('md')
        self.app.show_preview()
        managed = self.app.editor_view
        self.assertEqual([b.control_icon for b in managed.preview_box._native_reader_buttons()], ['edit', 'more'])
        self.assertIn('Read aloud…', [label for label, callback in managed.preview_actions.actions])
        (self.root / 'Note.md').write_text('# A note\n')
        async def exercise():
            self.assertTrue(await self.app.open_crypt(copies=LocalTextCopies(LocalFiles(self.root)), key='Note.md'))
            owner = self.app.private_sessions.active
            self.assertEqual([b.control_icon for b in owner.crypt_view._native_reader_buttons()], ['edit', 'more'])
            self.assertIn('Read aloud…', [label for label, callback in owner.crypt_actions_menu.actions])
            owner.toggle_private_preview()
            self.assertNotIn('Read aloud…', [label for label, callback in owner.crypt_actions_menu.actions])
            owner.crypt_text.value = '# An unsaved note\n'
            self.assertEqual([b.control_icon for b in owner.crypt_view._native_reader_buttons()], ['save', 'more'])
            self.assertIn('View Markdown', [label for label, callback in owner.crypt_actions_menu.actions])
        self.app.loop.run_until_complete(exercise())
