import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor.diff import DiffDialog
from features.text_editor.window import EditorWindow


class EditorExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = EditorWindow(history_path=self.root / "recent.json",
                                   preferences_path=self.root / "preferences.ini")
        self.service = self.window.service

    def tearDown(self):
        for window in tuple(self.service.windows):
            self.wait(window)
            for document in window.documents:
                document.editor.document().setModified(False)
            window.close()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def wait(self, window=None):
        window = window or self.window
        end = monotonic() + 5
        while window.task.busy or window._queue:
            self.assertLess(monotonic(), end)
            self.app.processEvents()
            sleep(.005)
        self.app.processEvents()

    def test_format_selection_undo_and_failure_preserves_buffer(self):
        editor = self.window.current.editor
        editor.setPlainText('prefix\n{"a":1}\nsuffix')
        cursor = editor.textCursor()
        cursor.setPosition(7)
        cursor.setPosition(14, qt.QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        self.window.structured_text("json", "format")
        self.assertEqual(editor.toPlainText(), 'prefix\n{\n    "a": 1\n}\nsuffix')
        editor.undo()
        self.assertEqual(editor.toPlainText(), 'prefix\n{"a":1}\nsuffix')
        editor.setPlainText('{bad')
        with patch.object(self.window, "show_error") as error:
            self.window.structured_text("json", "format")
            error.assert_called_once()
        self.assertEqual(editor.toPlainText(), '{bad')

    def test_compare_disk_review_apply_undo_and_stale_protection(self):
        path = self.root / "a.txt"
        path.write_text("😀 original\n")
        self.window.open_path(path)
        self.wait()
        editor = self.window.current.editor
        editor.setPlainText("😀 edited\n")
        self.window.compare_disk()
        self.wait()
        dialog = self.window.findChildren(DiffDialog)[0]
        self.assertEqual(len(dialog.model.changes), 1)
        self.assertTrue(all(e.isReadOnly() for e in dialog.editors))
        dialog.apply_current()
        self.assertEqual(editor.toPlainText(), "😀 original\n")
        editor.undo()
        self.assertEqual(editor.toPlainText(), "😀 edited\n")
        dialog.close()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.window.compare_disk(); self.wait()
        dialog = self.window.findChildren(DiffDialog)[0]
        editor.insertPlainText("stale")
        before = editor.toPlainText()
        dialog.apply_current()
        self.assertIn("changed after comparison", dialog.status.text())
        self.assertEqual(editor.toPlainText(), before)
        self.assertEqual(path.read_text(), "😀 original\n")

    def test_diff_dialog_history_roundtrips_each_hunk_and_blocks_changed_history(self):
        path = self.root / 'history.txt'; path.write_text('😀 left\nkeep\nend\n')
        self.window.open_path(path); self.wait()
        editor = self.window.current.editor; original = '😀 right\nkeep\nend'
        editor.setPlainText(original)
        self.window.compare_disk(); self.wait()
        dialog = self.window.findChildren(DiffDialog)[0]
        states = [original]
        while dialog.model.changes:
            dialog.apply_current(); states.append(editor.toPlainText())
        self.assertEqual(editor.toPlainText(), path.read_text())
        for _ in range(10):
            for state in reversed(states[:-1]):
                dialog.undo(); self.assertEqual(editor.toPlainText(), state)
                self.assertEqual(dialog.model.right, state)
            for state in states[1:]:
                dialog.redo(); self.assertEqual(editor.toPlainText(), state)
                self.assertEqual(dialog.model.right, state)
        editor.setReadOnly(True)
        before = editor.toPlainText(); dialog.undo()
        self.assertEqual(editor.toPlainText(), before)
        self.assertIn('read-only', dialog.status.text())
        editor.setReadOnly(False)
        # Same text can have a different undo stack; never undo that newer edit.
        cursor = editor.textCursor(); cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        cursor.insertText('external'); editor.undo()
        self.assertEqual(editor.toPlainText(), before)
        dialog.undo(); self.assertEqual(editor.toPlainText(), before)
        self.assertIn('history changed', dialog.status.text())
        dialog.close()

    def test_merge_disk_uses_ancestor_and_applies_one_undoable_buffer_edit(self):
        from commonUtils.ui.code_editor.merge import MergeDialog
        path = self.root / 'merge.txt'; path.write_text('a\nb\nc\n')
        self.window.open_path(path); self.wait()
        document = self.window.current
        document.editor.setPlainText('left\nb\nc\n')
        path.write_text('a\nb\nright\n')
        self.window.merge_disk(); self.wait()
        dialog = self.window.findChildren(MergeDialog)[0]
        dialog.widget.apply_nonconflicting(); dialog.apply_result()
        self.assertEqual(document.editor.toPlainText(), 'left\nb\nright\n')
        self.assertEqual(path.read_text(), 'a\nb\nright\n')
        self.assertEqual(document.snapshot.original, path.read_bytes())
        document.editor.undo(); self.assertEqual(document.editor.toPlainText(), 'left\nb\nc\n')
        document.editor.redo(); self.assertEqual(document.editor.toPlainText(), 'left\nb\nright\n')

    def test_review_shortcuts_do_not_route_to_parent_editor_history(self):
        from PySide6.QtTest import QTest
        from commonUtils.ui.code_editor.merge import MergeDialog
        path = self.root / 'shortcuts.txt'; path.write_text('base\n')
        self.window.open_path(path); self.wait()
        editor = self.window.current.editor
        editor.insertPlainText('local '); local = editor.toPlainText()
        path.write_text('disk\n'); self.window.merge_disk(); self.wait()
        dialog = self.window.findChildren(MergeDialog)[0]
        widget = dialog.widget; widget.choose(0, 'right')
        dialog.show(); dialog.raise_(); dialog.activateWindow()
        self.assertTrue(QTest.qWaitForWindowActive(dialog, 2000))
        widget.editors[0].setFocus(); self.app.processEvents()
        self.assertTrue(widget.editors[0].hasFocus())
        QTest.keySequence(widget.editors[0], qt.QKeySequence(qt.QKeySequence.StandardKey.Undo))
        self.app.processEvents()
        self.assertEqual(widget.session.text, 'base\n')
        self.assertEqual(editor.toPlainText(), local)
        QTest.keySequence(widget.editors[0], qt.QKeySequence(qt.QKeySequence.StandardKey.Redo))
        self.app.processEvents()
        self.assertEqual(widget.session.text, 'disk\n')
        self.assertEqual(editor.toPlainText(), local)
        dialog.close(); self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.window.compare_disk(); self.wait()
        dialog = self.window.findChildren(DiffDialog)[0]; dialog.apply_current()
        dialog.show(); dialog.raise_(); dialog.activateWindow()
        self.assertTrue(QTest.qWaitForWindowActive(dialog, 2000))
        dialog.editors[0].setFocus(); self.app.processEvents()
        self.assertTrue(dialog.editors[0].hasFocus())
        QTest.keySequence(dialog.editors[0], qt.QKeySequence(qt.QKeySequence.StandardKey.Undo))
        self.app.processEvents()
        self.assertEqual(editor.toPlainText(), local)
        self.assertEqual(dialog.model.right, local)
        QTest.keySequence(dialog.editors[0], qt.QKeySequence(qt.QKeySequence.StandardKey.Redo))
        self.app.processEvents()
        self.assertEqual(editor.toPlainText(), 'disk\n')
        self.assertEqual(dialog.model.right, 'disk\n')
        dialog.close()

    def test_merge_disk_rejects_external_change_during_review(self):
        from commonUtils.ui.code_editor.merge import MergeDialog
        path=self.root/'merge.txt'; path.write_text('base\n')
        self.window.open_path(path); self.wait()
        self.window.current.editor.setPlainText('local\n'); path.write_text('disk\n')
        self.window.merge_disk(); self.wait()
        dialog=self.window.findChildren(MergeDialog)[0]; dialog.widget.choose(0,'right')
        path.write_text('new disk\n'); dialog.apply_result()
        self.assertIn('changed on disk',dialog.widget.status.text())
        self.assertEqual(self.window.current.editor.toPlainText(),'local\n')
        dialog.close()

    def test_shortcuts_persist_propagate_conflicts_and_palette(self):
        from commonUtils.ui.command_palette import CommandPalette, shortcut_text
        self.window._save_shortcuts({"transform_trim": "Ctrl+Alt+T"})
        other = self.service.open()
        self.assertEqual(shortcut_text(other.actions["transform_trim"]), "Ctrl+Alt+T")
        with self.assertRaises(ValueError):
            self.window._save_shortcuts({"transform_trim": "Ctrl+S"})
        self.assertEqual(shortcut_text(self.window.actions["transform_trim"]), "Ctrl+Alt+T")
        editor = self.window.current.editor
        editor.setPlainText("value  ")
        palette = CommandPalette(self.window.actions, self.window)
        palette.query.setText("trim whitespace")
        self.assertEqual(palette.results.count(), 1)
        palette.run_current()
        self.assertEqual(editor.toPlainText(), "value")
        palette.deleteLater()
        self.window._save_shortcuts({})
        self.assertEqual(shortcut_text(other.actions["transform_trim"]), "")

    def test_synchronized_views_focus_undo_readonly_and_close(self):
        document = self.window.current
        primary = document.editor
        primary.setPlainText("one\ntwo")
        self.window.split_document(qt.Qt.Orientation.Horizontal)
        secondary = document.editor
        self.assertIsNot(primary, secondary)
        self.assertIs(primary.document(), secondary.document())
        primary.moveCursor(qt.QTextCursor.MoveOperation.Start)
        secondary.moveCursor(qt.QTextCursor.MoveOperation.End)
        secondary.insertPlainText("!")
        self.assertEqual(primary.toPlainText(), "one\ntwo!")
        self.assertEqual(primary.textCursor().position(), 0)
        primary.undo()
        self.assertEqual(secondary.toPlainText(), "one\ntwo")
        secondary.setReadOnly(True)
        self.assertTrue(primary.isReadOnly())
        primary.setReadOnly(False)
        self.assertFalse(secondary.isReadOnly())
        document.views.activate(primary)
        self.assertIs(document.editor, primary)
        self.assertIs(self.window.search.editor, primary)
        self.window.split_document(None)
        self.assertIs(document.editor, primary)
        self.assertEqual(primary.toPlainText(), "one\ntwo")

    def test_multicursor_clears_on_other_view_edit_and_escape(self):
        document = self.window.current
        primary = document.editor
        primary.setPlainText("foo foo")
        primary.add_next_occurrence()
        self.assertEqual(len(primary.extra_cursors), 1)
        self.window.escape_editor()
        self.assertEqual(primary.extra_cursors, [])
        primary.add_next_occurrence()
        self.window.split_document(qt.Qt.Orientation.Horizontal)
        document.editor.insertPlainText("other")
        self.assertEqual(primary.extra_cursors, [])
