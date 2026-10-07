"""
Feature discovery, dependency handling, initialization, and contribution aggregation for Logistics.
"""

import importlib
import weakref
from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import TypeVar

from commonUtils.debugUtils import Severity, log
from commonUtils.features import Feature as CommonFeature
from features.contributions import (
    BrowserExtensionContribution,
    DebugActionContribution,
    FeatureContributions,
    FolderFeatureContribution,
    LocalFolderSourceContribution,
    PageContribution,
    RegisteredContribution,
    RemoteFolderSourceContribution,
    ServerProviderContribution,
    WorkflowContribution,
)


T = TypeVar('T')
_disabled_features = set()
_initialized_features = set()
_listeners = []
_definitions = weakref.WeakKeyDictionary()


# ----------------------------------------------------------------------------------------------------------------------
# FEATURE DISCOVERY

def get_feature_names() -> list[str]:
    """
    Return the package names of features available in the features directory.

    A valid feature is a direct subdirectory containing an __init__.py file.
    """

    features_path = Path(__file__).parent
    feature_names = []

    for path in features_path.iterdir():
        if not path.is_dir():
            continue

        if path.name.startswith('_'):
            continue

        if not (path / '__init__.py').is_file():
            continue

        feature_names.append(path.name)

    return sorted(feature_names)


def load_features() -> list[ModuleType]:
    """Import and return all physically available Logistics feature modules."""

    features = []

    for package_name in get_feature_names():
        feature = importlib.import_module(f'{__package__}.{package_name}')
        features.append(feature)

    return features


# ----------------------------------------------------------------------------------------------------------------------
# FEATURE METADATA / DEPENDENCIES

def get_feature_definition(feature):
    """Return the cached register() declaration, or None for a legacy feature."""
    if isinstance(feature, str):
        feature = _get_feature_map().get(feature)
        if feature is None:
            raise ValueError('Unknown feature')
    register = getattr(feature, 'register', None)
    if register is None:
        return None
    if not callable(register):
        raise TypeError(f"Feature '{feature.__name__}' register must be callable")
    if feature not in _definitions:
        definition = register()
        if not isinstance(definition, CommonFeature):
            raise TypeError(f"Feature '{feature.__name__}' register() must return Feature")
        _definitions[feature] = definition
    return _definitions[feature]


def _get_feature_name(feature: ModuleType) -> str:
    """Return the stable feature name for a feature module."""

    definition = get_feature_definition(feature)
    return definition.id if definition is not None else getattr(feature, 'FEATURE_NAME', feature.__name__.rsplit('.', 1)[-1])


def _get_feature_label(feature: ModuleType) -> str:
    """Return the human-readable feature label used for grouping contributions."""

    definition = get_feature_definition(feature)
    if definition is not None:
        return definition.label
    explicit_label = getattr(feature, 'FEATURE_LABEL', None)

    if explicit_label is not None:
        return explicit_label

    return _get_feature_name(feature).replace('_', ' ').title()


def _get_dependency_names(feature: ModuleType, attribute_name: str) -> tuple[str, ...]:
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


def get_feature_dependencies(feature: ModuleType) -> tuple[str, ...]:
    """Return hard dependencies declared by a feature."""

    definition = get_feature_definition(feature)
    return definition.requires if definition is not None else _get_dependency_names(feature, 'FEATURE_DEPENDENCIES')


def get_feature_optional_dependencies(feature: ModuleType) -> tuple[str, ...]:
    """Return optional dependencies declared by a feature."""

    definition = get_feature_definition(feature)
    return definition.optional_requires if definition is not None else _get_dependency_names(feature, 'FEATURE_OPTIONAL_DEPENDENCIES')


def _get_feature_map() -> dict[str, ModuleType]:
    """Return loaded features indexed by stable FEATURE_NAME."""

    feature_map = {}

    for feature in load_features():
        feature_name = _get_feature_name(feature)

        if feature_name in feature_map:
            raise ValueError(f'Duplicate Logistics feature name: {feature_name}')

        feature_map[feature_name] = feature

    return feature_map


def _is_feature_available(
    feature_name: str,
    feature_map: dict[str, ModuleType],
    resolving: tuple[str, ...] = ()
) -> bool:
    """Resolve hard dependencies recursively for one feature."""

    feature = feature_map.get(feature_name)

    if feature is None:
        return False

    if feature_name in resolving:
        dependency_chain = ' -> '.join((*resolving, feature_name))
        raise RuntimeError(f'Circular Logistics feature dependency: {dependency_chain}')

    next_resolving = (*resolving, feature_name)

    for dependency_name in get_feature_dependencies(feature):
        if not _is_feature_available(dependency_name, feature_map, next_resolving):
            return False

    return True


def is_feature_available(feature_name: str) -> bool:
    """
    Return whether a feature exists and all of its hard dependencies are available.

    Optional dependencies do not affect feature availability.
    """

    return _is_feature_available(feature_name, _get_feature_map())


def get_available_features() -> list[ModuleType]:
    """Return features whose hard dependencies are all available."""

    feature_map = _get_feature_map()

    return [
        feature
        for feature in feature_map.values()
        if _is_feature_available(_get_feature_name(feature), feature_map)
    ]


def _log_unavailable_features() -> None:
    """Log features skipped because one or more hard dependencies are unavailable."""

    feature_map = _get_feature_map()

    for feature_name, feature in feature_map.items():
        if _is_feature_available(feature_name, feature_map):
            continue

        dependencies = get_feature_dependencies(feature)
        missing = [
            dependency_name
            for dependency_name in dependencies
            if not _is_feature_available(dependency_name, feature_map)
        ]

        log(
            Severity.WARNING,
            'Feature Registry',
            f'Skipping feature "{feature_name}". Missing hard dependencies: {", ".join(missing)}'
        )


# ----------------------------------------------------------------------------------------------------------------------
# FEATURE INITIALIZATION

def _get_initialization_order(features: list[ModuleType]) -> list[ModuleType]:
    """Visit hard dependencies first, preserving discovery order where possible."""

    feature_map = {_get_feature_name(feature): feature for feature in features}
    if len(feature_map) != len(features):
        raise ValueError('Duplicate Logistics feature names in initialization list.')

    ordered = []
    initialized_names = set()

    def visit(feature_name: str, chain: tuple[str, ...] = ()) -> None:
        if feature_name in initialized_names:
            return
        if feature_name in chain:
            dependency_chain = ' -> '.join((*chain, feature_name))
            raise RuntimeError(f'Circular Logistics feature dependency: {dependency_chain}')
        if feature_name not in feature_map:
            dependency_chain = ' -> '.join((*chain, feature_name))
            raise RuntimeError(f'Missing Logistics feature dependency: {dependency_chain}')

        feature = feature_map[feature_name]
        for dependency_name in get_feature_dependencies(feature):
            visit(dependency_name, (*chain, feature_name))
        initialized_names.add(feature_name)
        ordered.append(feature)

    for feature in features:
        visit(_get_feature_name(feature))
    return ordered


def initialize_features() -> list[ModuleType]:
    """Register enabled types before initializing dependencies, once per session."""
    _log_unavailable_features()
    features = _get_initialization_order(get_enabled_features())
    _activate_features(features)
    return features


def _activate_features(features):
    # Validate all hooks before starting any work.
    _get_startup_hooks(features, 'register_file_types')
    _get_startup_hooks(features, 'initialize')
    from commonUtils.fileTypes.registry import file_types, register_builtin_file_types
    register_builtin_file_types()
    for feature in features:
        definition = get_feature_definition(feature)
        hook = definition.register_types if definition is not None else getattr(feature, 'register_file_types', None)
        if hook is not None and _get_feature_name(feature) not in _initialized_features:
            with file_types.owner_scope(_get_feature_name(feature)):
                hook()
    for feature in features:
        name = _get_feature_name(feature)
        if name not in _initialized_features:
            definition = get_feature_definition(feature)
            hook = definition.initialize if definition is not None else getattr(feature, 'initialize', None)
            if hook is not None:
                hook()
            _initialized_features.add(name)


def get_enabled_features():
    available = get_available_features()
    feature_map = {_get_feature_name(feature): feature for feature in available}
    enabled = set(feature_map) - _disabled_features
    # Remove consumers of disabled dependencies, including transitive consumers.
    while True:
        filtered = {name for name in enabled if all(dep in enabled for dep in
                    get_feature_dependencies(feature_map[name]))}
        if filtered == enabled:
            return [feature for feature in available if _get_feature_name(feature) in enabled]
        enabled = filtered


def is_feature_enabled(name):
    return any(_get_feature_name(feature) == name for feature in get_enabled_features())


@dataclass(frozen=True)
class FeatureState:
    name: str
    label: str
    available: bool
    enabled: bool
    dependencies: tuple[str, ...]
    dependents: tuple[str, ...]


def get_feature_states():
    feature_map = _get_feature_map()
    enabled = {_get_feature_name(feature) for feature in get_enabled_features()}
    return [FeatureState(name, _get_feature_label(feature), _is_feature_available(name, feature_map),
                         name in enabled, get_feature_dependencies(feature),
                         tuple(other for other, module in feature_map.items()
                               if other in enabled and name in get_feature_dependencies(module)))
            for name, feature in feature_map.items()]


def subscribe(callback):
    """Observe session state changes without retaining UI instances."""
    reference = weakref.WeakMethod(callback) if getattr(callback, '__self__', None) is not None else weakref.ref(callback)
    _listeners.append(reference)
    def unsubscribe(*args):
        if reference in _listeners:
            _listeners.remove(reference)
    return unsubscribe


def _notify_changed():
    for reference in tuple(_listeners):
        callback = reference()
        if callback is None:
            _listeners.remove(reference)
        else:
            try:
                callback()
            except Exception as error:
                log(Severity.ERROR, 'Feature Registry', f'Cannot update a feature observer: {error}')


def set_feature_enabled(name, enabled):
    """Session toggle; enable dependencies and refuse disabling required features."""
    feature_map = _get_feature_map()
    if name not in feature_map:
        raise ValueError(f'Unknown feature: {name}')
    if is_feature_enabled(name) == enabled:
        return
    from commonUtils.fileTypes.registry import file_types
    before = set(_disabled_features)
    def activate(current, value):
        definition = get_feature_definition(feature_map[current])
        if definition is not None:
            definition.set_enabled(value)
        else:
            file_types.set_owner_enabled(current, value)
    if enabled:
        if not _is_feature_available(name, feature_map):
            raise ValueError(f'{name} has missing required dependencies')
        required = set()
        def visit(current):
            if current in required:
                return
            required.add(current)
            for dependency in get_feature_dependencies(feature_map[current]):
                visit(dependency)
        visit(name)
        plan = _get_initialization_order([feature_map[item] for item in feature_map if item in required])
        _disabled_features.difference_update(required)
        for item in required:
            activate(item, True)
        try:
            _activate_features(plan)
        except Exception:
            _disabled_features.clear()
            _disabled_features.update(before)
            for item in required:
                activate(item, item not in before)
            raise
    else:
        dependents = [state.label for state in get_feature_states() if state.enabled and name in state.dependencies]
        if dependents:
            raise ValueError(f'Disable these dependent features first: {", ".join(dependents)}')
        _disabled_features.add(name)
        activate(name, False)
    _notify_changed()


def _get_startup_hooks(features: list[ModuleType], name: str) -> list[Callable[[], None]]:
    """Validate the full startup plan before invoking any feature hook."""

    hooks = []
    for feature in features:
        definition = get_feature_definition(feature)
        hook = (definition.register_types if name == 'register_file_types' else definition.initialize) if definition is not None else getattr(feature, name, None)
        if hook is None:
            continue
        if not callable(hook):
            raise TypeError(f"Feature '{feature.__name__}' {name} must be callable.")
        hooks.append(hook)
    return hooks


# ----------------------------------------------------------------------------------------------------------------------
# CONTRIBUTIONS

def get_feature_contributions() -> list[tuple[ModuleType, FeatureContributions]]:
    """
    Return contribution sets exposed by available features.

    Features with unsatisfied hard dependencies are skipped before
    get_contributions() is called, allowing their implementation modules to
    safely import the dependencies they explicitly require.
    """

    feature_contributions = []

    for feature in get_enabled_features():
        definition = get_feature_definition(feature)
        if definition is not None:
            contributions = definition if isinstance(definition, FeatureContributions) else FeatureContributions()
            feature_contributions.append((feature, contributions))
            continue
        get_contributions = getattr(feature, 'get_contributions', None)

        if get_contributions is None:
            continue

        if not callable(get_contributions):
            raise TypeError(
                f"Feature '{feature.__name__}' defines get_contributions, "
                f'but it is not callable.'
            )

        contributions = get_contributions()

        if not isinstance(contributions, FeatureContributions):
            raise TypeError(
                f"Feature '{feature.__name__}' get_contributions() must return "
                f'FeatureContributions, got {type(contributions).__name__}.'
            )

        feature_contributions.append((feature, contributions))

    return feature_contributions


def _collect_contributions(attribute_name: str) -> list[RegisteredContribution[T]]:
    """Collect one contribution type from every available feature."""

    registered = []

    for feature, contributions in get_feature_contributions():
        feature_name = _get_feature_name(feature)
        feature_label = _get_feature_label(feature)

        for contribution in getattr(contributions, attribute_name):
            registered.append(
                RegisteredContribution(
                    feature_name=feature_name,
                    feature_label=feature_label,
                    contribution=contribution
                )
            )

    return registered


def get_local_folder_sources() -> list[RegisteredContribution[LocalFolderSourceContribution]]:
    """Return all local-folder source contributions in deterministic order."""

    sources = _collect_contributions('local_folder_sources')

    return sorted(
        sources,
        key=lambda registered: (
            registered.contribution.order,
            registered.contribution.name.casefold()
        )
    )


def get_remote_folder_sources() -> list[RegisteredContribution[RemoteFolderSourceContribution]]:
    """Return all remote-folder source contributions in deterministic order."""

    sources = _collect_contributions('remote_folder_sources')

    return sorted(
        sources,
        key=lambda registered: (
            registered.contribution.order,
            registered.contribution.name.casefold()
        )
    )


def get_folder_features() -> list[RegisteredContribution[FolderFeatureContribution]]:
    """Return all folder-feature contributions."""

    return _collect_contributions('folder_features')


def get_server_providers() -> list[RegisteredContribution[ServerProviderContribution]]:
    """Return all server-provider contributions."""

    return _collect_contributions('server_providers')


def get_debug_actions() -> list[RegisteredContribution[DebugActionContribution]]:
    """Return all debug-action contributions."""

    return _collect_contributions('debug_actions')


def get_workflows() -> list[RegisteredContribution[WorkflowContribution]]:
    """Return all contributed UI workflows."""

    return _collect_contributions('workflows')


def get_workflow(workflow_id: str) -> RegisteredContribution[WorkflowContribution]:
    """Return one contributed workflow and enforce globally unique workflow IDs."""

    matches = [
        registered
        for registered in get_workflows()
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


def get_pages() -> list[RegisteredContribution[PageContribution]]:

    """Return all standalone page contributions, ordered by page order then name."""

    pages = _collect_contributions('pages')

    return sorted(
        pages,
        key=lambda registered: (
            registered.contribution.order,
            registered.contribution.name.casefold()
        )
    )


def get_browser_extensions() -> list[RegisteredContribution[BrowserExtensionContribution]]:
    """Return extensions installed into each Logistics browser host."""
    extensions = _collect_contributions('browser_extensions')
    for feature in get_enabled_features():
        definition = get_feature_definition(feature)
        if definition is not None and definition.browser is not None:
            extensions.append(RegisteredContribution(definition.id, definition.label,
                BrowserExtensionContribution(lambda host, definition=definition:
                    definition.install_browser(host.file_browser, host=host))))
    return extensions
