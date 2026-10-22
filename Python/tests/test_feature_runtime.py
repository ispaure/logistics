"""Independent registry owners isolate state while the module facade stays stable."""
import gc
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from features import registry
from features.registry import FeatureRegistry
from features.contributions import Feature
from features.preferences import load_disabled


class FeatureRuntimeTests(unittest.TestCase):
    def test_enablement_and_preference_files_are_independent(self):
        module = ModuleType('features.isolated_runtime')
        module.FEATURE_NAME = 'isolated_runtime'
        left = FeatureRegistry(feature_loader=lambda: [module])
        right = FeatureRegistry(feature_loader=lambda: [module])
        with TemporaryDirectory() as directory:
            first, second = Path(directory) / 'left.ini', Path(directory) / 'right.ini'
            left.load_feature_preferences(first)
            right.load_feature_preferences(second)
            left.set_feature_enabled('isolated_runtime', False)
            self.assertFalse(left.is_feature_enabled('isolated_runtime'))
            self.assertTrue(right.is_feature_enabled('isolated_runtime'))
            self.assertEqual(load_disabled(first), {'isolated_runtime'})
            self.assertEqual(load_disabled(second), set())
            self.assertFalse(second.exists())

    def test_declarations_and_once_only_initialization_are_per_registry(self):
        initialized = Mock()
        module = ModuleType('features.isolated_runtime')
        module.register = Mock(side_effect=lambda: Feature(id='isolated_runtime', label='Isolated', initialize=initialized))
        left = FeatureRegistry(feature_loader=lambda: [module])
        right = FeatureRegistry(feature_loader=lambda: [module])
        self.assertIsNot(left.get_feature_definition(module), right.get_feature_definition(module))
        left.initialize_features()
        left.initialize_features()
        right.initialize_features()
        self.assertEqual(module.register.call_count, 2)
        self.assertEqual(initialized.call_count, 2)

    def test_observers_unsubscribe_and_retire_without_cross_registry_notifications(self):
        left, right = FeatureRegistry(), FeatureRegistry()
        first, second = Mock(), Mock()
        unsubscribe = left.subscribe(first)
        right.subscribe(second)
        left._notify_changed()
        first.assert_called_once_with()
        second.assert_not_called()
        unsubscribe()
        left._notify_changed()
        first.assert_called_once_with()
        class Observer:
            def changed(self):
                raise AssertionError('Retired observer must not be retained')
        observer = Observer()
        left.subscribe(observer.changed)
        del observer
        gc.collect()
        left._notify_changed()
        self.assertEqual(left._listeners, [])

    def test_settings_provider_is_owned_and_facade_resolves_current_default(self):
        first, second = Mock(), Mock()
        left = FeatureRegistry(feature_loader=lambda: [], settings_provider=lambda: first)
        right = FeatureRegistry(feature_loader=lambda: [], settings_provider=lambda: second)
        self.assertIs(left.feature_settings_store(), first)
        self.assertIs(right.feature_settings_store(), second)
        with patch.object(registry, 'default_registry', left):
            self.assertIs(registry.feature_settings_store(), first)
            self.assertEqual(registry.get_feature_states(), [])
        with patch.object(registry, 'default_registry', right):
            self.assertIs(registry.feature_settings_store(), second)
