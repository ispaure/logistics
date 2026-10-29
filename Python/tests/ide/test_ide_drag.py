"""End-to-end confined gestures, including native capture changing receivers."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from shiboken6 import isValid
from features.ide.projects import Project
from features.ide.ui.workspace import ProjectWorkspace


class IDEDragTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.directory = self.temporary_directory()
        self.root = Path(self.directory.name).resolve()
        # These gestures assert an unsaved buffer; background autosave must not
        # clear its modified flag simply because a slower host crosses the timer.
        self.view = ProjectWorkspace(Project('drag', str(self.root), autosave='off'))
        self.view.resize(1200, 700); self.view.show(); self.view.activateWindow()
        self.addCleanup(self.close_view)
        for name in ('left.py', 'right.py'):
            path = self.root / name
            path.write_text(name + '\n')
            self.view.open_path(path)
        self.wait()
        self.left, self.right = [self.view.groups[0].widget(i) for i in range(2)]
        self.view.drop_editor(self.right, self.view.groups[0], 'right')
        self.settle()

    def settle(self):
        for _ in range(6): self.app.processEvents()

    def wait(self):
        self.wait_until(lambda: not self.view.worker and not self.view.queue, timeout=8,
                        message='IDE drag worker did not finish')
        self.settle()

    def close_view(self):
        for doc in self.view.views(): doc.document().setModified(False)
        self.view.prepare_close(); self.wait()

    def mouse(self, receiver, kind, point):
        event = qt.QMouseEvent(kind, qt.QPointF(receiver.mapFromGlobal(point)), qt.QPointF(point),
            qt.Qt.MouseButton.NoButton if kind == qt.QEvent.Type.MouseMove else qt.Qt.MouseButton.LeftButton,
            qt.Qt.MouseButton.NoButton if kind == qt.QEvent.Type.MouseButtonRelease else qt.Qt.MouseButton.LeftButton,
            qt.Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(receiver, event)
        self.settle()

    def gesture(self, doc, target, placement, receiver='source', cancel=False):
        bar = self.view.group_for(doc).tabBar()
        start = bar.mapToGlobal(bar.tabRect(bar.group.indexOf(doc)).center())
        x = 6 if placement == 'left' else target.width()-7 if placement == 'right' else target.width()//2
        y = target.tabBar().height()//2 if placement == 'header' else max(100, target.height()//2)
        end = target.mapToGlobal(qt.QPoint(x, y))
        self.mouse(bar, qt.QEvent.Type.MouseButtonPress, start)
        sink = bar if receiver == 'source' else target.currentWidget()
        self.mouse(sink, qt.QEvent.Type.MouseMove, end)
        candidate = bar.target(end)
        self.assertTrue(bar.dragging)
        self.assertEqual(bar.preview.isVisible(), candidate is not None)
        if candidate:
            self.assertIs(candidate[0], target)
            self.assertEqual(candidate[1], 'tabs' if placement in ('tabs', 'header') else placement)
        if cancel:
            self.app.sendEvent(sink, qt.QKeyEvent(qt.QEvent.Type.KeyPress, qt.Qt.Key.Key_Escape,
                                               qt.Qt.KeyboardModifier.NoModifier))
        self.mouse(sink, qt.QEvent.Type.MouseButtonRelease, end)
        if isValid(bar):
            self.assertFalse(bar.dragging)
            self.assertFalse(bar.preview.isVisible())

    def assert_order(self, expected):
        self.assertEqual([self.view.editors.widget(i) for i in range(self.view.editors.count())], expected)
        self.assertEqual(self.view.groups, expected)
        self.assertEqual(sorted(expected, key=lambda g: g.x()), expected)

    def test_repeated_two_single_file_side_drops_preserve_buffer_and_layout(self):
        self.left.insertPlainText('unsaved ')
        document = self.left.document()
        content = self.left.toPlainText()
        cursor = self.left.textCursor().position()
        for width in (1200, 760, 1450):
            self.view.resize(width, 700); self.settle()
            for receiver in ('source', 'destination'):
                for moving, anchor in ((self.left, self.right), (self.right, self.left)):
                    for side in ('right', 'left', 'right', 'left'):
                        with self.subTest(width=width, receiver=receiver, moving=moving.path.name, side=side):
                            source = self.view.group_for(moving)
                            target = self.view.group_for(anchor)
                            self.gesture(moving, target, side, receiver)
                            self.assert_order([source, target] if side == 'left' else [target, source])
                            self.assertEqual(len(self.view.groups), 2)
                            self.assertIs(self.left.document(), document)
                            self.assertEqual(self.left.toPlainText(), content)
                            self.assertEqual(self.left.textCursor().position(), cursor)
                            self.assertTrue(document.isModified())
                            self.assertFalse(moving.isWindow())
        self.assertEqual(self.left.path.read_text(), 'left.py\n')
        self.left.undo()
        self.assertEqual(self.left.toPlainText(), 'left.py\n')

    def test_center_and_header_merge_then_split_again(self):
        for placement in ('tabs', 'header'):
            for receiver in ('source', 'destination'):
                with self.subTest(placement=placement, receiver=receiver):
                    target = self.view.group_for(self.right)
                    self.gesture(self.left, target, placement, receiver)
                    self.assertEqual(len(self.view.groups), 1)
                    self.assertIs(self.view.group_for(self.left), target)
                    self.assertEqual(target.count(), 2)
                    self.gesture(self.left, target, 'left', receiver)
                    self.assertEqual(len(self.view.groups), 2)
                    self.assert_order([self.view.group_for(self.left), self.view.group_for(self.right)])

    def test_qtest_press_move_release_repeatedly_reorders_two_columns(self):
        from PySide6.QtTest import QTest
        for width in (1200, 760):
            self.view.resize(width, 700); self.settle()
            for _ in range(3):
                for moving, anchor in ((self.left, self.right), (self.right, self.left)):
                    for side in ('left', 'right'):
                        source, target = self.view.group_for(moving), self.view.group_for(anchor)
                        bar = source.tabBar()
                        end = target.mapToGlobal(qt.QPoint(8 if side == 'left' else target.width()-9, 150))
                        QTest.mousePress(bar, qt.Qt.MouseButton.LeftButton, pos=bar.tabRect(0).center())
                        QTest.mouseMove(bar, bar.mapFromGlobal(end)); QTest.qWait(10)
                        self.assertTrue(bar.preview.isVisible())
                        self.assertEqual(bar.target(end)[1], side)
                        QTest.mouseRelease(bar, qt.Qt.MouseButton.LeftButton, pos=bar.mapFromGlobal(end))
                        self.settle()
                        self.assert_order([source, target] if side == 'left' else [target, source])
                        self.assertFalse(bar.dragging)

    def test_cancel_outside_and_group_cap_do_not_move_files(self):
        original = list(self.view.groups)
        self.gesture(self.left, self.view.group_for(self.right), 'right', 'destination', cancel=True)
        self.assert_order(original)
        bar = self.view.group_for(self.left).tabBar()
        start = bar.mapToGlobal(bar.tabRect(0).center())
        outside = self.view.editors.mapToGlobal(qt.QPoint(-20, 120))
        self.mouse(bar, qt.QEvent.Type.MouseButtonPress, start)
        self.mouse(bar, qt.QEvent.Type.MouseMove, outside)
        self.assertFalse(bar.preview.isVisible())
        self.mouse(self.view.browser, qt.QEvent.Type.MouseButtonRelease, outside)
        self.assert_order(original)
        for name in ('third.py', 'fourth.py'):
            path = self.root / name; path.write_text(name)
            self.view.open_path(path, self.view.group_for(self.left)); self.wait()
        third = self.view.view_for(self.root / 'third.py', self.view.group_for(self.left))
        self.gesture(third, self.view.group_for(self.right), 'right', 'destination')
        self.assertEqual(len(self.view.groups), 3)
        expected = list(self.view.groups)
        # A multi-file source would need a fourth column: neither preview nor move.
        self.gesture(self.left, self.view.group_for(self.right), 'left', 'destination')
        self.assert_order(expected)
        # Single-file columns can still be repositioned at the cap.
        source, target = self.view.group_for(third), self.view.group_for(self.right)
        self.gesture(third, target, 'left', 'destination')
        expected.remove(source); expected.insert(expected.index(target), source)
        self.assert_order(expected)
