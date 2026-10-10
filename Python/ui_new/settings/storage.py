"""Explain existing storage policy without moving files or introducing overrides."""
from pathlib import Path
from commonUtils.ui import pyside as qt

APPLICATION_ROOT = Path(__file__).resolve().parents[3]


class StorageNotice(qt.QLabel):
    def __init__(self, path, parent=None, *, scope=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.set_path(path, scope=scope)

    def set_path(self, path, *, scope=None):
        path = Path(path).absolute()
        self.scope = scope or ('application' if path.is_relative_to(APPLICATION_ROOT) or path.resolve().is_relative_to(APPLICATION_ROOT) else 'external')
        meaning = {
            'application': 'Application configuration · saved with this installation. Changes affect everyone using this copy '
                           'and may be replaced by an update. Edit these shared defaults deliberately for testing.',
            'personal': 'Personal preferences · saved for your user account. Changes affect your profile; application defaults remain unchanged.',
            'external': 'External configuration · saved at the location below. Changes affect applications reading this file; this does not create a Logistics personal override.',
        }[self.scope]
        self.setText(meaning + '\nFile: ' + str(path))


class StoragePanel(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        from features.preferences import preferences_path
        from features.text_editor.preferences import Preferences as EditorPreferences
        from commonUtils.configuration.settings import settings_path
        from commonUtils.storage import cache_directory
        layout = qt.QVBoxLayout(self)
        title = qt.QLabel('Where settings are saved'); font = title.font(); font.setBold(True); title.setFont(font)
        layout.addWidget(title)
        note = qt.QLabel('Logistics keeps its shared configuration with the application. Feature choices and document preferences '
                        'belong to your account. The settings pages identify the file being edited. Saving application configuration '
                        'changes this installation; it does not create a personal override.')
        note.setWordWrap(True); layout.addWidget(note)
        rows = [
            ('Application', 'Logistics configuration and indexing', APPLICATION_ROOT/'Python'/'configFile.ini'),
            ('Application', 'Maintenance defaults', APPLICATION_ROOT/'Python'/'maintenance.ini'),
            ('Application', 'Launcher defaults', APPLICATION_ROOT/'launch_config.ini'),
            ('Application', 'Shared commonUtils UI defaults', settings_path()),
            ('Application', 'Text editor starting defaults', APPLICATION_ROOT/'Python'/'features'/'text_editor'/'config.ini'),
            ('Personal', 'Enabled features', preferences_path()),
            ('Personal', 'Git executable and repository history', preferences_path().with_name('git.json')),
            ('Personal', 'Text editor overrides (take precedence over starting defaults)', EditorPreferences().path),
            ('Personal', 'Text editor recent files and recovery', EditorPreferences().path.parent),
            ('Personal', 'Reading position and reader recent files', cache_directory(create=False)),
            ('Cache', 'File index database', cache_directory(create=False)/'directory-index.sqlite3'),
        ]
        self.table = qt.QTreeWidget(); self.table.setHeaderLabels(['Storage', 'Used for', 'Location'])
        self.table.setRootIsDecorated(False)
        for scope, purpose, path in rows:
            item = qt.QTreeWidgetItem([scope, purpose, str(path)]); item.setToolTip(2, str(path)); self.table.addTopLevelItem(item)
        self.table.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(1, 420)
        layout.addWidget(self.table, 1)
        footer = qt.QLabel('The text editor currently stores personal overrides in the commonUtils cache folder shown above. '
                          'Appearance changes from the dropdown apply to this session; saving [Theme] in the commonUtils INI sets the startup default. '
                          'Bulk rename rules stay in the current session unless you save a rules preset to a location you choose.')
        footer.setWordWrap(True); layout.addWidget(footer)
