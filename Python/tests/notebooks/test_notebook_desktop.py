"""Desktop feature catalog, launcher dispatch and retired-canvas event isolation."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from features import notebooks
from features.feature_runtime import FeatureRegistry


class NotebookDesktopTests(unittest.TestCase):
    def test_feature_contributes_document_launcher_and_browser_activation(self):
        runtime = FeatureRegistry(feature_loader=lambda: [notebooks])
        self.assertEqual(runtime.get_pages(), [])
        launcher, = runtime.get_document_launchers()
        self.assertEqual(launcher.contribution.editor_id, 'rmdoc')
        self.assertIs(launcher.contribution.new_document, notebooks.new_document)
        self.assertEqual(len(runtime.get_browser_extensions()), 1)
        self.assertEqual(notebooks.register().file_types[0].extensions, ('rmdoc',))

    def test_new_creates_notebook_and_open_launches_file_picker(self):
        from desktop.navigation.catalog import document_launchers, launch_document
        runtime = FeatureRegistry(feature_loader=lambda: [notebooks])
        launchers = document_launchers(runtime)
        window = Mock()
        with patch('services.documents.ui.notebooks.choose_notebook_document', return_value=window) as opening:
            self.assertIs(launch_document(launchers, 'rmdoc', None), window)
            opening.assert_called_once_with(None)
        with patch('services.documents.ui.notebooks.new_notebook_document', return_value=window) as create:
            self.assertIs(launch_document(launchers, 'rmdoc', None, new=True), window)
            create.assert_called_once_with(None)

    def test_retired_canvas_cannot_edit_replacement_notebook_or_library(self):
        from features.notebooks.ui.workspace import NotebookWorkspace
        old, current = object(), object()
        owner = NS(web=NS(page=lambda: current), perform=Mock())
        NotebookWorkspace.deliver(owner, old, dict(op='delete-page'))
        owner.perform.assert_not_called()
        NotebookWorkspace.deliver(owner, current, dict(op='undo'))
        owner.perform.assert_called_once_with(dict(op='undo'))
        owner.perform.reset_mock()
        owner.web = None
        NotebookWorkspace.deliver(owner, current, dict(op='delete-page'))
        owner.perform.assert_not_called()

    def test_new_opens_editable_draft_without_choosing_storage(self):
        from features.notebooks.workspace import Editor
        window = Mock()
        with patch('features.notebooks.ui.workspace.open_workspace', return_value=window) as open_workspace, \
                patch('services.documents.ui.editors.choose_editor_resource') as choose:
            self.assertIs(notebooks.new_document(), window)
        choose.assert_not_called()
        document = open_workspace.call_args.kwargs['document']
        self.assertIsNone(document.resource)
        self.assertIsNone(document.recovery)
        self.assertFalse(document.dirty)
        editor = Editor(document.book, document.checkpoint)
        editor.apply(dict(op='stroke', points=[[20, 30, .5], [40, 50, .5]], tool=17, width=2))
        self.assertEqual(len(document.book.page(0).strokes), 1)
        self.assertTrue(document.dirty)

    def test_first_save_cancel_keeps_draft_and_close_protects_edits(self):
        from features.notebooks.notebook import Notebook
        from features.notebooks.storage import NotebookDocument
        from features.notebooks.workspace import Editor
        from features.notebooks.ui.workspace import NotebookWorkspace, NotebookWindow
        from commonUtils.ui import pyside as qt
        document = NotebookDocument(Notebook.new())
        editor = Editor(document.book, document.checkpoint)
        editor.apply(dict(op='rename', name='Draft'))
        panel = NS(document=document, editor=editor, busy=False, web=Mock(), state=editor.state,
                   dispose=Mock())
        with patch('services.documents.ui.editors.choose_editor_resource', return_value=None) as choose:
            self.assertFalse(NotebookWorkspace.save_document(panel))
        self.assertEqual(choose.call_args.args[1], 'save')
        self.assertEqual(document.book.name, 'Draft')
        self.assertTrue(document.dirty)
        event = Mock()
        window = NS(centralWidget=lambda: panel)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel) as prompt:
            NotebookWindow.closeEvent(window, event)
        prompt.assert_called_once()
        event.ignore.assert_called_once()
        panel.dispose.assert_not_called()

    def test_untouched_new_draft_closes_without_save_prompt(self):
        from features.notebooks.notebook import Notebook
        from features.notebooks.storage import NotebookDocument
        from features.notebooks.ui.workspace import NotebookWindow
        from commonUtils.ui import pyside as qt
        panel = NS(document=NotebookDocument(Notebook.new()), busy=False, dispose=Mock())
        event = Mock()
        with patch.object(qt.QMessageBox, 'question') as prompt:
            NotebookWindow.closeEvent(NS(centralWidget=lambda: panel), event)
        prompt.assert_not_called()
        panel.dispose.assert_called_once()
        event.accept.assert_called_once()
