"""Feature choices survive startup, preserve unrelated settings and roll back failed saves."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import Mock, patch
import unittest
from features.application import registry
from features.preferences import load_disabled, save_disabled


class FeaturePreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'preferences.ini'
        for name, value in [('_disabled_features', set()), ('_initialized_features', set()), ('_preferences_path', None), ('_layered_preferences', False)]:
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

    def test_software_defaults_and_personal_reset_keep_layers_separate(self):
        from commonUtils.configuration.layered import register_settings
        defaults = self.path.with_name('defaults.ini')
        defaults.write_text('[FeatureDefaults]\ndisabled_list-str = []\n')
        store = register_settings(defaults, self.path.with_name('personal.ini'))
        with patch('features.application.registry.feature_settings_store', return_value=store), \
                patch('features.preferences.preferences_path', return_value=self.path):
            registry.set_feature_default('pref_child', False)
            self.assertEqual(registry.default_disabled_features(), {'pref_child'})
            self.assertNotIn(('FeatureDefaults', 'disabled_list-str'), store.overrides())
            registry.load_feature_preferences()
            self.assertFalse(registry.is_feature_enabled('pref_child'))
            registry.set_feature_enabled('pref_child', True)
            self.assertEqual(store.overrides()['FeatureOverrides', 'pref_child_bool'], 'true')
            self.assertEqual(registry.default_disabled_features(), {'pref_child'})
            registry.reset_feature_defaults()
            self.assertFalse(registry.is_feature_enabled('pref_child'))
            self.assertNotIn(('FeatureDefaults', 'disabled_list-str'), store.overrides())

    def test_legacy_feature_choices_migrate_once_and_do_not_return_after_reset(self):
        from commonUtils.configuration.layered import register_settings
        defaults = self.path.with_name('defaults.ini')
        defaults.write_text('[FeatureDefaults]\ndisabled_list-str = []\n')
        store = register_settings(defaults, self.path.with_name('personal.ini'))
        save_disabled(self.path, {'pref_child'})
        original = self.path.read_bytes()
        with patch('features.application.registry.feature_settings_store', return_value=store), \
                patch('features.preferences.preferences_path', return_value=self.path):
            registry.load_feature_preferences()
            self.assertFalse(registry.is_feature_enabled('pref_child'))
            registry.reset_feature_defaults()
            registry.load_feature_preferences()
            self.assertTrue(registry.is_feature_enabled('pref_child'))
        self.assertEqual(self.path.read_bytes(), original)

    def layered_store(self):
        from commonUtils.configuration.layered import register_settings
        defaults = self.path.with_name('defaults.ini')
        defaults.write_text('[FeatureDefaults]\ndisabled_list-str = []\n')
        store = register_settings(defaults, self.path.with_name('personal.ini'))
        replacement = patch.object(registry, 'feature_settings_store', return_value=store)
        replacement.start(); self.addCleanup(replacement.stop)
        replacement = patch('features.preferences.preferences_path', return_value=self.path)
        replacement.start(); self.addCleanup(replacement.stop)
        registry.load_feature_preferences()
        return store

    def test_matching_values_remain_explicit_and_untouched_defaults_flow_through(self):
        store = self.layered_store()
        registry.set_feature_enabled('pref_child', False)
        registry.set_feature_enabled('pref_child', True)
        self.assertEqual(registry.feature_overrides(), {'pref_child': True})
        self.assertEqual(store.overrides(), {('FeatureOverrides', 'pref_child_bool'): 'true'})
        registry.set_feature_default('pref_child', False)
        registry.load_feature_preferences()
        self.assertTrue(registry.is_feature_enabled('pref_child'))
        registry.reset_feature_override('pref_child')
        self.assertFalse(registry.is_feature_enabled('pref_child'))
        self.assertEqual(registry.feature_overrides(), {})
        registry.set_feature_default('pref_child', True)
        registry.load_feature_preferences()
        self.assertTrue(registry.is_feature_enabled('pref_child'))

    def test_matching_disabled_override_blocks_future_default_enable(self):
        store = self.layered_store()
        registry.set_feature_default('pref_child', False)
        registry.load_feature_preferences()
        registry.set_feature_enabled('pref_child', True)
        registry.set_feature_enabled('pref_child', False)
        self.assertEqual(registry.feature_overrides(), {'pref_child': False})
        registry.set_feature_default('pref_child', True)
        registry.load_feature_preferences()
        self.assertFalse(registry.is_feature_enabled('pref_child'))
        registry.reset_feature_override('pref_child')
        self.assertTrue(registry.is_feature_enabled('pref_child'))
        self.assertNotIn(('FeatureOverrides', 'pref_child_bool'), store.overrides())

    def test_dependencies_get_only_necessary_overrides_and_reset_is_checked(self):
        store = self.layered_store()
        registry.set_feature_default('pref_child', False)
        registry.set_feature_default('pref_base', False)
        registry.load_feature_preferences()
        registry.set_feature_enabled('pref_child', True)
        self.assertEqual(registry.feature_overrides(), {'pref_base': True, 'pref_child': True})
        before = store.personal.read_bytes()
        with self.assertRaisesRegex(ValueError, 'dependent'):
            registry.reset_feature_override('pref_base')
        self.assertEqual(store.personal.read_bytes(), before)
        self.assertTrue(registry.is_feature_enabled('pref_base'))
        registry.reset_feature_override('pref_child')
        self.assertEqual(registry.feature_overrides(), {'pref_base': True})
        registry.reset_feature_override('pref_base')
        self.assertEqual(registry.feature_overrides(), {})

    def test_legacy_snapshot_migrates_differences_and_preserves_unknown_choices(self):
        store = self.layered_store()
        store.save({('FeatureDefaults', 'disabled_list-str'): '["pref_child", "not_installed"]',
                    ('Other', 'choice'): 'kept'})
        # Simulate a pre-v2 installation's migration ledger.
        from features.settings import migration_ledger
        ledger = migration_ledger(store)
        ledger.path.write_text('[Migrations]\nfeature-enable-v1=done\n')
        registry.load_feature_preferences()
        self.assertEqual(registry.feature_overrides(), {'pref_child': False, 'not_installed': False})
        self.assertNotIn(('FeatureDefaults', 'disabled_list-str'), store.overrides())
        self.assertNotIn(('FeatureOverrides', 'pref_base_bool'), store.overrides())
        self.assertEqual(store.overrides()['Other', 'choice'], 'kept')
        registry.reset_feature_defaults()
        registry.load_feature_preferences()
        self.assertEqual(registry.feature_overrides(), {})
        self.assertEqual(store.overrides(), {('Other', 'choice'): 'kept'})

    def test_failed_sparse_save_and_arrow_reset_roll_back_runtime(self):
        store = self.layered_store()
        registry.set_feature_enabled('pref_child', False)
        original = store.personal.read_bytes()
        with patch.object(store, 'save', side_effect=OSError('Read only')):
            with self.assertRaises(OSError):
                registry.reset_feature_override('pref_child')
            self.assertFalse(registry.is_feature_enabled('pref_child'))
            with self.assertRaises(OSError):
                registry.set_feature_enabled('pref_child', True)
            self.assertFalse(registry.is_feature_enabled('pref_child'))
        self.assertEqual(store.personal.read_bytes(), original)

    def test_group_arrow_restores_each_engine_default_and_initializes_enabled_members(self):
        store = self.layered_store()
        self.child.FEATURE_GROUP = 'pref_base'
        store.save({('FeatureDefaults', 'disabled_list-str'): '["pref_child"]'}, scope='application')
        registry.load_feature_preferences()
        registry.set_feature_enabled('pref_base', False)
        self.assertEqual(registry.feature_overrides(), {'pref_base': False, 'pref_child': False})
        registry.reset_feature_override('pref_base')
        self.assertEqual(registry.feature_overrides(), {})
        self.assertTrue(registry.is_feature_enabled('pref_base'))
        self.assertFalse(registry.is_feature_enabled('pref_child'))
        self.base.initialize.assert_called_once()

    def test_failed_snapshot_migration_preserves_selection_and_retries(self):
        store = self.layered_store()
        store.save({('FeatureDefaults', 'disabled_list-str'): '["pref_child"]'})
        from features.settings import migration_ledger
        ledger = migration_ledger(store)
        ledger.path.write_text('[Migrations]\nfeature-enable-v1=done\n')
        original = store.personal.read_bytes()
        with patch.object(store, 'save', side_effect=OSError('Read only')):
            registry.load_feature_preferences()
        self.assertFalse(registry.is_feature_enabled('pref_child'))
        self.assertEqual(store.personal.read_bytes(), original)
        self.assertEqual(ledger.state('feature-overrides-v2'), 'pending')
        registry.load_feature_preferences()
        self.assertEqual(registry.feature_overrides(), {'pref_child': False})
        self.assertEqual(ledger.state('feature-overrides-v2'), 'done')
