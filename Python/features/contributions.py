"""
Contribution contracts used by Logistics features.

Features contribute capabilities and lazy UI factories without the generic
frontend importing feature-specific implementations.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

from models.folder_entry import FolderEntry
from commonUtils.ui.features import Feature as CommonFeature


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
class LocalFolderSource:
    """
    One selectable local-folder context exposed to the generic Folders page.

    get_local_folders returns the local folders shown for this source.
    """

    name: str
    get_local_folders: Callable[[], list[Any]]
    context: Any = None


@dataclass(frozen=True)
class LocalFolderSourceContribution:
    """A provider of selectable local-folder sources."""

    name: str
    get_sources: Callable[[], list[LocalFolderSource]]
    order: int = 0


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
    """Detect availability/actions off the GUI thread; create_widget runs on it."""

    name: str
    is_available: Callable[[FolderEntry], bool]
    get_actions: Callable[[FolderEntry], list[UIAction]]
    order: int = 0
    create_widget: Callable[[FolderEntry, Any], Any] | None = None
    actions_horizontal: bool = False


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
    navigation_icon: str | None = None


@dataclass(frozen=True)
class SettingsContribution:
    """Feature-owned settings layout hosted by Settings, with optional raw INI files.

    Factories run lazily on selection, only for enabled features. The widget may
    expose refresh() and can_close() to participate in the host lifecycle.
    scope identifies where custom settings are saved; config_scope overrides
    scope for raw config files. separate_tab gives the custom panel its own section.
    """
    name: str
    settings_id: str
    create_widget: Callable[[Any], Any] | None = None
    order: int = 0
    config_files: tuple[Any, ...] = ()
    separate_tab: bool = False
    scope: str = 'application'
    config_scope: str | None = None

    def __post_init__(self):
        if self.scope not in ('application', 'personal'):
            raise ValueError('Settings scope must be application or personal')
        if self.config_scope not in (None, 'application', 'personal'):
            raise ValueError('Config scope must be application or personal')


@dataclass(frozen=True)
class BrowserExtensionContribution:
    """Install feature services into a Logistics file-browser window lazily.

    The returned controller has prepare_close() -> bool and an idle Qt signal.
    False defers closure until idle; controllers stay owned by the host window.
    """

    install: Callable[[Any], Any]


@dataclass(frozen=True)
class DocumentLauncherContribution:
    """Feature-owned editor launcher; optional creation enables shared New/Open menus."""
    editor_id: str
    name: str
    open_document: Callable[[Any], Any]
    icon: str = 'documents'
    order: int = 0
    new_document: Callable[[Any], Any] | None = None


@dataclass
class FeatureContributions:
    """All optional contribution types exposed by one feature."""

    local_folder_sources: list[LocalFolderSourceContribution] = field(default_factory=list)
    remote_folder_sources: list[RemoteFolderSourceContribution] = field(default_factory=list)
    folder_features: list[FolderFeatureContribution] = field(default_factory=list)
    server_providers: list[ServerProviderContribution] = field(default_factory=list)
    debug_actions: list[DebugActionContribution] = field(default_factory=list)
    workflows: list[WorkflowContribution] = field(default_factory=list)
    document_launchers: list[DocumentLauncherContribution] = field(default_factory=list)
    pages: list[PageContribution] = field(default_factory=list)
    settings: list[SettingsContribution] = field(default_factory=list)
    browser_extensions: list[BrowserExtensionContribution] = field(default_factory=list)


@dataclass(kw_only=True)
class Feature(CommonFeature, FeatureContributions):
    """Unified commonUtils feature declaration plus Logistics UI contributions."""

    def __post_init__(self):
        super().__post_init__()
        if self.browser is not None and self.browser_extensions:
            raise ValueError('Use browser or legacy browser_extensions, not both')


T = TypeVar('T')


@dataclass(frozen=True)
class RegisteredContribution(Generic[T]):
    """A contribution paired with the feature that supplied it."""

    feature_name: str
    feature_label: str
    contribution: T
