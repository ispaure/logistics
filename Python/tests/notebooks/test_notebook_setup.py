"""Creation chooses initial paper; subsequent edits and insertions stay per page."""
import json
from copy import deepcopy
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

    def test_failed_single_page_change_and_failed_insertion_restore_all_pages(self):
        book = Notebook.new('Mixed', template='Logistics Grid', paper_format='pro')
        editor = Editor(book)
        editor.apply(dict(op='stroke', points=[[700, 100, .5], [710, 120, .5]]))
        editor.apply(dict(op='add-page'))
        editor.apply(dict(op='template', name='P Lines small', format='pro', visible=True))
        editor.apply(dict(op='page', index=0))
        before = [(p.id, p.template, deepcopy(p.record), book.page(i).to_bytes()) for i, p in enumerate(book.pages)]
        members = dict(book.members)
        undo, redo = list(editor.undo), list(editor.redo)
        editor.checkpoint = Mock(side_effect=OSError('Storage unavailable'))
        for action in [dict(op='template', name='Logistics Checklist', format='move', visible=False),
                       dict(op='add-page')]:
            with self.assertRaisesRegex(OSError, 'Storage unavailable'):
                editor.apply(action)
            after = [(p.id, p.template, p.record, book.page(i).to_bytes()) for i, p in enumerate(book.pages)]
            self.assertEqual(after, before)
            self.assertEqual(book.members, members)
            self.assertEqual(editor.index, 0)
            self.assertEqual(editor.undo, undo)
            self.assertEqual(editor.redo, redo)

    def test_imported_artwork_and_display_settings_inherit_without_copying_ink(self):
        book = Notebook.new()
        page = book.pages[0]
        page.template = 'Imported ruling'
        book.members[page.template + '.template'] = b'{"vendor":"unmodified artwork"}'
        sidecar = json.dumps(dict(format='move', visible=False, opaque=dict(retain=True))).encode()
        book.members[f'{book.id}/{page.id}.logistics-template.json'] = sidecar
        editor = Editor(book)
        editor.apply(dict(op='stroke', points=[[700, 100, .5], [730, 120, .5]]))
        editor.apply(dict(op='add-page'))
        self.assertEqual(book.pages[1].template, 'Imported ruling')
        self.assertEqual(book.members[f'{book.id}/{book.pages[1].id}.logistics-template.json'], sidecar)
        self.assertEqual(book.members['Imported ruling.template'], b'{"vendor":"unmodified artwork"}')
        self.assertFalse(book.page(1).strokes)
        self.assertEqual(len(book.page(0).strokes), 1)
        self.assertNotIn('Original Logistics', editor.state()['template_description'])

    def test_foreign_artwork_under_a_known_name_is_not_labeled_original(self):
        book = Notebook.new(template='Logistics Grid')
        book.members[book.pages[0].template + '.template'] = b'{"vendor":"different grid"}'
        state = Editor(book).state()
        self.assertFalse(state['template_available'])
        self.assertIn('Imported', state['template_description'])
        self.assertNotIn('Original Logistics', state['template_description'])

    def test_modern_reordered_page_inherits_from_current_page_and_preserves_neighbors(self):
        book = Notebook.new('Modern', template='P Lines small')
        editor = Editor(book)
        editor.apply(dict(op='add-page'))
        editor.apply(dict(op='template', name='Logistics Checklist', format='move', visible=False))
        editor.apply(dict(op='add-page'))
        editor.apply(dict(op='template', name='P Lines large', format='pro', visible=True))
        book.content['cPages'] = dict(pages=[])
        for index, page in enumerate(book.pages):
            page.record.update(id=page.id, idx=dict(value='b' + chr(97 + index)), opaque=dict(owner=index))
            book.content['cPages']['pages'].append(deepcopy(page.record))
        editor.apply(dict(op='page', index=0))
        editor.apply(dict(op='move-page', index=2))
        editor.apply(dict(op='page', index=0))
        parent = book.pages[0]
        editor.apply(dict(op='add-page'))
        reopened = Notebook.read(book.to_bytes())
        self.assertEqual([p.template for p in reopened.pages],
            ['Logistics Checklist Move', 'Logistics Checklist Move', 'P Lines large', 'P Lines small'])
        self.assertEqual(reopened.pages[0].id, parent.id)
        self.assertEqual(reopened.pages[0].record['opaque'], dict(owner=1))
        self.assertEqual(settings(reopened, reopened.pages[1]), dict(format='move', visible=False))
        self.assertFalse(reopened.page(1).strokes)

    def test_pdf_pages_explain_template_limit_and_insert_without_copying_pdf_background(self):
        from features.notebooks.remarkable_export import export_rmdoc
        book = Notebook.read(export_rmdoc(Notebook.new(template='Logistics Checklist', paper_format='move')))
        editor = Editor(book)
        state = editor.state()
        self.assertFalse(state['template_editable'])
        self.assertIn('fixed PDF backgrounds', state['template_description'])
        before = dict(book.members)
        with self.assertRaisesRegex(ValueError, 'PDF backgrounds'):
            editor.apply(dict(op='template', name='P Lines small', format='pro', visible=True))
        self.assertEqual(book.members, before)
        editor.apply(dict(op='add-page'))
        self.assertEqual(book.pages[1].template, 'Blank')
        self.assertEqual(book.pages[1].record['redir']['value'], -1)
        self.assertFalse(book.page(1).strokes)
