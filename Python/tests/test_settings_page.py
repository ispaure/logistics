"""Settings retains custom feature layouts and protects raw configuration edits."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import Mock, patch
from commonUtils.ui import pyside as qt
from features import registry
from features.contributions import SettingsContribution, RegisteredContribution
from ui_new.pages.settings import SettingsPage, ConfigurationPanel


class SettingsPageTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def state(self):
        return SimpleNamespace(name='test', label='Test', enabled=True, available=True,
                               dependencies=(), dependents=())

    def test_indexing_has_boolean_rules_and_explicit_save_preserves_other_sections(self):
        from ui_new.settings.indexing import IndexSettingsPanel
        from commonUtils.ui.file_browser.index_policy import index_policy
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'configFile.ini'
            path.write_text('[Other]\nvalue=kept\n[FileIndex]\nscan_on_open=true\nrecursive_on_open=false\nwatch_changes=true\n')
            panel = IndexSettingsPanel(path=path); self.addCleanup(panel.deleteLater)
            field = panel.editor.fields['FileIndex', 'scan_on_open']
            self.assertIsInstance(field, qt.QCheckBox)
            field.setChecked(False)
            self.assertTrue(index_policy(path=path).scan_on_open)
            self.assertTrue(panel.editor.save())
            self.assertFalse(index_policy(path=path).scan_on_open)
            self.assertIn('value=kept', path.read_text())

    def test_indexing_dependencies_keep_saved_values_and_independent_triggers(self):
        from ui_new.settings.indexing import IndexSettingsPanel
        from commonUtils.ui.file_browser.index_policy import index_policy
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'config.ini'
            path.write_text('[FileIndex]\nscan_on_open=true\nrecursive_on_open=true\n'
                            'refresh_cached_on_startup=true\nwatch_changes=true\nrefresh_on_revisit=true\n')
            panel = IndexSettingsPanel(path=path); self.addCleanup(panel.deleteLater)
            fields = panel.editor.fields
            scan = fields['FileIndex', 'scan_on_open']
            startup = fields['FileIndex', 'refresh_cached_on_startup']
            scan.setChecked(False)
            self.assertFalse(startup.isEnabled())
            self.assertTrue(startup.isChecked())
            self.assertIn('saved value is retained', startup.toolTip())
            for name in ('watch_changes', 'refresh_on_revisit', 'recursive_on_open'):
                self.assertTrue(fields['FileIndex', name].isEnabled())
                self.assertTrue(fields['FileIndex', name].toolTip())
            self.assertTrue(panel.editor.save())
            self.assertTrue(index_policy(path=path).refresh_cached_on_startup)
            fields = panel.editor.fields
            fields['FileIndex', 'scan_on_open'].setChecked(True)
            self.assertTrue(fields['FileIndex', 'refresh_cached_on_startup'].isEnabled())

    def test_custom_layout_is_lazy_and_retained_across_feature_toggles(self):
        state = self.state()
        factory = Mock(side_effect=lambda parent: qt.QWidget(parent))
        contribution = RegisteredContribution('test', 'Test', SettingsContribution('Custom', 'custom', factory))
        with patch.object(registry, 'get_feature_states', return_value=[state]), patch.object(registry, 'get_settings', return_value=[contribution]) as settings:
            page = SettingsPage(); self.addCleanup(page.deleteLater)
            factory.assert_not_called()
            item = next(page.sidebar.topLevelItem(i) for i in range(page.sidebar.topLevelItemCount()) if page.sidebar.topLevelItem(i).text(0) == 'Feature settings').child(0)
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

    def test_settings_categories_have_no_storage_summary(self):
        with patch.object(registry, 'get_feature_states', return_value=[]):
            page = SettingsPage(); self.addCleanup(page.deleteLater)
            names = [page.sidebar.topLevelItem(i).text(0) for i in range(page.sidebar.topLevelItemCount())]
            self.assertNotIn('Storage & defaults', names)
            personal = page.panels['features'].sections
            self.assertEqual(personal.tabs.tabText(0), 'Personal')

    def test_commonutils_settings_expose_ini_and_preserve_edits(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'settings.ini'
            path.write_text('[WheelNavigation]\nsensitivity=20\n')
            with patch('ui_new.pages.settings.settings_path', return_value=path):
                page = SettingsPage(); self.addCleanup(page.deleteLater)
                item = next(page.sidebar.topLevelItem(i) for i in range(page.sidebar.topLevelItemCount()) if page.sidebar.topLevelItem(i).text(0) == 'commonUtils')
                self.assertEqual(item.text(0), 'commonUtils')
                page.sidebar.setCurrentItem(item)
                editor = page.panels['commonutils'].editors[path]
                editor.text.setPlainText('[WheelNavigation]\nsensitivity=10\n')
                editor.text.document().setModified(True)
                page.sidebar.setCurrentItem(page.sidebar.topLevelItem(0))
                page.sidebar.setCurrentItem(item)
                self.assertIs(page.stack.currentWidget().stack.currentWidget(), editor)
                self.assertTrue(editor.save())
                from commonUtils.configuration.settings import get_wheel_navigation_settings
                self.assertEqual(get_wheel_navigation_settings(path=path).sensitivity, 10)

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
        from features.contributions import RemoteFolderSourceContribution
        self.assertEqual([entry.settings_id for entry in contributions.settings],
                         ['credentials', 'software_downloads'])
        self.assertTrue(all(isinstance(entry, RemoteFolderSourceContribution)
                            for entry in contributions.remote_folder_sources))
        self.assertEqual(len(contributions.remote_folder_sources), 1)
        self.assertTrue(contributions.settings[0].separate_tab)
        self.assertEqual(contributions.settings[0].scope, 'personal')

    def test_feature_guide_is_in_header_and_available_when_disabled(self):
        from ui_new.pages.settings import FeatureSettingsPanel
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            guide = root / 'test' / 'user_docs' / 'index.md'
            guide.parent.mkdir(parents=True); guide.write_text('# Test\n')
            state = self.state(); state.enabled = False
            with patch.object(registry, '__file__', str(root / 'registry.py')), \
                    patch.object(registry, 'get_settings', return_value=[]):
                panel = FeatureSettingsPanel(state); self.addCleanup(panel.deleteLater)
                panel.resize(850, 600); panel.show(); self.app.processEvents()
                self.assertTrue(panel.guide_button.isEnabled())
                self.assertGreater(panel.guide_button.x(), panel.width() / 2)
                self.assertLess(panel.guide_button.y(), 60)
                with patch('ui_new.pages.settings.open_markdown') as opened:
                    panel.guide_button.click()
                opened.assert_called_once_with(guide, parent=panel.window(), detached=True, allow_new_tabs=False)
                self.assertIn('Alt', panel.guide_button.toolTip())
                panel.close()

    def test_tabbed_settings_retain_custom_state_and_unsaved_ini_edits(self):
        from ui_new.pages.settings import FeatureSettingsPanel
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'config.ini'; path.write_text('[Test]\nkey=value\n')
            factory = Mock(side_effect=lambda parent: qt.QLineEdit('credential state', parent))
            tab = RegisteredContribution('test', 'Test', SettingsContribution(
                'Credential packages', 'credentials', factory, separate_tab=True, scope='personal'))
            ini = RegisteredContribution('test', 'Test', SettingsContribution(
                'INI', 'ini', lambda parent: qt.QLabel('Configuration', parent), config_files=(path,)))
            state = self.state()
            with patch.object(registry, 'get_settings', return_value=[tab, ini]) as entries:
                panel = FeatureSettingsPanel(state); self.addCleanup(panel.deleteLater)
                panel.show(); self.app.processEvents()
                self.assertEqual([panel.settings_tabs.tabText(i) for i in range(2)], ['Application Settings', 'Personal'])
                widget = panel.custom['credentials']
                self.assertFalse(widget.isVisible())
                editor = panel.config.editors[path]
                editor.text.insertPlainText('# unsaved\n')
                panel.settings_tabs.setCurrentIndex(1)
                widget.setText('retained')
                panel.refresh(state)
                self.assertIs(panel.sections.pages['personal'].direct, widget)
                self.assertTrue(widget.isVisible())
                self.assertFalse(panel.body.isVisible())
                state.enabled = False; entries.return_value = []
                panel.refresh(state)
                self.assertEqual(panel.settings_tabs.count(), 1)
                state.enabled = True; entries.return_value = [tab, ini]
                panel.refresh(state)
                self.assertIs(panel.custom['credentials'], widget)
                self.assertEqual(widget.text(), 'retained')
                self.assertTrue(editor.is_modified)
                factory.assert_called_once()
                with patch.object(editor, 'can_close', return_value=False):
                    self.assertFalse(panel.can_close())
                editor.text.document().setModified(False)
                panel.close()


    def test_ini_files_are_combined_once_per_scope_with_retained_buffers(self):
        from ui_new.pages.settings import FeatureSettingsPanel
        with TemporaryDirectory() as temporary:
            paths = [Path(temporary) / name for name in ('app.ini', 'another.ini', 'personal.ini')]
            for path in paths:
                path.write_text('[Section]\nkey=value\n')
            contributions = [RegisteredContribution('test', 'Test', SettingsContribution(
                str(index), str(index), config_files=(path,), scope='personal' if index == 2 else 'application'))
                for index, path in enumerate(paths)]
            with patch.object(registry, 'get_settings', return_value=contributions):
                panel = FeatureSettingsPanel(self.state()); self.addCleanup(panel.deleteLater)
                self.assertEqual([panel.settings_tabs.tabText(i) for i in range(2)], ['Application Settings', 'Personal'])
                for scope in ('application', 'personal'):
                    inner = panel.sections.pages[scope].tabs
                    self.assertEqual(inner.count(), 1)
                    self.assertEqual(inner.tabText(0), 'INI files')
                app = panel.configs['application']
                self.assertEqual(app.files.count(), 2)
                editor = app.editors[paths[0]]
                editor.text.insertPlainText('# pending\n')
                panel.refresh(self.state())
                self.assertIs(app.editors[paths[0]], editor)
                self.assertTrue(editor.is_modified)
                editor.text.document().setModified(False)

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
                self.assertGreater(panel.config.height(), 500)
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
