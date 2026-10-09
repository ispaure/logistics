"""An explicit-save home for browser refresh rules in Logistics' existing INI."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.index_policy import IndexPolicy
from .ini_editor import INISettingsEditor


class IndexSettingsEditor(INISettingsEditor):
    def _key_type(self, key):
        return (key, 'bool') if key in vars(IndexPolicy()) else super()._key_type(key)

    def _build_fields(self):
        super()._build_fields()
        for index in range(self.sections.count()-1, -1, -1):
            if self.sections.tabText(index) != 'FileIndex':
                widget = self.sections.widget(index)
                self.sections.removeTab(index)
                widget.deleteLater()
        self.fields = {key: value for key, value in self.fields.items() if key[0] == 'FileIndex'}


class IndexSettingsPanel(qt.QWidget):
    def __init__(self, parent=None, *, path=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        title = qt.QLabel('File indexing')
        layout.addWidget(title)
        note = qt.QLabel('The default indexes only folders you visit and opens saved results immediately. '
                        'Refresh index checks the full subtree. Enable recursive on open for continuous subtree scanning, '
                        'or turn off scan on open for manual indexing. Watch changes updates notified folders. '
                        'Startup refresh validates saved contents once per launch; revisit refresh checks each reopening. '
                        'These rules also apply to new tabs. Save explicitly; changes apply to the next request.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.editor = IndexSettingsEditor(path or Path(__file__).resolve().parents[2]/'configFile.ini', self)
        layout.addWidget(self.editor, 1)

    def can_close(self):
        return self.editor.can_close()
