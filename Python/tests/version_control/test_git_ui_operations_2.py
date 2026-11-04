"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase


from tests.version_control.fixtures import GitUIFixture


class GitUIOperationsTests(GitUIFixture, QtTestCase):
    def test_subtree_help_exit_129_still_opens_dialog(self):
        self.commit_fixture(); self.open()
        with patch('features.git.ui.repository_tools.FormDialog.submitted', return_value=False) as accepted:
            self.page.repository_tools.subtree_dialog(); self.wait()
            if 'unavailable' in self.page.status.text(): self.skipTest('git subtree not installed')
            accepted.assert_called_once()

    def test_edit_remote_reads_and_prefills_current_url(self):
        self.repo.remote_add('origin', '/example/remote.git')
        self.open()
        captured = []
        def submitted(dialog):
            captured.extend(edit.text() for edit in dialog.findChildren(qt.QLineEdit))
            return False
        with patch('features.git.ui.commands.forms.FormDialog.submitted', submitted):
            self.page.remote_dialog('origin'); self.wait()
        self.assertIn('/example/remote.git', captured)
