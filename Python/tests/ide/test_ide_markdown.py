"""Markdown tabs participate in the IDE document lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import time
from pathlib import Path
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from features.ide.projects import Project
from features.ide.ui.workspace import ProjectWorkspace
from features.ide.ui.markdown_document import MarkdownDocument
from commonUtils.tests.qt_test_case import QtTestCase


class MarkdownTabTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def wait(self, workspace):
        deadline = time.monotonic() + 5
        while workspace.worker or workspace.queue:
            self.app.processEvents()
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.001)

    def test_formatted_edits_share_save_conflict_and_survive_view_destruction(self):
        with self.temporary_directory() as directory:
            path = Path(directory).resolve() / 'guide.md'
            path.write_bytes(b'# Guide\r\n\r\nOriginal\r\n')
            code = path.with_name('code.py')
            code.write_text('value = 1\n')
            workspace = ProjectWorkspace(Project('test', directory))
            self.wait(workspace)
            workspace.open_path(code)
            workspace.open_path(path)
            self.wait(workspace)
            first = workspace.current
            self.assertIsInstance(first, MarkdownDocument)
            self.assertEqual(first.editor.column_guide, 120)
            self.assertEqual(workspace.active_group.count(), 2)
            self.assertEqual(first.edit_mode.currentData(), 'formatted')
            self.assertEqual(first.active_editor().textCursor().position(), 0)
            self.assertEqual(first.active_editor().verticalScrollBar().value(), 0)
            self.assertTrue(workspace.save_current())
            self.assertEqual(path.read_bytes(), b'# Guide\r\n\r\nOriginal\r\n')
            workspace.split_right()
            second = workspace.current
            self.assertIsNot(first, second)
            self.assertEqual(second.editor.column_guide, 120)
            self.assertIs(first.document(), second.document())
            first.formatted_editor.moveCursor(qt.QTextCursor.MoveOperation.End)
            first.formatted_editor.insertPlainText(' edited')
            self.assertIn('edited', second.toPlainText())
            self.assertTrue(second.document().isModified())
            self.assertTrue(second.title.endswith(' *'))
            path.write_text('external\n')
            self.assertFalse(workspace.save_document(second))
            self.assertEqual(path.read_text(), 'external\n')
            workspace.close_document(first)
            qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            second.set_edit_mode('source')
            second.editor.moveCursor(qt.QTextCursor.MoveOperation.End)
            second.editor.insertPlainText(' after close')
            self.assertIn('after close', second.toPlainText())
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(workspace.close_document(second))
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
                self.assertTrue(workspace.close_document(second))
            self.wait(workspace)
            workspace.prepare_close()
            workspace.close()

    def test_links_open_other_tabs_and_save_as_updates_shared_identity(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path, linked, destination = root / 'a.MARKDOWN', root / 'b.md', root / 'saved.md'
            path.write_text('# First\n\n[Other](b.md)\n')
            linked.write_text('# Other\n')
            workspace = ProjectWorkspace(Project('test', directory))
            self.wait(workspace)
            workspace.open_path(path)
            self.wait(workspace)
            first = workspace.current
            first.follow_link(qt.QUrl('b.md'))
            self.wait(workspace)
            self.assertEqual(first.path, path)
            self.assertEqual(workspace.current.path, linked)
            workspace.open_path(path)
            workspace.split_right()
            second = workspace.current
            with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(destination), '')):
                self.assertTrue(workspace.save_current(True))
            self.assertEqual(first.path, destination)
            self.assertEqual(second.current_path, destination)
            self.assertNotIn(path, workspace.documents)
            second.set_edit_mode('source')
            second.editor.insertPlainText('unsaved')
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
                workspace.reload_current()
            self.assertEqual(first.toPlainText(), destination.read_text())
            workspace.find()
            self.assertTrue(second.find_bar.isVisibleTo(second))
            self.wait(workspace)
            self.assertTrue(workspace.can_close())
            workspace.prepare_close()
            workspace.close()

    def test_linked_tabs_inherit_read_and_edit_modes(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            origin, target = root / 'origin.md', root / 'target.md'
            origin.write_text('# Origin\n\n[Target](target.md#details)\n')
            target.write_text('# Target\n\n## Details\n\nText\n')
            workspace = ProjectWorkspace(Project('test', directory))
            self.wait(workspace)
            workspace.open_path(origin)
            self.wait(workspace)
            first = workspace.current
            for editing, mode in ((False, 'formatted'), (True, 'formatted'),
                                  (True, 'source'), (False, 'source')):
                with self.subTest(editing=editing, mode=mode):
                    workspace.open_path(origin)
                    first.set_edit_mode(mode)
                    first.set_editing(editing)
                    first.follow_link(qt.QUrl('target.md#details'))
                    self.wait(workspace)
                    linked = workspace.current
                    self.assertEqual(linked.path, target)
                    self.assertEqual(linked.edit_button.isChecked(), editing)
                    self.assertEqual(linked.edit_mode.currentData(), mode)
                    self.assertIs(linked.pages.currentWidget(),
                                  linked.active_editor() if editing else linked.browser)
                    self.assertEqual(first.edit_button.isChecked(), editing)
            workspace.prepare_close()
            workspace.close()
