"""Presentation hooks supplied explicitly by the mobile application host."""

from dataclasses import dataclass
from contextlib import nullcontext
from typing import Any, Awaitable, Callable, ContextManager, Iterable, Protocol
from services.mobile_presentation import IconButtonFactory


class LocalReadAvailable(Protocol):
    def __call__(self, owner: Any, *, private: bool = True) -> bool: ...


class ExportFile(Protocol):
    def __call__(self, owner: Any, selected: Any) -> Awaitable[Any]: ...


class OpeningStatus(Protocol):
    def __call__(
        self, source: dict, *, destination: str | None = None
    ) -> ContextManager[None]: ...


class FeatureCommandsFactory(Protocol):
    def __call__(
        self,
        button: Any,
        owner: Any,
        actions: Iterable,
        fallback: Callable,
        *,
        document: bool = False,
    ) -> Any: ...


class RecordFolder(Protocol):
    def __call__(
        self,
        view: Any,
        browser: Any,
        kind: str,
        source: Any,
        path: str,
        navigate: Callable,
    ) -> None: ...


@dataclass(frozen=True)
class MobileHostUI:
    icon_button: IconButtonFactory
    NativeBrowser: Callable
    FeatureCommands: FeatureCommandsFactory
    private_label: Callable[[Any], str]
    visible_remotes: Callable[[Iterable[str]], list[str]]
    exclusions: Callable[[], Any]
    pick_document: Callable[[Any], Awaitable[Any]]
    ResourceImports: Callable
    export_file: ExportFile
    accessible_name: Callable[[Any, str], Any]
    local_read_available: LocalReadAvailable
    refresh_folder_source_actions: Callable[[], None] = lambda: None
    settings: "ConnectionPresentation | None" = None
    record_folder: RecordFolder = lambda *args, **kwargs: None
    opening_status: OpeningStatus = lambda *args, **kwargs: nullcontext()
    refresh_transfer_chrome: Callable[[], None] = lambda: None


@dataclass(frozen=True)
class ConnectionPresentation:
    page: Callable[[str, str, list[Any]], Any]
    group: Callable[[list[Any]], Any]
    field: Callable[[str, Any], Any]
    note: Callable[[str], Any]
    heading: Callable[[str], Any]
    disclosure: Callable[[str, list[Any]], tuple[Any, Any]]
