"""
Feature discovery, dependency handling, initialization, and contribution aggregation for Logistics.
"""

import json
import weakref
from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import TypeVar

from commonUtils.runtime.diagnostics import Severity, log
from commonUtils.ui.features import Feature as CommonFeature
from features.contributions import (
    BrowserExtensionContribution,
    DebugActionContribution,
    DocumentLauncherContribution,
    FeatureContributions,
    FolderFeatureContribution,
    LocalFolderSourceContribution,
    PageContribution,
    RegisteredContribution,
    RemoteFolderSourceContribution,
    ServerProviderContribution,
    SettingsContribution,
    WorkflowContribution,
)


from .runtime.preferences import PreferenceState
from .runtime.activation import FeatureActivation
from .runtime.catalog import ContributionCatalog
from .discovery import get_feature_names as discover_feature_names, load_named_features

T = TypeVar('T')


@dataclass(frozen=True)
class FeatureState:
    name: str
    label: str
    available: bool
    enabled: bool
    dependencies: tuple[str, ...]
    dependents: tuple[str, ...]
    members: tuple[str, ...] = ()
    error: str = ''
    description: str = ''


class FeatureRegistry:
    """Feature activation, preferences, declaration cache and observers per runtime.

    Optional loader/settings providers allow isolated registries without replacing
    application globals. Shared file-type machinery remains process-owned.
    """

    def __init__(self, *, feature_loader=None, settings_provider=None, features_path=None):
        self._features_path = features_path or (lambda: Path(__file__).parent)
        self._feature_loader = feature_loader
        self._settings_provider = settings_provider
        self.preferences = PreferenceState(lambda: self.feature_settings_store())
        self.activation = FeatureActivation()
        self.catalog = ContributionCatalog()
        self._listeners = []
        self._definitions = weakref.WeakKeyDictionary()

    @property
    def _disabled_features(self):
        return self.preferences.disabled

    @_disabled_features.setter
    def _disabled_features(self, value):
        self.preferences.disabled = value

    @_disabled_features.deleter
    def _disabled_features(self):
        del self.preferences.disabled

    @property
    def _preferences_path(self):
        return self.preferences.path

    @_preferences_path.setter
    def _preferences_path(self, value):
        self.preferences.path = value

    @_preferences_path.deleter
    def _preferences_path(self):
        del self.preferences.path

    @property
    def _layered_preferences(self):
        return self.preferences.layered

    @_layered_preferences.setter
    def _layered_preferences(self, value):
        self.preferences.layered = value

    @_layered_preferences.deleter
    def _layered_preferences(self):
        del self.preferences.layered

    @property
    def _initialized_features(self):
        return self.activation.initialized

    @_initialized_features.setter
    def _initialized_features(self, value):
        self.activation.initialized = value

    @_initialized_features.deleter
    def _initialized_features(self):
        del self.activation.initialized

    def feature_settings_store(self):
        if self._settings_provider is not None:
            return self._settings_provider()
        from .settings import settings_store
        return settings_store(Path(__file__).resolve().parents[1] / 'configFile.ini')

    def default_disabled_features(self):
        return self.preferences.default_disabled_features()

    def set_feature_default(self, name, enabled):
        feature_map = self._get_feature_map()
        if name not in feature_map:
            raise ValueError(f'Unknown feature: {name}')
        leaders, groups = self._feature_groups(feature_map)
        members = groups[leaders[name]]
        disabled = self.default_disabled_features()
        if enabled:
            required = set()
            def visit(current):
                if current in required:
                    return
                required.add(current)
                for dependency in self.get_feature_dependencies(feature_map[current]):
                    visit(dependency)
            for member in members:
                visit(member)
            disabled.difference_update(required)
        else:
            dependents = [other for other, module in feature_map.items() if other not in members
                          and other not in disabled and any(member in self.get_feature_dependencies(module) for member in members)]
            if dependents:
                raise ValueError('Disable these default dependent features first: ' + ', '.join(dependents))
            disabled.update(members)
        self.feature_settings_store().save({('FeatureDefaults', 'disabled_list-str'): json.dumps(sorted(disabled))}, scope='application')
        self._notify_changed()

    def load_feature_preferences(self, path=None):
        return self.preferences.load_feature_preferences(path)

    def feature_overrides(self):
        return self.preferences.feature_overrides()

    def _effective_disabled_features(self, store):
        return self.preferences._effective_disabled_features(store)

    def _migrate_feature_overrides(self, store):
        return self.preferences._migrate_feature_overrides(store)

    def _save_feature_preferences(self, changes=None):
        return self.preferences._save_feature_preferences(changes)

    def reset_feature_defaults(self):
        """Remove personal choices and restore software defaults atomically."""
        before = set(self._disabled_features)
        feature_map = self._get_feature_map()
        from commonUtils.formats.registry import file_types
        def activate(name, enabled):
            definition = self.get_feature_definition(feature_map[name])
            if definition is not None:
                definition.set_enabled(enabled)
            else:
                file_types.set_owner_enabled(name, enabled)
        try:
            self._disabled_features.clear()
            if self._layered_preferences:
                self._disabled_features.update(self.default_disabled_features())
            for name in feature_map:
                activate(name, name not in self._disabled_features and self._is_feature_available(name, feature_map))
            self.initialize_features()
            self._save_feature_preferences()
        except Exception:
            self._disabled_features.clear()
            self._disabled_features.update(before)
            for name in feature_map:
                activate(name, name not in before and self._is_feature_available(name, feature_map))
            raise
        self._notify_changed()

    def get_feature_names(self):
        return discover_feature_names(self._features_path())

    def load_features(self) -> list[ModuleType]:
        if self._feature_loader is not None:
            return list(self._feature_loader())
        return load_named_features(self.get_feature_names(), __package__)

    def get_feature_definition(self, feature):
        """Return the cached register() declaration, or None for a legacy feature."""
        if isinstance(feature, str):
            feature = self._get_feature_map().get(feature)
            if feature is None:
                raise ValueError('Unknown feature')
        register = getattr(feature, 'register', None)
        if register is None:
            return None
        if not callable(register):
            raise TypeError(f"Feature '{feature.__name__}' register must be callable")
        if feature not in self._definitions:
            definition = register()
            if not isinstance(definition, CommonFeature):
                raise TypeError(f"Feature '{feature.__name__}' register() must return Feature")
            self._definitions[feature] = definition
        return self._definitions[feature]

    def _get_feature_name(self, feature: ModuleType) -> str:
        """Return the stable feature name for a feature module."""

        definition = self.get_feature_definition(feature)
        return definition.id if definition is not None else getattr(feature, 'FEATURE_NAME', feature.__name__.rsplit('.', 1)[-1])

    def _get_feature_label(self, feature: ModuleType) -> str:
        """Return the human-readable feature label used for grouping contributions."""

        definition = self.get_feature_definition(feature)
        if definition is not None:
            return definition.label
        explicit_label = getattr(feature, 'FEATURE_LABEL', None)

        if explicit_label is not None:
            return explicit_label

        return self._get_feature_name(feature).replace('_', ' ').title()

    def _get_dependency_names(self, feature: ModuleType, attribute_name: str) -> tuple[str, ...]:
        """Return and validate one dependency metadata tuple from a feature."""

        dependency_names = getattr(feature, attribute_name, ())

        if not isinstance(dependency_names, (tuple, list)):
            raise TypeError(
                f"Feature '{feature.__name__}' {attribute_name} must be a tuple/list of feature names."
            )

        for dependency_name in dependency_names:
            if not isinstance(dependency_name, str) or not dependency_name:
                raise TypeError(
                    f"Feature '{feature.__name__}' {attribute_name} contains an invalid feature name."
                )

        return tuple(dependency_names)

    def get_feature_dependencies(self, feature: ModuleType) -> tuple[str, ...]:
        """Return hard dependencies declared by a feature."""

        definition = self.get_feature_definition(feature)
        return definition.requires if definition is not None else self._get_dependency_names(feature, 'FEATURE_DEPENDENCIES')

    def get_feature_optional_dependencies(self, feature: ModuleType) -> tuple[str, ...]:
        """Return optional dependencies declared by a feature."""

        definition = self.get_feature_definition(feature)
        return definition.optional_requires if definition is not None else self._get_dependency_names(feature, 'FEATURE_OPTIONAL_DEPENDENCIES')

    def _get_feature_map(self) -> dict[str, ModuleType]:
        """Return loaded features indexed by stable FEATURE_NAME."""

        feature_map = {}

        for feature in self.load_features():
            feature_name = self._get_feature_name(feature)

            if feature_name in feature_map:
                raise ValueError(f'Duplicate Logistics feature name: {feature_name}')

            feature_map[feature_name] = feature

        return feature_map

    def _is_feature_available(self, feature_name: str, feature_map: dict[str, ModuleType],
                              resolving: tuple[str, ...] = ()) -> bool:
        from .runtime.dependencies import available
        return available(feature_name, feature_map, self.get_feature_dependencies, resolving)

    def is_feature_available(self, feature_name: str) -> bool:
        """
        Return whether a feature exists and all of its hard dependencies are available.

        Optional dependencies do not affect feature availability.
        """

        return self._is_feature_available(feature_name, self._get_feature_map())

    def get_available_features(self) -> list[ModuleType]:
        """Return features whose hard dependencies are all available."""

        feature_map = self._get_feature_map()

        return [
            feature
            for feature in feature_map.values()
            if self._is_feature_available(self._get_feature_name(feature), feature_map)
        ]

    def _log_unavailable_features(self) -> None:
        """Log features skipped because one or more hard dependencies are unavailable."""

        feature_map = self._get_feature_map()

        for feature_name, feature in feature_map.items():
            if self._is_feature_available(feature_name, feature_map):
                continue

            dependencies = self.get_feature_dependencies(feature)
            missing = [
                dependency_name
                for dependency_name in dependencies
                if not self._is_feature_available(dependency_name, feature_map)
            ]

            log(
                Severity.WARNING,
                'Feature Registry',
                f'Skipping feature "{feature_name}". Missing hard dependencies: {", ".join(missing)}'
            )

    def _get_initialization_order(self, features: list[ModuleType]) -> list[ModuleType]:
        from .runtime.dependencies import initialization_order
        return initialization_order(features, self._get_feature_name, self.get_feature_dependencies)

    def initialize_features(self) -> list[ModuleType]:
        """Register enabled types before initializing dependencies, once per session."""
        self._log_unavailable_features()
        features = self._get_initialization_order(self.get_enabled_features())
        self._activate_features(features)
        return features

    def _activate_features(self, features):
        return self.activation.activate(features, name_of=self._get_feature_name,
                                        definition_of=self.get_feature_definition)

    def get_enabled_features(self):
        available = self.get_available_features()
        feature_map = {self._get_feature_name(feature): feature for feature in available}
        enabled = set(feature_map) - self._disabled_features
        # Remove consumers of disabled dependencies, including transitive consumers.
        while True:
            filtered = {name for name in enabled if all(dep in enabled for dep in
                        self.get_feature_dependencies(feature_map[name]))}
            if filtered == enabled:
                return [feature for feature in available if self._get_feature_name(feature) in enabled]
            enabled = filtered

    def is_feature_enabled(self, name):
        return any(self._get_feature_name(feature) == name for feature in self.get_enabled_features())

    def _feature_groups(self, feature_map):
        """Present grouped engines together while preserving their runtime identities."""
        leaders = {}
        for name, feature in feature_map.items():
            group = getattr(feature, 'FEATURE_GROUP', None)
            if group is not None and (not isinstance(group, str) or not group):
                raise TypeError(f'{name} FEATURE_GROUP must be a feature name')
            leaders[name] = group if group in feature_map else name
        groups = {}
        for name, leader in leaders.items():
            if leaders[leader] != leader:
                raise ValueError('Feature groups must point directly to their visible leader')
            groups.setdefault(leader, []).append(name)
        return leaders, groups

    def get_feature_states(self):
        feature_map = self._get_feature_map()
        enabled = {self._get_feature_name(feature) for feature in self.get_enabled_features()}
        leaders, groups = self._feature_groups(feature_map)
        states = []
        for name, members in groups.items():
            dependencies = tuple(dict.fromkeys(leaders.get(dependency, dependency)
                for member in members for dependency in self.get_feature_dependencies(feature_map[member])
                if dependency not in members))
            dependents = tuple(dict.fromkeys(leaders[other] for other, module in feature_map.items()
                if other in enabled and other not in members
                and any(member in self.get_feature_dependencies(module) for member in members)))
            states.append(FeatureState(name, self._get_feature_label(feature_map[name]),
                all(self._is_feature_available(member, feature_map) for member in members),
                all(member in enabled for member in members), dependencies, dependents, tuple(members),
                "; ".join(getattr(feature_map[member], 'FEATURE_LOAD_ERROR', '') for member in members).strip('; '),
                getattr(feature_map[name], 'FEATURE_DESCRIPTION', '')))
        return states

    def subscribe(self, callback):
        """Observe session state changes without retaining UI instances."""
        reference = weakref.WeakMethod(callback) if getattr(callback, '__self__', None) is not None else weakref.ref(callback)
        self._listeners.append(reference)
        def unsubscribe(*args):
            if reference in self._listeners:
                self._listeners.remove(reference)
        return unsubscribe

    def _notify_changed(self):
        for reference in tuple(self._listeners):
            callback = reference()
            if callback is None:
                self._listeners.remove(reference)
            else:
                try:
                    callback()
                except Exception as error:
                    log(Severity.ERROR, 'Feature Registry', f'Cannot update a feature observer: {error}')

    def set_feature_enabled(self, name, enabled):
        """Persist an explicit choice, even when it matches the software default."""
        self._set_feature_enabled(name, enabled)

    def _set_feature_enabled(self, name, enabled, *, _inherit=False):
        """Enable dependencies and refuse disabling required features."""
        feature_map = self._get_feature_map()
        if name not in feature_map:
            raise ValueError(f'Unknown feature: {name}')
        leaders, groups = self._feature_groups(feature_map)
        members = groups[leaders[name]]
        if not self._layered_preferences and all(self.is_feature_enabled(member) == enabled for member in members):
            return
        from commonUtils.formats.registry import file_types
        before = set(self._disabled_features)
        changes = {member: None if _inherit else enabled for member in members}
        def activate(current, value):
            definition = self.get_feature_definition(feature_map[current])
            if definition is not None:
                definition.set_enabled(value)
            else:
                file_types.set_owner_enabled(current, value)
        if enabled and not (_inherit and not all(self._is_feature_available(member, feature_map) for member in members)):
            if not all(self._is_feature_available(member, feature_map) for member in members):
                raise ValueError(f'{name} has missing required dependencies')
            required = set()
            def visit(current):
                if current in required:
                    return
                required.add(current)
                for dependency in self.get_feature_dependencies(feature_map[current]):
                    visit(dependency)
            for member in members:
                visit(member)
            plan = self._get_initialization_order([feature_map[item] for item in feature_map if item in required])
            self._disabled_features.difference_update(required)
            changes.update({item: True for item in required & before if item not in members})
            for item in required:
                activate(item, True)
            try:
                self._activate_features(plan)
            except Exception:
                self._disabled_features.clear()
                self._disabled_features.update(before)
                for item in required:
                    activate(item, item not in before)
                raise
        else:
            dependents = list(dict.fromkeys(self._get_feature_label(feature_map[leaders[other]])
                for other, module in feature_map.items() if other not in members and self.is_feature_enabled(other)
                and any(member in self.get_feature_dependencies(module) for member in members)))
            if dependents:
                raise ValueError(f'Disable these dependent features first: {", ".join(dependents)}')
            for member in members:
                if _inherit and member not in self.default_disabled_features():
                    self._disabled_features.discard(member)
                else:
                    self._disabled_features.add(member)
                activate(member, member not in self._disabled_features and self._is_feature_available(member, feature_map))
        try:
            if _inherit:
                self.initialize_features()
            self._save_feature_preferences(changes)
        except Exception:
            self._disabled_features.clear()
            self._disabled_features.update(before)
            for current in feature_map:
                activate(current, current not in before and self._is_feature_available(current, feature_map))
            raise
        self._notify_changed()

    def reset_feature_override(self, name):
        """Remove this visible feature's explicit choices; keep other overrides."""
        feature_map = self._get_feature_map()
        if name not in feature_map:
            raise ValueError(f'Unknown feature: {name}')
        leaders, groups = self._feature_groups(feature_map)
        members = groups[leaders[name]]
        defaults = self.default_disabled_features()
        self._set_feature_enabled(name, all(member not in defaults for member in members), _inherit=True)

    def _get_startup_hooks(self, features, name):
        return self.activation.hooks(features, self.get_feature_definition, name)

    def get_feature_contributions(self):
        return self.catalog.get(self.get_enabled_features(), self.get_feature_definition)

    def _collect_contributions(self, attribute_name):
        return self.catalog.collect(self.get_feature_contributions(), attribute_name,
                                    self._get_feature_name, self._get_feature_label)

    def get_local_folder_sources(self) -> list[RegisteredContribution[LocalFolderSourceContribution]]:
        """Return all local-folder source contributions in deterministic order."""

        sources = self._collect_contributions('local_folder_sources')

        return sorted(
            sources,
            key=lambda registered: (
                registered.contribution.order,
                registered.contribution.name.casefold()
            )
        )

    def get_remote_folder_sources(self) -> list[RegisteredContribution[RemoteFolderSourceContribution]]:
        """Return all remote-folder source contributions in deterministic order."""

        sources = self._collect_contributions('remote_folder_sources')

        return sorted(
            sources,
            key=lambda registered: (
                registered.contribution.order,
                registered.contribution.name.casefold()
            )
        )

    def get_folder_features(self) -> list[RegisteredContribution[FolderFeatureContribution]]:
        """Return all folder-feature contributions."""

        return self._collect_contributions('folder_features')

    def get_server_providers(self) -> list[RegisteredContribution[ServerProviderContribution]]:
        """Return all server-provider contributions."""

        return self._collect_contributions('server_providers')

    def get_debug_actions(self) -> list[RegisteredContribution[DebugActionContribution]]:
        """Return all debug-action contributions."""

        return self._collect_contributions('debug_actions')

    def get_workflows(self) -> list[RegisteredContribution[WorkflowContribution]]:
        """Return all contributed UI workflows."""

        return self._collect_contributions('workflows')

    def get_workflow(self, workflow_id: str) -> RegisteredContribution[WorkflowContribution]:
        """Return one contributed workflow and enforce globally unique workflow IDs."""

        matches = [
            registered
            for registered in self.get_workflows()
            if registered.contribution.workflow_id == workflow_id
        ]

        if not matches:
            raise ValueError(f'Unknown UI workflow: {workflow_id}')

        if len(matches) > 1:
            feature_names = ', '.join(
                sorted(registered.feature_name for registered in matches)
            )
            raise ValueError(
                f'Duplicate UI workflow ID "{workflow_id}" contributed by: {feature_names}'
            )

        return matches[0]

    def get_pages(self) -> list[RegisteredContribution[PageContribution]]:

        """Return all standalone page contributions, ordered by page order then name."""

        pages = self._collect_contributions('pages')

        return sorted(
            pages,
            key=lambda registered: (
                registered.contribution.order,
                registered.contribution.name.casefold()
            )
        )

    def get_browser_extensions(self) -> list[RegisteredContribution[BrowserExtensionContribution]]:
        """Return extensions installed into each Logistics browser host."""
        extensions = self._collect_contributions('browser_extensions')
        for feature in self.get_enabled_features():
            definition = self.get_feature_definition(feature)
            if definition is not None and definition.browser is not None:
                extensions.append(RegisteredContribution(definition.id, definition.label,
                    BrowserExtensionContribution(lambda host, definition=definition:
                        definition.install_browser(host.file_browser, host=host))))
        return extensions

    def get_settings(self):
        """Return lazy feature settings, with stable identities within each feature."""
        entries = self._collect_contributions('settings')
        seen = set()
        for entry in entries:
            key = (entry.feature_name, entry.contribution.settings_id)
            if key in seen:
                raise ValueError(f'Duplicate settings ID for {entry.feature_name}: {key[1]}')
            seen.add(key)
        return sorted(entries, key=lambda entry: (entry.contribution.order, entry.contribution.name.casefold()))

    def get_document_launchers(self) -> list[RegisteredContribution[DocumentLauncherContribution]]:
        """Return enabled editor categories and their lazy openers in navigation order."""
        return sorted(self._collect_contributions('document_launchers'),
                      key=lambda entry: (entry.contribution.order, entry.contribution.name.casefold()))


