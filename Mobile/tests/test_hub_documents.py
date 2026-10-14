"""Hub commands and search must retain the correct draft/session owner."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.app import LogisticsMobile


class HubDocumentTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_new_from_home_displays_new_editor_and_keeps_previous_draft(self):
        app = self.app
        first = app.current.id
        app.editor.value = 'Retain my draft'
        app.show_home()
        app.new_hub_document()
        self.assertNotEqual(app.current.id, first)
        self.assertEqual(app.native_host.state.destination, 'documents')
        self.assertIn(app.document_view, app.body.children)
        self.assertEqual(app.store.open(first).text, 'Retain my draft')

    def test_home_browse_refreshes_local_root_after_other_views_and_search(self):
        import asyncio
        import toga
        app = self.app
        def button(widget):
            if isinstance(widget, toga.Button) and widget.text == 'Browse files':
                return widget
            children = list(widget.children)
            if isinstance(widget, toga.ScrollContainer) and widget.content is not None:
                children.append(widget.content)
            return next((found for child in children if (found := button(child)) is not None), None)
        async def press_home():
            app.show_home()
            action = button(app.body)
            self.assertIsNotNone(action)
            result = action.on_press()
            if result is not None:
                await result
            self.assertEqual(app.native_host.state.destination, 'files')
            self.assertIn('All files', app.folder_picker_choices)
            app.folder_choice.value = 'All files'
            await app.folder_browse_button.on_press()
            self.assertIn(app.files_view, app.body.children)
            self.assertEqual(app.file_storage.value, 'Local files')
            self.assertEqual(app.file_path, '')
            self.assertEqual(app.file_browser.search.value, '')
        async def exercise():
            await press_home()
            root = app.private_root / 'LocalFiles'
            (root / 'Notes').mkdir()
            (root / 'Notes' / 'Draft.md').write_text('# Draft')
            await app.browser_file_location(('Local files', 'Notes'))
            app.file_browser.search.value = 'Missing filename'
            for view in (app.show_documents, app.show_settings, app.show_documents_hub):
                view()
                await press_home()
                self.assertIn('Notes', [entry.label for entry in app.file_browser.entries])
            (root / 'New while away.txt').write_text('Fresh item')
            app.show_settings()
            await press_home()
            self.assertIn('New while away.txt', [entry.label for entry in app.file_browser.entries])
            # A pending cloud probe/credential restore must not block local entry.
            app.set_cloud_busy(True)
            try:
                await press_home()
                self.assertTrue(app.cloud_busy)
            finally:
                app.set_cloud_busy(False)
        app.loop.run_until_complete(exercise())

    def test_continue_resumes_selected_document_and_preview(self):
        app = self.app
        app.name.value = 'Notes.md'
        app.editor.value = '# Retained'
        first = app.editor_view.session.id
        app.show_preview()
        app.show_home()
        card = app.body.children[0].content.children[3]
        card.children[-1].on_press()
        self.assertEqual(app.workspace.active, first)
        self.assertEqual(app.editor.value, '# Retained')
        self.assertEqual(app.editor_view.session.view['markdown_mode'], 'preview')

    def test_search_wraps_unicode_literal_replacement_and_draft_recovery(self):
        app = self.app
        app.editor.value = '😀 One one ONE'
        search = app.editor_view.search
        search.query.value = 'one'
        search.next()
        self.assertEqual(search.span, (2, 5))
        search.previous()
        self.assertEqual(search.span, (10, 13))
        search.next()
        self.assertEqual(search.span, (2, 5))
        search.replacement.value = r'\1$'
        search.replace()
        self.assertEqual(app.current.text, '😀 \\1$ one ONE')
        search.case.value = True
        search.replace_all()
        self.assertEqual(app.current.text, '😀 \\1$ \\1$ ONE')
        self.assertEqual(app.store.open(app.current.id).text, app.current.text)
        self.assertTrue(app.current.modified)

    def test_search_is_owned_by_each_document_and_does_not_change_other_drafts(self):
        app = self.app
        app.editor.value = 'first first'
        first = app.editor_view
        first.search.query.value = 'first'
        app.new_hub_document()
        app.editor.value = 'second'
        second = app.editor_view
        second.search.query.value = 'second'
        second.search.replacement.value = 'changed'
        second.search.replace_all()
        self.assertEqual(first.document.text, 'first first')
        self.assertEqual(first.search.query.value, 'first')
        self.assertEqual(second.document.text, 'changed')

    def test_home_reflows_existing_panels_without_replacing_commands(self):
        grid = self.app.home_panels
        cards = list(grid.cards)
        for width, columns in ((360, 1), (800, 2), (1200, 3), (360, 1)):
            grid.reflow(width)
            self.assertEqual(grid.columns, columns)
            self.assertEqual([card for row in grid.children for card in row.children], cards)
            self.assertTrue(all(len(row.children) <= columns for row in grid.children))


if __name__ == '__main__':
    unittest.main()
