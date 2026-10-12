"""Shared/personal addon catalog, independent of individual preset management."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from .library import version_tuple
from . import bluehole


def source_label(source):
    return {'Provided': 'Shared', 'Personal': 'User provided'}.get(source, source)


class AddonLibraryPage(qt.QWidget):
    changed = qt.Signal()
    idle = qt.Signal()

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        layout = qt.QVBoxLayout(self)
        note = qt.QLabel('Available addon packages, grouped by addon. Expand an addon to see its versions and Blender compatibility. Imports go to your user library.')
        note.setWordWrap(True)
        layout.addWidget(note)
        toolbar = qt.QHBoxLayout()
        self.add_button = qt.QPushButton('Add Addon…')
        self.add_button.setToolTip('Import a ZIP into your user library. Shared packages remain unchanged.')
        self.refresh_button = qt.QPushButton('Refresh')
        toolbar.addWidget(self.add_button)
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
        self.status = qt.QLabel()
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.task = OperationProgress(self)
        layout.addWidget(self.task)
        self.task.completed.connect(self._finished)
        self.add_button.clicked.connect(self._add)
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self):
        if self.task.busy:
            return
        try:
            entries = self.library.entries()
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
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _add(self):
        if self.task.busy:
            return
        package, _ = qt.QFileDialog.getOpenFileName(self, 'Add Addon to Library', '', 'Addon ZIP (*.zip)')
        if package:
            self.add_button.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.task.start(lambda report, cancelled: self.library.add(package, cancelled=cancelled), message='Adding addon to library…')

    def _finished(self, result, error):
        self.add_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.refresh()
        if error:
            self.status.setText(f'Import failed: {error}')
        elif self.task.cancelled.is_set():
            self.status.setText('Cancelled.')
        else:
            self.status.setText(f'{result.name} {result.version} added · User provided')
            self.changed.emit()
        self.idle.emit()

    def prepare_close(self):
        if self.task.busy:
            self.task.request_cancel()
            return False
        return True

    def closeEvent(self, event):
        if not self.prepare_close():
            event.ignore()
        else:
            super().closeEvent(event)
