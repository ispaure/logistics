"""
UI contribution contracts for Logistics features.

Features may contribute to any combination of UI surfaces without depending
on each other or on the concrete UI implementation.
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

    The callback should already be bound to any model or context it needs.
    """

    name: str
    callback: Callable[[], Any]
    description: str | None = None
    destructive: bool = False
    enabled: bool = True


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

    Server objects are intentionally opaque to the shared UI layer.
    """

    name: str
    get_servers: Callable[[], list[Any]]
    get_display_name: Callable[[Any], str]
    get_actions: Callable[[Any], list[UIAction]]
    get_group_name: Callable[[Any], str] | None = None
    order: int = 0


# ----------------------------------------------------------------------------------------------------------------------
# DEBUG CONTRIBUTIONS

@dataclass(frozen=True)
class DebugActionContribution:
    """
    An action contributed to the dynamically generated Debug UI.
    """

    name: str
    callback: Callable[[], Any]
    description: str | None = None
    destructive: bool = False
    order: int = 0


# ----------------------------------------------------------------------------------------------------------------------
# STANDALONE PAGE CONTRIBUTIONS

@dataclass(frozen=True)
class PageContribution:
    """
    A standalone page contributed to the main Logistics navigation.

    page_id identifies the UI implementation without making the feature import
    a concrete PySide page or other frontend code.
    """

    name: str
    page_id: str
    order: int = 0


# ----------------------------------------------------------------------------------------------------------------------
# FEATURE CONTRIBUTIONS

@dataclass
class FeatureContributions:
    """
    All UI contributions exposed by one feature.

    Every contribution type is optional. A feature may contribute to several
    UI surfaces, one surface, or none at all.
    """

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
