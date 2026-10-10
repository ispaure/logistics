"""An explicit-save home for browser refresh rules in Logistics' existing INI."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from .ini_editor import INISettingsEditor

INDEX_FIELDS = {
    'scan_on_open': ('Build an index when opening an unindexed folder',
        'Opening a folder without saved index data starts a scan. Saved data is reused unless '
        '“Recheck saved indexes on first use” is enabled. Turning this off still allows Refresh index, '
        'change notifications and reopening checks to update the index.'),
    'recursive_on_open': ('Include subfolders in automatic scans',
        'Automatic index creation or reconciliation may scan subfolders and collect their sizes. '
        'When off, automatic scans check the current folder only, so subtree search and sizes may be partial. '
        'This does not continuously scan, or rebuild an existing cache just because you open it. '
        'Refresh index always checks the full subtree. Large trees can take several minutes.'),
    'refresh_cached_on_startup': ('Recheck saved indexes on first use',
        'The first use of a saved index in this application session checks it instead of only reading the cache. '
        'This requires automatic indexing on open. Further visits reuse the session’s results unless '
        'a change notification, reopening check or Refresh index requests another check.'),
    'refresh_on_revisit': ('Recheck the current folder when reopened',
        'Opening the current indexed folder again while its index job is idle requests a check. '
        'This can update saved search results and sizes even when indexing on open is off. '
        'It does not poll in the background; scan depth follows the subfolder setting.'),
    'watch_changes': ('Update the index after filesystem notifications',
        'Notifications for watched files and folders request an index update after a short delay. '
        'This can update saved search results and sizes even when indexing on open is off. '
        'Only watched locations are monitored; this is not a repeated full-tree scan.'),
    'background_priority': ('Run index jobs at background priority',
        'Use lower worker priority for index jobs to keep other work responsive. '
        'This does not change scan depth or which files are indexed.'),
}


class IndexSettingsEditor(INISettingsEditor):
    def _key_type(self, key):
        return (INDEX_FIELDS[key][0], 'bool') if key in INDEX_FIELDS else super()._key_type(key)

    def _build_fields(self):
        super()._build_fields()
        for index in range(self.sections.count()-1, -1, -1):
            if self.sections.tabText(index) != 'FileIndex':
                widget = self.sections.widget(index)
                self.sections.removeTab(index)
                widget.deleteLater()
        self.fields = {key: value for key, value in self.fields.items() if key[0] == 'FileIndex'}
        for (_, key), control in self.fields.items():
            if key in INDEX_FIELDS:
                control.setToolTip(INDEX_FIELDS[key][1])
        scan = self.fields.get(('FileIndex', 'scan_on_open'))
        if isinstance(scan, qt.QCheckBox):
            scan.toggled.connect(self._dependencies)
        self._dependencies()

    def _dependencies(self, *args):
        scan = self.fields.get(('FileIndex', 'scan_on_open'))
        startup = self.fields.get(('FileIndex', 'refresh_cached_on_startup'))
        if isinstance(scan, qt.QCheckBox) and startup is not None:
            startup.setEnabled(scan.isChecked())
            startup.setToolTip(INDEX_FIELDS['refresh_cached_on_startup'][1] +
                              ('' if scan.isChecked() else '\nEnable indexing on open to use this option. Its saved value is retained.'))


class IndexSettingsPanel(qt.QWidget):
    def __init__(self, parent=None, *, path=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        title = qt.QLabel('File indexing')
        layout.addWidget(title)
        note = qt.QLabel('Save to apply changes to the next index request. Hover over an option for details.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.editor = IndexSettingsEditor(path or Path(__file__).resolve().parents[2]/'configFile.ini', self)
        from commonUtils.ui.settings_sections import ScopedSettings, SettingsSection
        self.sections = ScopedSettings(self)
        self.sections.set_sections([SettingsSection('application', 'ini', 'INI files', self.editor, nested=True)])
        layout.addWidget(self.sections, 1)

    def can_close(self):
        return self.editor.can_close()
