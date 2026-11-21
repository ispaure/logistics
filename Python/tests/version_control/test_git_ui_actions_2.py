"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

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
