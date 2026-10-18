"""Presentation hooks supplied explicitly by the mobile application host."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class MobileHostUI:
    icon_button: Callable
    NativeBrowser: Callable
    FeatureCommands: Callable
    private_label: Callable
    visible_remotes: Callable
    exclusions: Callable
    pick_document: Callable
    ResourceImports: Callable
    export_file: Callable
    accessible_name: Callable
    local_read_available: Callable
    refresh_folder_source_actions: Callable = lambda: None
