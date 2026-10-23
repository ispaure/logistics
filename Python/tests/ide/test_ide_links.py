"""IDE-only modifier navigation feedback and stale worker results."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.ide.projects import Project
from features.ide.ui.workspace import ProjectWorkspace


class IDELinkTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_reachable_link_preserves_buffer_and_rejects_stale_hover(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'main.py'
            path.write_text('value = 1\nprint(value)\n')
            view = ProjectWorkspace(Project('links', str(root)))
            view.resize(900, 600)
            view.show()
            view.open_path(path)
            self.wait(view)
            doc = view.current
            self.app.processEvents()
            cursor = doc.textCursor()
            cursor.setPosition(18)
            point = doc.cursorRect(cursor).center()
            requests = []
            with patch.object(view, 'run', side_effect=lambda callback, done, failed=None: requests.append((callback, done))):
                doc.update_link(point, True)
                self.assertEqual(doc.viewport().cursor().shape(), qt.Qt.CursorShape.PointingHandCursor)
                callback, done = requests.pop()
                done(callback())
                self.assertEqual(doc.link_selection.cursor.selectedText(), 'value')
                self.assertTrue(doc.link_selection.format.fontUnderline())
                self.assertFalse(doc.document().isModified())
                self.assertEqual(doc.textCursor().position(), 0)
                doc.highlight_cursor()
                self.assertTrue(any(s.cursor.selectedText() == "value" and s.format.fontUnderline()
                                    for s in doc.extraSelections()))
                doc.update_link(point, False)
                self.assertIsNone(doc.link_selection)
                self.assertEqual(doc.viewport().cursor().shape(), qt.Qt.CursorShape.IBeamCursor)
                doc.update_link(point, True)
                callback, done = requests.pop()
                doc.update_link(point, False)
                done(callback())
                self.assertIsNone(doc.link_selection)
                doc.update_link(point, True)
                callback, done = requests.pop()
                done([])
                self.assertIsNone(doc.link_selection)
                doc.update_link(point, False)
                doc.update_link(point, True)
                callback, done = requests.pop()
                doc.insertPlainText('# edit\n')
                done(callback())
                self.assertIsNone(doc.link_selection)
            doc.reload()
            self.assertTrue(view.prepare_close())
            view.close()

    def wait(self, view):
        from PySide6.QtTest import QTest
        for _ in range(1000):
            self.app.processEvents()
            if not view.worker and not view.queue:
                return
            QTest.qWait(5)
        self.fail('Workspace worker did not finish')
