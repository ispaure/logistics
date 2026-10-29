"""Logistics update defaults, settings, offers and safe UI handoff."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.configuration.layered import register_settings
from services import updates
from desktop.updater import UpdateController
from desktop.landing import LaunchSurface
from desktop.pages.settings import ConfigurationPanel


class UpdatePolicyTests(unittest.TestCase):
    def test_defaults_disable_branch_choices_and_only_new_commits_are_offered(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'Python').mkdir()
            config = root / 'Python/configFile.ini'
            config.write_text('[Updates]\nenabled_bool=true\nbranch_mode=main\n')
            client = Mock()
            client.latest_release.return_value = {'branch': 'main', 'tag': 'v1.0.0', 'commit': 'b' * 40}
            client.has_new_commits.return_value = True
            with patch.object(updates, 'ROOT', root), patch.object(updates, 'source', return_value=client), patch.object(updates, 'installed_revision', return_value='a' * 40):
                self.assertEqual(updates.choice(), updates.UpdateChoice(True, 'main'))
                self.assertEqual(updates.check(root), client.latest_release.return_value)
                client.has_new_commits.return_value = False
                self.assertIsNone(updates.check(root))
                config.write_text('[Updates]\nenabled_bool=false\nbranch_mode=beta\n')
                client.reset_mock()
                self.assertIsNone(updates.check(root))
                client.latest_release.assert_not_called()
                config.write_text('[Updates]\nbranch_mode=unsafe\n')
                with self.assertRaises(ValueError): updates.choice()


class UpdateUITests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_configuration_has_updates_tab_with_default_enabled_and_branch_dropdown(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            path = updates.ROOT / 'Python/configFile.ini'
            store = register_settings(path, root / 'personal.ini')
            with patch('desktop.pages.settings.settings_store', return_value=store):
                panel = ConfigurationPanel([path], layered=True, scoped=False, scope='personal')
            editor = panel.stack.currentWidget()
            tabs = [editor.sections.tabText(i) for i in range(editor.sections.count())]
            self.assertIn('Updates', tabs)
            self.assertIn('FeatureDefaults', tabs)
            self.assertNotIn('General', tabs)
            self.assertTrue(editor.fields[('Updates', 'enabled_bool')].isChecked())
            branch = editor.fields[('Updates', 'branch_mode')]
            self.assertEqual([branch.itemText(i) for i in range(branch.count())], ['main', 'beta', 'alpha'])
            self.assertEqual(branch.currentText(), 'main')
            self.assertIn(('FeatureDefaults', 'disabled_list-str'), editor.fields)
            panel.deleteLater()
            self.app.processEvents()

    def controller(self, *, preferences=Path('/missing-test/preferences.json')):
        dialog = qt.QMainWindow()
        surface = LaunchSurface(dialog)
        dialog.setCentralWidget(surface)
        surface.resize(850, 550)
        owner = SimpleNamespace(dlg=dialog, launch_surface=surface,
                                _closing=False, pending_update=None, _update_offer_visibility=Mock())
        with patch('desktop.updater.preferences_path', return_value=preferences), patch('desktop.updater.qt.QTimer.singleShot'):
            controller = UpdateController(owner)
        self.addCleanup(dialog.deleteLater)
        controller.timer.stop()
        return controller, owner

    def test_preparation_label_fits_and_remains_anchored_after_reset(self):
        controller, owner = self.controller()
        controller.available = {'branch': 'main', 'commit': 'a' * 40}
        button = owner.launch_surface.update_button
        font = button.font()
        font.setPixelSize(32)  # Maximum supported interface size at 96 DPI.
        button.setFont(font)
        owner.launch_surface.position_settings()
        idle_width = button.width()
        with patch.object(controller.progress, 'start'):
            controller.install()
        self.assertGreater(button.width(), idle_width)
        self.assertGreaterEqual(button.width(), button.sizeHint().width())
        self.assertGreaterEqual(button.height(), button.sizeHint().height())
        self.assertEqual(button.x() + button.width(), owner.launch_surface.width() - 12)
        with patch('desktop.updater.notify'):
            controller._finished(None, 'Preparation failed')
        self.assertEqual(button.width(), idle_width)
        self.assertEqual(button.x() + button.width(), owner.launch_surface.width() - 12)

    def test_successful_prepare_requests_close_without_applying_in_running_process(self):
        controller, owner = self.controller()
        controller.operation = 'prepare'
        controller.selected = updates.UpdateChoice(True, 'main')
        with TemporaryDirectory() as temp:
            request = Path(temp) / 'request.json'
            request.write_text('{}')
            with patch('services.updates.choice', return_value=controller.selected), patch.object(owner.dlg, 'close') as close:
                controller._finished(request, None)
            self.assertEqual(owner.pending_update, request)
            close.assert_called_once()

    def test_failed_prepare_keeps_app_open_and_notifies(self):
        controller, owner = self.controller()
        controller.operation = 'prepare'
        with patch('desktop.updater.notify') as notice, patch.object(owner.dlg, 'close') as close:
            controller._finished(None, 'local tracked changes')
        self.assertIsNone(owner.pending_update)
        close.assert_not_called()
        self.assertIn('local tracked changes', notice.call_args.args)

    def test_worker_admission_failure_restores_the_offer_without_closing(self):
        controller, owner = self.controller()
        controller.available = {'branch': 'main', 'commit': 'a' * 40}
        with patch('commonUtils.ui.tasks.operation_progress.Operation.start',
                   side_effect=RuntimeError('thread admission denied')), \
                patch('desktop.updater.notify') as notice, \
                patch.object(owner.dlg, 'close') as close:
            controller.install()
            self.assertFalse(controller.button.isEnabled())
            self.wait_until(lambda: not controller.progress.busy,
                            message='Failed update admission did not retire')
            self.assertTrue(controller.button.isEnabled())
            self.assertEqual(controller.button.text(), 'Update Logistics')
            self.assertIsNone(owner.pending_update)
            close.assert_not_called()
            notice.assert_called_once()
            self.assertIn('thread admission denied', notice.call_args.args)

    def test_disabled_updates_hide_offer_without_network(self):
        controller, owner = self.controller()
        controller.available = {'branch': 'main', 'commit': 'a' * 40}
        with patch('services.updates.choice', return_value=updates.UpdateChoice(False, 'main')), patch('services.updates.check') as check:
            controller.poll()
        self.assertIsNone(controller.available)
        check.assert_not_called()
        owner._update_offer_visibility.assert_called()

    def test_invalid_preferences_after_preparation_discard_staging_and_leave_app_open(self):
        controller, owner = self.controller()
        controller.operation = 'prepare'
        controller.selected = updates.UpdateChoice(True, 'main')
        controller.last_check = 123
        with self.temporary_directory() as temp:
            workspace = Path(temp) / 'prepared'
            workspace.mkdir()
            request = workspace / 'request.json'
            request.write_text('{}')
            with patch('services.updates.choice', side_effect=ValueError('invalid branch')), \
                    patch.object(owner.dlg, 'close') as close:
                controller._finished(request, '')
            close.assert_not_called()
            self.assertIsNone(owner.pending_update)
            self.assertFalse(workspace.exists())
            self.assertEqual(controller.last_check, 0)
            self.assertTrue(controller.button.isEnabled())

    def test_malformed_receipts_do_not_prevent_startup_or_get_deleted(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            receipt = root / 'state/updates/last-result.json'
            receipt.parent.mkdir(parents=True)
            for value in (None, [], True, {}, {'success': 'false'},
                          {'success': False, 'message': 42}):
                with self.subTest(receipt=value):
                    content = json.dumps(value)
                    receipt.write_text(content)
                    with patch('desktop.updater.notify') as notice:
                        self.controller(preferences=root / 'preferences.json')
                    notice.assert_not_called()
                    self.assertEqual(receipt.read_text(), content)

    def test_valid_failure_receipt_notifies_once_and_is_consumed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            receipt = root / 'state/updates/last-result.json'
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({'success': False, 'message': 'recovery required'}))
            with patch('desktop.updater.notify') as notice:
                self.controller(preferences=root / 'preferences.json')
                self.controller(preferences=root / 'preferences.json')
            notice.assert_called_once()
            self.assertIn('recovery required', notice.call_args.args)
            self.assertFalse(receipt.exists())


if __name__ == '__main__':
    unittest.main()
