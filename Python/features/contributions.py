"""
Contribution contracts used by Logistics features.

Features contribute capabilities and lazy UI factories without the generic
frontend importing feature-specific implementations.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

from models.folder_entry import FolderEntry


@dataclass(frozen=True)
class UIAction:
    """A user-facing action exposed by a feature."""

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


@dataclass(frozen=True)
class RemoteFolderSource:
    """
    One selectable remote-folder context exposed to the generic Folders page.

    context is backend-owned opaque data passed through FolderEntry objects.
    """

    name: str
    get_remote_names: Callable[[], list[str]]
    context: Any = None


@dataclass(frozen=True)
class RemoteFolderSourceContribution:
    """A provider of selectable remote-folder sources."""

    name: str
    get_sources: Callable[[], list[RemoteFolderSource]]
    order: int = 0


@dataclass(frozen=True)
class FolderFeatureContribution:
    """A feature section that may appear for a logical FolderEntry."""

    name: str
    is_available: Callable[[FolderEntry], bool]
    get_actions: Callable[[FolderEntry], list[UIAction]]
    order: int = 0


@dataclass(frozen=True)
class ServerProviderContribution:
    """A provider of server-like entities for the generic Servers UI."""

    name: str
    get_servers: Callable[[], list[Any]]
    get_display_name: Callable[[Any], str]
    get_actions: Callable[[Any], list[UIAction]]
    get_group_name: Callable[[Any], str] | None = None
    get_details: Callable[[Any], list[tuple[str, str]]] | None = None
    order: int = 0


@dataclass(frozen=True)
class DebugActionContribution:
    """An action contributed to the generic Debug page."""

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


@dataclass(frozen=True)
class WorkflowContribution:
    """
    A lazily opened feature-owned UI workflow.

    The handler receives workflow data and an optional parent widget. Feature UI
    imports should stay inside the handler.
    """

    workflow_id: str
    handler: Callable[[Any, Any], Any]


@dataclass(frozen=True)
class PageContribution:
    """A standalone feature-owned page contributed to the main navigation."""

    name: str
    page_id: str
    create_page: Callable[[Any], Any]
    order: int = 0


@dataclass
class FeatureContributions:
    """All optional contribution types exposed by one feature."""

    remote_folder_sources: list[RemoteFolderSourceContribution] = field(default_factory=list)
    folder_features: list[FolderFeatureContribution] = field(default_factory=list)
    server_providers: list[ServerProviderContribution] = field(default_factory=list)
    debug_actions: list[DebugActionContribution] = field(default_factory=list)
    workflows: list[WorkflowContribution] = field(default_factory=list)
    pages: list[PageContribution] = field(default_factory=list)


T = TypeVar('T')


@dataclass(frozen=True)
class RegisteredContribution(Generic[T]):
    """A contribution paired with the feature that supplied it."""

    feature_name: str
    feature_label: str
    contribution: T
