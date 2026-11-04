"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase


from tests.version_control.fixtures import GitUIFixture


class GitUIFilesTests(GitUIFixture, QtTestCase):
    def test_edit_working_file_reuses_text_editor_service(self):
        from unittest.mock import Mock
        self.commit_fixture(); self.open()
        service = Mock()
        with patch('features.application.registry.is_feature_enabled', return_value=True), \
             patch('features.text_editor.ui.service.editor_service', return_value=service):
            self.page.edit_file('file.txt')
            self.page.edit_file('file.txt')
        self.assertEqual(service.open.call_count, 2)
        service.open.assert_called_with(self.repo.root() / 'file.txt')
        service.saved.connect.assert_called_once()

    def test_double_click_routes_to_ide_before_text_editor_and_validates_paths(self):
        from unittest.mock import Mock
        self.commit_fixture()
        (self.repo.path / 'file.txt').write_text('changed\n')
        self.open()
        opener = self.page.working_file_opener = Mock(return_value=True)
        item = self.page.changes.unstaged_files.topLevelItem(0)
        with patch('features.application.registry.is_feature_enabled', return_value=False), \
             patch('features.text_editor.ui.service.editor_service') as service:
            self.page.changes.unstaged_files.itemDoubleClicked.emit(item, 0)
            opener.assert_called_once_with(self.repo.root() / 'file.txt')
            service.assert_not_called()
            self.page.edit_file('../outside.txt')
            self.page.edit_file('missing.txt')
            opener.assert_called_once()

    def test_unmatched_file_falls_back_to_text_editor(self):
        from unittest.mock import Mock
        self.commit_fixture(); self.open()
        self.page.working_file_opener = Mock(return_value=False)
        service = Mock()
        with patch('features.application.registry.is_feature_enabled', return_value=True), \
             patch('features.text_editor.ui.service.editor_service', return_value=service):
            self.page.edit_file('file.txt')
        service.open.assert_called_once_with(self.repo.root() / 'file.txt')

    def test_history_double_click_opens_current_file_in_ide(self):
        from unittest.mock import Mock
        self.commit_fixture()
        (self.repo.path / 'file.txt').write_text('current working content\n')
        self.open()
        self.page.views.setCurrentIndex(1); self.wait()
        self.page.history.select_ref(self.page.snapshot.status.oid); self.wait()
        opener = self.page.working_file_opener = Mock(return_value=True)
        with patch('features.text_editor.ui.service.editor_service') as service:
            for mode in (0, 1):
                with self.subTest(mode=mode):
                    self.page.history.file_mode.setCurrentIndex(mode); self.wait()
                    item = self.page.history.tree.topLevelItem(0)
                    self.page.history.tree.itemDoubleClicked.emit(item, 0)
                    opener.assert_called_with(self.repo.root() / 'file.txt')
            self.assertEqual(opener.call_count, 2)
            service.assert_not_called()
        self.assertEqual((self.repo.path / 'file.txt').read_text(), 'current working content\n')

    def test_history_working_copy_double_click_falls_back_to_text_editor(self):
        from unittest.mock import Mock
        self.commit_fixture()
        (self.repo.path / 'file.txt').write_text('changed\n')
        self.open()
        self.page.views.setCurrentIndex(1); self.wait()
        self.page.history.table.setCurrentItem(self.page.history.table.topLevelItem(0)); self.wait()
        self.assertTrue(self.page.history.working_copy_is_selected())
        self.page.working_file_opener = Mock(return_value=False)
        service = Mock()
        with patch('features.application.registry.is_feature_enabled', return_value=True), \
             patch('features.text_editor.ui.service.editor_service', return_value=service):
            self.page.history.tree.itemDoubleClicked.emit(self.page.history.tree.topLevelItem(0), 0)
        service.open.assert_called_once_with(self.repo.root() / 'file.txt')

    def test_history_file_activation_ignores_folders_and_invalid_working_paths(self):
        from unittest.mock import Mock
        from features.git.models import TreeEntry
        self.commit_fixture(); self.open()
        opener = self.page.working_file_opener = Mock(return_value=True)
        # Both history panels use the same activation contract and path validation.
        for panel in (self.page.history, self.page.search_results):
            with qt.QSignalBlocker(panel): panel.file_mode.setCurrentIndex(1)
            panel.set_tree([TreeEntry('100644', 'blob', '', path)
                            for path in ('folder/missing.txt', '../outside.txt', 'file.txt')])
            folder = panel.tree.topLevelItem(0)
            panel.tree.itemDoubleClicked.emit(folder, 0)
            panel.tree.itemDoubleClicked.emit(folder.child(0), 0)
            panel.tree.itemDoubleClicked.emit(panel.tree.topLevelItem(1).child(0), 0)
            opener.assert_not_called()
            panel.tree.itemDoubleClicked.emit(panel.tree.topLevelItem(2), 0)
            opener.assert_called_once_with(self.repo.root() / 'file.txt')
            opener.reset_mock()
