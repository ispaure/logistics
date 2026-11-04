"""Git focus callbacks tolerate native menu retirement during parent teardown."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from shiboken6 import delete, isValid
from commonUtils.tests.qt_test_case import QtTestCase
from features.git.ui.repository_view import RepositoryView


class GitMenuRetirementTests(QtTestCase):
    def test_focus_callback_ignores_menus_deleted_before_the_view(self):
        with self.temporary_directory() as temporary:
            page = RepositoryView(preferences_path=Path(temporary) / 'git.json')
            controls = page.menu_controls
            delete(controls.menus['View'])
            self.assertTrue(isValid(page))
            self.assertFalse(page.closing)
            controls.focus_changed(None, None)
            controls.update()
