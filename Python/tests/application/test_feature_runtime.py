"""Independent registry owners isolate state while the application has an explicit runtime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import gc
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import Mock

from features.application import registry
from features.feature_runtime import FeatureRegistry
from features.contributions import BrowserExtensionContribution, Feature, FeatureContributions
from features.preferences import load_disabled


class FeatureRuntimeTests(unittest.TestCase):
    def test_states_use_one_discovery_and_refresh_on_the_next_call(self):
        base = ModuleType('features.base')
        consumer = ModuleType('features.consumer')
        consumer.FEATURE_DEPENDENCIES = ('base',)
        loader = Mock(side_effect=[[consumer, base], [consumer]])
        runtime = FeatureRegistry(feature_loader=loader)

        states = runtime.get_feature_states()
        self.assertEqual([(state.name, state.available, state.enabled) for state in states],
                         [('consumer', True, True), ('base', True, True)])
        self.assertEqual(states[0].dependencies, ('base',))
        self.assertEqual(states[1].dependents, ('consumer',))
        loader.assert_called_once_with()

        states = runtime.get_feature_states()
        self.assertEqual([(state.name, state.available, state.enabled) for state in states],
                         [('consumer', False, False)])
        self.assertEqual(states[0].dependencies, ('base',))
        self.assertEqual(loader.call_count, 2)

    def test_browser_roster_is_shared_by_legacy_and_unified_extensions_and_refreshes(self):
        from commonUtils.ui.features import BrowserExtension
        rosters = []
        installers = []
        for name in ('first', 'second'):
            install = Mock()
            installers.append(install)
            legacy = ModuleType(f'features.{name}_legacy')
            legacy.get_contributions = Mock(return_value=FeatureContributions(
                browser_extensions=[BrowserExtensionContribution(install)]))
            modern = ModuleType(f'features.{name}_modern')
            modern.register = Mock(return_value=Feature(
                id=f'{name}_modern', label=f'{name.title()} Modern', browser=BrowserExtension()))
            rosters.append([modern, legacy])
        loader = Mock(side_effect=[rosters[0], rosters[1], rosters[0]])
        runtime = FeatureRegistry(feature_loader=loader)

        for calls, name in enumerate(('first', 'second', 'first'), start=1):
            extensions = runtime.get_browser_extensions()
            self.assertEqual([entry.feature_name for entry in extensions],
                             [f'{name}_legacy', f'{name}_modern'])
            self.assertEqual([entry.feature_label for entry in extensions],
                             [f'{name.title()} Legacy', f'{name.title()} Modern'])
            self.assertEqual(loader.call_count, calls)
        for modern, legacy in rosters:
            modern.register.assert_called_once_with()
        for install in installers:
            install.assert_not_called()

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

    def test_settings_provider_and_application_runtime_have_explicit_owners(self):
        first, second = Mock(), Mock()
        left = FeatureRegistry(feature_loader=lambda: [], settings_provider=lambda: first)
        right = FeatureRegistry(feature_loader=lambda: [], settings_provider=lambda: second)
        self.assertIs(left.feature_settings_store(), first)
        self.assertIs(right.feature_settings_store(), second)
        from features import application
        self.assertIs(application.registry, registry)
        self.assertIsInstance(registry, FeatureRegistry)
