"""Compatibility entry point; desktop implementation lives under ``features.lm.ui``."""
from .ui.page import LMPage
from .ui.composer import Composer, SamplingSpin
from .ui.profiles import ProfilesDialog
from .ui.mode_tabs import ModeTabs

__all__ = ['LMPage', 'Composer', 'SamplingSpin', 'ProfilesDialog', 'ModeTabs']
