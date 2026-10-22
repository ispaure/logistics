"""Compatibility facade for the application's default feature registry.

Use FeatureRegistry with explicit providers for an independent runtime. Existing
module functions retain their signatures and resolve default_registry at call time.
"""
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import TypeVar

from .feature_runtime import FeatureRegistry, FeatureState  # noqa: F401 - public value type
from .contributions import (
    BrowserExtensionContribution, DebugActionContribution, DocumentLauncherContribution,
    FeatureContributions, FolderFeatureContribution, LocalFolderSourceContribution,
    PageContribution, RegisteredContribution, RemoteFolderSourceContribution,
    ServerProviderContribution, WorkflowContribution,
)

T = TypeVar('T')

default_registry = FeatureRegistry(features_path=lambda: Path(__file__).parent)


def feature_settings_store():
    return default_registry.feature_settings_store()


def default_disabled_features():
    return default_registry.default_disabled_features()


def set_feature_default(name, enabled):
    return default_registry.set_feature_default(name, enabled)


def load_feature_preferences(path=None):
    """Load defaults before feature initialization; no package folders are renamed."""
    return default_registry.load_feature_preferences(path)


def feature_overrides():
    """Return explicit per-engine personal choices, including matching defaults."""
    return default_registry.feature_overrides()


def _effective_disabled_features(store):
    return default_registry._effective_disabled_features(store)


def _migrate_feature_overrides(store):
    return default_registry._migrate_feature_overrides(store)


def _save_feature_preferences(changes=None):
    return default_registry._save_feature_preferences(changes)


def reset_feature_defaults():
    """Remove personal choices and restore software defaults atomically."""
    return default_registry.reset_feature_defaults()


def get_feature_names():
    return default_registry.get_feature_names()


def load_features() -> list[ModuleType]:
    return default_registry.load_features()


def get_feature_definition(feature):
    """Return the cached register() declaration, or None for a legacy feature."""
    return default_registry.get_feature_definition(feature)


def _get_feature_name(feature: ModuleType) -> str:
    """Return the stable feature name for a feature module."""
    return default_registry._get_feature_name(feature)


def _get_feature_label(feature: ModuleType) -> str:
    """Return the human-readable feature label used for grouping contributions."""
    return default_registry._get_feature_label(feature)


def _get_dependency_names(feature: ModuleType, attribute_name: str) -> tuple[str, ...]:
    """Return and validate one dependency metadata tuple from a feature."""
    return default_registry._get_dependency_names(feature, attribute_name)


def get_feature_dependencies(feature: ModuleType) -> tuple[str, ...]:
    """Return hard dependencies declared by a feature."""
    return default_registry.get_feature_dependencies(feature)


def get_feature_optional_dependencies(feature: ModuleType) -> tuple[str, ...]:
    """Return optional dependencies declared by a feature."""
    return default_registry.get_feature_optional_dependencies(feature)


def _get_feature_map() -> dict[str, ModuleType]:
    """Return loaded features indexed by stable FEATURE_NAME."""
    return default_registry._get_feature_map()


def _is_feature_available(feature_name: str, feature_map: dict[str, ModuleType],
                          resolving: tuple[str, ...] = ()) -> bool:
    return default_registry._is_feature_available(feature_name, feature_map, resolving)


def is_feature_available(feature_name: str) -> bool:
    """Return whether a feature exists and all of its hard dependencies are available."""
    return default_registry.is_feature_available(feature_name)


def get_available_features() -> list[ModuleType]:
    """Return features whose hard dependencies are all available."""
    return default_registry.get_available_features()


def _log_unavailable_features() -> None:
    """Log features skipped because one or more hard dependencies are unavailable."""
    return default_registry._log_unavailable_features()


def _get_initialization_order(features: list[ModuleType]) -> list[ModuleType]:
    return default_registry._get_initialization_order(features)


def initialize_features() -> list[ModuleType]:
    """Register enabled types before initializing dependencies, once per session."""
    return default_registry.initialize_features()


def _activate_features(features):
    return default_registry._activate_features(features)


def get_enabled_features():
    return default_registry.get_enabled_features()


def is_feature_enabled(name):
    return default_registry.is_feature_enabled(name)


def _feature_groups(feature_map):
    """Present grouped engines together while preserving their runtime identities."""
    return default_registry._feature_groups(feature_map)


def get_feature_states():
    return default_registry.get_feature_states()


def subscribe(callback):
    """Observe session state changes without retaining UI instances."""
    return default_registry.subscribe(callback)


def _notify_changed():
    return default_registry._notify_changed()


def set_feature_enabled(name, enabled):
    """Persist an explicit choice, even when it matches the software default."""
    return default_registry.set_feature_enabled(name, enabled)


def _set_feature_enabled(name, enabled, *, _inherit=False):
    """Enable dependencies and refuse disabling required features."""
    return default_registry._set_feature_enabled(name, enabled, _inherit=_inherit)


def reset_feature_override(name):
    """Remove this visible feature's explicit choices; keep other overrides."""
    return default_registry.reset_feature_override(name)


def _get_startup_hooks(features: list[ModuleType], name: str) -> list[Callable[[], None]]:
    """Validate the full startup plan before invoking any feature hook."""
    return default_registry._get_startup_hooks(features, name)


def get_feature_contributions() -> list[tuple[ModuleType, FeatureContributions]]:
    """Return enabled contributions, checking category types before UI creation."""
    return default_registry.get_feature_contributions()


def _collect_contributions(attribute_name: str) -> list[RegisteredContribution[T]]:
    """Collect one contribution type from every available feature."""
    return default_registry._collect_contributions(attribute_name)


def get_local_folder_sources() -> list[RegisteredContribution[LocalFolderSourceContribution]]:
    """Return all local-folder source contributions in deterministic order."""
    return default_registry.get_local_folder_sources()


def get_remote_folder_sources() -> list[RegisteredContribution[RemoteFolderSourceContribution]]:
    """Return all remote-folder source contributions in deterministic order."""
    return default_registry.get_remote_folder_sources()


def get_folder_features() -> list[RegisteredContribution[FolderFeatureContribution]]:
    """Return all folder-feature contributions."""
    return default_registry.get_folder_features()


def get_server_providers() -> list[RegisteredContribution[ServerProviderContribution]]:
    """Return all server-provider contributions."""
    return default_registry.get_server_providers()


def get_debug_actions() -> list[RegisteredContribution[DebugActionContribution]]:
    """Return all debug-action contributions."""
    return default_registry.get_debug_actions()


def get_workflows() -> list[RegisteredContribution[WorkflowContribution]]:
    """Return all contributed UI workflows."""
    return default_registry.get_workflows()


def get_workflow(workflow_id: str) -> RegisteredContribution[WorkflowContribution]:
    """Return one contributed workflow and enforce globally unique workflow IDs."""
    return default_registry.get_workflow(workflow_id)


def get_pages() -> list[RegisteredContribution[PageContribution]]:
    """Return all standalone page contributions, ordered by page order then name."""
    return default_registry.get_pages()


def get_browser_extensions() -> list[RegisteredContribution[BrowserExtensionContribution]]:
    """Return extensions installed into each Logistics browser host."""
    return default_registry.get_browser_extensions()


def get_settings():
    """Return lazy feature settings, with stable identities within each feature."""
    return default_registry.get_settings()


def get_document_launchers() -> list[RegisteredContribution[DocumentLauncherContribution]]:
    """Return enabled editor categories and their lazy openers in navigation order."""
    return default_registry.get_document_launchers()
