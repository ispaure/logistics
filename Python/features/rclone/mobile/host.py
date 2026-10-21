"""Presentation hooks supplied explicitly by the mobile application host."""
from dataclasses import dataclass
from contextlib import nullcontext
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
    settings_page: Callable = None
    settings_group: Callable = None
    settings_field: Callable = None
    settings_note: Callable = None
    settings_heading: Callable = None
    settings_disclosure: Callable = None
    record_folder: Callable = lambda *args, **kwargs: None
    opening_status: Callable = lambda *args, **kwargs: nullcontext()
    refresh_transfer_chrome: Callable = lambda: None
