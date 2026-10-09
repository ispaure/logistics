"""Feature choices survive startup, preserve unrelated settings and roll back failed saves."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import Mock, patch
import unittest
from features import registry
from features.preferences import load_disabled, save_disabled


class FeaturePreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'preferences.ini'
        for name, value in [('_disabled_features', set()), ('_initialized_features', set()), ('_preferences_path', None)]:
            replacement = patch.object(registry, name, value); replacement.start(); self.addCleanup(replacement.stop)
        self.base = ModuleType('features.pref_base'); self.base.FEATURE_NAME = 'pref_base'
        self.child = ModuleType('features.pref_child'); self.child.FEATURE_NAME = 'pref_child'
        self.child.FEATURE_DEPENDENCIES = ('pref_base',)
        self.base.initialize = Mock(); self.child.initialize = Mock()
        replacement = patch.object(registry, 'load_features', return_value=[self.base, self.child])
        replacement.start(); self.addCleanup(replacement.stop)

    def test_saved_choices_load_before_startup_hooks_and_dependencies_reenable(self):
        registry.load_feature_preferences(self.path)
        registry.set_feature_enabled('pref_child', False)
        registry.set_feature_enabled('pref_base', False)
        self.assertEqual(load_disabled(self.path), {'pref_base', 'pref_child'})
        registry._disabled_features.clear()
        registry.load_feature_preferences(self.path)
        self.assertEqual(registry.initialize_features(), [])
        self.base.initialize.assert_not_called(); self.child.initialize.assert_not_called()
        registry.set_feature_enabled('pref_child', True)
        self.assertTrue(registry.is_feature_enabled('pref_base'))
        self.assertEqual(load_disabled(self.path), set())

    def test_save_keeps_other_sections_and_uninstalled_feature_choices(self):
        self.path.write_text('[Window]\nmode=sidebar\n[Features]\ndisabled=not_installed\n')
        registry.load_feature_preferences(self.path)
        registry.set_feature_enabled('pref_child', False)
        self.assertEqual(load_disabled(self.path), {'not_installed', 'pref_child'})
        self.assertIn('mode = sidebar', self.path.read_text())

    def test_failed_save_rolls_back_runtime_state_and_keeps_old_defaults(self):
        registry.load_feature_preferences(self.path)
        registry.set_feature_enabled('pref_child', False)
        original = self.path.read_bytes()
        with patch('features.preferences.os.replace', side_effect=OSError('Read only')):
            with self.assertRaises(OSError):
                registry.set_feature_enabled('pref_child', True)
        self.assertFalse(registry.is_feature_enabled('pref_child'))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_reset_restores_available_features_and_persists_defaults(self):
        save_disabled(self.path, {'pref_child', 'pref_base', 'removed_feature'})
        registry.load_feature_preferences(self.path)
        registry.reset_feature_defaults()
        self.assertTrue(registry.is_feature_enabled('pref_child'))
        self.assertEqual(load_disabled(self.path), set())

    def test_malformed_preferences_keep_recovery_copy_and_use_defaults(self):
        original = b'[Features\ndisabled=broken\n'
        self.path.write_bytes(original)
        registry.load_feature_preferences(self.path)
        self.assertTrue(registry.is_feature_enabled('pref_base'))
        backups = list(self.path.parent.glob('preferences.ini.broken-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        registry.set_feature_enabled('pref_child', False)
        self.assertEqual(load_disabled(self.path), {'pref_child'})

    def test_unreadable_preferences_do_not_block_startup_or_erase_file(self):
        self.path.write_text('[Features]\ndisabled=pref_child\n')
        with patch.object(Path, 'open', side_effect=PermissionError('No access')):
            self.assertEqual(load_disabled(self.path), set())
        self.assertEqual(load_disabled(self.path), {'pref_child'})
