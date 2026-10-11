"""Discover optional feature packages without letting a failed import hide the app."""
from pathlib import Path
import importlib
from types import ModuleType


def get_feature_names(features_path=None) -> list[str]:
    """
    Return the package names of features available in the features directory.

    A valid feature is a direct subdirectory containing an __init__.py file.
    """

    features_path = Path(features_path) if features_path is not None else Path(__file__).parent
    feature_names = []

    for path in features_path.iterdir():
        if not path.is_dir():
            continue

        if path.name == 'emulation':
            from services.ally_integration import is_active
            if not is_active(path):
                continue

        if path.name.startswith('_'):
            continue

        if not (path / '__init__.py').is_file():
            continue

        feature_names.append(path.name)

    return sorted(feature_names)


def load_named_features(names, package):
    features = []
    for name in names:
        try:
            feature = importlib.import_module(f'{package}.{name}')
        except Exception as error:
            feature = ModuleType(f'{package}.{name}')
            feature.FEATURE_NAME = name
            feature.FEATURE_LOAD_ERROR = f'{type(error).__name__}: {error}'
        features.append(feature)
    return features
