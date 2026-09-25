"""
Feature discovery, loading, initialization, and UI contribution aggregation for Logistics.
"""

import importlib
from pathlib import Path
from types import ModuleType
from typing import TypeVar

from features.contributions import (
    DebugActionContribution,
    FeatureContributions,
    FolderFeatureContribution,
    PageContribution,
    RegisteredContribution,
    ServerProviderContribution,
)


T = TypeVar('T')


# ----------------------------------------------------------------------------------------------------------------------
# FEATURE DISCOVERY

def get_feature_names() -> list[str]:
    """
    Return the names of feature packages available in the features directory.

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
    """Import and return all available Logistics feature modules."""

    features = []

    for feature_name in get_feature_names():
        feature = importlib.import_module(f'{__package__}.{feature_name}')
        features.append(feature)

    return features


# ----------------------------------------------------------------------------------------------------------------------
# FEATURE INITIALIZATION

def initialize_features() -> list[ModuleType]:
    """Load and initialize all available Logistics features."""

    features = load_features()

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

def _get_feature_name(feature: ModuleType) -> str:
    """Return the stable feature name for a feature module."""

    return getattr(feature, 'FEATURE_NAME', feature.__name__.rsplit('.', 1)[-1])


def _get_feature_label(feature: ModuleType) -> str:
    """Return the human-readable feature label used for grouping contributions."""

    explicit_label = getattr(feature, 'FEATURE_LABEL', None)

    if explicit_label is not None:
        return explicit_label

    return _get_feature_name(feature).replace('_', ' ').title()


def get_feature_contributions() -> list[tuple[ModuleType, FeatureContributions]]:
    """
    Return contribution sets exposed by all loaded features.

    A feature participates by defining:

        get_contributions() -> FeatureContributions

    Features that do not define get_contributions are simply skipped.
    """

    feature_contributions = []

    for feature in load_features():
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
    """Collect one contribution type from every feature."""

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


def get_folder_features() -> list[RegisteredContribution[FolderFeatureContribution]]:
    """Return all folder-feature contributions."""

    return _collect_contributions('folder_features')


def get_server_providers() -> list[RegisteredContribution[ServerProviderContribution]]:
    """Return all server-provider contributions."""

    return _collect_contributions('server_providers')


def get_debug_actions() -> list[RegisteredContribution[DebugActionContribution]]:
    """Return all debug-action contributions."""

    return _collect_contributions('debug_actions')


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
