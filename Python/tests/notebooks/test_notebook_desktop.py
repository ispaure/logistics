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
        from features.notebooks.notebook import Notebook
        window = Mock()
        with patch('features.notebooks.ui.workspace.open_workspace', return_value=window) as open_workspace, \
                patch('services.documents.ui.editors.choose_editor_resource') as choose, \
                patch('features.notebooks.ui.setup.choose_new_notebook', return_value=Notebook.new()):
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

    def test_discard_closes_only_after_resetting_the_observed_recovery_draft(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from commonUtils.ui import pyside as qt
        from features.notebooks.editor import Editor
        from features.notebooks.notebook import Notebook, MAX_ARCHIVE
        from features.notebooks.recovery import Repository
        from features.notebooks.storage import NotebookDocument
        from features.notebooks.ui.workspace import NotebookWindow
        from services.documents.storage import local_document_resource

        for conflict in (False, True):
            with self.subTest(conflict=conflict), TemporaryDirectory() as directory:
                path = Path(directory) / 'Saved.rmdoc'
                saved = Notebook.new('Saved').to_bytes()
                path.write_bytes(saved)
                repository = Repository(Path(directory) / 'recovery')
                unrelated = repository.create(Notebook.new('Unrelated'))
                with local_document_resource(path, max_bytes=MAX_ARCHIVE) as resource:
                    document = NotebookDocument(Notebook.read(resource.read()), resource=resource, recovery=repository)
                    editor = Editor(document.book, document.checkpoint)
                    editor.apply(dict(op='rename', name='Draft'))
                    if conflict:
                        newer = repository.open(document.key)
                        Editor(newer, lambda book: repository.save(document.key, book)).apply(
                            dict(op='rename', name='Other window'))
                    panel = NS(document=document, editor=editor, busy=False, dispose=Mock())
                    window = NS(centralWidget=lambda: panel)
                    event = Mock()
                    with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard), \
                            patch.object(qt.QMessageBox, 'warning') as warning:
                        NotebookWindow.closeEvent(window, event)
                    self.assertEqual(path.read_bytes(), saved)
                    self.assertEqual(repository.open(unrelated).name, 'Unrelated')
                    if conflict:
                        event.ignore.assert_called_once()
                        event.accept.assert_not_called()
                        panel.dispose.assert_not_called()
                        warning.assert_called_once()
                        self.assertIn('another window', warning.call_args.args[2])
                        self.assertTrue(document.dirty)
                        self.assertEqual(editor.notebook.name, 'Draft')
                        self.assertEqual(repository.open(document.key).name, 'Other window')
                    else:
                        event.accept.assert_called_once()
                        event.ignore.assert_not_called()
                        panel.dispose.assert_called_once()
                        warning.assert_not_called()
                        self.assertFalse(document.dirty)
                        self.assertEqual(repository.open(document.key).name, 'Saved')

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

    def test_unconfirmed_library_checkpoint_blocks_close_and_navigation(self):
        from features.notebooks.ui.workspace import NotebookWorkspace, NotebookWindow
        from commonUtils.ui import pyside as qt
        panel = NS(document=None, editor=NS(checkpoint_unconfirmed=True), busy=False, dispose=Mock())
        event = Mock()
        with patch.object(qt.QMessageBox, 'warning') as warning:
            NotebookWindow.closeEvent(NS(centralWidget=lambda: panel), event)
            self.assertFalse(NotebookWorkspace.can_leave(panel))
        self.assertEqual(warning.call_count, 2)
        event.ignore.assert_called_once()
        panel.dispose.assert_not_called()
        panel.editor.checkpoint_unconfirmed = False
        self.assertTrue(NotebookWorkspace.can_leave(panel))


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
    def test_rejected_bridge_commands_acknowledge_without_changing_recovery_or_history(self):
        from copy import deepcopy
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from urllib.parse import quote
        from features.notebooks.bridge import Bridge
        from features.notebooks.editor import Editor
        from features.notebooks.notebook import Notebook, read_archive
        from features.notebooks.protocol import document_state
        from features.notebooks.recovery import Repository
        from features.notebooks.storage import NotebookDocument
        from features.notebooks.ui.workspace import NotebookWorkspace

        with TemporaryDirectory() as directory, patch('features.notebooks.notebook.time.time', return_value=1234567890):
            original = Notebook.new('Imported notebook')
            original.metadata['opaque'] = {'source': 'synthetic', 'version': 17}
            original.members['unknown/sidecar.bin'] = b'synthetic opaque bytes'
            book = Notebook.read(original.to_bytes())
            repository = Repository(directory)
            document = NotebookDocument(book, recovery=repository)
            editor = Editor(book, document.checkpoint)
            for x in (20, 40):
                editor.apply(dict(op='stroke', points=[[x, 30, .5]]))
            editor.apply(dict(op='undo'))
            owner = NS(busy=False, editor=editor, document_window=None, web=Mock(), progress=None,
                       state=lambda: document_state(editor, document),
                       acknowledge_stroke=Mock(), save_document=Mock(), export_document=Mock())
            bridge = Bridge()
            recovery_path = Path(directory, document.key)
            recovery_before = {path.name: path.read_bytes() for path in recovery_path.iterdir()}
            archive_before = read_archive(book.to_bytes())
            state_before = deepcopy(owner.state())
            history_before = (list(editor.undo), list(editor.redo))
            revision_before = dict(repository.revisions[book])
            dirty_before = document.dirty
            actions = [dict(op='unknown'), dict(op='page', index=True), dict(op='rename', name=[]),
                       dict(op='stroke', points='invalid'), dict(op='stroke', points=[[20, 30, .5]], width=999)]
            for sequence, action in enumerate(actions, 1):
                with self.subTest(action=action):
                    accepted = bridge.command(bridge.url + '?command=' + quote(json.dumps(
                        dict(sequence=sequence, action=action))))
                    self.assertEqual(accepted, action)
                    owner.web.page.return_value.runJavaScript.reset_mock()
                    NotebookWorkspace.perform(owner, accepted)
                    owner.web.page.return_value.runJavaScript.assert_called_once()
                    script = owner.web.page.return_value.runJavaScript.call_args.args[0]
                    self.assertTrue(script.startswith('window.notebookUpdate('))
                    state, error = json.loads('[' + script[len('window.notebookUpdate('):-1] + ']')
                    self.assertTrue(error)
                    self.assertEqual(state, json.loads(json.dumps(state_before)))
                    self.assertEqual(read_archive(book.to_bytes()), archive_before)
                    self.assertEqual({path.name: path.read_bytes() for path in recovery_path.iterdir()}, recovery_before)
                    self.assertEqual(repository.revisions[book], revision_before)
                    self.assertEqual((editor.undo, editor.redo), history_before)
                    self.assertEqual(document.dirty, dirty_before)
                    self.assertFalse(owner.busy)
            owner.save_document.assert_not_called()
            owner.export_document.assert_not_called()
            owner.acknowledge_stroke.assert_not_called()
            action = bridge.command(bridge.url + '?command=' + quote(json.dumps(
                dict(sequence=len(actions) + 1, action=dict(op='rename', name='Still editable')))))
            NotebookWorkspace.perform(owner, action)
            self.assertEqual(repository.open(document.key).name, 'Still editable')
            self.assertEqual(book.members['unknown/sidecar.bin'], b'synthetic opaque bytes')
            self.assertEqual(book.metadata['opaque'], original.metadata['opaque'])

    def test_save_and_export_keep_worker_busy_ownership_until_completion(self):
        from features.notebooks.ui.workspace import NotebookWorkspace
        for op in ('save', 'save-as', 'export'):
            with self.subTest(op=op):
                owner = NS(busy=False, web=Mock(), state=Mock())
                def start(*args, **kwargs):
                    self.assertFalse(owner.busy)
                    owner.busy = True
                owner.save_document = Mock(side_effect=start)
                owner.export_document = Mock(side_effect=start)
                NotebookWorkspace.perform(owner, dict(op=op))
                if op == 'export':
                    owner.export_document.assert_called_once_with()
                    owner.save_document.assert_not_called()
                else:
                    owner.save_document.assert_called_once_with(save_as=op == 'save-as')
                    owner.export_document.assert_not_called()
                self.assertTrue(owner.busy)
                owner.web.page.assert_not_called()
                owner.state.assert_not_called()

    def test_stroke_delta_avoids_full_state_but_failure_resynchronizes(self):
        from features.notebooks.notebook import Notebook
        from features.notebooks.editor import Editor
        from features.notebooks.ui.workspace import NotebookWorkspace
        editor = Editor(Notebook.new())
        owner = NS(busy=False, editor=editor, document_window=None, web=Mock(), progress=None,
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
