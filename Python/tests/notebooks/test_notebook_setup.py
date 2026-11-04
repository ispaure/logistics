"""Creation chooses initial paper; subsequent edits and insertions stay per page."""
from unittest.mock import Mock, patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.testing.stages import TestStage
from features.notebooks.notebook import Notebook
from features.notebooks.editor import Editor
from features.notebooks.templates import settings

TEST_STAGE = TestStage.REGRESSION


class NotebookSetupTests(QtTestCase):
    def test_desktop_creation_dialog_builds_selected_first_page(self):
        from features.notebooks.ui.setup import NotebookSetup
        dialog = NotebookSetup(name='Field notes')
        self.addCleanup(dialog.deleteLater)
        dialog.template.setCurrentIndex(dialog.template.findData('Logistics Cornell notes'))
        dialog.paper_format.setCurrentIndex(dialog.paper_format.findData('move'))
        self.assertFalse(dialog.preview.pixmap().isNull())
        book = Notebook.read(dialog.notebook().to_bytes())
        self.assertEqual(book.name, 'Field notes')
        self.assertEqual(book.pages[0].template, 'Logistics Cornell notes Move')
        self.assertEqual(settings(book, book.pages[0]), dict(format='move', visible=True))
        dialog.template.setCurrentIndex(dialog.template.findData('P Lines small'))
        self.assertFalse(dialog.paper_format.isEnabled())
        native = dialog.notebook()
        self.assertEqual(native.pages[0].template, 'P Lines small')
        self.assertFalse(any(name.endswith('.template') for name in native.members))

    def test_cancel_draft_creation_does_not_open_workspace(self):
        from services.documents.ui.notebooks import new_notebook_document, open_notebook_choice
        with patch('features.notebooks.ui.setup.choose_new_notebook', return_value=None), \
                patch('features.notebooks.ui.workspace.open_workspace') as opening:
            self.assertIsNone(new_notebook_document())
            choice = Mock(path='Notes.rmdoc')
            self.assertIsNone(open_notebook_choice(choice, create=True))
        opening.assert_not_called()
        choice.close.assert_called_once()

    def test_inserted_page_inherits_current_template_without_changing_neighbors(self):
        book = Notebook.new('Mixed', template='P Lines small')
        editor = Editor(book)
        editor.apply(dict(op='add-page'))
        editor.apply(dict(op='template', name='Logistics Cornell notes', format='move', visible=False))
        editor.apply(dict(op='add-page'))
        editor.apply(dict(op='template', name='Logistics Checklist', format='pro', visible=True))
        editor.apply(dict(op='page', index=1))
        editor.apply(dict(op='stroke', points=[[700, 100, .5], [740, 120, .7]]))
        original_ink = book.page(1).to_bytes()
        editor.apply(dict(op='add-page'))
        self.assertEqual(editor.index, 2)
        self.assertEqual(book.pages[2].template, 'Logistics Cornell notes Move')
        self.assertEqual(settings(book, book.pages[2]), dict(format='move', visible=False))
        self.assertEqual(book.page(2).strokes, [])
        self.assertEqual(book.page(1).to_bytes(), original_ink)
        self.assertEqual(book.pages[3].template, 'Logistics Checklist Pro')
        editor.apply(dict(op='template', name='P Lines large', format='pro', visible=True))
        self.assertEqual(book.pages[1].template, 'Logistics Cornell notes Move')
        editor.apply(dict(op='undo'))
        self.assertEqual(book.pages[2].template, 'Logistics Cornell notes Move')
        editor.apply(dict(op='undo'))
        self.assertEqual(len(book.pages), 3)
        editor.apply(dict(op='redo'))
        reopened = Notebook.read(book.to_bytes())
        self.assertEqual(reopened.pages[2].template, 'Logistics Cornell notes Move')
        self.assertEqual(settings(reopened, reopened.pages[2]), dict(format='move', visible=False))
