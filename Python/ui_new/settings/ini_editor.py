"""Compatibility editor retaining Logistics' typed-key default."""
from commonUtils.ui.ini_editor import INISettingsEditor as SharedINISettingsEditor


class INISettingsEditor(SharedINISettingsEditor):
    """Existing Logistics callers opt into the shared schema by default."""
    def __init__(self, path, parent=None, *, typed_keys=True):
        super().__init__(path, parent, typed_keys=typed_keys)
