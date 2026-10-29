"""Compact controls keep navigation, selection and editor ownership intact."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from mobile.app import LogisticsMobile
from mobile.control_icons import apply_icon


class ControlIconTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_find_icon_opens_own_search_without_losing_unsaved_text(self):
        self.app.new_document(extension='md')
        owner = self.app.editor_view
        owner.editor.value = 'Keep this unsaved draft'
        find = next(button for row in owner.document_view.children for button in row.children
                    if getattr(button, 'control_icon', '') == 'find')
        find.on_press()
        self.assertIn(owner.search.box, owner.document_view.children)
        self.assertEqual(owner.editor.value, 'Keep this unsaved draft')
        self.assertEqual(find.accessible_name, 'Find and replace')
        self.assertEqual(owner.save_button.control_icon, 'save')

    def test_search_back_dismisses_only_search_and_restores_document_close(self):
        self.app.new_document(extension='txt')
        self.app.show_documents(edit=True)
        owner = self.app.editor_view
        owner.editor.value = 'Keep the draft'
        button = owner.document_view._reader_close_button
        owner.toggle_search()
        self.assertEqual(button.control_icon, 'back')
        self.assertEqual(button.accessible_name, 'Back to document')
        button.on_press()
        self.assertNotIn(owner.search.box, owner.document_view.children)
        self.assertIn(owner.session.id, self.app.workspace.sessions)
        self.assertEqual(owner.editor.value, 'Keep the draft')
        self.assertEqual(button.control_icon, 'close')
        self.assertFalse(getattr(self.app, '_document_close_tasks', {}))
        owner.toggle_search()
        self.assertTrue(self.app.routes.back())
        self.assertNotIn(owner.search.box, owner.document_view.children)
        self.assertIn(owner.session.id, self.app.workspace.sessions)

    def test_restyling_browser_back_preserves_disabled_state_and_history_handler(self):
        self.app.show_cloud(present=False)
        self.app.loop.run_until_complete(self.app.show_files())
        browser = self.app.file_browser
        button = browser.back_button
        handler = button.on_press
        enabled = button.enabled
        apply_icon(button, 'back', 'Go back')
        self.assertIs(button.on_press, handler)
        self.assertEqual(button.enabled, enabled)
        self.assertEqual(button.accessible_name, 'Go back')
        self.assertEqual(browser.previous.accessible_name, 'Previous results')
        self.assertEqual(browser.next.accessible_name, 'Next results')

    def test_repeated_file_skip_taps_do_not_skip_multiple_comics(self):
        import asyncio
        import toga
        from mobile.reader_controls import ComicHeader
        async def exercise():
            started, release = asyncio.Event(), asyncio.Event()
            calls = []
            async def next_comic():
                calls.append('next')
                started.set()
                await release.wait()
            header = ComicHeader(toga.Button('More'), following=next_comic)
            pending = header.following.on_press()
            await started.wait()
            try:
                self.assertFalse(header.following.enabled)
                await header.following.on_press()
                self.assertEqual(calls, ['next'])
            finally:
                release.set()
                await pending
            self.assertTrue(header.following.enabled)
            self.assertFalse(header.previous.enabled)
        self.app.loop.run_until_complete(exercise())
