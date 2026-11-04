"""Feature groups toggle dependencies atomically without constructing a reader."""
from types import ModuleType
from unittest import TestCase
from unittest.mock import Mock, patch
from commonUtils.testing.stages import TestStage
from commonUtils.ui.features import Feature
from features.application import registry

TEST_STAGE = TestStage.REGRESSION


class FeatureGroupTests(TestCase):
    def engines(self):
        owner = ModuleType('features.owner')
        child = ModuleType('features.child')
        dependency = ModuleType('features.dependency')
        owner.register = lambda: Feature(id='owner', label='Reading')
        child.register = lambda: Feature(id='child', requires=('dependency',))
        dependency.register = lambda: Feature(id='dependency')
        child.FEATURE_GROUP = 'owner'
        return owner, child, dependency

    def test_group_has_one_state_and_toggles_all_engines_with_dependencies(self):
        engines = self.engines()
        with patch.object(registry, 'load_features', return_value=list(engines)), \
             patch.object(registry, '_disabled_features', set()), patch.object(registry, '_initialized_features', set()):
            states = {state.name: state for state in registry.get_feature_states()}
            self.assertEqual(set(states), {'owner', 'dependency'})
            self.assertEqual(states['owner'].members, ('owner', 'child'))
            self.assertEqual(states['owner'].dependencies, ('dependency',))
            with self.assertRaisesRegex(ValueError, 'Reading'):
                registry.set_feature_enabled('dependency', False)
            registry.set_feature_enabled('owner', False)
            self.assertFalse(registry.is_feature_enabled('owner'))
            self.assertFalse(registry.is_feature_enabled('child'))
            registry.set_feature_enabled('dependency', False)
            registry.set_feature_enabled('child', True)
            self.assertTrue(all(registry.is_feature_enabled(name) for name in ('owner', 'child', 'dependency')))

    def test_failed_group_enable_rolls_back_both_engines(self):
        engines = self.engines()
        engines[1].register = lambda: Feature(id='child', initialize=Mock(side_effect=RuntimeError('Cannot initialize')))
        with patch.object(registry, 'load_features', return_value=list(engines)), \
             patch.object(registry, '_disabled_features', {'owner', 'child'}), patch.object(registry, '_initialized_features', set()):
            with self.assertRaisesRegex(RuntimeError, 'Cannot initialize'):
                registry.set_feature_enabled('owner', True)
            self.assertEqual(registry._disabled_features, {'owner', 'child'})
