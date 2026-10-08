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

    def test_config_addition_keeps_existing_dirty_editor(self):
        with TemporaryDirectory() as temporary:
            first, second = [Path(temporary) / name for name in ('one.ini', 'two.ini')]
            first.write_text('one'); second.write_text('two')
            panel = ConfigurationPanel([first]); self.addCleanup(panel.deleteLater)
            editor = panel.editors[first]
            editor.text.insertPlainText('pending')
            panel.add_paths([first, second])
            self.assertEqual(panel.files.count(), 2)
            self.assertIs(panel.editors[first], editor)
            self.assertTrue(editor.is_modified)
            editor.text.document().setModified(False)

    def test_feature_status_directs_enablement_to_features_and_reports_missing_dependencies(self):
        from ui_new.pages.settings import FeatureSettingsPanel
        state = self.state()
        state.enabled = False
        with patch.object(registry, 'get_settings', return_value=[]):
            panel = FeatureSettingsPanel(state); self.addCleanup(panel.deleteLater)
            self.assertEqual(panel.findChildren(qt.QCheckBox), [])
            self.assertIn('under Features', panel.status.text())
            state.available = False
            panel.refresh(state)
            self.assertIn('dependencies are unavailable', panel.status.text())

    def test_empty_feature_settings_keep_heading_and_status_at_top(self):
        from ui_new.pages.settings import FeatureSettingsPanel
        with patch.object(registry, 'get_settings', return_value=[]):
            panel = FeatureSettingsPanel(self.state()); self.addCleanup(panel.deleteLater)
            panel.resize(850, 800); panel.show(); self.app.processEvents()
            self.assertLess(panel.title.height(), 50)
            self.assertLess(panel.status.geometry().bottom(), 140)
            panel.close()

    def test_description_is_compact_and_configuration_editor_fills_page(self):
        from ui_new.pages.settings import FeatureSettingsPanel
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'config.ini'; path.write_text('[Test]\nkey=value\n')
            contribution = RegisteredContribution('test', 'Test', SettingsContribution(
                'Configuration', 'config', lambda parent: qt.QLabel('Edit configuration below.', parent),
                config_files=(path,)))
            with patch.object(registry, 'get_settings', return_value=[contribution]):
                panel = FeatureSettingsPanel(self.state()); self.addCleanup(panel.deleteLater)
                panel.resize(850, 800); panel.show(); self.app.processEvents()
                self.assertLess(panel.custom['config'].height(), 50)
                self.assertGreater(panel.config.height(), 600)
                self.assertTrue(panel.status.isHidden())
                panel.close()

    def test_custom_expanding_layout_fills_available_space(self):
        from ui_new.pages.settings import FeatureSettingsPanel
        def factory(parent):
            widget = qt.QWidget(parent)
            layout = qt.QVBoxLayout(widget)
            layout.addWidget(qt.QListWidget())
            return widget
        contribution = RegisteredContribution('test', 'Test', SettingsContribution('Custom', 'custom', factory))
        with patch.object(registry, 'get_settings', return_value=[contribution]):
            panel = FeatureSettingsPanel(self.state()); self.addCleanup(panel.deleteLater)
            panel.resize(850, 800); panel.show(); self.app.processEvents()
            self.assertGreater(panel.custom['custom'].height(), 650)
            panel.close()
