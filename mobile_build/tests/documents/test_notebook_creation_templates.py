"""Mobile naming, format switches, publication and cancellation retain paper choices."""
import unittest
from unittest.mock import AsyncMock, patch
from commonUtils.testing.stages import TestStage
from mobile_build.tests.documents import test_document_creation as creation
from features.notebooks.notebook import Notebook
from features.notebooks.templates import CATALOG, FORMATS, settings

TEST_STAGE = TestStage.REGRESSION


class NotebookCreationTemplateTests(unittest.TestCase):
    setUp = creation.DocumentCreationTests.setUp
    tearDown = creation.DocumentCreationTests.tearDown
    choose = creation.DocumentCreationTests.choose

    def test_mobile_creation_publishes_selected_template_after_format_switches(self):
        _, picker = self.choose('Ruled notes', 'Remarkable Document (.rmdoc)')
        controls = picker.notebook_templates
        controls.template.value = CATALOG['Logistics Cornell notes']
        controls.paper_format.value = FORMATS['move']
        self.assertEqual(picker.operation.notebook_template, 'Logistics Cornell notes')
        picker.creation_type.value = 'Plain text (.txt)'
        self.assertIsNone(controls.parent)
        picker.creation_type.value = 'Remarkable Document (.rmdoc)'
        self.assertIs(controls.parent, picker.name_view)
        self.assertEqual(controls.template.value, CATALOG['Logistics Cornell notes'])
        self.app.loop.run_until_complete(picker.save_text_destination())
        book = Notebook.read((self.root / 'LocalFiles/Ruled notes.rmdoc').read_bytes())
        self.assertEqual(book.pages[0].template, 'Logistics Cornell notes Move')
        self.assertEqual(settings(book, book.pages[0]), dict(format='move', visible=True))
        self.assertEqual(self.app.notebook_panel.editor.notebook.pages[0].template, book.pages[0].template)

    def test_cancel_leaves_no_notebook_and_fresh_creation_resets_choices(self):
        self.app.loop.run_until_complete(self.app.choose_document_type())
        picker = self.app.editor_picker()
        picker.creation_type.value = 'Remarkable Document (.rmdoc)'
        picker.notebook_templates.template.value = CATALOG['P Lines large']
        picker.cancel_text_destination()
        self.assertFalse(list(self.root.rglob('*.rmdoc')))
        self.app.loop.run_until_complete(self.app.choose_document_type())
        self.assertEqual(picker.operation.notebook_template, 'Blank')
        self.assertEqual(picker.notebook_templates.template.value, CATALOG['Blank'])
        picker.cancel_text_destination()

    def test_late_native_creation_does_not_replace_a_new_navigation(self):
        from types import SimpleNamespace
        from features.notebooks.mobile.panel import NotebookPanel
        app = SimpleNamespace(active_host=True, navigation_generation=1)
        owner = SimpleNamespace(app=app, busy=False, closed=False, load=AsyncMock())
        async def choose(*args):
            app.navigation_generation += 1
            return Notebook.new(template='P Lines small')
        with patch('features.notebooks.mobile.setup.choose_new_notebook', side_effect=choose):
            self.assertFalse(self.app.loop.run_until_complete(NotebookPanel.new(owner)))
        owner.load.assert_not_awaited()
        self.assertFalse(owner.busy)

    def test_native_notebook_library_creation_uses_same_catalog_and_can_cancel(self):
        from features.notebooks.mobile.setup import choose_new_notebook
        with patch.object(self.app.main_window, 'dialog', AsyncMock(side_effect=['Logistics Checklist', 'move'])):
            book = self.app.loop.run_until_complete(choose_new_notebook(self.app))
        self.assertEqual(book.pages[0].template, 'Logistics Checklist Move')
        with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='cancel')):
            self.assertIsNone(self.app.loop.run_until_complete(choose_new_notebook(self.app)))
