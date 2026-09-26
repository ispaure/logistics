"""
UI and discovery contribution contracts for Logistics features.

Features may contribute to any combination of application surfaces without
depending on each other or on concrete frontend implementations.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

from models.folder_entry import FolderEntry


# ----------------------------------------------------------------------------------------------------------------------
# SHARED ACTION

@dataclass(frozen=True)
class UIAction:
    """
    A user-facing action exposed by a feature.

    An action either executes a backend callback directly or requests a named
    UI workflow. UI workflows are resolved by the frontend, keeping features
    independent from concrete PySide implementations.
    """

    name: str
    callback: Callable[[], Any] | None = None
    description: str | None = None
    destructive: bool = False
    enabled: bool = True
    workflow_id: str | None = None
    workflow_data: Any = None

    def __post_init__(self):
        has_callback = self.callback is not None
        has_workflow = self.workflow_id is not None

        if has_callback == has_workflow:
            raise ValueError(
                f'UIAction "{self.name}" must define exactly one of callback or workflow_id.'
            )


# ----------------------------------------------------------------------------------------------------------------------
# REMOTE FOLDER SOURCES

@dataclass(frozen=True)
class RemoteFolderSourceContribution:
    """
    A provider of configured remote logical folder names.

    The generic folder-entry service receives these names as data and therefore
    does not need to know which feature or storage backend supplied them.
    """

    name: str
    get_remote_names: Callable[[], list[str]]
    order: int = 0


# ----------------------------------------------------------------------------------------------------------------------
# FOLDER CONTRIBUTIONS

@dataclass(frozen=True)
class FolderFeatureContribution:
    """
    A feature section that may appear for a logical FolderEntry.
    """

    name: str
    is_available: Callable[[FolderEntry], bool]
    get_actions: Callable[[FolderEntry], list[UIAction]]
    order: int = 0


# ----------------------------------------------------------------------------------------------------------------------
# SERVER CONTRIBUTIONS

@dataclass(frozen=True)
class ServerProviderContribution:
    """
    A provider of server-like entities for the Servers UI.

    Server objects are intentionally opaque to the shared UI layer. Providers
    supply the display name, optional group, optional details, and actions for
    each server they return.
    """

    name: str
    get_servers: Callable[[], list[Any]]
    get_display_name: Callable[[Any], str]
    get_actions: Callable[[Any], list[UIAction]]
    get_group_name: Callable[[Any], str] | None = None
    get_details: Callable[[Any], list[tuple[str, str]]] | None = None
    order: int = 0


# ----------------------------------------------------------------------------------------------------------------------
# DEBUG CONTRIBUTIONS

@dataclass(frozen=True)
class DebugActionContribution:
    """
    An action contributed to the dynamically generated Debug UI.

    Like UIAction, a Debug action may either execute directly or request a
    named frontend workflow.
    """

    name: str
    callback: Callable[[], Any] | None = None
    description: str | None = None
    destructive: bool = False
    enabled: bool = True
    workflow_id: str | None = None
    workflow_data: Any = None
    order: int = 0

    def __post_init__(self):
        has_callback = self.callback is not None
        has_workflow = self.workflow_id is not None

        if has_callback == has_workflow:
            raise ValueError(
                f'DebugActionContribution "{self.name}" must define exactly one '
                f'of callback or workflow_id.'
            )


# ----------------------------------------------------------------------------------------------------------------------
# STANDALONE PAGE CONTRIBUTIONS

@dataclass(frozen=True)
class PageContribution:
    """
    A standalone page contributed to the main Logistics navigation.

    page_id resolves to ``ui_new.pages.<page_id>``. The page class follows the
    ``<PageId>Page`` naming convention, keeping feature packages independent
    from concrete PySide page implementations.

    order is shared with core tabs. Current core positions are:
      - Folders: 0
      - Servers: 20
      - Debug: 100
    """

    name: str
    page_id: str
    order: int = 0


# ----------------------------------------------------------------------------------------------------------------------
# FEATURE CONTRIBUTIONS

@dataclass
class FeatureContributions:
    """
    Contributions exposed by one feature.

    Every contribution type is optional. A feature may contribute to several
    application surfaces, one surface, or none at all.
    """

    remote_folder_sources: list[RemoteFolderSourceContribution] = field(default_factory=list)
    folder_features: list[FolderFeatureContribution] = field(default_factory=list)
    server_providers: list[ServerProviderContribution] = field(default_factory=list)
    debug_actions: list[DebugActionContribution] = field(default_factory=list)
    pages: list[PageContribution] = field(default_factory=list)


T = TypeVar('T')


@dataclass(frozen=True)
class RegisteredContribution(Generic[T]):
    """
    A contribution paired with the feature that supplied it.
    """

    feature_name: str
    feature_label: str
    contribution: T
