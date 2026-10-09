"""Feature startup order, missing dependencies and contribution contracts."""

from types import ModuleType
from unittest.mock import Mock, patch
import unittest

from features import registry
from features.contributions import Feature, BrowserExtensionContribution, FeatureContributions, WorkflowContribution


def feature(name, dependencies=(), optional_dependencies=(), **hooks):
    module = ModuleType(f'features.{name}')
    module.FEATURE_NAME = name
    module.FEATURE_DEPENDENCIES = dependencies
    module.FEATURE_OPTIONAL_DEPENDENCIES = optional_dependencies
    for key, value in hooks.items():
        setattr(module, key, value)
    return module


class FeatureRegistryTests(unittest.TestCase):
    def setUp(self):
        disabled = patch.object(registry, '_disabled_features', set())
        initialized = patch.object(registry, '_initialized_features', set())
        disabled.start()
        initialized.start()
        self.addCleanup(disabled.stop)
        self.addCleanup(initialized.stop)

    def test_settings_cannot_be_registered_as_folder_sources(self):
        from features.contributions import SettingsContribution
        wrong = FeatureContributions(remote_folder_sources=[
            SettingsContribution('Downloads', 'downloads', lambda parent: None)])
        provider = feature('bad', get_contributions=lambda: wrong)
        with patch.object(registry, 'get_enabled_features', return_value=[provider]):
            with self.assertRaisesRegex(TypeError, 'remote_folder_sources requires RemoteFolderSourceContribution'):
                registry.get_feature_contributions()

    def test_dependencies_initialize_first_and_all_types_register_before_startup(self):
        events = []
        def tracked(name, dependencies=()):
            return feature(name, dependencies,
                           register_file_types=lambda: events.append(('register', name)),
                           initialize=lambda: events.append(('initialize', name)))
        consumer = tracked('consumer', ('middle',))
        unrelated = tracked('unrelated')
        middle = tracked('middle', ('base',))
        base = tracked('base')
        with patch.object(registry, '_log_unavailable_features'), patch.object(
                registry, 'get_available_features', return_value=[consumer, unrelated, middle, base]):
            initialized = registry.initialize_features()
        self.assertEqual([item.FEATURE_NAME for item in initialized], ['base', 'middle', 'consumer', 'unrelated'])
        self.assertEqual(events, [(kind, name) for kind in ('register', 'initialize')
                                 for name in ('base', 'middle', 'consumer', 'unrelated')])

    def test_optional_dependencies_do_not_affect_availability_or_initialization(self):
        consumer = feature('consumer', optional_dependencies=('missing',))
        with patch.object(registry, 'load_features', return_value=[consumer]):
            self.assertTrue(registry.is_feature_available('consumer'))
            self.assertFalse(registry.is_feature_available('missing'))
            self.assertEqual(registry.get_available_features(), [consumer])
        self.assertEqual(registry._get_initialization_order([consumer]), [consumer])

    def test_missing_transitive_dependency_skips_consumer_contributions(self):
        hook = Mock(return_value=FeatureContributions())
        consumer = feature('consumer', ('middle',), get_contributions=hook)
        middle = feature('middle', ('missing',))
        available = feature('available')
        with patch.object(registry, 'load_features', return_value=[consumer, middle, available]):
            self.assertEqual(registry.get_available_features(), [available])
            self.assertEqual(registry.get_feature_contributions(), [])
        hook.assert_not_called()

    def test_cycles_fail_before_registration_or_initialization(self):
        hook = Mock()
        first = feature('first', ('second',), register_file_types=hook, initialize=hook)
        second = feature('second', ('first',), register_file_types=hook, initialize=hook)
        with patch.object(registry, '_log_unavailable_features'), patch.object(
                registry, 'get_available_features', return_value=[first, second]):
            with self.assertRaisesRegex(RuntimeError, 'first -> second -> first'):
                registry.initialize_features()
        hook.assert_not_called()

    def test_invalid_hooks_fail_before_any_startup_side_effect(self):
        for hook_name in ('initialize', 'register_file_types'):
            with self.subTest(hook=hook_name):
                callback = Mock()
                good = feature('good', initialize=callback, register_file_types=callback)
                bad = feature('bad', **{hook_name: 'not callable'})
                with patch.object(registry, '_log_unavailable_features'), patch.object(
                        registry, 'get_available_features', return_value=[good, bad]), patch(
                        'commonUtils.fileTypes.registry.register_builtin_file_types') as builtins:
                    with self.assertRaisesRegex(TypeError, 'callable'):
                        registry.initialize_features()
                callback.assert_not_called()
                builtins.assert_not_called()

    def test_duplicate_names_and_invalid_dependency_metadata_are_rejected(self):
        with patch.object(registry, 'load_features', return_value=[feature('same'), feature('same')]):
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                registry.get_available_features()
        for dependencies in ('one', (None,), ('',)):
            with self.subTest(dependencies=dependencies):
                with self.assertRaises(TypeError):
                    registry.get_feature_dependencies(feature('bad', dependencies))

    def test_workflow_resolution_rejects_duplicates_and_missing_ids(self):
        one = feature('one', get_contributions=lambda: FeatureContributions(
            workflows=[WorkflowContribution('shared', lambda data, parent: None)]))
        two = feature('two', get_contributions=lambda: FeatureContributions(
            workflows=[WorkflowContribution('shared', lambda data, parent: None)]))
        with patch.object(registry, 'load_features', return_value=[one, two]):
            with self.assertRaisesRegex(ValueError, 'Duplicate UI workflow ID'):
                registry.get_workflow('shared')
            with self.assertRaisesRegex(ValueError, 'Unknown UI workflow'):
                registry.get_workflow('missing')

    def test_browser_extensions_preserve_feature_identity_and_are_lazy(self):
        install = Mock()
        extension = BrowserExtensionContribution(install)
        comics = feature('comics', get_contributions=lambda: FeatureContributions(browser_extensions=[extension]))
        with patch.object(registry, 'load_features', return_value=[comics]):
            contributions = registry.get_browser_extensions()
        self.assertEqual(len(contributions), 1)
        self.assertEqual(contributions[0].feature_name, 'comics')
        self.assertEqual(contributions[0].feature_label, 'Comics')
        self.assertIs(contributions[0].contribution, extension)
        install.assert_not_called()

    def test_toggle_filters_contributions_and_dependencies_and_initializes_once(self):
        from commonUtils.fileTypes.registry import file_types
        events = []
        base = feature('toggle_base', initialize=lambda: events.append('base'))
        child = feature('toggle_child', ('toggle_base',), initialize=lambda: events.append('child'),
                        get_contributions=lambda: FeatureContributions(workflows=[WorkflowContribution('toggle', Mock())]))
        with patch.object(registry, 'load_features', return_value=[child, base]), patch.object(registry, '_log_unavailable_features'):
            registry.initialize_features()
            with self.assertRaisesRegex(ValueError, 'Toggle Child'):
                registry.set_feature_enabled('toggle_base', False)
            self.assertTrue(registry.is_feature_enabled('toggle_base'))
            registry.set_feature_enabled('toggle_child', False)
            self.assertFalse(registry.get_workflows())
            registry.set_feature_enabled('toggle_base', False)
            registry.set_feature_enabled('toggle_child', True)
            self.assertTrue(registry.is_feature_enabled('toggle_base'))
            self.assertEqual(len(registry.get_workflows()), 1)
            self.assertEqual(events, ['base', 'child'])
            registry.set_feature_enabled('toggle_child', True)
            self.assertEqual(events, ['base', 'child'])
        file_types.set_owner_enabled('toggle_base', True)
        file_types.set_owner_enabled('toggle_child', True)

    def test_owned_file_types_toggle_and_late_registration_stays_disabled(self):
        from commonUtils.fileUtils import File
        from commonUtils.fileTypes.registry import register_file_type, file_types, file_from_path
        class OwnedFile(File):
            pass
        handles = []
        def register():
            handles.append(register_file_type(OwnedFile, 'toggle_owned', owner='toggle_owned'))
        owned = feature('toggle_owned', register_file_types=register)
        with patch.object(registry, 'load_features', return_value=[owned]), patch.object(registry, '_log_unavailable_features'):
            registry.initialize_features()
            directory_class = type(file_from_path('item.toggle_owned'))
            self.assertIs(directory_class, OwnedFile)
            registry.set_feature_enabled('toggle_owned', False)
            register()
            self.assertIs(type(file_from_path('item.toggle_owned')), File)
            registry.set_feature_enabled('toggle_owned', True)
            self.assertIs(type(file_from_path('item.toggle_owned')), OwnedFile)
        # Remove all distinct handles to avoid leaking test formats.
        for handle in set(handles):
            file_types.unregister(handle)

    def test_failed_enable_restores_state_and_deactivates_partial_registration(self):
        from commonUtils.fileUtils import File
        from commonUtils.fileTypes.registry import register_file_type, file_types, file_from_path
        handles = []
        bad = feature('toggle_bad', register_file_types=lambda: handles.append(register_file_type(File, 'toggle_bad')),
                      initialize=Mock(side_effect=RuntimeError('cannot initialize')))
        registry._disabled_features.add('toggle_bad')
        file_types.set_owner_enabled('toggle_bad', False)
        with patch.object(registry, 'load_features', return_value=[bad]):
            with self.assertRaisesRegex(RuntimeError, 'cannot initialize'):
                registry.set_feature_enabled('toggle_bad', True)
            self.assertFalse(registry.is_feature_enabled('toggle_bad'))
            self.assertIn('toggle_bad', file_types._disabled_owners)
        file_types.set_owner_enabled('toggle_bad', True)
        for handle in handles:
            file_types.unregister(handle)

    def test_first_enable_registers_active_formats_before_initializer(self):
        from commonUtils.fileUtils import File
        from commonUtils.fileTypes.registry import register_file_type, file_types, file_from_path
        class OwnedFile(File):
            pass
        handles = []
        seen = []
        module = feature('toggle_first',
            register_file_types=lambda: handles.append(register_file_type(OwnedFile, 'toggle_first')),
            initialize=lambda: seen.append(type(file_from_path('item.toggle_first'))))
        registry._disabled_features.add('toggle_first')
        file_types.set_owner_enabled('toggle_first', False)
        with patch.object(registry, 'load_features', return_value=[module]):
            registry.set_feature_enabled('toggle_first', True)
            self.assertEqual(seen, [OwnedFile])
            registry.set_feature_enabled('toggle_first', False)
            registry.set_feature_enabled('toggle_first', True)
            self.assertEqual(len(handles), 1)
            self.assertEqual(seen, [OwnedFile])
        for handle in handles:
            file_types.unregister(handle)

    def test_unified_declaration_owns_identity_dependencies_types_and_ui(self):
        from commonUtils.features import FileType, BrowserExtension, SelectionAction
        from commonUtils.fileUtils import File
        from commonUtils.fileTypes.registry import file_types, file_from_path
        class UnifiedFile(File):
            pass
        initialized = []
        definition = Feature(id='unified_registry', label='Unified Registry', requires=('base',),
            file_types=[FileType(UnifiedFile, 'unified_registry')],
            browser=BrowserExtension(actions=[SelectionAction('edit', 'Edit', UnifiedFile, Mock())]),
            workflows=[WorkflowContribution('unified_registry.edit', Mock())],
            initialize=lambda: initialized.append('unified'))
        module = feature('package_name', register=Mock(return_value=definition))
        base = feature('base', initialize=lambda: initialized.append('base'))
        with patch.object(registry, 'load_features', return_value=[module, base]), patch.object(registry, '_log_unavailable_features'):
            self.assertIs(registry.get_feature_definition(module), definition)
            self.assertEqual(registry.get_feature_states()[0].name, 'unified_registry')
            self.assertEqual(registry.get_feature_dependencies(module), ('base',))
            registry.initialize_features()
            self.assertEqual(initialized, ['base', 'unified'])
            self.assertIs(type(file_from_path('file.unified_registry')), UnifiedFile)
            self.assertEqual(registry.get_workflows()[0].feature_label, 'Unified Registry')
            self.assertEqual(registry.get_browser_extensions()[0].feature_name, 'unified_registry')
            registry.set_feature_enabled('unified_registry', False)
            self.assertIs(type(file_from_path('file.unified_registry')), File)
            self.assertFalse(registry.get_workflows())
            self.assertFalse(registry.get_browser_extensions())
            registry.set_feature_enabled('unified_registry', True)
            self.assertEqual(initialized, ['base', 'unified'])
            module.register.assert_called_once()
        for handle in definition.register_types():
            file_types.unregister(handle)

    def test_unified_missing_dependency_never_loads_deferred_format(self):
        from commonUtils.features import FileType
        definition = Feature(id='blocked_unified', requires=('missing',),
                             file_types=[FileType('missing.package:FileClass', 'blocked_unified')])
        module = feature('package', register=lambda: definition)
        with patch.object(registry, 'load_features', return_value=[module]), patch.object(registry, '_log_unavailable_features'):
            self.assertFalse(registry.is_feature_available('blocked_unified'))
            self.assertFalse(registry.get_feature_contributions())
            self.assertFalse(registry.initialize_features())

    def test_invalid_register_contract_fails_before_initialization(self):
        initialize = Mock()
        for register in ('invalid', Mock(return_value='not a Feature')):
            module = feature('invalid_register', register=register, initialize=initialize)
            with patch.object(registry, 'load_features', return_value=[module]):
                with self.assertRaises(TypeError):
                    registry.get_available_features()
        initialize.assert_not_called()
