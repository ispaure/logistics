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
        editor.insertPlainText("stale")
        before = editor.toPlainText()
        dialog.apply_current()
        self.assertIn("changed after comparison", dialog.status.text())
        self.assertEqual(editor.toPlainText(), before)
        self.assertEqual(path.read_text(), "😀 original\n")
