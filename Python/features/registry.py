"""
Feature discovery, dependency handling, initialization, and contribution aggregation for Logistics.
"""

import importlib
from pathlib import Path
from types import ModuleType
from typing import TypeVar

from commonUtils.debugUtils import Severity, log
from features.contributions import (
    DebugActionContribution,
    FeatureContributions,
    FolderFeatureContribution,
    PageContribution,
    RegisteredContribution,
    RemoteFolderSourceContribution,
    ServerProviderContribution,
    WorkflowContribution,
)


T = TypeVar('T')


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

def _get_feature_name(feature: ModuleType) -> str:
    """Return the stable feature name for a feature module."""

    return getattr(feature, 'FEATURE_NAME', feature.__name__.rsplit('.', 1)[-1])


def _get_feature_label(feature: ModuleType) -> str:
    """Return the human-readable feature label used for grouping contributions."""

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

    return _get_dependency_names(feature, 'FEATURE_DEPENDENCIES')


def get_feature_optional_dependencies(feature: ModuleType) -> tuple[str, ...]:
    """Return optional dependencies declared by a feature."""

    return _get_dependency_names(feature, 'FEATURE_OPTIONAL_DEPENDENCIES')


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

def initialize_features() -> list[ModuleType]:
    """Initialize every feature whose hard dependencies are available."""

    _log_unavailable_features()
    features = get_available_features()

    for feature in features:
        initialize = getattr(feature, 'initialize', None)

        if initialize is None:
            continue

        if not callable(initialize):
            raise TypeError(
                f"Feature '{feature.__name__}' defines initialize, "
                f'but it is not callable.'
            )

        initialize()

    return features


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

    for feature in get_available_features():
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
