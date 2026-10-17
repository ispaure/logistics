"""Shared addon catalog, independent of individual preset management."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.status_line import StatusLine
from ..library import version_tuple
from .. import bluehole


def source_label(source):
    return {'Provided': 'Shared', 'Personal': 'User provided (legacy)', 'Preset': 'Preset provided'}.get(source, source)


class AddonLibraryPage(qt.QWidget):
    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        layout = qt.QVBoxLayout(self)
        note = qt.QLabel('Shared addon packages, grouped by addon. Expand an addon to see its versions and Blender compatibility. Add your own ZIPs from the selected preset’s Add Addon button.')
        note.setWordWrap(True)
        layout.addWidget(note)
        toolbar = qt.QHBoxLayout()
        self.refresh_button = qt.QPushButton('Refresh')
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.tree = qt.QTreeWidget()
        self.tree.setHeaderLabels(['Addon / version', 'Package date', 'Blender minimum', 'Blender maximum (exclusive)', 'Type', 'Library', 'ZIP'])
        self.tree.setAccessibleName('Blender addon library and versions')
        self.tree.setSelectionBehavior(qt.QAbstractItemView.SelectionBehavior.SelectRows)
        for column in range(self.tree.columnCount() - 1):
            self.tree.header().setSectionResizeMode(column, qt.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)
        self.status = StatusLine()
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.tree.clearSelection()
        try:
            entries = self.library.entries(shared_only=True)
            groups = {}
            for addon in entries:
                if addon.identity != bluehole.IDENTITY:
                    groups.setdefault(addon.identity, []).append(addon)
            expanded = {self.tree.topLevelItem(i).data(0, qt.Qt.ItemDataRole.UserRole)
                        for i in range(self.tree.topLevelItemCount()) if self.tree.topLevelItem(i).isExpanded()}
            self.tree.clear()
            for identity, versions in sorted(groups.items(), key=lambda pair: (pair[1][0].name.casefold(), pair[0])):
                versions.sort(key=lambda addon: (version_tuple(addon.version), addon.published), reverse=True)
                latest = versions[0]
                count = f"{len(versions)} package" + ('s' if len(versions) != 1 else '')
                group = qt.QTreeWidgetItem([latest.name, '', '', '', '', '', count])
                group.setData(0, qt.Qt.ItemDataRole.UserRole, identity)
                group.setToolTip(0, identity)
                self.tree.addTopLevelItem(group)
                for addon in versions:
                    item = qt.QTreeWidgetItem([addon.version, addon.published or '—', addon.minimum or 'Unknown', addon.maximum or '—', addon.kind, source_label(addon.source), addon.package_name or addon.package.name])
                    item.setToolTip(6, str(addon.package))
                    group.addChild(item)
                group.setExpanded(identity in expanded)
            self.status.setText(f'{len(groups)} addons · {sum(len(items) for items in groups.values())} packages. Versions are listed newest first; each preset chooses its latest compatible version.')
            if self.library.errors:
                self.status.setText(self.status.text() + '\nSkipped packages:\n' + '\n'.join(self.library.errors))
        except (OSError, ValueError) as error:
            self.tree.clear()
            self.status.setText(str(error))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
