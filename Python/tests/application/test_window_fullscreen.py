"""Window shortcuts remain available after leaving an embedded reader."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.readers.reader_chrome import ReaderFullscreen
from PySide6.QtTest import QTest
from desktop.fullscreen import WindowFullscreen


class WindowFullscreenTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.window = qt.QMainWindow()
        self.stack = qt.QStackedWidget()
        self.window.setCentralWidget(self.stack)
        self.reader = qt.QWidget()
        self.editor = qt.QPlainTextEdit()
        self.stack.addWidget(self.reader)
        self.stack.addWidget(self.editor)
        self.command = WindowFullscreen(self.window, self.window.menuBar().addMenu('Logistics'))
        self.reader_action = qt.QAction('Full screen', self.reader)
        self.reader_action.setCheckable(True)
        self.reader_action.setShortcut(qt.QKeySequence('F11'))
        self.reader.addAction(self.reader_action)
        self.reader_state = ReaderFullscreen(self.reader, self.reader_action)
        self.reader_action.triggered.connect(self.reader_state.toggle)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()

    def test_reader_shortcut_does_not_conflict_and_exits_after_tab_switch(self):
        self.reader.setFocus()
        QTest.keyClick(self.reader, qt.Qt.Key.Key_F11)
        self.assertTrue(self.window.isFullScreen())
        self.assertTrue(self.reader_action.isChecked())
        self.stack.setCurrentWidget(self.editor)
        self.editor.setFocus()
        QTest.keyClick(self.editor, qt.Qt.Key.Key_F11)
        self.assertFalse(self.window.isFullScreen())
        self.assertFalse(self.reader_action.isChecked())
        self.assertEqual(self.command.action.text(), 'Full screen')

    def test_reader_button_entry_menu_exit_and_maximized_restore(self):
        self.window.showMaximized()
        self.reader_action.trigger()
        self.assertTrue(self.command.action.isChecked())
        self.assertEqual(self.command.action.text(), 'Exit full screen')
        self.stack.setCurrentWidget(self.editor)
        self.command.action.trigger()
        self.assertFalse(self.window.isFullScreen())
        self.assertTrue(self.window.isMaximized())

    def test_f12_modifiers_and_dialogs_keep_their_own_keys(self):
        self.stack.setCurrentWidget(self.editor)
        for key, modifiers in ((qt.Qt.Key.Key_F12, qt.Qt.KeyboardModifier.NoModifier),
                               (qt.Qt.Key.Key_F11, qt.Qt.KeyboardModifier.ControlModifier)):
            QTest.keyClick(self.editor, key, modifiers)
            self.assertFalse(self.window.isFullScreen())
        dialog = qt.QDialog(self.window)
        dialog.show()
        dialog.activateWindow()
        dialog.setFocus()
        self.app.processEvents()
        QTest.keyClick(dialog, qt.Qt.Key.Key_F11)
        self.assertFalse(self.window.isFullScreen())
