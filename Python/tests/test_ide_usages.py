"""Semantic usages and declaration-click navigation."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from features.ide.analysis import analyze
from features.ide.projects import Project


class UsageAnalysisTests(unittest.TestCase):
    def test_declaration_lists_cross_file_usages_without_unrelated_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'model.py'
            code = 'def action():\n    pass\n\naction()\n'
            source.write_text(code)
            caller = root / 'caller.py'
            caller.write_text('from model import action\naction()\n')
            other = root / 'other.py'
            other.write_text('def action():\n    pass\naction()\n')
            excluded = root / 'ignored'
            excluded.mkdir()
            (excluded / 'call.py').write_text('from model import action\naction()\n')
            project = Project('usages', str(root), excluded_paths=['ignored'])
            result = analyze(project, source, code, 1, 6, 'navigate')
            self.assertEqual(result['kind'], 'usages')
            locations = {(Path(path).resolve(), line) for path, line, _, _ in result['targets']}
            self.assertEqual(locations, {(source, 4), (caller, 2)})
            self.assertEqual(analyze(project, source, code, 4, 2, 'navigate')['kind'], 'definition')
            self.assertEqual(analyze(project, source, code, 1, 6, 'definition')[0][1], 1)
            caller_code = caller.read_text()
            self.assertEqual(analyze(project, caller, caller_code, 1, 20, 'navigate')['kind'], 'definition')
            refs = analyze(project, caller, caller_code, 2, 2, 'usages')
            self.assertEqual({(Path(p).resolve(), line) for p, line, _, _ in refs}, locations)

    def test_previews_use_current_buffer_and_bound_external_reads(self):
        from features.ide.usages import usage_previews
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'source.py'
            source.write_text('saved()\n')
            external = root / 'external.py'
            external.write_bytes(b'x' * (1024 * 1024 + 1))
            missing = root / 'missing.py'
            targets = [(str(source), 1, 0, 'edited'),
                       (str(external), 1, 0, 'x'), (str(missing), 1, 0, 'missing')]
            self.assertEqual(usage_previews(targets, source, 'edited()\n'),
                             ['edited()', 'Source preview unavailable', 'Source preview unavailable'])

    def test_unused_declaration_returns_empty_usages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'unused.py'
            code = 'class Unused:\n    pass\n'
            source.write_text(code)
            self.assertEqual(analyze(Project('empty', str(root)), source, code, 1, 8, 'navigate'),
                             {'kind': 'usages', 'targets': []})


from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.ide.workspace import ProjectWorkspace


class UsageNavigationTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def wait(self, view):
        self.wait_until(lambda: not view.worker and not view.queue,
                        message='Workspace worker did not finish')

    def test_popup_filters_dismisses_outside_and_on_escape(self):
        from PySide6.QtTest import QTest
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'main.py'
            code = 'def action():\n    pass\n\naction()\n'
            path.write_text(code)
            view = ProjectWorkspace(Project('popup', str(root)))
            view.resize(900, 600)
            view.show()
            view.open_path(path)
            self.wait(view)
            view.place_view(view.current, line=1, column=6)
            view.query('usages')
            self.wait(view)
            popup = view.usage_popup
            self.assertTrue(popup.isVisible())
            popup.filter.setText('absent')
            self.assertTrue(popup.tree.topLevelItem(0).isHidden())
            self.assertTrue(popup.empty.isVisible())
            QTest.keyClick(popup.filter, qt.Qt.Key.Key_Return)
            self.assertEqual(view.current.textCursor().blockNumber(), 0)
            popup.filter.clear()
            self.assertFalse(popup.tree.topLevelItem(0).isHidden())
            QTest.keyClick(popup.tree, qt.Qt.Key.Key_Escape)
            self.assertFalse(popup.isVisible())
            view.query('usages')
            self.wait(view)
            self.assertTrue(popup.isVisible())
            QTest.mouseClick(view.current.viewport(), qt.Qt.MouseButton.LeftButton,
                             qt.Qt.KeyboardModifier.NoModifier, qt.QPoint(1, 1))
            self.assertFalse(popup.isVisible())
            view.place_view(view.current, line=1, column=6)
            view.query('usages')
            self.wait(view)
            self.assertTrue(popup.isVisible())
            view.current.insertPlainText('# edited\n')
            self.assertFalse(popup.isVisible())
            view.current.reload()
            view.prepare_close()
            view.close()

    def test_click_declaration_selects_usage_and_returns_through_history(self):
        from PySide6.QtTest import QTest
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            source = root / 'model.py'
            source.write_text('def action():\n    pass\n')
            caller = root / 'caller.py'
            caller.write_text('from model import action\naction()\n')
            view = ProjectWorkspace(Project('click', str(root)))
            view.resize(900, 600)
            view.show()
            view.open_path(source)
            self.wait(view)
            doc = view.current
            view.place_view(doc, line=1, column=6)
            self.app.processEvents()
            with patch.object(qt.QInputDialog, 'getItem') as picker:
                QTest.mouseClick(doc.viewport(), qt.Qt.MouseButton.LeftButton,
                                 qt.Qt.KeyboardModifier.ControlModifier, doc.cursorRect().center())
                self.wait(view)
                picker.assert_not_called()
            popup = view.usage_popup
            self.assertTrue(popup.isVisible())
            self.assertEqual(popup.windowType(), qt.Qt.WindowType.Popup)
            self.assertEqual(popup.tree.topLevelItem(0).text(0), 'caller.py')
            self.assertEqual(popup.tree.topLevelItem(0).text(1), '2')
            self.assertEqual(popup.tree.topLevelItem(0).text(2), 'action()')
            QTest.keyClick(popup.tree, qt.Qt.Key.Key_Return)
            self.wait(view)
            self.assertFalse(popup.isVisible())
            self.assertEqual(view.current.path, caller)
            self.assertEqual(view.current.textCursor().blockNumber(), 1)
            view.travel(-1)
            self.wait(view)
            self.assertEqual(view.current.path, source)
            # Edits made before reference analysis completes invalidate its results.
            requests = []
            with patch.object(view, 'run', side_effect=lambda cb, done, failed=None: requests.append((cb, done))):
                view.query('usages')
            doc.insertPlainText('# changed\n')
            with patch.object(qt.QInputDialog, 'getItem') as picker:
                callback, done = requests.pop()
                done(callback())
                picker.assert_not_called()
            doc.reload()
            self.assertTrue(view.prepare_close())
            view.close()
