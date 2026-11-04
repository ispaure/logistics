"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase
from features.git.repository import Repository


from tests.version_control.fixtures import GitUIFixture


class GitUIActionsTests(GitUIFixture, QtTestCase):
    def test_conventional_menus_share_toolbar_actions_and_busy_guards(self):
        menus = self.page.menu_controls.menus
        self.assertEqual([a.text() for a in self.page.menuBar().actions()],
                         ['File', 'Edit', 'View', 'Repository', 'Actions'])
        self.assertIn(self.page.action_buttons['Fetch'].defaultAction(), menus['Repository'].actions())
        self.assertFalse(self.page.action_buttons['Fetch'].defaultAction().isEnabled())
        self.open()
        fetch = self.page.action_buttons['Fetch'].defaultAction()
        with patch.object(self.page, '_operation') as operation:
            fetch.trigger()
            operation.assert_called_once()
        self.page._set_busy(True)
        self.assertFalse(fetch.isEnabled())
        self.assertFalse(menus['File'].actions()[0].isEnabled())
        self.page._set_busy(False)
        self.assertTrue(fetch.isEnabled())

    def test_primary_push_publishes_once_then_pushes_without_a_dialog(self):
        from unittest.mock import Mock
        self.commit_fixture()
        remote_path = self.root / 'remote.git'
        self.repo.runner.run(['init', '--bare', str(remote_path)])
        self.repo.remote_add('origin', str(remote_path))
        self.open()
        button = self.page.action_buttons['Push']
        self.assertEqual(button.defaultAction().text(), 'Publish branch…')
        self.assertEqual(button.popupMode(), qt.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.assertIs(button.menu(), self.page.push_menu)
        self.assertIn(self.page.push_menu.menuAction(),
                      self.page.menu_controls.menus['Repository'].actions())
        dialog = Mock()
        dialog.choice.return_value.currentText.return_value = 'origin'
        dialog.text.return_value.text.return_value = 'published'
        dialog.submitted.return_value = True
        with patch('features.git.ui.commands.forms.FormDialog', return_value=dialog) as form:
            button.defaultAction().trigger()
            self.wait()
            form.assert_called_once()
        self.assertEqual(self.repo.status().upstream, 'origin/published')
        self.assertEqual(button.defaultAction().text(), 'Push')
        self.assertIn('origin/published', button.defaultAction().toolTip())
        (self.repo.path / 'file.txt').write_text('second')
        self.repo.stage(['file.txt'])
        self.repo.commit('Second')
        self.page.refresh(); self.wait()
        with patch('features.git.ui.commands.forms.FormDialog') as form:
            button.defaultAction().trigger()
            self.wait()
            form.assert_not_called()
        subject = Repository(remote_path).run(['log', '-1', '--format=%s', 'refs/heads/published']).stdout
        self.assertEqual(subject.decode().strip(), 'Second')
        self.assertEqual(self.repo.status().ahead, 0)

    def test_push_options_force_confirmation_and_busy_guards(self):
        from dataclasses import replace
        self.commit_fixture()
        self.open()
        snapshot = self.page.snapshot
        self.page._render(replace(snapshot, status=replace(snapshot.status, upstream='origin/main')))
        self.assertFalse(self.page.force_push_action.isVisible())
        self.page.preferences.options['allow_force_push'] = True
        self.page.apply_preferences()
        self.assertTrue(self.page.force_push_action.isVisible())
        with patch.object(self.page, '_confirm', return_value=False) as confirm, \
                patch.object(self.page.commands, 'dispatch') as dispatch:
            self.page.force_push_action.trigger()
            confirm.assert_called_once()
            dispatch.assert_not_called()
        with patch.object(self.page, '_confirm', return_value=True), \
                patch.object(self.page.commands, 'dispatch') as dispatch:
            self.page.force_push_action.trigger()
            self.assertTrue(dispatch.call_args.kwargs['force_with_lease'])
            self.assertEqual(dispatch.call_args.kwargs['branch'], 'main')
        self.page._set_busy(True)
        self.assertFalse(self.page.publish_action.isEnabled())
        self.assertFalse(self.page.force_push_action.isEnabled())
        self.assertFalse(self.page.action_buttons['Push'].defaultAction().isEnabled())
        self.page._set_busy(False)
        self.page._render(snapshot)
        self.assertFalse(self.page.force_push_action.isEnabled())
        self.repo.run(['checkout', '--detach', 'HEAD'])
        self.page.refresh(); self.wait()
        self.assertFalse(self.page.action_buttons['Push'].defaultAction().isEnabled())
        self.assertFalse(self.page.push_menu.isEnabled())

    def test_edit_menu_dispatches_to_focused_field_and_protects_read_only_text(self):
        self.open()
        editor = self.page.changes.message
        editor.setFocus(); editor.setPlainText('draft'); editor.selectAll()
        self.app.processEvents()
        controls = self.page.menu_controls
        controls.update()
        self.assertTrue(controls.edit_actions['copy'].isEnabled())
        controls.edit_actions['copy'].trigger()
        self.assertEqual(self.app.clipboard().text(), 'draft')
        controls.edit_actions['cut'].trigger()
        self.assertEqual(editor.toPlainText(), '')
        self.page.log_toggle.setChecked(True)
        self.page.log.setFocus(); self.page.log.setPlainText('operation output'); self.page.log.selectAll()
        self.app.processEvents(); controls.update()
        self.assertTrue(controls.edit_actions['copy'].isEnabled())
        self.assertFalse(controls.edit_actions['cut'].isEnabled())
        self.assertFalse(controls.edit_actions['paste'].isEnabled())

    def test_commit_badge_and_commit_button_track_staged_files(self):
        from dataclasses import replace
        self.open()
        self.assertEqual(self.page.changes.commit_button.text(), 'Commit')
        self.assertFalse(self.page.changes.commit_button.isEnabled())
        (self.repo.path / 'new.txt').write_text('new')
        self.page.refresh(); self.wait()
        self.assertEqual(self.page.action_buttons['Commit'].property('badge_count'), 1)
        self.assertFalse(self.page.changes.commit_button.isEnabled())
        self.page.changes.stage_all(); self.wait()
        self.assertTrue(self.page.changes.commit_button.isEnabled())
        snapshot = self.page.snapshot
        self.page._render(replace(snapshot, status=replace(snapshot.status, upstream='origin/main', ahead=3, behind=2)))
        self.assertEqual(self.page.action_buttons['Push'].property('badge_count'), 3)
        self.assertEqual(self.page.action_buttons['Pull…'].property('badge_count'), 2)

    def test_terminal_opens_at_active_repository_root(self):
        self.open()
        with patch('commonUtils.integrations.wrappers.cmdShellWrapper.terminal.exec_cmd_new_window') as launch:
            self.page.open_terminal()
        import shlex
        command = 'cd' if os.sys.platform == 'win32' else f'cd -- {shlex.quote(str(self.page.path))} && pwd'
        launch.assert_called_once_with(command, str(self.page.path))

    def test_repository_settings_dialog_saves_without_overwriting_draft(self):
        from features.git.ui.settings import RepositorySettingsDialog
        self.open()
        self.page.changes.message.setPlainText('Keep this draft')
        def accept(dialog):
            self.assertEqual([dialog.tabs.tabText(i) for i in range(dialog.tabs.count())],
                             ['Commit Template', 'Remotes', 'Security', 'Advanced'])
            dialog.template_mode.setCurrentIndex(2)
            dialog.template.setPlainText('New template')
            return qt.QDialog.DialogCode.Accepted
        with patch.object(RepositorySettingsDialog, 'exec', accept):
            self.page.settings_dialog(); self.wait()
        self.assertEqual(self.repo.template_text(), 'New template')
        self.assertEqual(self.page.changes.message.toPlainText(), 'Keep this draft')
        self.page.changes.message.clear()
        self.page.refresh(); self.wait()
        self.assertEqual(self.page.changes.message.toPlainText(), 'New template')
        self.assertTrue(self.page.can_close())
