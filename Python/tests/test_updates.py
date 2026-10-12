"""Logistics update defaults, settings, offers and safe UI handoff."""
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
from ui_new.updater import UpdateController
from ui_new.pages.settings import ConfigurationPanel


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
            with patch('ui_new.pages.settings.settings_store', return_value=store):
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

    def controller(self):
        dialog = qt.QMainWindow()
        button = qt.QPushButton(dialog)
        owner = SimpleNamespace(dlg=dialog, launch_surface=SimpleNamespace(update_button=button),
                                _closing=False, pending_update=None, _update_offer_visibility=Mock())
        with patch('ui_new.updater.preferences_path', return_value=Path('/missing-test/preferences.json')), patch('ui_new.updater.qt.QTimer.singleShot'):
            controller = UpdateController(owner)
        self.addCleanup(dialog.deleteLater)
        controller.timer.stop()
        return controller, owner

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
        with patch('ui_new.updater.notify') as notice, patch.object(owner.dlg, 'close') as close:
            controller._finished(None, 'local tracked changes')
        self.assertIsNone(owner.pending_update)
        close.assert_not_called()
        self.assertIn('local tracked changes', notice.call_args.args)

    def test_disabled_updates_hide_offer_without_network(self):
        controller, owner = self.controller()
        controller.available = {'branch': 'main', 'commit': 'a' * 40}
        with patch('services.updates.choice', return_value=updates.UpdateChoice(False, 'main')), patch('services.updates.check') as check:
            controller.poll()
        self.assertIsNone(controller.available)
        check.assert_not_called()
        owner._update_offer_visibility.assert_called()


if __name__ == '__main__':
    unittest.main()
