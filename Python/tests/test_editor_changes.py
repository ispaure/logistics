import subprocess
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.persistence.text import read_text_file
from features.editor_changes import compare
from features.ide.projects import Project
from features.ide.workspace import ProjectWorkspace


class BaselineTests(unittest.TestCase):
    def test_editor_git_reads_honor_configured_executable(self):
        executable = shutil.which('git')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run([executable, '-C', directory, 'init'], check=True, capture_output=True)
            path = root / 'file.txt'
            path.write_text('original\n')
            subprocess.run([executable, '-C', directory, 'add', 'file.txt'], check=True, capture_output=True)
            path.write_text('edited\n')
            # Model a GUI launch where only the configured absolute Git path
            # is usable; the plain "git" command cannot be resolved.
            with patch('commonUtils.configuration.settings.get_setting', return_value=executable), \
                    patch('features.git.runner.shutil.which', side_effect=lambda name: executable if name == executable else None):
                snapshot = read_text_file(path)
                changes, label = compare(snapshot, snapshot.text)
            self.assertEqual(changes[0].kind, 'modify')
            self.assertIn('Git index', label)

    def test_unregistered_repo_index_refresh_and_missing_git_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git('init')
            path = root / 'file.txt'
            path.write_text('original\n')
            git('add', 'file.txt')
            path.write_text('edited\n')
            snapshot = read_text_file(path)
            changes, label = compare(snapshot, snapshot.text)
            self.assertEqual(changes[0].kind, 'modify')
            self.assertIn('Git index', label)
            git('add', 'file.txt')
            self.assertFalse(compare(snapshot, snapshot.text)[0])
            with patch('features.git.editor_baseline.index_baseline', side_effect=OSError('missing')):
                self.assertIn('Last saved', compare(snapshot, 'unsaved\n')[1])
            new = root / 'new.txt'
            new.write_text('new\n')
            changes, label = compare(read_text_file(new), 'new\n')
            self.assertEqual(changes[0].kind, 'add')

    def test_worktree_discovery_and_index_are_local_to_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'main'
            root.mkdir()
            def git(path, *args):
                return subprocess.run(['git', '-C', str(path), *args], check=True, capture_output=True)
            git(root, 'init')
            (root / 'a.txt').write_text('base\n')
            git(root, 'add', 'a.txt')
            git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'initial')
            worktree = Path(directory) / 'worktree'
            git(root, 'worktree', 'add', '-b', 'test-worktree', str(worktree))
            path = worktree / 'a.txt'
            path.write_text('worktree\n')
            snapshot = read_text_file(path)
            self.assertTrue(compare(snapshot, snapshot.text)[0])
            git(worktree, 'add', 'a.txt')
            self.assertFalse(compare(snapshot, snapshot.text)[0])
            self.assertEqual(git(root, 'show', ':a.txt').stdout, b'base\n')


class AutoSaveTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def until(self, predicate):
        deadline = time.monotonic() + 8
        while not predicate():
            self.app.processEvents()
            autosave = getattr(getattr(getattr(self, 'doc', None), 'buffer', None), 'autosave', None)
            self.assertLess(time.monotonic(), deadline,
                f'Autosave busy={getattr(autosave, "busy", None)}, error={getattr(autosave, "error", None)}, '
                f'timer={autosave.timer.isActive() if autosave else None}, '
                f'workspace worker={bool(getattr(getattr(self, "view", None), "worker", None))}')
            time.sleep(.005)

    def setUp(self):
        self.directory = self.temporary_directory()
        self.path = Path(self.directory.name) / 'file.py'
        self.path.write_bytes(b'original\r\n')
        self.view = ProjectWorkspace(Project('Test', self.directory.name))
        self.view.open_path(self.path)
        self.until(lambda: not self.view.worker and not self.view.queue)
        self.doc = self.view.current
        self.addCleanup(self.cleanup_view)

    def cleanup_view(self):
        self.until(lambda: not self.view.worker and not self.view.queue)
        self.view.closing = True
        # Leave the owner alive for the managed fixture to capture marker
        # futures and stop browser workers before deleting the folder. Native
        # Windows handles can outlive deleteLater while an executor task ends.

    def test_saved_git_changes_keep_markers_until_staged(self):
        root = str(self.path.parent)
        def git(*args):
            subprocess.run(['git', '-C', root, *args], check=True, capture_output=True)
        git('init')
        git('add', self.path.name)
        self.doc.insertPlainText('changed ')
        self.until(lambda: not self.doc.document().isModified())
        self.until(lambda: bool(self.doc.line_changes))
        self.assertIn('Git index', self.doc.gutter.toolTip())
        git('add', self.path.name)
        self.until(lambda: not self.doc.line_changes)

    def test_debounce_shared_buffer_undo_and_external_conflict(self):
        self.view.split_right()
        self.until(lambda: not self.view.worker and not self.view.queue)
        self.assertIs(self.doc.buffer.autosave, self.view.current.buffer.autosave)
        self.doc.insertPlainText('first ')
        self.assertEqual(self.path.read_bytes(), b'original\r\n')
        self.until(lambda: not self.doc.document().isModified())
        self.assertEqual(self.path.read_bytes(), b'first original\r\n')
        self.assertTrue(self.doc.document().isUndoAvailable())
        self.path.write_bytes(b'external\r\n')
        self.doc.insertPlainText('second ')
        self.until(lambda: bool(self.doc.buffer.autosave.error))
        self.assertEqual(self.path.read_bytes(), b'external\r\n')
        self.assertTrue(self.doc.document().isModified())
        self.assertFalse(self.view.autosave_notice.isHidden())

    def test_edit_during_save_stays_dirty_and_close_save_reload_are_guarded(self):
        from features.ide.autosave import write_snapshot
        started, release = Event(), Event()
        def delayed(snapshot, text):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Test worker timed out')
            return write_snapshot(snapshot, text)
        with patch('features.ide.autosave.write_snapshot', side_effect=delayed):
            self.doc.insertPlainText('first ')
            self.doc.buffer.autosave.save()
            self.until(started.is_set)
            self.doc.insertPlainText('second ')
            self.assertFalse(self.view.close_document(self.doc))
            self.assertFalse(self.view.save_document(self.doc))
            self.view.reload_current()
            release.set()
            self.until(lambda: not self.doc.buffer.autosave.busy)
        self.assertTrue(self.doc.document().isModified())
        self.assertEqual(self.path.read_bytes(), b'first original\r\n')
        self.until(lambda: not self.doc.document().isModified())
        self.assertEqual(self.path.read_bytes(), b'first second original\r\n')

    def test_autosave_mode_roundtrips_project_store(self):
        from features.ide.projects import ProjectStore
        path = Path(self.directory.name) / 'workspace.json'
        store = ProjectStore(path)
        self.view.project.autosave = 'off'
        store.projects[self.view.project.id] = self.view.project
        store.save()
        self.assertEqual(ProjectStore(path).projects[self.view.project.id].autosave, 'off')
        legacy = {'id': 'old', 'name': 'Old', 'root_path': self.directory.name}
        self.assertEqual(Project.from_dict(legacy).autosave, 'after_delay')
        with self.assertRaises(ValueError):
            Project.from_dict(dict(legacy, autosave='invalid'))

    def test_format_only_revision_during_save_does_not_leave_text_dirty(self):
        from features.ide.autosave import write_snapshot
        started, release = Event(), Event()
        def delayed(snapshot, text):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Test worker timed out')
            return write_snapshot(snapshot, text)
        self.addCleanup(release.set)
        with patch('features.ide.autosave.write_snapshot', side_effect=delayed):
            self.doc.insertPlainText('edit ')
            self.doc.buffer.autosave.save()
            self.until(started.is_set)
            revision = self.doc.document().revision()
            cursor = qt.QTextCursor(self.doc.document())
            cursor.select(qt.QTextCursor.SelectionType.Document)
            style = qt.QTextCharFormat()
            style.setForeground(qt.QColor('blue'))
            cursor.mergeCharFormat(style)
            self.assertGreater(self.doc.document().revision(), revision)
            self.assertEqual(self.doc.toPlainText(), 'edit original\n')
            release.set()
            self.until(lambda: not self.doc.buffer.autosave.busy)
        self.assertFalse(self.doc.document().isModified())
        self.assertEqual(self.path.read_bytes(), b'edit original\r\n')

    def test_format_only_notifications_do_not_restart_text_debounce(self):
        self.doc.buffer.autosave.timer.setInterval(150)
        self.doc.insertPlainText('edit ')
        color = False
        def saved():
            nonlocal color
            if self.path.read_bytes() == b'edit original\r\n':
                return True
            cursor = qt.QTextCursor(self.doc.document())
            cursor.select(qt.QTextCursor.SelectionType.Document)
            style = qt.QTextCharFormat()
            style.setForeground(qt.QColor('blue' if color else 'red'))
            cursor.mergeCharFormat(style)
            color = not color
            return False
        self.until(saved)
        self.assertEqual(self.path.read_bytes(), b'edit original\r\n',
                         'Formatting notifications postponed the source-text autosave indefinitely')

    def test_off_and_focus_mode(self):
        self.view.set_autosave('off')
        self.doc.insertPlainText('edit ')
        self.doc.buffer.autosave.save()
        self.assertFalse(self.doc.buffer.autosave.busy)
        self.view.set_autosave('focus_change')
        self.doc.buffer.autosave.focus_changed(self.doc, self.view.browser)
        self.until(lambda: not self.doc.buffer.autosave.busy)
        self.assertFalse(self.doc.document().isModified())

    def test_modal_close_does_not_focus_autosave_and_stale_markers_are_rejected(self):
        from concurrent.futures import Future
        self.view.set_autosave('focus_change')
        self.doc.insertPlainText('edit ')
        def cancel(*args):
            self.doc.buffer.autosave.focus_changed(self.doc, self.view.browser)
            self.assertFalse(self.doc.buffer.autosave.busy)
            return qt.QMessageBox.StandardButton.Cancel
        with patch.object(qt.QMessageBox, 'question', side_effect=cancel):
            self.assertFalse(self.view.confirm_document(self.doc))
        markers = self.doc.buffer.markers
        markers.timer.stop()
        markers.refresh_timer.stop()
        markers.request = (self.doc.snapshot, self.doc.document().revision())
        markers.future = Future()
        self.doc.insertPlainText('newer ')
        markers.future.set_result((('stale',), 'stale', ''))
        markers.finished()
        self.assertEqual(self.doc.line_changes, ())
