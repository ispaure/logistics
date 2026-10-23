import tempfile
import unittest
from pathlib import Path
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.persistence.text import read_text_file, FileConflictError
from features.ide.ui.documents import EditorDocument


class IDEQtTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        from commonUtils.ui import pyside as qt
        cls.app = qt.QApplication.instance() or qt.QApplication([])


class DocumentTests(IDEQtTests):
    def test_theme_switch_preserves_unsaved_shared_buffer_and_finishes_highlighting(self):
        import io
        from contextlib import redirect_stderr
        from commonUtils.ui import pyside as qt
        from commonUtils.ui.appearance.theme import apply_theme
        with self.temporary_directory() as directory:
            path = Path(directory) / 'example.py'
            path.write_text('x = 1\n' * 1000)
            editor = EditorDocument(read_text_file(path))
            editor.show()
            editor.moveCursor(qt.QTextCursor.MoveOperation.End)
            editor.insertPlainText('# unsaved\n')
            original = editor.toPlainText()
            font = qt.QFont(editor.font())
            theme = apply_theme(self.app, mode='light')
            errors = io.StringIO()
            with redirect_stderr(errors):
                for mode in ('dark', 'light', 'dark'):
                    theme.set_mode(mode)
                    self.wait_until(lambda: not editor.buffer.highlighter.theme_timer.isActive(),
                                    message='IDE palette update did not finish')
                    self.assertEqual(editor.toPlainText(), original)
                    self.assertEqual(editor.font(), font)
                    self.assertTrue(editor.document().isModified())
            self.assertNotIn('Error calling Python override', errors.getvalue())
            self.assertNotIn('IndexError', errors.getvalue())
            editor.undo()
            self.assertEqual(editor.toPlainText(), path.read_text())

    def test_shared_editor_preserves_endings_and_refuses_external_overwrite(self):
        with self.temporary_directory() as directory:
            path = Path(directory) / 'example.py'
            path.write_bytes(b'x = 1\r\n')
            editor = EditorDocument(read_text_file(path))
            editor.setPlainText('x = 2\n')
            editor.save()
            self.assertEqual(path.read_bytes(), b'x = 2\r\n')
            path.write_bytes(b'external\n')
            editor.setPlainText('mine\n')
            editor.document().setModified(True)
            with self.assertRaises(FileConflictError):
                editor.save()
            self.assertEqual(path.read_bytes(), b'external\n')
            self.assertTrue(editor.document().isModified())
            path.unlink()
            with self.assertRaises(FileConflictError):
                editor.save()
            self.assertFalse(path.exists())
            editor.close()


class ProjectTests(unittest.TestCase):
    def test_column_guide_persistence_legacy_default_and_validation(self):
        from features.ide.projects import Project, ProjectStore
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory) / 'workspace.json')
            project = Project('Example', directory, column_guide=79)
            store.projects[project.id] = project
            store.save()
            self.assertEqual(ProjectStore(store.path).projects[project.id].column_guide, 79)
            legacy = {'id': 'old', 'name': 'Old', 'root_path': directory}
            self.assertEqual(Project.from_dict(legacy).column_guide, 120)
            self.assertEqual(Project.from_dict(dict(legacy, column_guide=0)).column_guide, 0)
            for value in (-1, 1001, True, '120'):
                with self.assertRaises(ValueError):
                    Project.from_dict(dict(legacy, column_guide=value))

    def test_roundtrip_missing_root_sources_and_conflicting_instance(self):
        from features.ide.projects import Project, ProjectStore
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory) / 'IDE' / 'workspace.json')
            project = Project('Example', str(Path(directory) / 'missing'), source_paths=['.', 'src', 'src'])
            store.projects[project.id] = project
            store.open_ids = [project.id]
            store.save()
            restored = ProjectStore(store.path)
            self.assertEqual(restored.open_ids, [project.id])
            self.assertEqual(len(restored.projects[project.id].sources()), 2)
            project.python_interpreter = '.venv'
            self.assertEqual(project.environment(), str(project.root / '.venv'))
            restored.active_id = project.id
            restored.save()
            with self.assertRaises(OSError):
                store.save()

    def test_invalid_workspace_never_publishes_partially_loaded_projects(self):
        import json
        from features.ide.projects import ProjectStore
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'workspace.json'
            project = {'name': 'Example', 'root_path': directory, 'id': 'project'}
            malformed = [
                {'version': 1, 'projects': [project]},
                {'version': 1, 'projects': [project], 'open_ids': [['project']]},
                {'version': 1, 'projects': [project], 'open_ids': 'project'},
                {'version': 1, 'projects': [project], 'open_ids': [], 'active_id': []},
                {'version': 1, 'projects': [project, project], 'open_ids': []},
            ]
            for payload in malformed:
                with self.subTest(payload=payload):
                    original = json.dumps(payload).encode()
                    path.write_bytes(original)
                    store = ProjectStore(path)
                    self.assertTrue(store.error)
                    self.assertEqual(store.projects, {})
                    self.assertEqual(store.open_ids, [])
                    self.assertIsNone(store.active_id)
                    with self.assertRaises(ValueError):
                        store.save()
                    self.assertEqual(path.read_bytes(), original)

    def test_malformed_store_is_not_overwritten(self):
        from features.ide.projects import ProjectStore
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'workspace.json'
            path.write_text('{bad')
            store = ProjectStore(path)
            with self.assertRaises(ValueError):
                store.save()
            self.assertEqual(path.read_text(), '{bad')


class WorkspaceFixture(IDEQtTests):
    def wait(self, view):
        self.wait_until(lambda: not view.worker and not view.queue,
                        message='IDE workspace operation did not finish')


class WorkspaceTests(WorkspaceFixture):
    def test_file_tabs_keep_type_icons_and_neutral_close_on_right_after_reorder(self):
        from commonUtils.ui import pyside as qt
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            first, second = root / 'file.py', root / 'notes.txt'
            first.write_text('first\n'); second.write_text('second\n')
            view = ProjectWorkspace(Project('test', directory, autosave='off'))
            view.open_path(first); view.open_path(second)
            self.wait(view)
            view.resize(900, 500); view.show()
            self.app.processEvents()
            group = view.active_group
            for index in range(group.count()):
                self.assertFalse(group.tabIcon(index).isNull())
                self.assertIsNone(group.tabBar().tabButton(index, qt.QTabBar.ButtonPosition.LeftSide))
                button = group.tabBar().tabButton(index, qt.QTabBar.ButtonPosition.RightSide)
                self.assertIsInstance(button, qt.QToolButton)
                self.assertFalse(button.icon().isNull())
                self.assertEqual(button.text(), '')
            original = group.widget(0).path
            button = group.tabBar().tabButton(0, qt.QTabBar.ButtonPosition.RightSide)
            group.tabBar().moveTab(0, 1)
            self.app.processEvents()
            button.click()
            self.assertNotIn(original, view.documents)
            self.assertEqual(group.count(), 1)

    def test_rename_open_modified_and_untracked_files_preserves_buffers_and_saves_to_new_paths(self):
        import subprocess
        from commonUtils.ui import pyside as qt
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'tracked.py'
            path.write_text('original\n')
            def git(*args):
                subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git('init'); git('add', 'tracked.py')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'initial')
            folder = root / 'folder'
            folder.mkdir()
            new_file = folder / 'new.py'
            new_file.write_text('new\n')
            view = ProjectWorkspace(Project('test', directory, autosave='off'))
            view.open_path(path)
            self.wait(view)
            first = view.current
            view.split_right()
            self.wait(view)
            first.insertPlainText('edited ')
            buffer = first.buffer
            position = first.textCursor().position()
            index = view.browser.proxy.mapFromSource(view.browser.model.index(str(path)))
            self.assertTrue(view.browser.proxy.flags(index) & qt.Qt.ItemFlag.ItemIsEditable)
            self.assertTrue(view.browser.proxy.setData(index, 'renamed.py'))
            renamed = root / 'renamed.py'
            self.assertIs(view.documents[renamed].buffer, buffer)
            self.assertEqual(first.textCursor().position(), position)
            self.assertTrue(buffer.text.isUndoAvailable())
            self.assertTrue(buffer.text.isModified())
            for editor in buffer.views:
                self.assertEqual(editor.path, renamed)
                self.assertEqual(editor.toPlainText(), 'edited original\n')
            self.assertNotIn(path, view.documents)
            self.assertIn(str(renamed), view.watch.files())
            self.assertTrue(view.save_document(first))
            self.assertEqual(renamed.read_text(), 'edited original\n')
            self.assertFalse(path.exists())
            first.undo()
            self.assertEqual(first.toPlainText(), 'original\n')
            view.open_path(new_file)
            self.wait(view)
            untracked = view.current
            untracked.insertPlainText('unsaved ')
            index = view.browser.proxy.mapFromSource(view.browser.model.index(str(new_file)))
            self.assertTrue(view.browser.proxy.setData(index, 'new_name.py'))
            self.assertEqual(untracked.path, folder / 'new_name.py')
            self.assertTrue(untracked.document().isModified())
            folder_index = view.browser.proxy.mapFromSource(view.browser.model.index(str(folder)))
            self.assertTrue(view.browser.proxy.setData(folder_index, 'renamed_folder'))
            self.assertEqual(untracked.path, root / 'renamed_folder' / 'new_name.py')
            self.assertTrue(view.save_document(untracked))
            self.assertEqual(untracked.path.read_text(), 'unsaved new\n')
            self.assertFalse(folder.exists())

    def test_unsaved_filename_color_undo_and_save_in_non_git_project(self):
        from commonUtils.ui import pyside as qt
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'file.py'
            path.write_text('original\n')
            view = ProjectWorkspace(Project('test', directory, autosave='off'))
            view.open_path(path)
            self.wait(view)
            editor = view.current
            editor.insertPlainText('edited ')
            index = view.browser.proxy.mapFromSource(view.browser.model.index(str(path)))
            self.assertEqual(view.browser.proxy.data(index, qt.Qt.ItemDataRole.ForegroundRole).color().name(), '#408bd6')
            self.assertIn('Unsaved changes', view.browser.proxy.data(index, qt.Qt.ItemDataRole.ToolTipRole))
            self.assertEqual(view.browser.proxy.data(index), 'file.py')
            source = view.browser.proxy.mapToSource(index)
            self.assertEqual(view.browser.proxy.data(index, qt.Qt.ItemDataRole.DecorationRole).cacheKey(),
                             view.browser.model.data(source, qt.Qt.ItemDataRole.DecorationRole).cacheKey())
            editor.undo()
            self.assertNotIn(path, view.browser.proxy.unsaved_paths)
            editor.insertPlainText('saved ')
            self.assertTrue(view.save_document(editor))
            self.assertNotIn(path, view.browser.proxy.unsaved_paths)

    def test_project_settings_updates_guide_in_existing_and_split_editors(self):
        from unittest.mock import patch
        from commonUtils.ui import pyside as qt
        from features.ide.ui.page import IDEPage
        from features.ide.projects import Project
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'file.py'
            path.write_text('original\n')
            page = IDEPage(store_path=root / 'workspace.json')
            project = Project('test', directory)
            page.store.projects[project.id] = project
            view = page.open_project(project)
            view.open_path(path)
            self.wait(view)
            self.assertEqual(view.current.column_guide, 120)
            view.split_right()
            self.wait(view)
            def accept(dialog):
                dialog.findChild(qt.QSpinBox).setValue(79)
                return qt.QDialog.DialogCode.Accepted
            with patch.object(qt.QDialog, 'exec', accept):
                page.settings(view)
            self.assertEqual(project.column_guide, 79)
            for editor in view.views():
                self.assertEqual(editor.column_guide, 79)
                self.assertFalse(editor.document().isModified())
                self.assertEqual(editor.toPlainText(), 'original\n')

    def test_navigation_applies_unicode_location_to_requested_view(self):
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            a, b = root / 'a.py', root / 'b.py'
            a.write_text('header\n😀target\n')
            b.write_text('other\n')
            view = ProjectWorkspace(Project('test', directory))
            self.wait(view)
            first = view.active_group
            second = view.add_group()
            view.navigate_to(a, group=first, line=2, column=1)
            view.navigate_to(b, group=second, position=3)
            self.wait(view)
            left, right = first.widget(0), second.widget(0)
            self.assertEqual(left.textCursor().position(), 9)
            self.assertEqual(right.textCursor().position(), 3)
            view.place_view(left, position=10000)
            self.assertEqual(left.textCursor().position(), left.document().characterCount() - 1)
            view.place_view(left, position=-10)
            self.assertEqual(left.textCursor().position(), 0)
            view.prepare_close()
            view.close()

    def test_history_and_analysis_use_the_selected_shared_view(self):
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        from unittest.mock import patch
        with self.temporary_directory() as directory:
            path = Path(directory).resolve() / 'a.py'
            path.write_text('value = 1\n' * 30)
            view = ProjectWorkspace(Project('test', directory))
            view.show()
            view.open_path(path)
            self.wait(view)
            left = view.current
            view.split_right()
            right = view.current
            view.activate(view.group_for(left))
            view.remember()
            view.activate(view.group_for(right))
            cursor = right.textCursor()
            cursor.setPosition(30)
            right.setTextCursor(cursor)
            view.travel(-1)
            self.wait(view)
            self.assertIs(view.current, left)
            view.travel(1)
            self.wait(view)
            self.assertIs(view.current, right)
            pending = []
            with patch.object(view, 'run', side_effect=lambda work, done: pending.append(done)):
                view.query('definition')
            pending[0]([(str(path), 20, 0, 'value')])
            self.wait(view)
            self.assertEqual(right.textCursor().blockNumber(), 19)
            self.assertEqual(left.textCursor().blockNumber(), 0)
            view.prepare_close()
            view.close()

    def test_split_views_share_edits_undo_save_and_survive_original_close(self):
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        from unittest.mock import patch
        from commonUtils.ui import pyside as qt
        with self.temporary_directory() as directory:
            path = Path(directory).resolve() / 'a.py'
            path.write_bytes(b'value = 1\r\nsecond = 2\r\n')
            view = ProjectWorkspace(Project('test', directory))
            view.open_path(path)
            self.wait(view)
            left = view.current
            view.split_right()
            right = view.current
            self.assertIsNot(left, right)
            self.assertIs(left.document(), right.document())
            self.assertEqual(len(view.documents), 1)
            cursor = right.textCursor()
            cursor.setPosition(10)
            right.setTextCursor(cursor)
            self.assertEqual(left.textCursor().position(), 0)
            left.insertPlainText('# left\n')
            self.assertEqual(right.toPlainText(), left.toPlainText())
            right.insertPlainText('# right')
            self.assertEqual(right.toPlainText(), left.toPlainText())
            right.undo()
            self.assertNotIn('# right', left.toPlainText())
            left.redo()
            self.assertIn('# right', right.toPlainText())
            for group in view.groups:
                self.assertTrue(group.tabText(0).endswith(' *'))
            with patch.object(qt.QMessageBox, 'question') as prompt:
                self.assertTrue(view.close_document(left))
                prompt.assert_not_called()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            self.app.processEvents()
            right.insertPlainText('more')
            self.assertTrue(view.save_document(right))
            self.assertIn(b'\r\n', path.read_bytes())
            self.assertFalse(right.document().isModified())
            right.insertPlainText('unsaved')
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel) as prompt:
                self.assertFalse(view.close_document(right))
                self.assertEqual(prompt.call_count, 1)
            right.document().setModified(False)
            view.prepare_close()
            view.close()

    def test_shared_save_as_reload_merge_and_single_close_prompt(self):
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        from unittest.mock import patch
        from commonUtils.ui import pyside as qt
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            source, target = root / 'a.py', root / 'b.js'
            source.write_text('value = 1\n')
            view = ProjectWorkspace(Project('test', directory))
            view.open_path(source)
            self.wait(view)
            left = view.current
            view.split_right()
            right = view.current
            right.insertPlainText('# edit\n')
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard) as prompt:
                self.assertTrue(view.can_close())
                self.assertEqual(prompt.call_count, 1)
            with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
                self.assertTrue(view.save_document(right, True))
            self.assertEqual(left.path, target)
            self.assertEqual(right.path, target)
            self.assertEqual(left.comment_prefix, '//')
            self.assertEqual(right.comment_prefix, '//')
            self.assertEqual(set(view.documents), {target})
            target.write_text('external\n')
            right.insertPlainText('mine')
            self.assertFalse(view.save_document(left))
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
                view.reload_current()
            self.assertEqual(left.toPlainText(), 'external\n')
            self.assertEqual(right.toPlainText(), 'external\n')
            right.insertPlainText('retained')
            view.move(-1)
            self.assertEqual(len(view.views()), 1)
            self.assertIs(view.current, left)
            view.split_right()
            with patch.object(qt.QMessageBox, 'question') as prompt:
                view.close_group()
                prompt.assert_not_called()
            # Moving the last file prunes its empty source column; merging
            # duplicate views still preserves the shared buffer.
            view.close_group()
            self.assertEqual(len(view.groups), 1)
            self.assertEqual(view.groups[0].count(), 1)
            self.assertIn('retained', view.current.toPlainText())
            view.current.document().setModified(False)
            self.wait(view)
            view.prepare_close()
            view.close()

    def test_same_file_views_restore_independent_positions(self):
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        with self.temporary_directory() as directory:
            path = Path(directory).resolve() / 'a.py'
            path.write_text('value = 1\n' * 300)
            project = Project('test', directory)
            view = ProjectWorkspace(project)
            view.resize(1000, 500)
            view.show()
            view.open_path(path)
            self.wait(view)
            left = view.current
            view.split_right()
            right = view.current
            self.app.processEvents()
            cursor = right.textCursor()
            cursor.setPosition(800)
            right.setTextCursor(cursor)
            left.verticalScrollBar().setValue(2)
            right.verticalScrollBar().setValue(90)
            self.assertNotEqual(left.verticalScrollBar().value(), right.verticalScrollBar().value())
            project.layout = view.state()
            view.prepare_close()
            view.close()
            restored = ProjectWorkspace(project)
            restored.resize(1000, 500)
            restored.show()
            self.wait(restored)
            left, right = (group.widget(0) for group in restored.groups)
            self.assertIs(left.document(), right.document())
            self.assertEqual(left.textCursor().position(), 0)
            self.assertEqual(right.textCursor().position(), 800)
            self.assertEqual(left.verticalScrollBar().value(), 2)
            self.assertEqual(right.verticalScrollBar().value(), 90)
            self.assertIs(restored.current, right)
            restored.prepare_close()
            restored.close()

    def test_pending_open_blocks_browser_mutation_and_callback_failure_drains_queue(self):
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        from unittest.mock import patch
        from commonUtils.ui import pyside as qt
        with self.temporary_directory() as directory:
            path = Path(directory).resolve() / 'a.py'
            path.write_text('value = 1\n')
            view = ProjectWorkspace(Project('test', directory))
            self.wait(view)
            view.open_path(path)
            with patch.object(qt.QMessageBox, 'question') as question, patch.object(qt.QInputDialog, 'getText') as prompt:
                view.browser.delete(path)
                view.browser.rename(path)
                question.assert_not_called()
                prompt.assert_not_called()
            self.assertTrue(path.exists())
            self.wait(view)
            self.assertFalse(view.pending_opens)
            def broken(_):
                raise ValueError('completion failed')
            completed = []
            view.run(lambda: None, broken)
            view.run(lambda: None, lambda _: completed.append(True))
            self.wait(view)
            self.assertEqual(completed, [True])
            self.assertIn('completion failed', view.status.text())
            view.prepare_close()
            view.close()

    def test_navigation_branch_replaces_forward_history(self):
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            paths = [root / f'{name}.py' for name in 'abcd']
            for path in paths:
                path.write_text('value = 1\n')
            view = ProjectWorkspace(Project('test', directory))
            view.open_path(paths[0])
            self.wait(view)
            for path in paths[1:3]:
                view.remember()
                view.open_path(path)
                self.wait(view)
            view.travel(-1)
            self.wait(view)
            self.assertEqual(view.current.path, paths[1])
            view.remember()
            view.open_path(paths[3])
            self.wait(view)
            view.travel(-1)
            self.wait(view)
            self.assertEqual(view.current.path, paths[1])
            view.travel(1)
            self.wait(view)
            self.assertEqual(view.current.path, paths[3])
            self.assertNotIn(str(paths[2]), [entry[0] for entry in view.history])
            view.prepare_close()
            view.close()

    def test_missing_files_retain_group_cursor_and_browser_state(self):
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        from unittest.mock import patch
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'offline' / 'a.py'
            browser = {'expanded': [str(path.parent)], 'selected': str(path)}
            project = Project('test', directory, excluded_paths=['.'], layout={
                'browser': browser, 'groups': [{}, {'files': [{'path': str(path), 'cursor': 5}]}]})
            view = ProjectWorkspace(project)
            self.wait(view)
            self.assertTrue(view.browser.tree.rootIndex().isValid())
            state = view.state()
            self.assertEqual(state['unavailable'][0]['group'], 1)
            self.assertEqual(state['browser']['expanded'], browser['expanded'])
            self.assertEqual(state['browser']['selected'], browser['selected'])
            view.prepare_close()
            view.close()
            path.parent.mkdir()
            path.write_text('value = 1\n')
            project.layout = state
            restored = ProjectWorkspace(project)
            self.wait(restored)
            self.assertEqual(restored.groups[1].widget(0).path, path)
            self.assertEqual(restored.groups[1].widget(0).textCursor().position(), 5)
            with patch('features.ide.ui.browser.desktop_actions.reveal') as reveal:
                restored.browser.reveal(path)
                reveal.assert_called_once_with(path)
            restored.prepare_close()
            restored.close()

    def test_canonical_buffer_moves_and_group_close_preserves_unsaved_text(self):
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        from unittest.mock import patch
        from commonUtils.ui import pyside as qt
        with self.temporary_directory() as directory:
            path = Path(directory) / 'a.py'
            path.write_text('value = 1\n')
            view = ProjectWorkspace(Project('one', directory))
            view.open_path(path)
            self.wait(view)
            doc = view.current
            doc.insertPlainText('# changed\n')
            view.move(1)
            view.open_path(path)
            self.wait(view)
            self.assertEqual(len(view.documents), 1)
            self.assertIs(view.current, doc)
            view.close_group()
            self.assertEqual(len(view.groups), 1)
            self.assertTrue(doc.document().isModified())
            view.add_group()
            view.add_group()
            self.assertIsNone(view.add_group())
            self.assertEqual(len(view.groups), 3)
            view.activate(view.group_for(doc))
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(view.can_close())
                self.assertFalse(view.close_document(doc))
            self.assertTrue(view.save_document(doc))
            self.assertTrue(view.can_close())
            self.assertTrue(view.prepare_close())
            view.close()


class NavigationTests(unittest.TestCase):
    def test_import_definition_with_src_layout_and_relative_import(self):
        from features.ide.projects import Project
        from features.ide.analysis import analyze, project_files
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'src' / 'sample'
            package.mkdir(parents=True)
            (package / '__init__.py').write_text('')
            (package / 'models.py').write_text('class Widget:\n    pass\n')
            path = package / 'main.py'
            code = 'from .models import Widget\nvalue = Widget()\n'
            path.write_text(code)
            project = Project('Example', directory, source_paths=['src'])
            result = analyze(project, path, code, 2, 10)
            self.assertEqual(result[0][:2], (str(package / 'models.py'), 1))
            code = 'from sample.models import Widget\nvalue = Widget()\n'
            self.assertEqual(Path(analyze(project, root / 'test.py', code, 2, 10)[0][0]).resolve(), (package / 'models.py').resolve())
            (root / '.venv').mkdir()
            (root / '.venv' / 'hidden.py').write_text('')
            self.assertFalse(any('.venv' in p for p in project_files(project)))

    def test_project_search_skips_binary_exclusions_and_supports_cancellation(self):
        from features.ide.projects import Project
        from features.ide.analysis import search_project
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('needle\n')
            (root / 'binary').write_bytes(b'needle\x00')
            (root / '.git').mkdir()
            (root / '.git' / 'secret').write_text('needle')
            project = Project('test', directory)
            results = search_project(project, 'NEEDLE')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][1], 1)
            self.assertEqual(search_project(project, 'needle', cancelled=lambda: True), [])


class RestoreTests(WorkspaceFixture):
    def test_failed_restore_read_keeps_file_record(self):
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        from unittest.mock import patch
        with self.temporary_directory() as directory:
            path = Path(directory).resolve() / 'a.py'
            path.write_text('value = 1\n')
            project = Project('test', directory, layout={'groups': [
                {'files': [{'path': str(path), 'cursor': 4, 'scroll': 2}]}]})
            with patch('features.ide.ui.workspace.read_text_file', side_effect=OSError('temporarily unreadable')):
                view = ProjectWorkspace(project)
                self.wait(view)
            record = view.state()['unavailable'][0]
            self.assertEqual(record, {'path': str(path), 'cursor': 4, 'scroll': 2, 'group': 0})
            self.assertFalse(view.pending_opens)
            view.prepare_close()
            view.close()

    def test_independent_projects_layout_and_missing_files_survive_restart(self):
        from features.ide.ui.page import IDEPage
        from features.ide.projects import Project
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            state = root / 'IDE' / 'workspace.json'
            a, b = root / 'a.py', root / 'b.py'
            a.write_text('a = 1\n')
            b.write_text('b = 2\n')
            page = IDEPage(store_path=state)
            first, second = Project('first', str(root)), Project('second', str(root))
            for p in (first, second):
                page.store.projects[p.id] = p
            one = page.open_project(first)
            one.open_path(a)
            self.wait(one)
            one.split_right()
            two = page.open_project(second)
            two.open_path(b)
            self.wait(two)
            self.assertIsNot(one.documents[a], two.documents[b])
            self.assertTrue(page.prepare_close())
            self.assertTrue(any(first.layout['splitter']))
            self.assertTrue(any(first.layout['editors']))
            page.close()
            b.unlink()
            restored = IDEPage(store_path=state)
            for project_view in restored.views:
                self.wait(project_view)
            self.assertEqual(len(restored.views), 2)
            self.assertEqual(len(restored.views[0].groups), 2)
            self.assertEqual(restored.views[1].unavailable[0]['path'], str(b))
            self.assertTrue(restored.prepare_close())
            restored.close()

    def test_stale_analysis_result_does_not_navigate(self):
        from features.ide.ui.workspace import ProjectWorkspace
        from features.ide.projects import Project
        from unittest.mock import patch
        with self.temporary_directory() as directory:
            path = Path(directory).resolve() / 'a.py'
            path.write_text('value = 1\nvalue\n')
            view = ProjectWorkspace(Project('test', directory))
            view.open_path(path)
            self.wait(view)
            view.show()
            self.app.processEvents()
            pending = []
            with patch.object(view, 'run', side_effect=lambda work, done: pending.append(done)):
                view.query('definition')
            view.current.insertPlainText('# changed')
            with patch.object(view, 'open_path') as opened:
                pending[0]([(str(path), 1, 0, 'value')])
                opened.assert_not_called()
            pending.clear()
            with patch.object(view, 'run', side_effect=lambda work, done: pending.append(done)):
                view.query('definition')
            view.project.source_paths = ['changed-source-root']
            with patch.object(view, 'open_path') as opened:
                pending[0]([(str(path), 1, 0, 'value')])
                opened.assert_not_called()
            view.current.document().setModified(False)
            self.assertTrue(view.prepare_close())
            view.close()


    def test_modifier_click_definition_and_history(self):
        from features.ide.ui.workspace import ProjectWorkspace
        from features.ide.projects import Project
        from commonUtils.ui import pyside as qt
        from PySide6.QtTest import QTest
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            source, target = root / 'main.py', root / 'models.py'
            code = 'from models import Thing\nThing()\n'
            source.write_text(code)
            target.write_text('class Thing:\n    pass\n')
            view = ProjectWorkspace(Project('test', str(root)))
            view.resize(900, 600)
            view.show()
            view.open_path(source)
            self.wait(view)
            doc = view.current
            cursor = doc.textCursor()
            cursor.setPosition(code.index('Thing()') + 2)
            doc.setTextCursor(cursor)
            self.app.processEvents()
            QTest.mouseClick(doc.viewport(), qt.Qt.MouseButton.LeftButton,
                             qt.Qt.KeyboardModifier.ControlModifier, doc.cursorRect().center())
            self.wait(view)
            self.assertEqual(view.current.path, target)
            view.travel(-1)
            self.wait(view)
            self.assertEqual(view.current.path, source)
            view.travel(1)
            self.wait(view)
            self.assertEqual(view.current.path, target)
            self.assertTrue(view.prepare_close())
            view.close()


    def test_watcher_distinguishes_own_save_from_external_write(self):
        from features.ide.ui.workspace import ProjectWorkspace
        from features.ide.projects import Project
        with self.temporary_directory() as directory:
            path = Path(directory).resolve() / 'a.py'
            path.write_text('original\n')
            view = ProjectWorkspace(Project('test', directory))
            view.open_path(path)
            self.wait(view)
            view.current.insertPlainText('# edit\n')
            self.assertTrue(view.save_current())
            view.external_change(str(path))
            self.wait(view)
            self.assertEqual(view.status.text(), 'Saved.')
            path.write_text('external\n')
            view.external_change(str(path))
            self.wait(view)
            self.assertIn('externally', view.status.text())
            self.assertTrue(view.prepare_close())
            view.close()
