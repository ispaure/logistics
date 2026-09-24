"""
Feature discovery and loading for Logistics.
"""

import importlib
from pathlib import Path
from types import ModuleType


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

        if path.name.startswith("_"):
            continue

        if not (path / "__init__.py").is_file():
            continue

        feature_names.append(path.name)

    return sorted(feature_names)


def load_features() -> list[ModuleType]:
    """
    Import and return all available Logistics feature modules.
    """

    features = []

    for feature_name in get_feature_names():
        feature = importlib.import_module(f"{__package__}.{feature_name}")
        features.append(feature)

    return features


def initialize_features() -> list[ModuleType]:
    """
    Load and initialize all available Logistics features.
    """

    features = load_features()

    for feature in features:
        initialize = getattr(feature, "initialize", None)

        if initialize is None:
            continue

        if not callable(initialize):
            raise TypeError(
                f"Feature '{feature.__name__}' defines initialize, "
                f"but it is not callable."
            )

        initialize()

    return features
