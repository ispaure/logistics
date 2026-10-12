"""Feature controls display session state and handle required dependencies."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from commonUtils.tests.qt_test_case import QtTestCase
from types import ModuleType
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.formats.registry import file_types
from features import registry
from features.contributions import FeatureContributions
from ui_new.pages.features import FeaturesPage


class FeaturesPageTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.base = ModuleType('features.test_base')
        self.base.FEATURE_NAME = 'test_base'
        self.base.FEATURE_LABEL = 'Test Base'
        self.child = ModuleType('features.test_child')
        self.child.FEATURE_NAME = 'test_child'
        self.child.FEATURE_LABEL = 'Test Child'
        self.child.FEATURE_DEPENDENCIES = ('test_base',)
        self.child.get_contributions = lambda: FeatureContributions()
        self.missing = ModuleType('features.test_missing')
        self.missing.FEATURE_NAME = 'test_missing'
        self.missing.FEATURE_DEPENDENCIES = ('not_installed',)
        temporary = TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        from commonUtils.configuration.layered import register_settings
        defaults = Path(temporary.name) / 'defaults.ini'
        defaults.write_text('[FeatureDefaults]\ndisabled_list-str = []\n')
        self.store = register_settings(defaults, Path(temporary.name) / 'personal.ini')
        store_patch = patch.object(registry, 'feature_settings_store', return_value=self.store)
        store_patch.start(); self.addCleanup(store_patch.stop)
        for target, value in [('_disabled_features', set()), ('_initialized_features', set()),
                              ('_layered_preferences', True), ('_preferences_path', None)]:
            patcher = patch.object(registry, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.feature_patch = patch.object(registry, 'load_features', return_value=[self.base, self.child, self.missing])
        self.feature_patch.start()
        self.addCleanup(self.feature_patch.stop)
        self.addCleanup(file_types.set_owner_enabled, 'test_base', True)
        self.addCleanup(file_types.set_owner_enabled, 'test_child', True)
        self.page = FeaturesPage()
        self.addCleanup(self.page.deleteLater)

    def item(self, name):
        return self.page.toggles[name]

    def test_checkbox_dependency_error_and_reenable_dependencies(self):
        self.item('test_base').setChecked(False)
        self.assertIn('Test Child', self.page.status.text())
        self.assertTrue(registry.is_feature_enabled('test_base'))
        self.item('test_child').setChecked(False)
        self.app.processEvents()
        self.assertFalse(registry.is_feature_enabled('test_child'))
        self.item('test_base').setChecked(False)
        self.app.processEvents()
        self.item('test_child').setChecked(True)
        self.app.processEvents()
        self.assertTrue(registry.is_feature_enabled('test_base'))
        self.assertTrue(registry.is_feature_enabled('test_child'))
        self.assertEqual(self.item('test_base').checkState(), qt.Qt.CheckState.Checked)

    def test_missing_dependency_is_not_checkable(self):
        item = self.item('test_missing')
        self.assertEqual(self.page.states['test_missing'].text(), 'Missing dependency')
        self.assertFalse(item.isEnabled())

    def test_rejected_toggle_keeps_emitting_item_alive_until_signal_returns(self):
        from shiboken6 import isValid
        item = self.item('test_base')
        item.setChecked(False)
        self.assertTrue(isValid(item))
        self.assertTrue(registry.is_feature_enabled('test_base'))
        self.app.processEvents()
        self.assertEqual(self.item('test_base').checkState(), qt.Qt.CheckState.Checked)

    def test_toggle_cards_are_bounded_and_do_not_use_a_table(self):
        self.page.resize(1400, 800); self.page.show(); self.app.processEvents()
        self.assertLessEqual(self.page.content.width(), 820)
        self.assertEqual(self.page.findChildren(qt.QTreeWidget), [])
        self.assertEqual(self.page.cards.count(), 3)
        self.page.close()

    def test_selection_source_and_reset_follow_actual_saved_override(self):
        self.assertIn('Personal overrides · Inherited', self.page.scope_label.text())
        self.assertEqual(self.page.indicators['test_base'].text(), 'Inherited')
        self.assertFalse(self.page.reset_all.isEnabled())
        self.item('test_child').setChecked(False)
        self.app.processEvents()
        self.assertIn('Override', self.page.scope_label.text())
        self.assertEqual(self.page.indicators['test_child'].text(), 'Override')
        # Even an unchanged feature is in the saved whole-selection override.
        self.assertEqual(self.page.indicators['test_base'].text(), 'Override')
        self.assertIn('matches', self.page.indicators['test_base'].toolTip())
        self.assertTrue(self.page.reset_buttons['test_child'].isEnabled())
        self.page.reset_all.click()
        self.app.processEvents()
        self.assertEqual(self.page.indicators['test_child'].text(), 'Inherited')
        self.assertNotIn(('FeatureDefaults', 'disabled_list-str'), self.store.overrides())

    def test_software_scope_and_reset_use_current_defaults(self):
        toggle = self.item('test_child')
        self.page.set_scope('application')
        toggle.setChecked(False)
        self.app.processEvents()
        self.assertEqual(self.page.scope_label.text(), 'Software defaults')
        self.assertEqual(self.page.indicators['test_child'].text(), '')
        self.assertEqual(registry.default_disabled_features(), {'test_child'})
        self.page.set_scope('personal')
        self.assertIs(self.item('test_child'), toggle)
        self.assertTrue(toggle.isChecked())
        self.page.reset_buttons['test_child'].click()
        self.app.processEvents()
        self.assertFalse(toggle.isChecked())
        self.assertEqual(self.page.indicators['test_child'].text(), 'Inherited')

    def test_toggle_preserves_scrolling_and_keyboard_focus(self):
        features = []
        for index in range(30):
            feature = ModuleType(f'features.scroll_{index}')
            feature.FEATURE_NAME = f'scroll_{index}'
            feature.FEATURE_LABEL = f'Scroll {index:02}'
            feature.FEATURE_DESCRIPTION = 'A short description of this feature.'
            features.append(feature)
        registry.load_features.return_value = features
        self.page.refresh()
        self.page.resize(650, 450); self.page.show(); self.app.processEvents()
        self.page.activateWindow(); self.app.processEvents()
        scrollbar = self.page.scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum() - 50)
        toggle = self.item('scroll_29')
        toggle.setFocus(); self.app.processEvents()
        position = scrollbar.value()
        self.assertGreater(position, 0)
        toggle.setChecked(False)
        self.app.processEvents(); self.app.processEvents()
        self.assertIs(self.item('scroll_29'), toggle)
        self.assertEqual(scrollbar.value(), position)
        self.assertIs(self.app.focusWidget(), toggle)
        self.assertEqual(self.page.summaries['scroll_29'].text(), features[-1].FEATURE_DESCRIPTION)
        registry.reset_feature_defaults()
        self.page.close()

    def test_clarified_labels_and_feature_owned_descriptions(self):
        import importlib
        expected = {'minecraft': 'Minecraft Server', 'links': 'Personal Links',
                    'images': 'Image Tools', 'media': 'Media Tools',
                    'perforce': 'Perforce Server', 'flight_sim': 'X-Plane Presets'}
        for name, label in expected.items():
            module = importlib.import_module(f'features.{name}')
            with self.subTest(feature=name):
                self.assertEqual(registry._get_feature_label(module), label)
                self.assertTrue(module.FEATURE_DESCRIPTION)
