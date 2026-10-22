"""Toolkit-independent contract for application presentation policy."""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Protocol

Action = tuple[str, Callable[[], Any]]


class Surface(Protocol):
    def __call__(
        self,
        widget: Any,
        *,
        radius: int = 12,
        background: str = "surface",
        foreground: str | None = None,
        outlined: bool = False,
        eink_outlined: bool = True,
        eink_selected: bool = False,
    ) -> Any: ...


class ActionButton(Protocol):
    def __call__(self, button: Any, *, destructive: bool = False) -> Any: ...


class MenuButton(Protocol):
    def __call__(self, callback: Callable, label: str = "Browse files") -> Any: ...


class ExportDocument(Protocol):
    def __call__(
        self,
        owner: Any,
        name: str,
        content: bytes,
        *,
        max_bytes: int | None = None,
        mime_type: str | None = None,
    ) -> Awaitable[Any]: ...


class SummaryList(Protocol):
    def __call__(
        self, *, kind: str, icon_kind: str, on_select: Callable, **kwargs: Any
    ) -> Any: ...


class IconButtonFactory(Protocol):
    def __call__(
        self,
        name: str,
        label: str,
        *,
        on_press: Callable | None = None,
        enabled: bool = True,
    ) -> Any: ...


class ApplyIcon(Protocol):
    def __call__(
        self,
        button: Any,
        name: str,
        label: str,
        *,
        preserve_layout: bool = False,
        size: int | None = None,
    ) -> Any: ...


class MarkdownPreview(Protocol):
    def __call__(
        self,
        text: str,
        font_size: int = 16,
        *,
        local_links: bool = False,
        image_source: Any = None,
    ) -> str: ...


class Stylesheet(Protocol):
    def __call__(self, mode: str = "system") -> str: ...


class FontBinding(Protocol):
    def __call__(
        self, widget: Any, kind: str, *, web: bool = False, formatted: Any = None
    ) -> Any: ...


@dataclass(frozen=True)
class MobilePresentation:
    icon_button: IconButtonFactory
    apply_icon: ApplyIcon
    action_button: ActionButton
    ActionMenu: Callable
    NativeMenu: Callable
    surface: Surface
    apple_color: Callable[[str], Any]
    menu_button: MenuButton
    export_document: ExportDocument
    markdown_preview: MarkdownPreview
    css_variables: Stylesheet
    summary_list: SummaryList
    font_size: Callable[[str], int]
    bind_font: FontBinding
    folder_actions: Callable[[Any], Iterable[Action]]
