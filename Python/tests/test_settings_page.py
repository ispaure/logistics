"""Settings retains custom feature layouts and protects raw configuration edits."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from commonUtils.ui import pyside as qt
from features import registry
from features.contributions import SettingsContribution, RegisteredContribution
from ui_new.pages.settings import SettingsPage, ConfigurationPanel


class SettingsPageTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def state(self):
        return SimpleNamespace(name='test', label='Test', enabled=True, available=True,
                               dependencies=(), dependents=())

    def test_custom_layout_is_lazy_and_retained_across_feature_toggles(self):
        state = self.state()
        factory = Mock(side_effect=lambda parent: qt.QWidget(parent))
        contribution = RegisteredContribution('test', 'Test', SettingsContribution('Custom', 'custom', factory))
        with patch.object(registry, 'get_feature_states', return_value=[state]), patch.object(registry, 'get_settings', return_value=[contribution]) as settings:
            page = SettingsPage(); self.addCleanup(page.deleteLater)
            factory.assert_not_called()
            item = page.sidebar.topLevelItem(2).child(0)
            page.sidebar.setCurrentItem(item)
            factory.assert_called_once()
            panel = page.panels['feature:test']
            custom = panel.custom['custom']
            state.enabled = False; settings.return_value = []
            page.refresh()
            self.assertTrue(custom.isHidden())
            state.enabled = True; settings.return_value = [contribution]
            page.refresh()
            self.assertIs(panel.custom['custom'], custom)
            factory.assert_called_once()

    def test_configuration_file_switch_retains_unsaved_edits(self):
        with TemporaryDirectory() as temporary:
            paths = [Path(temporary) / name for name in ('one.ini', 'two.ini')]
            for path in paths: path.write_text('[Section]\nkey=value\n')
            panel = ConfigurationPanel(paths); self.addCleanup(panel.deleteLater)
            first = panel.editors[paths[0]]
            first.text.insertPlainText('# pending\n')
            panel.files.setCurrentIndex(1)
            panel.files.setCurrentIndex(0)
            self.assertIs(panel.stack.currentWidget(), first)
            self.assertTrue(first.is_modified)
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(panel.can_close())
            first.text.document().setModified(False)

    def test_rclone_contributes_settings_instead_of_navigation_page(self):
        from features.rclone.ui_contributions import get_contributions
        contributions = get_contributions()
        self.assertEqual(contributions.pages, [])
        self.assertEqual(contributions.settings[0].name, 'Credential packages')

    def test_settings_api_rejects_duplicate_identity(self):
        contribution = RegisteredContribution('test', 'Test', SettingsContribution('Custom', 'custom', lambda parent: None))
        with patch.object(registry, '_collect_contributions', return_value=[contribution, contribution]):
            with self.assertRaisesRegex(ValueError, 'Duplicate settings ID'):
                registry.get_settings()
