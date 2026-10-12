"""Feature-owned Blender manager page; all lengthy work uses shared workers."""
from pathlib import Path
from configparser import Error as ConfigError

from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from .addons import inspect_addons, scan_preset
from .manager import BlenderManager
from .releases import load_releases, platform_key


class BlenderPage(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent=None, *, manager=None):
        super().__init__(parent)
        self.manager = manager or BlenderManager()
        self.releases = []
        self._operation = ''
        self._select_preset = None
        self.task = OperationProgress(self)
        self.task.completed.connect(self._finished)
        self.task.completed.connect(lambda *args: self.idle.emit())
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        title = qt.QLabel('Blender')
        font = title.font()
        font.setPointSize(font.pointSize() + 7)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        description = qt.QLabel('Install Blender versions and launch them with independent preferences and addons.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.controls = qt.QWidget()
        controls = qt.QVBoxLayout(self.controls)
        controls.setContentsMargins(0, 0, 0, 0)
        selection = qt.QFormLayout()
        self.version = qt.QComboBox()
        self.preset = qt.QComboBox()
        selection.addRow('Blender version', self.version)
        selection.addRow('Preference preset', self.preset)
        controls.addLayout(selection)
        self.install_status = qt.QLabel()
        self.install_status.setWordWrap(True)
        self.install_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        controls.addWidget(self.install_status)
        self.install_button = qt.QPushButton('Install')
        self.remove_button = qt.QPushButton('Remove Installation')
        self.launch_button = qt.QPushButton('Launch Blender')
        self.install_folder = qt.QPushButton('Open Installation Folder')
        self.create_button = qt.QPushButton('Create Preset')
        self.duplicate_button = qt.QPushButton('Duplicate Preset')
        self.copy_button = qt.QPushButton('Copy to Another Version')
        self.rename_button = qt.QPushButton('Rename Preset')
        self.delete_button = qt.QPushButton('Delete Preset')
        self.preset_folder = qt.QPushButton('Open Preset Folder')
        self.refresh_button = qt.QPushButton('Refresh Addons')
        self.addon_folder = qt.QPushButton('Open Addon Folder')
        for buttons in ((self.install_button, self.remove_button, self.launch_button, self.install_folder),
                        (self.create_button, self.duplicate_button, self.copy_button, self.rename_button, self.delete_button,
                         self.preset_folder), (self.refresh_button, self.addon_folder)):
            row = qt.QGridLayout()
            for index, button in enumerate(buttons):
                row.addWidget(button, index // 3, index % 3)
            for column in range(3):
                row.setColumnStretch(column, 1)
            controls.addLayout(row)
        layout.addWidget(self.controls)
        self.status = qt.QLabel()
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table = qt.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Addon', 'Version', 'Type', 'Enabled', 'Source', 'Location'])
        self.table.setSelectionBehavior(qt.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(qt.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.task)
        self.version.currentIndexChanged.connect(self._version_changed)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.install_button.clicked.connect(self._install)
        self.remove_button.clicked.connect(self._remove)
        self.launch_button.clicked.connect(self._launch)
        self.create_button.clicked.connect(self._create)
        self.duplicate_button.clicked.connect(self._duplicate)
        self.copy_button.clicked.connect(self._copy)
        self.rename_button.clicked.connect(self._rename)
        self.delete_button.clicked.connect(self._delete)
        self.install_folder.clicked.connect(lambda: self._open(self.manager.installation(self.release)))
        self.preset_folder.clicked.connect(lambda: self._open(self.manager.preset(self.release, self.preset.currentText())))
        self.refresh_button.clicked.connect(self._inspect)
        self.addon_folder.clicked.connect(self._open_addon)
        self.refresh()

    @property
    def release(self):
        index = self.version.currentIndex()
        return self.releases[index] if 0 <= index < len(self.releases) else None

    def refresh(self):
        if self.task.busy:
            return
        previous = self.version.currentText()
        self.version.blockSignals(True)
        self.version.clear()
        try:
            self.releases = load_releases()
            self.version.addItems([release.version for release in self.releases])
            if previous in [release.version for release in self.releases]:
                self.version.setCurrentText(previous)
            if not self.releases:
                self.status.setText(f'No official package is configured for {platform_key()}. '
                                    'Available platforms are listed in Settings → Blender → Release downloads.')
        except (OSError, ValueError, KeyError, ConfigError) as error:
            self.releases = []
            self.status.setText(f'Cannot read release configuration: {error}')
        finally:
            self.version.blockSignals(False)
        self.controls.setEnabled(True)
        self._version_changed()

    def _version_changed(self, *_args):
        previous = self._select_preset or self.preset.currentText()
        self._select_preset = None
        self.preset.blockSignals(True)
        self.preset.clear()
        try:
            if self.release:
                self.preset.addItems(self.manager.presets(self.release))
                if previous:
                    self.preset.setCurrentText(previous)
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
        finally:
            self.preset.blockSignals(False)
        self._preset_changed()

    def _update_controls(self):
        release = self.release
        ready = bool(release and self.manager.ready(release))
        has_preset = bool(release and self.preset.currentText())
        self.install_button.setEnabled(bool(release) and not ready)
        self.remove_button.setEnabled(ready)
        self.launch_button.setEnabled(ready and has_preset)
        self.install_folder.setEnabled(ready)
        self.create_button.setEnabled(bool(release))
        for button in (self.duplicate_button, self.rename_button, self.delete_button,
                       self.preset_folder, self.refresh_button):
            button.setEnabled(has_preset)
        self.copy_button.setEnabled(has_preset and len(self.releases) > 1)
        self.addon_folder.setEnabled(self.table.rowCount() > 0)
        self.install_status.setText('' if not release else
                                   f'{"Installed" if ready else "Not installed"} · {platform_key()}\n'
                                   f'{self.manager.installation(release)}')

    def _preset_changed(self, *_args):
        try:
            rows = scan_preset(self.manager.preset(self.release, self.preset.currentText())) if (
                self.release and self.preset.currentText()) else []
            self._show_rows(rows)
            if self.release:
                self.status.setText('Showing preset files. Refresh Addons reads saved enabled state using Blender.'
                                    if self.preset.currentText() else 'Create a preference preset to launch Blender.')
            self._update_controls()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            self.controls.setEnabled(False)

    def _show_rows(self, rows):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        root = self.manager.preset(self.release, self.preset.currentText()) if self.release and self.preset.currentText() else None
        installation = self.manager.installation(self.release) if self.release else None
        for index, row in enumerate(rows):
            path = Path(row['path'])
            source = ('Preset' if root and path.resolve().is_relative_to(root.resolve()) else
                      'Bundled' if installation and path.resolve().is_relative_to(installation.resolve()) else 'External')
            enabled = 'Unknown' if row['enabled'] is None else 'Yes' if row['enabled'] else 'No'
            for column, value in enumerate((row['name'], row['version'], row['kind'], enabled, source, row['path'])):
                self.table.setItem(index, column, qt.QTableWidgetItem(str(value)))
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    def _confirm(self, text):
        return qt.QMessageBox.question(self, 'Blender', text,
                                      qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.No,
                                      qt.QMessageBox.StandardButton.No) == qt.QMessageBox.StandardButton.Yes

    def _name(self, title, suggested):
        name, accepted = qt.QInputDialog.getText(self, title, 'Preset name:', text=suggested)
        return name if accepted else None

    def _run(self, operation, work):
        if self.task.busy:
            return
        self._operation = operation
        self.controls.setEnabled(False)
        self.table.setEnabled(False)
        self.task.start(work, message=f'{operation}…')

    def _finished(self, result, error):
        self.controls.setEnabled(True)
        self.table.setEnabled(True)
        cancelled = self.task.cancelled.is_set() and (not error or error == 'Operation cancelled')
        if self._operation == 'Refreshing addons' and not error and not cancelled:
            rows, message = result
            self._show_rows(rows)
            self.status.setText(message)
            self._update_controls()
        else:
            if isinstance(result, Path) and self._operation == 'Duplicating preset':
                self._select_preset = result.name
            self._version_changed()
            self.status.setText('Cancelled.' if cancelled else
                                f'{self._operation} failed: {error}' if error else f'{self._operation} finished.')
            if cancelled:
                self.task.message.setText('Cancelled.')

    def _install(self):
        release = self.release
        if release and self._confirm(f'Download and install Blender {release.version} for {release.platform}?\n\n'
                                     f'Destination: {self.manager.installation(release)}\n'
                                     'The package will be verified and deleted after installation.'):
            self._run('Installing Blender', lambda report, cancelled:
                      self.manager.install(release, report=report, cancelled=cancelled))

    def _remove(self):
        release = self.release
        if release and self._confirm(f'Remove Blender {release.version}? Presets and addons will be kept. '
                                     'Close any Blender instances using this installation first.'):
            self._run('Removing Blender', lambda report, cancelled: self.manager.remove(release))

    def _launch(self):
        try:
            pid = self.manager.launch(self.release, self.preset.currentText())
            self.status.setText(f'Launched Blender {self.release.version} with {self.preset.currentText()} (PID {pid}).')
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def _create(self):
        name = self._name('Create Preset', 'Default')
        if name is not None:
            try:
                destination = self.manager.create_preset(self.release, name)
                self._select_preset = destination.name
                self._version_changed()
            except (OSError, ValueError) as error:
                self.status.setText(str(error))

    def _duplicate(self):
        source, release = self.preset.currentText(), self.release
        name = self._name('Duplicate Preset', source + ' Copy')
        if name is not None:
            self._run('Duplicating preset', lambda report, cancelled:
                      self.manager.duplicate_preset(release, source, name, cancelled=cancelled))

    def _rename(self):
        name = self._name('Rename Preset', self.preset.currentText())
        if name is not None:
            try:
                destination = self.manager.rename_preset(self.release, self.preset.currentText(), name)
                self._select_preset = destination.name
                self._version_changed()
            except (OSError, ValueError) as error:
                self.status.setText(str(error))

    def _copy(self):
        source, release = self.preset.currentText(), self.release
        targets = [item for item in self.releases if item != release]
        version, accepted = qt.QInputDialog.getItem(self, 'Copy Preset', 'Destination Blender version:',
                                                  [item.version for item in targets], editable=False)
        if not accepted:
            return
        name = self._name('Copy Preset', source)
        if name is not None:
            target = next(item for item in targets if item.version == version)
            if self._confirm(f'Copy “{source}” from Blender {release.version} to {version}? '
                             'Preferences and addons may need adjustments for the destination version.'):
                self._run('Copying preset', lambda report, cancelled:
                          self.manager.duplicate_preset(release, source, name, target_release=target,
                                                        cancelled=cancelled))

    def _delete(self):
        name, release = self.preset.currentText(), self.release
        if name and self._confirm(f'Permanently delete preset “{name}”, including its preferences and addons? '
                                  'Close Blender instances using it first.'):
            self._run('Deleting preset', lambda report, cancelled: self.manager.remove_preset(release, name))

    def _inspect(self):
        release, name = self.release, self.preset.currentText()
        self._run('Refreshing addons', lambda report, cancelled:
                  inspect_addons(self.manager, release, name, cancelled=cancelled))

    def _open(self, path):
        if not qt.QDesktopServices.openUrl(qt.QUrl.fromLocalFile(str(path))):
            self.status.setText(f'Could not open {path}')

    def _open_addon(self):
        row = self.table.currentRow()
        if row >= 0:
            self._open(Path(self.table.item(row, 5).text()).parent)

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
