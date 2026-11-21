"""Desktop clipboard commands use the same protection in real Qt controls."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest
from shiboken6 import isValid

from services.documents.ui import clipboard
from features.rclone import session
from services.documents.ui.private_views import protect_private_view

MARKER = 'generated clipboard QA selection'
OTHER = 'generated unrelated clipboard QA text'


class DesktopClipboardTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.app = qt.QApplication.instance()
        if qt.QApplication.platformName() != 'offscreen':
            self.skipTest('Requires the isolated Qt offscreen clipboard.')
        self.filter = clipboard.ClipboardFilter(self.app)
        self.addCleanup(self.filter.deleteLater)
        self.addCleanup(self.app.removeEventFilter, self.filter)
        self.clip = self.app.clipboard()
        self.addCleanup(self.clip.clear)
        self.restrict = self.enterContext(patch.object(clipboard, 'enabled', return_value=True))
        self.credential = Path('clipboard-qa.session')
        self.addCleanup(session.forget, self.credential)

    def flush_deletes(self):
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def widget(self, kind):
        widget = kind()
        self.addCleanup(lambda: widget.deleteLater() if isValid(widget) else None)
        widget.show()
        widget.activateWindow()
        widget.setFocus()
        self.app.processEvents()
        return widget

    def activate(self):
        session.remember(self.credential, {'synthetic': {'type': 'memory'}})

    def check_commands(self, widget, invoke, restricted):
        get = getattr(widget, 'toPlainText', None) or widget.text
        put = getattr(widget, 'setPlainText', None) or widget.setText
        for command in ('cut', 'copy', 'paste'):
            with self.subTest(command=command, restricted=restricted):
                self.clip.setText(OTHER)
                put(MARKER)
                widget.selectAll()
                invoke(widget, command)
                self.assertEqual(self.clip.text(), OTHER if restricted or command == 'paste' else MARKER)
                expected = MARKER if restricted or command == 'copy' else (OTHER if command == 'paste' else '')
                self.assertEqual(get(), expected)

    def shortcut(self, widget, command):
        keys = qt.QKeySequence.keyBindings(getattr(qt.QKeySequence.StandardKey, 'SelectAll' if command == 'selectAll' else command.title()))
        self.assertTrue(keys)
        QTest.keySequence(widget, keys[0])

    def context(self, widget, command):
        menu = widget.createStandardContextMenu()
        menu.popup(widget.mapToGlobal(widget.rect().center()))
        try:
            action = next(action for action in menu.actions() if action.objectName() == 'edit-' + command)
            action.trigger()
        finally:
            menu.close()
            menu.deleteLater()
            self.flush_deletes()

    def test_native_selection_commands_across_windows_until_final_release(self):
        first = self.widget(qt.QLineEdit)
        second = self.widget(qt.QPlainTextEdit)
        self.check_commands(first, self.shortcut, False)
        self.check_commands(second, self.context, False)

        self.activate()
        protected = self.widget(qt.QMainWindow)
        protect_private_view(protected, SimpleNamespace(session_only=True))
        self.check_commands(first, self.shortcut, True)
        self.check_commands(second, self.context, True)
        session.forget(self.credential)
        self.check_commands(first, self.context, True)
        protected.deleteLater()
        self.flush_deletes()
        self.check_commands(second, self.shortcut, False)

    def test_markdown_edit_menu_rechecks_when_the_action_runs(self):
        from commonUtils.ui.markdown import MarkdownViewer

        viewer = MarkdownViewer(allow_edit=True)
        self.addCleanup(viewer.deleteLater)
        clipboard.guard_markdown_actions(viewer)
        viewer.set_edit_mode('source')
        viewer.set_editing(True)

        def action(widget, command):
            getattr(viewer, command + '_action').trigger()

        self.check_commands(viewer.editor, action, False)
        self.activate()
        self.check_commands(viewer.editor, action, True)

    def test_switch_off_and_non_clipboard_actions_still_work(self):
        editor = self.widget(qt.QLineEdit)
        self.activate()
        editor.setText(MARKER)
        self.shortcut(editor, 'selectAll')
        self.assertEqual(editor.selectedText(), MARKER)
        action = qt.QAction('File Browser move', editor)
        called = []
        action.triggered.connect(lambda: called.append(True))
        action.trigger()
        self.assertEqual(called, [True])
        self.restrict.return_value = False
        self.check_commands(editor, self.shortcut, False)
