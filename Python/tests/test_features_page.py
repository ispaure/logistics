"""Feature controls display session state and handle required dependencies."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from types import ModuleType
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.fileTypes.registry import file_types
from features import registry
from features.contributions import FeatureContributions
from ui_new.pages.features import FeaturesPage


class FeaturesPageTests(unittest.TestCase):
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
        for target, value in [('_disabled_features', set()), ('_initialized_features', set())]:
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
