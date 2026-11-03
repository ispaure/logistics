"""Scoped Notes Library tab groups retain independent drafts and provider leases."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from unittest.mock import patch
from shiboken6 import isValid
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.ui.library_workspace import TabbedNotesLibrary


class NotesLibraryTabTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.enterContext(patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard))
    def opened(self, root):
        (root / '.obsidian').mkdir()
        (root / 'A.md').write_text('# A')
        (root / 'B.md').write_text('# B')
        owner = TabbedNotesLibrary(lambda: LocalFiles(root), 'Tabs')
        owner.show()
        self.addCleanup(lambda: owner.close() if isValid(owner) else None)
        self.wait_until(lambda: not owner.progress.busy)
        return owner

    def note(self, owner, path):
        child = owner.open_note(path)
        self.wait_until(lambda: not child.progress.busy and child.index >= 0)
        return child

    def test_independent_drafts_scoped_groups_and_cancelled_close(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            from desktop.location_context import document_title
            self.assertEqual(owner.windowTitle(), root.name)
            first = self.note(owner, 'A.md')
            self.assertEqual(document_title(owner), root.name)
            first.viewer.set_editing(True)
            first.viewer.set_edit_mode('source')
            first.viewer.editor.insertPlainText('Unsaved A ')
            with patch.object(qt.QMessageBox, 'warning', side_effect=AssertionError('Switching tabs must retain drafts')):
                second = self.note(owner, 'B.md')
            self.assertIn('Unsaved A', first.viewer.editor.toPlainText())
            tabs = owner.document_tabs
            group = tabs.active_group
            self.assertTrue(tabs.move(second, group, 'right'))
            self.assertEqual(len(tabs.groups), 2)
            self.assertEqual(tabs.groups[0].widget(0), first)
            self.assertEqual(tabs.groups[1].widget(0), second)
            self.assertIs(owner.open_note('A.md'), first)
            self.assertIs(tabs.current, first)
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(tabs.close_tab(first))
            self.assertIn(first, tabs.documents)
            from PySide6.QtTest import QTest
            owner.activateWindow()
            first.viewer.editor.setFocus()
            self.app.processEvents()
            self.assertIs(self.app.focusWidget(), first.viewer.editor)
            combination = first.save_action.shortcut()[0]
            QTest.keyClick(first.viewer.editor, combination.key(), combination.keyboardModifiers())
            self.wait_until(lambda: not first.progress.busy)
            self.assertIn('Unsaved A', (root / 'A.md').read_text(),
                          (first.save_action.shortcut().toString(), first.save_action.isEnabled(), self.app.activeWindow()))
            self.assertTrue(tabs.close_tab(first))
            self.assertNotIn(first, tabs.documents)
            owner.close()

    def test_rename_and_delete_update_all_open_document_tabs(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            first = self.note(owner, 'A.md')
            second = self.note(owner, 'B.md')
            owner.document_tabs.move(second, owner.document_tabs.active_group, 'right')
            first_group = owner.document_tabs.documents[first]['group']
            owner.move_entry('A.md', 'Renamed.md')
            self.wait_until(lambda: not owner.progress.busy and (root / 'Renamed.md').exists())
            self.wait_until(lambda: any(child.index >= 0 and child.history[child.index] == 'Renamed.md'
                                       for child in owner.document_tabs.documents))
            self.assertFalse(any(owner.document_tabs.path(child) == 'A.md' for child in owner.document_tabs.documents))
            moved = next(child for child in owner.document_tabs.documents if owner.document_tabs.path(child) == 'Renamed.md')
            self.assertIs(owner.document_tabs.documents[moved]['group'], first_group)
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
                owner.delete_entry('B.md')
                self.wait_until(lambda: not owner.progress.busy)
            self.assertFalse(any(owner.document_tabs.path(child) == 'B.md' for child in owner.document_tabs.documents))
            owner.close()

    def test_private_tabs_share_a_lease_until_all_documents_close(self):
        from io import BytesIO
        from features.rclone import executable
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is unavailable')
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as fixture:
            provider = fixture.provider
            provider.mkdir('.obsidian')
            provider.create_file('B.md', BytesIO(b'# B'))
            owner = TabbedNotesLibrary(lambda: provider, 'Private tabs')
            owner.show()
            self.wait_until(lambda: not owner.progress.busy)
            first = self.note(owner, 'note.md')
            self.note(owner, 'B.md')
            self.assertTrue(owner.document_tabs.close_tab(first))
            self.assertFalse(provider.closed)
            owner.close()
            self.wait_until(lambda: provider.closed)
