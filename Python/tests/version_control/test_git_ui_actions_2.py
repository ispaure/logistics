"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase


from tests.version_control.fixtures import GitUIFixture


class GitUIActionsTests(GitUIFixture, QtTestCase):
    def test_all_repository_tool_dialogs_use_workspace_as_parent(self):
        self.commit_fixture(); self.open()
        for method in (self.page.repository_tools.worktrees_dialog, self.page.repository_tools.submodules_dialog):
            with patch('features.git.ui.repository_tools.FormDialog.submitted', return_value=False) as submitted:
                method(); self.wait(); submitted.assert_called_once()
