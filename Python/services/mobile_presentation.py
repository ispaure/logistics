"""Toolkit-independent contract for application presentation policy."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class MobilePresentation:
    icon_button: Callable
    apply_icon: Callable
    action_button: Callable
    ActionMenu: Callable
    surface: Callable
    apple_color: Callable
    menu_button: Callable
    export_document: Callable
    markdown_preview: Callable
    css_variables: Callable
    summary_list: Callable
