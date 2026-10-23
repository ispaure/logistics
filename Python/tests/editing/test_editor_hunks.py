import subprocess
import tempfile
import unittest
from pathlib import Path
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.markers import line_changes
from services.editors.ui.hunks import restore_change
from features.git.editor_baseline import stage_preview, stage_reviewed
from features.git.runner import GitError


class HunkStageTests(unittest.TestCase):
    def test_stage_exact_reviewed_patch_and_reject_unsaved_or_stale_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True).stdout
            git('init')
            path = root / 'a.txt'
            before = ''.join(f'line {n}\n' for n in range(30))
            path.write_text(before)
            git('add', 'a.txt')
            after = before.replace('line 1\n', 'first changed\n').replace('line 25\n', 'second changed\n')
            path.write_text(after)
            inputs = stage_preview(path, 'utf-8', after, 1, 2)
            self.assertIn('first changed', inputs[-1])
            self.assertNotIn('second changed', inputs[-1])
            stage_reviewed(inputs)
            self.assertEqual(git('show', ':a.txt').decode(), before.replace('line 1\n', 'first changed\n'))
            self.assertEqual(path.read_text(), after)
            with self.assertRaises(ValueError):
                stage_preview(path, 'utf-8', after + 'unsaved', 25, 26)
            inputs = stage_preview(path, 'utf-8', after, 25, 26)
            path.write_text(after + 'external\n')
            with self.assertRaises(GitError):
                stage_reviewed(inputs)
            self.assertNotIn('second changed', git('show', ':a.txt').decode())


class HunkRestoreTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_unicode_restore_is_one_undo_and_rejects_stale_or_readonly_buffer(self):
        editor = CodeEdit()
        self.addCleanup(editor.deleteLater)
        before = '😀 unchanged\noriginal\n'
        after = '😀 unchanged\nreplacement\n'
        change, = line_changes(before, after)
        editor.setPlainText(after)
        restore_change(editor, after, before, change)
        self.assertEqual(editor.toPlainText(), before)
        editor.undo()
        self.assertEqual(editor.toPlainText(), after)
        editor.insertPlainText('changed')
        with self.assertRaises(ValueError):
            restore_change(editor, after, before, change)
        editor.setPlainText(after)
        editor.setReadOnly(True)
        with self.assertRaises(ValueError):
            restore_change(editor, after, before, change)

    def test_deleted_eof_and_added_file_restore(self):
        editor = CodeEdit()
        self.addCleanup(editor.deleteLater)
        for before, after in [('a\nb', 'a\n'), ('', 'new\n'), ('a', '')]:
            editor.setPlainText(after)
            change, = line_changes(before, after)
            restore_change(editor, after, before, change)
            self.assertEqual(editor.toPlainText(), before)

    def test_mixed_replacement_markers_restore_without_losing_deleted_lines(self):
        editor = CodeEdit()
        self.addCleanup(editor.deleteLater)
        for before, after in [('old\nremoved', 'new'),
                              ('old\nremoved\nend\n', 'new\nend\n'),
                              ('old', 'new\nadded')]:
            editor.setPlainText(after)
            changes = line_changes(before, after)
            for change in reversed(changes):
                restore_change(editor, editor.toPlainText(), before, change)
            self.assertEqual(editor.toPlainText(), before)

    def test_click_red_boundary_reviews_deletion_instead_of_overlapping_modify(self):
        from PySide6.QtTest import QTest
        from features.text_editor.ui.document import Document
        from commonUtils.persistence.text import TextSnapshot
        from services.editors.ui.hunks import HunkReview
        document = Document(TextSnapshot(None, b'old\nremoved', 'old\nremoved'))
        self.addCleanup(document.deleteLater)
        editor = document.editor
        editor.setPlainText('new')
        controller = document.markers
        controller.timer.stop()
        controller.refresh_timer.stop()
        controller.request = (document.snapshot, editor.document().revision())
        controller.baseline = ('old\nremoved', 'Last saved file (unsaved changes)')
        controller.run = lambda work, done, failed: done(work())
        editor.set_line_changes(line_changes('old\nremoved', 'new'))
        editor.gutter.installEventFilter(controller)
        editor.resize(480, 240)
        editor.show()
        self.app.processEvents()
        block = editor.document().firstBlock()
        top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
        height = round(editor.blockBoundingRect(block).height())
        QTest.mouseClick(editor.gutter, qt.Qt.MouseButton.LeftButton,
                        pos=qt.QPoint(3, top + height - 2))
        review = next(w for w in self.app.topLevelWidgets() if isinstance(w, HunkReview))
        self.addCleanup(review.deleteLater)
        self.assertEqual(review.change.kind, 'delete')

    def test_review_restores_through_host_and_blocks_stale_ui(self):
        from features.text_editor.ui.document import Document
        from commonUtils.persistence.text import TextSnapshot
        from services.editors.ui.changes import compare
        from services.editors.ui.hunks import HunkReview
        document = Document(TextSnapshot(None, b'original\n', 'original\n'))
        self.addCleanup(document.deleteLater)
        document.editor.setPlainText('edited\n')
        controller = document.markers
        controller.timer.stop()
        controller.refresh_timer.stop()
        controller.baseline = ('original\n', 'Last saved file (unsaved changes)')
        def run(work, done, failed):
            try:
                done(work())
            except Exception as error:
                failed(str(error))
        controller.run = run
        changes, _ = compare(document.snapshot, document.editor.toPlainText())
        review = HunkReview(controller, document.editor, changes[0])
        self.addCleanup(review.deleteLater)
        review.restore()
        self.assertEqual(document.editor.toPlainText(), 'original\n')
        document.editor.undo()
        stale = HunkReview(controller, document.editor, changes[0])
        self.addCleanup(stale.deleteLater)
        document.editor.insertPlainText('newer ')
        stale.restore()
        self.assertIn('buffer changed', stale.status.text())
        self.assertNotEqual(document.editor.toPlainText(), 'original\n')

    def test_gutter_click_opens_review_in_ide_and_standalone(self):
        import time
        from PySide6.QtTest import QTest
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        from features.text_editor.ui.window import EditorWindow
        from services.editors.ui.hunks import HunkReview
        def until(predicate):
            deadline = time.monotonic() + 8
            while not predicate():
                self.app.processEvents()
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.005)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'a.py'
            path.write_text('original\n')
            ide = ProjectWorkspace(Project('Test', directory, autosave='off'))
            ide.open_path(path)
            until(lambda: not ide.worker and not ide.queue)
            standalone = EditorWindow(history_path=root/'recent.json', preferences_path=root/'preferences.ini')
            standalone.open_path(path)
            until(lambda: not standalone.task.busy and not standalone._queue)
            for host, editor, busy in [
                (ide, ide.current, lambda: bool(ide.worker or ide.queue)),
                (standalone, standalone.current.editor, lambda: bool(standalone.task.busy or standalone._queue)),
            ]:
                host.show()
                editor.insertPlainText('edited ')
                until(lambda: bool(editor.line_changes))
                QTest.mouseClick(editor.gutter, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(3, 8))
                reviews = host.findChildren(HunkReview)
                self.assertTrue(reviews)
                reviews[-1].restore()
                until(lambda: not busy())
                self.assertEqual(editor.toPlainText(), 'original\n')
                editor.undo()
                self.assertEqual(editor.toPlainText(), 'edited original\n')
                editor.document().setModified(False)
            ide.closing = True
            ide.deleteLater()
            standalone.close()
            standalone.deleteLater()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def test_destroying_document_cancels_queued_baseline_read(self):
        from concurrent.futures import Future
        from features.text_editor.ui.document import Document
        document = Document()
        markers = document.markers
        cancel = markers.cancel
        future = Future()
        markers.pending[:] = [future]
        document.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.assertTrue(cancel.is_set())
        self.assertTrue(future.cancelled())
