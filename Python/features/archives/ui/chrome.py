"""Archive workspace toolbar and page chrome; no archive I/O or credentials."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.archive_view import ArchiveContents


def build_workspace(page):
    layout = qt.QVBoxLayout(page)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(10)
    toolbar = qt.QHBoxLayout()
    page.commands = {}
    for key, title, icon, callback in [
        ('open', 'Open archive…', qt.QStyle.StandardPixmap.SP_DialogOpenButton, page.open_dialog),
        ('create', 'Create archive…', qt.QStyle.StandardPixmap.SP_FileDialogNewFolder, page.new_archive),
        ('extract', 'Extract all…', qt.QStyle.StandardPixmap.SP_ArrowDown, page.extract_all),
        ('selected', 'Extract selected…', qt.QStyle.StandardPixmap.SP_DirOpenIcon, page.extract_selected),
        ('test', 'Test integrity', qt.QStyle.StandardPixmap.SP_DialogApplyButton, page.test),
    ]:
        button = qt.QToolButton()
        button.setText(title)
        button.setAccessibleName(title)
        button.setToolTip(title)
        button.setIcon(page.style().standardIcon(icon))
        button.setIconSize(qt.QSize(24, 24))
        button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.clicked.connect(callback)
        page.commands[key] = button
        toolbar.addWidget(button)
    toolbar.addStretch()
    page.edit_menu = qt.QToolButton()
    page.edit_menu.setText('Edit ZIP')
    page.edit_menu.setAccessibleName('Edit ZIP archive')
    page.edit_menu.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = qt.QMenu(page.edit_menu)
    menu.addAction('Add files…', page.add_files)
    menu.addAction('Add folder…', page.add_folder)
    page.remove_action = menu.addAction('Remove selected entries…', page.remove_selected)
    page.edit_menu.setMenu(menu)
    toolbar.addWidget(page.edit_menu)
    layout.addLayout(toolbar)
    location_row = qt.QHBoxLayout()
    page.location = qt.QLineEdit()
    page.location.setPlaceholderText('Open an archive, paste its path, or drop it here')
    page.location.setAccessibleName('Archive path')
    page.location.returnPressed.connect(lambda: page.open_archive(page.location.text().strip()))
    location_row.addWidget(page.location, 1)
    page.reload = qt.QToolButton()
    page.reload.setIcon(page.style().standardIcon(qt.QStyle.StandardPixmap.SP_BrowserReload))
    page.reload.setToolTip('Reload archive')
    page.reload.setAccessibleName('Reload archive')
    page.reload.clicked.connect(page.refresh)
    location_row.addWidget(page.reload)
    layout.addLayout(location_row)
    page.summary = qt.QLabel('ARCHIVES  /  ZIP · AES ZIP · TAR · GZIP · XZ')
    page.summary.setTextFormat(qt.Qt.TextFormat.PlainText)
    layout.addWidget(page.summary)
    page.contents = ArchiveContents(page)
    page.contents.preview_requested.connect(page.preview_selected)
    page.contents.extract_requested.connect(page.extract_selected)
    page.contents.remove_requested.connect(page.remove_selected)
    page.contents.selection_changed.connect(page._enabled)
    layout.addWidget(page.contents, 1)
    page.status = qt.QLabel('Ready. Sources and existing output files are preserved.')
    page.status.setTextFormat(qt.Qt.TextFormat.PlainText)
    page.status.setWordWrap(True)
    layout.addWidget(page.status)
    layout.addWidget(page.task)
    page.setStyleSheet('''
        QWidget#archiveWorkspace QToolButton { padding: 6px; }
        QWidget#archiveWorkspace QTreeWidget::item { padding: 3px 4px; margin: 0; }
        QWidget#archiveWorkspace QHeaderView::section { padding: 6px 4px; }
    ''')
    for key, callback in [('Ctrl+O', page.open_dialog), ('Ctrl+N', page.new_archive),
                          ('Alt+Up', page.contents.up_folder), ('Ctrl+F', page.contents.search.setFocus), ('F5', page.refresh)]:
        shortcut = qt.QShortcut(qt.QKeySequence(key), page)
        shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(callback)
