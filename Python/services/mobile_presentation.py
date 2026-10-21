"""Toolkit-independent contract for application presentation policy."""
from dataclasses import dataclass
from typing import Any, Callable, Protocol


class IconButtonFactory(Protocol):
    def __call__(self, name: str, label: str, *, on_press: Callable | None = None,
                 enabled: bool = True) -> Any: ...


class ApplyIcon(Protocol):
    def __call__(self, button: Any, name: str, label: str, *,
                 preserve_layout: bool = False, size: int | None = None) -> Any: ...


class MarkdownPreview(Protocol):
    def __call__(self, text: str, font_size: int = 16, *, local_links: bool = False,
                 image_source: Any = None) -> str: ...


class Stylesheet(Protocol):
    def __call__(self, mode: str = 'system') -> str: ...


class FontBinding(Protocol):
    def __call__(self, widget: Any, kind: str, *, web: bool = False,
                 formatted: Any = None) -> Any: ...


@dataclass(frozen=True)
class MobilePresentation:
    icon_button: IconButtonFactory
    apply_icon: ApplyIcon
    action_button: Callable
    ActionMenu: Callable
    NativeMenu: Callable
    surface: Callable
    apple_color: Callable
    menu_button: Callable
    export_document: Callable
    markdown_preview: MarkdownPreview
    css_variables: Stylesheet
    summary_list: Callable
    font_size: Callable[[str], int]
    bind_font: FontBinding
    folder_actions: Callable
