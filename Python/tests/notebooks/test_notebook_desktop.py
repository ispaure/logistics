"""Desktop feature catalog, launcher dispatch and retired-canvas event isolation."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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

    def test_save_completion_from_retired_canvas_closes_result_without_retargeting(self):
        from features.notebooks.bridge import Bridge
        from features.notebooks.ui.workspace import NotebookWorkspace
        old = Bridge()
        old.retire()
        current = Bridge()
        previous, result = Mock(), Mock()
        choice = Mock()
        owner = NS(_pending_choice=choice, _pending_canvas=old, bridge=current,
                   _pending_operation=Mock(), document=previous, busy=True)
        NotebookWorkspace.saved(owner, result, '')
        choice.close.assert_called_once()
        result.close.assert_called_once()
        previous.close.assert_not_called()
        self.assertIs(owner.document, previous)
        self.assertFalse(owner.busy)

    def test_new_opens_editable_draft_without_choosing_storage(self):
        from features.notebooks.editor import Editor
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
        from features.notebooks.editor import Editor
        from features.notebooks.ui.workspace import NotebookWorkspace, NotebookWindow
        from commonUtils.ui import pyside as qt
        document = NotebookDocument(Notebook.new())
        editor = Editor(document.book, document.checkpoint)
        editor.apply(dict(op='rename', name='Draft'))
        from features.notebooks.bridge import Bridge
        panel = NS(document=document, editor=editor, bridge=Bridge(), busy=False, web=Mock(), state=editor.state,
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


class NotebookMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from commonUtils.ui import pyside as qt
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def owner(self, *, index=0, count=1, undo=False):
        from commonUtils.ui import pyside as qt
        from features.notebooks.ui.menus import NotebookMenus
        window = qt.QMainWindow()
        panel = qt.QWidget()
        panel.editor = NS(index=index)
        panel.busy = False
        panel.web = None
        panel.request_command = Mock()
        panel.request_ui = Mock()
        panel.state = lambda: dict(index=index, count=count, undo=undo, redo=False)
        window.setCentralWidget(panel)
        window.notebook_menus = NotebookMenus(window)
        window.notebook_menus.refresh()
        self.addCleanup(window.deleteLater)
        return window

    def test_standard_shortcuts_page_bounds_and_disabled_history(self):
        from commonUtils.ui import pyside as qt
        window = self.owner()
        menus = window.notebook_menus
        for name, key in [('save', qt.QKeySequence.StandardKey.Save),
                          ('save-as', qt.QKeySequence.StandardKey.SaveAs),
                          ('undo', qt.QKeySequence.StandardKey.Undo),
                          ('redo', qt.QKeySequence.StandardKey.Redo)]:
            self.assertEqual(menus.actions[name].shortcut(), qt.QKeySequence(key))
            self.assertEqual(menus.actions[name].shortcutContext(), qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        for name in ('undo', 'redo', 'prev', 'next', 'delete-page', 'move-earlier', 'move-later'):
            self.assertFalse(menus.actions[name].isEnabled(), name)
        menus.actions['save-as'].trigger()
        window.centralWidget().request_command.assert_called_once_with({'op': 'save-as'})

    def test_host_publishes_active_notebook_menus_and_dispatches_to_its_owner(self):
        from commonUtils.ui import pyside as qt
        from commonUtils.ui.workspaces.workspace_menus import sync_native_menus
        first, second = self.owner(count=2, undo=True), self.owner(index=1, count=2)
        host = qt.QMainWindow()
        host.workspace_publish_menus = True
        self.addCleanup(host.deleteLater)
        for window in (first, second):
            sync_native_menus(host, window)
            self.assertEqual([action.text() for action in host.menuBar().actions()], ['File', 'Edit', 'View', 'Page'])
            self.assertIs(host.menuBar().actions()[0], window.notebook_menus.menus['File'].menuAction())
            window.notebook_menus.actions['save'].trigger()
        first.centralWidget().request_command.assert_called_once_with({'op': 'save'})
        second.centralWidget().request_command.assert_called_once_with({'op': 'save'})
        second.notebook_menus.actions['prev'].trigger()
        second.centralWidget().request_command.assert_called_with({'op': 'page', 'index': 0})
        self.assertFalse(second.notebook_menus.actions['next'].isEnabled())
        second.notebook_menus.actions['toolbar'].trigger()
        second.centralWidget().request_ui.assert_called_once_with('toolbar', None)

    def test_zoom_actions_use_platform_shortcuts_and_dispatch_to_canvas(self):
        from commonUtils.ui import pyside as qt
        window = self.owner()
        menus = window.notebook_menus
        self.assertIn(qt.QKeySequence('Ctrl+='), menus.actions['zoom-in'].shortcuts())
        self.assertIn(qt.QKeySequence(qt.QKeySequence.StandardKey.ZoomIn), menus.actions['zoom-in'].shortcuts())
        self.assertEqual(menus.actions['zoom-out'].shortcut(), qt.QKeySequence(qt.QKeySequence.StandardKey.ZoomOut))
        self.assertEqual(menus.actions['fit-page'].shortcut(), qt.QKeySequence('Ctrl+0'))
        for name, expected in [('zoom-in', ('zoom-in', None)), ('zoom-out', ('zoom-out', None)),
                               ('fit-page', ('zoom', 'page'))]:
            menus.actions[name].trigger()
            window.centralWidget().request_ui.assert_called_with(*expected)


class NotebookAcknowledgementTests(unittest.TestCase):
    def test_stroke_delta_avoids_full_state_but_failure_resynchronizes(self):
        from features.notebooks.notebook import Notebook
        from features.notebooks.editor import Editor
        from features.notebooks.ui.workspace import NotebookWorkspace
        editor = Editor(Notebook.new())
        owner = NS(busy=False, editor=editor, document_window=None, web=Mock(),
                   state=Mock(side_effect=editor.state), acknowledge_stroke=Mock())
        action = dict(op='stroke', points=[[20, 30, .5], [40, 50, .7]], tool=17, width=2)
        NotebookWorkspace.perform(owner, action)
        owner.acknowledge_stroke.assert_called_once_with()
        owner.state.assert_not_called()
        self.assertEqual(len(editor.notebook.page(0).strokes), 1)
        owner.acknowledge_stroke.reset_mock()
        NotebookWorkspace.perform(owner, dict(action, width=999))
        owner.acknowledge_stroke.assert_not_called()
        owner.state.assert_called_once_with()
        self.assertEqual(len(editor.notebook.page(0).strokes), 1)
        self.assertIn('Unsupported', owner.web.page.return_value.runJavaScript.call_args.args[0])
        self.assertFalse(owner.busy)
