"""Compact controls keep navigation, selection and editor ownership intact."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.control_icons import apply_icon


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
        self.assertEqual(owner.save_button.text, 'Save')

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
