"""Category contracts and contribution collection, separate from feature state."""
from types import ModuleType
from typing import TypeVar
from ..contributions import (
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
T = TypeVar("T")


class ContributionCatalog:
    def get(self, features, definition_of) -> list[tuple[ModuleType, FeatureContributions]]:
        """Return enabled contributions, checking category types before UI creation."""
        feature_contributions = []
        expected_types = {
            'local_folder_sources': LocalFolderSourceContribution,
            'remote_folder_sources': RemoteFolderSourceContribution,
            'folder_features': FolderFeatureContribution,
            'server_providers': ServerProviderContribution,
            'debug_actions': DebugActionContribution,
            'workflows': WorkflowContribution,
            'pages': PageContribution,
            'document_launchers': DocumentLauncherContribution,
            'settings': SettingsContribution,
            'browser_extensions': BrowserExtensionContribution,
        }
        for feature in features:
            definition = definition_of(feature)
            if definition is not None:
                contributions = definition if isinstance(definition, FeatureContributions) else FeatureContributions()
            else:
                get_contributions = getattr(feature, 'get_contributions', None)
                if get_contributions is None:
                    continue
                if not callable(get_contributions):
                    raise TypeError(f"Feature '{feature.__name__}' defines get_contributions, but it is not callable.")
                contributions = get_contributions()
                if not isinstance(contributions, FeatureContributions):
                    raise TypeError(f"Feature '{feature.__name__}' get_contributions() must return "
                                    f'FeatureContributions, got {type(contributions).__name__}.')
            for category, expected in expected_types.items():
                for item in getattr(contributions, category):
                    if not isinstance(item, expected):
                        raise TypeError(f"Feature '{feature.__name__}' {category} requires "
                                        f'{expected.__name__}, got {type(item).__name__}.')
            feature_contributions.append((feature, contributions))
        return feature_contributions


    def collect(self, contributions_by_feature, attribute_name: str, name_of, label_of) -> list[RegisteredContribution[T]]:
        """Collect one contribution type from every available feature."""

        registered = []

        for feature, contributions in contributions_by_feature:
            feature_name = name_of(feature)
            feature_label = label_of(feature)

            for contribution in getattr(contributions, attribute_name):
                registered.append(
                    RegisteredContribution(
                        feature_name=feature_name,
                        feature_label=feature_label,
                        contribution=contribution
                    )
                )

        return registered
