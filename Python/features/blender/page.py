"""Feature-owned Blender manager page; all lengthy work uses shared workers."""
from pathlib import Path
from configparser import Error as ConfigError

from commonUtils.ui import pyside as qt
from commonUtils.runtime.operations import check_cancelled
from commonUtils.ui.tasks.operation_progress import OperationProgress
from .addons import inspect_addons, scan_preset
from .library import AddonLibrary, version_tuple
from .library_page import source_label
from ui_new.landing import LaunchCard
from .manager import get_manager
from . import bluehole
from .releases import load_releases, platform_key


class BlenderPage(qt.QWidget):
    idle = qt.Signal()
    feature_settings_requested = qt.Signal(str)

    def __init__(self, parent=None, *, manager=None, settings_mode=False):
        super().__init__(parent)
        self.manager = manager or get_manager()
        self.settings_mode = settings_mode
        self.library = AddonLibrary(self.manager)
        self.releases = []
        self._operation = ''
        self._select_preset = None
        self._choices_context = None
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
        description = qt.QLabel('Your Blender configurations, ready to launch.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.stack = qt.QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.home = qt.QWidget()
        home = qt.QVBoxLayout(self.home)
        home.setContentsMargins(0, 0, 0, 0)
        toolbar = qt.QHBoxLayout()
        self.add_configuration = qt.QPushButton('Add Configuration…')
        toolbar.addWidget(self.add_configuration)
        toolbar.addStretch()
        home.addLayout(toolbar)
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.cards_widget = qt.QWidget()
        self.cards = qt.QVBoxLayout(self.cards_widget)
        self.cards.setContentsMargins(0, 12, 0, 0)
        scroll.setWidget(self.cards_widget)
        home.addWidget(scroll)
        self.stack.addWidget(self.home)
        self.manage = qt.QWidget()
        manage_layout = qt.QVBoxLayout(self.manage)
        manage_layout.setContentsMargins(0, 0, 0, 0)
        back = qt.QPushButton('‹ Back to configurations')
        back.clicked.connect(lambda: self.stack.setCurrentWidget(self.home))
        manage_layout.addWidget(back, 0, qt.Qt.AlignmentFlag.AlignLeft)
        back.setVisible(not settings_mode)
        self.manage_heading = qt.QLabel('Manage configuration')
        manage_layout.addWidget(self.manage_heading)
        self.preset_list = None
        if settings_mode:
            self.preset_splitter = qt.QSplitter(qt.Qt.Orientation.Horizontal)
            selector = qt.QWidget()
            selector_layout = qt.QVBoxLayout(selector)
            selector_layout.setContentsMargins(0, 0, 8, 0)
            selector_header = qt.QHBoxLayout()
            selector_header.addWidget(qt.QLabel('Presets'), 1)
            self.add_preset_button = qt.QToolButton()
            self.add_preset_button.setText('+')
            self.add_preset_button.setAccessibleName('Add Blender preset')
            self.add_preset_button.setToolTip('Add a preset')
            self.add_preset_button.clicked.connect(self._add_configuration)
            selector_header.addWidget(self.add_preset_button)
            selector_layout.addLayout(selector_header)
            self.preset_list = qt.QListWidget()
            self.preset_list.setAccessibleName('Blender presets')
            self.preset_list.setMinimumWidth(180)
            self.preset_list.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
            self.preset_list.currentItemChanged.connect(self._select_list_preset)
            self.preset_list.customContextMenuRequested.connect(self._preset_context_menu)
            selector_layout.addWidget(self.preset_list, 1)
            self.preset_splitter.addWidget(selector)
            self.preset_splitter.addWidget(self.manage)
            self.preset_splitter.setStretchFactor(0, 0)
            self.preset_splitter.setStretchFactor(1, 1)
            self.preset_splitter.setSizes([230, 750])
            self.stack.addWidget(self.preset_splitter)
            title.hide()
            description.hide()
        else:
            self.stack.addWidget(self.manage)
        self.controls = qt.QWidget()
        controls = qt.QVBoxLayout(self.controls)
        controls.setContentsMargins(0, 0, 0, 0)
        selection = qt.QFormLayout()
        self.version = qt.QComboBox()
        self.preset = qt.QComboBox()
        self.preset_version_label = qt.QLabel()
        if settings_mode:
            selection.addRow('Blender version', self.preset_version_label)
            self.version.setParent(self.controls)
            self.preset.setParent(self.controls)
            self.version.hide()
            self.preset.hide()
        else:
            selection.addRow('Blender version', self.version)
            selection.addRow('Preference preset', self.preset)
        controls.addLayout(selection)
        self.install_status = qt.QLabel()
        self.install_status.setWordWrap(True)
        self.install_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        controls.addWidget(self.install_status)
        self.remove_button = qt.QPushButton('Remove Installation')
        self.launch_button = qt.QPushButton('Launch Blender')
        self.install_folder = qt.QPushButton('Open Installation Folder')
        self.create_button = qt.QPushButton('New Preset…')
        self.duplicate_button = qt.QPushButton('Duplicate Preset')
        self.copy_button = qt.QPushButton('Copy to Another Version')
        self.rename_button = qt.QPushButton('Rename Preset')
        self.delete_button = qt.QPushButton('Delete Preset')
        self.preset_folder = qt.QPushButton('Open Preset Folder')
        self.refresh_button = qt.QPushButton('Refresh Addons')
        self.addon_folder = qt.QPushButton('Open Addon Folder')
        primary = qt.QHBoxLayout()
        if not settings_mode:
            primary.addWidget(self.create_button)
        else:
            self.create_button.setParent(self.controls)
            self.create_button.hide()
        primary.addWidget(self.launch_button)
        self.actions = qt.QToolButton()
        self.actions.setText('More…')
        self.actions.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = qt.QMenu(self.actions)
        for button in (self.duplicate_button, self.copy_button, self.rename_button, self.delete_button,
                       self.preset_folder, self.refresh_button, self.addon_folder, self.install_folder, self.remove_button):
            action = menu.addAction(button.text())
            action.triggered.connect(button.click)
            button.hide()
            button.setParent(self.controls)
            button._menu_action = action
        self.actions.setMenu(menu)
        primary.addWidget(self.actions)
        self.add_addon = qt.QPushButton('Add Addon…')
        self.add_addon.setToolTip('Import a ZIP for this preset only; shared packages remain unchanged.')
        self.add_addon.clicked.connect(self._add_preset_addon)
        if settings_mode:
            primary.addWidget(self.add_addon)
        else:
            self.add_addon.setParent(self.controls)
            self.add_addon.hide()
        primary.addStretch()
        controls.addLayout(primary)
        manage_layout.addWidget(self.controls)
        self.choices = qt.QTableWidget(0, 6)
        self.choices.setHorizontalHeaderLabels(['Load', 'Addon', 'Installed', 'Latest compatible', 'Status', 'Library'])
        self.choices.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.choices.horizontalHeader().setStretchLastSection(False)
        for column in range(6):
            self.choices.horizontalHeader().setSectionResizeMode(column, qt.QHeaderView.ResizeMode.Stretch if column == 1 else qt.QHeaderView.ResizeMode.ResizeToContents)
        self.apply_button = qt.QPushButton('Save Addon Selection')
        self.apply_button.clicked.connect(self._apply_addons)
        self.tabs = qt.QTabWidget()
        selection_page = qt.QWidget()
        selection_layout = qt.QVBoxLayout(selection_page)
        note = qt.QLabel('Choose addons from the library for this preset. Installed shows the current files; Latest compatible shows what the next launch will apply.')
        note.setWordWrap(True)
        selection_layout.addWidget(note)
        self.catalog_warning = qt.QLabel()
        self.catalog_warning.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.catalog_warning.setWordWrap(True)
        self.catalog_warning.hide()
        selection_layout.addWidget(self.catalog_warning)
        self.bluehole_group = qt.QGroupBox('Blue Hole')
        bluehole_form = qt.QFormLayout(self.bluehole_group)
        self.bluehole_enabled = qt.QCheckBox('Enable Blue Hole')
        self.bluehole_branch = qt.QComboBox()
        self.bluehole_branch.addItems(bluehole.BRANCHES)
        self.bluehole_branch.setAccessibleName('Blue Hole branch')
        self.bluehole_deluxe = qt.QComboBox()
        self.bluehole_deluxe.addItems(['No', 'Yes'])
        self.bluehole_deluxe.setAccessibleName('Blue Hole Deluxe')
        bluehole_form.addRow(self.bluehole_enabled)
        bluehole_form.addRow('Branch', self.bluehole_branch)
        bluehole_form.addRow('Deluxe', self.bluehole_deluxe)
        self.bluehole_installed = qt.QLabel('Not installed')
        self.bluehole_installed.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        bluehole_form.addRow('Currently installed', self.bluehole_installed)
        bluehole_form.addRow(qt.QLabel('Deluxe copies Blue Hole keymaps and stamps this preset’s saved preferences.'))
        controls.insertWidget(1, self.bluehole_group)
        selection_layout.addWidget(self.choices)
        selection_layout.addWidget(self.apply_button, 0, qt.Qt.AlignmentFlag.AlignLeft)
        self.tabs.addTab(selection_page, 'Addons')
        manage_layout.addWidget(self.tabs, 1)
        self.add_configuration.clicked.connect(self._add_configuration)
        self.setStyleSheet("""
            QPushButton#launchCard { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }
            QPushButton#launchCard:hover { background: palette(midlight); border-color: palette(highlight); }
            QPushButton#launchCard:focus { border: 2px solid palette(highlight); }
            QLabel#launchTitle { font-size: 16px; font-weight: 600; }
            QLabel#launchDetail { color: palette(text); }
        """)
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
        self.tabs.addTab(self.table, 'Installed files')
        layout.addWidget(self.task)
        self.version.currentIndexChanged.connect(self._version_changed)
        self.preset.currentIndexChanged.connect(self._preset_changed)
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
        if not settings_mode:
            self.add_configuration.setText('Configure Blender…')
        self.refresh()
        if settings_mode:
            self.stack.setCurrentWidget(self.preset_splitter if self.settings_mode else self.manage)

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
        self._rebuild_cards()
        self._rebuild_preset_list()

    def _update_controls(self):
        release = self.release
        ready = bool(release and self.manager.ready(release))
        has_preset = bool(release and self.preset.currentText())
        self.remove_button.setEnabled(ready)
        self.launch_button.setEnabled(has_preset)
        self.install_folder.setEnabled(ready)
        self.create_button.setEnabled(bool(release))
        for button in (self.duplicate_button, self.rename_button, self.delete_button,
                       self.preset_folder, self.refresh_button):
            button.setEnabled(has_preset)
        self.copy_button.setEnabled(has_preset and len(self.releases) > 1)
        self.addon_folder.setEnabled(self.table.rowCount() > 0)
        self.add_addon.setEnabled(has_preset)
        self.apply_button.setEnabled(has_preset and self._choices_context is not None)
        self.bluehole_group.setEnabled(has_preset)
        self.tabs.setEnabled(has_preset)
        self.bluehole_enabled.setEnabled(has_preset)
        self.bluehole_branch.setEnabled(has_preset)
        for button in (self.duplicate_button, self.copy_button, self.rename_button, self.delete_button,
                       self.preset_folder, self.refresh_button, self.addon_folder, self.install_folder, self.remove_button):
            button._menu_action.setEnabled(button.isEnabled())
        self.install_status.setText('' if not release else
                                   f'{"Installed" if ready else "Not installed"} · {platform_key()}')

    def _preset_changed(self, *_args):
        self._invalidate_choices()
        try:
            rows = scan_preset(self.manager.preset(self.release, self.preset.currentText())) if (
                self.release and self.preset.currentText()) else []
            self._show_rows(rows)
            self._show_choices()
            if self.release:
                self.status.setText('Choose a configuration to launch, or open Settings to adjust its addons.'
                                    if self.preset.currentText() else 'Create a preset in Settings → Blender → Presets to get started.')
                self.manage_heading.setText(f'Blender {self.release.version} · {self.preset.currentText()}'
                                            if self.preset.currentText() else f'Manage Blender {self.release.version}')
            self.preset_version_label.setText(self.release.version if self.release and self.preset.currentText() else 'Select or add a preset')
            self._mark_selected_preset()
            self.controls.setEnabled(True)
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
        self.stack.setEnabled(False)
        self.controls.setEnabled(False)
        self.table.setEnabled(False)
        self.task.start(work, message=f'{operation}…')

    def _finished(self, result, error):
        self.stack.setEnabled(True)
        self.controls.setEnabled(True)
        self.table.setEnabled(True)
        cancelled = self.task.cancelled.is_set() and (not error or error == 'Operation cancelled')
        if self._operation == 'Refreshing addons' and not error and not cancelled:
            rows, message = result
            self._show_rows(rows)
            self.status.setText(message)
            self._update_controls()
        else:
            if isinstance(result, Path) and self._operation in ('Duplicating preset', 'Copying preset'):
                self._select_preset = result.name
                if self._operation == 'Copying preset':
                    with qt.QSignalBlocker(self.version):
                        self.version.setCurrentText(result.parent.name)
            self._version_changed()
            self.status.setText('Cancelled.' if cancelled else
                                f'{self._operation} failed: {error}' if error else f'{self._operation} finished.')
            if cancelled:
                self.task.message.setText('Cancelled.')

    def _remove(self):
        release = self.release
        if release and self._confirm(f'Remove Blender {release.version}? Presets and addons will be kept. '
                                     'Close any Blender instances using this installation first.'):
            self._run('Removing Blender', lambda report, cancelled: self.manager.remove(release))

    def _launch(self):
        if self.task.busy:
            return
        release, name = self.release, self.preset.currentText()
        if not release or not name:
            return
        try:
            state = self.library.selection(self.manager.preset(release, name))
            needs_install = not self.manager.ready(release)
            if needs_install and not self._confirm(f'Download and install Blender {release.version}?\n\n'
                                                  f'Destination: {self.manager.installation(release)}'):
                return
            bluehole_choice = bluehole.validate(state.get('bluehole', bluehole.DEFAULT))
            if needs_install or state['selected'] or state['installed'] or bluehole_choice['enabled']:
                def work(report, cancelled):
                    if needs_install:
                        self.manager.install(release, report=report, cancelled=cancelled)
                    check_cancelled(cancelled)
                    if state['selected'] or state['installed'] or bluehole_choice['enabled']:
                        self.library.apply(release, name, state['selected'], bluehole=bluehole_choice, cancelled=cancelled)
                    check_cancelled(cancelled)
                    return self.manager.launch(release, name)
                self._run('Installing and launching Blender' if needs_install else 'Launching Blender', work)
            else:
                pid = self.manager.launch(release, name)
                self.status.setText(f'Launched Blender {release.version} with {name} (PID {pid}).')
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def _create(self, *, name=None):
        if name is None:
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

    def _rebuild_cards(self):
        while self.cards.count():
            item = self.cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.launch_cards = []
        for release in self.releases:
            for name in self.manager.presets(release):
                row = qt.QWidget()
                horizontal = qt.QHBoxLayout(row)
                horizontal.setContentsMargins(0, 0, 0, 0)
                ready = self.manager.ready(release)
                card = LaunchCard(f'Blender {release.version} · {name}',
                                  'Click to launch' if ready else 'Click to install and launch', 'blender')
                card.clicked.connect(lambda checked=False, r=release, n=name: self._launch_card(r, n))
                manage = qt.QPushButton('Manage')
                manage.setAccessibleName(f'Manage Blender {release.version} {name}')
                manage.clicked.connect(lambda checked=False, r=release, n=name: self._manage_configuration(r, n))
                horizontal.addWidget(card, 1)
                horizontal.addWidget(manage)
                self.cards.addWidget(row)
                self.launch_cards.append(card)
        if not self.launch_cards:
            message = qt.QLabel('Create your first preset in Settings → Blender → Presets. Each preset keeps its own preferences and addon selection.')
            message.setWordWrap(True)
            self.cards.addWidget(message)
        self.cards.addStretch()

    def _manage_configuration(self, release=None, name=None):
        if not self.settings_mode:
            self.manager.settings_selection = (release.version if release else None, name)
            self.feature_settings_requested.emit('blender')
            return
        if release:
            self.version.setCurrentText(release.version)
        if name:
            self.preset.setCurrentText(name)
        self.stack.setCurrentWidget(self.preset_splitter if self.settings_mode else self.manage)

    def _launch_card(self, release, name):
        self.version.setCurrentText(release.version)
        self.preset.setCurrentText(name)
        self._launch()

    def _mark_selected_preset(self):
        if self.preset_list is None:
            return
        selected = (self.release.version, self.preset.currentText()) if self.release else None
        with qt.QSignalBlocker(self.preset_list):
            for index in range(self.preset_list.count()):
                item = self.preset_list.item(index)
                if item.data(qt.Qt.ItemDataRole.UserRole) == selected:
                    self.preset_list.setCurrentItem(item)
                    return
            self.preset_list.setCurrentRow(-1)

    def _rebuild_preset_list(self):
        if self.preset_list is None:
            return
        with qt.QSignalBlocker(self.preset_list):
            self.preset_list.clear()
            for release in self.releases:
                for name in self.manager.presets(release):
                    item = qt.QListWidgetItem(f'{name}\nBlender {release.version}')
                    item.setData(qt.Qt.ItemDataRole.UserRole, (release.version, name))
                    self.preset_list.addItem(item)
        self._mark_selected_preset()
        if self.preset_list.currentRow() < 0 and self.preset_list.count() and not getattr(self, '_adding_preset', False):
            self.preset_list.setCurrentRow(0)
        self.add_preset_button.setEnabled(bool(self.releases))

    def _select_list_preset(self, item, previous=None):
        if item is None:
            return
        version, name = item.data(qt.Qt.ItemDataRole.UserRole)
        self.version.setCurrentText(version)
        self.preset.setCurrentText(name)

    def _preset_context_menu(self, position):
        item = self.preset_list.itemAt(position)
        if item is None or self.task.busy:
            return
        self.preset_list.setCurrentItem(item)
        menu = qt.QMenu(self.preset_list)
        for title, callback in (('Rename…', self._rename), ('Duplicate…', self._duplicate),
                                ('Copy to Another Version…', self._copy), ('Delete…', self._delete)):
            action = menu.addAction(title)
            action.triggered.connect(callback)
        menu.exec(self.preset_list.viewport().mapToGlobal(position))

    def _preset_details(self):
        dialog = qt.QDialog(self)
        dialog.setWindowTitle('New Blender Preset')
        form = qt.QFormLayout(dialog)
        version = qt.QComboBox(dialog)
        version.addItems([release.version for release in self.releases])
        version.setCurrentText(self.version.currentText())
        version.setAccessibleName('Blender version')
        name = qt.QLineEdit('Default', dialog)
        name.setAccessibleName('Preset name')
        name.selectAll()
        form.addRow('Blender version', version)
        form.addRow('Preset name', name)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok | qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        name.setFocus()
        if dialog.exec() == qt.QDialog.DialogCode.Accepted:
            return version.currentText(), name.text()
        return None

    def _add_configuration(self):
        if not self.settings_mode:
            self._manage_configuration()
            return
        if not self.releases:
            self.status.setText('Configure a Blender release in Settings first.')
            return
        details = self._preset_details()
        if details is not None:
            version, name = details
            self._adding_preset = True
            try:
                self.version.setCurrentText(version)
                self._create(name=name)
                self._manage_configuration()
            finally:
                self._adding_preset = False
                self._rebuild_preset_list()

    def _add_preset_addon(self):
        if self.task.busy or not self.release or not self.preset.currentText():
            return
        release, name = self.release, self.preset.currentText()
        try:
            self.manager._require_idle(release, name)
            library = self.library.for_preset(self.manager.preset(release, name))
            package, _ = qt.QFileDialog.getOpenFileName(self, 'Add Addon to Preset', '', 'Addon ZIP (*.zip)')
            if package:
                self._run('Adding preset addon', lambda report, cancelled: library.add(package, cancelled=cancelled))
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def _invalidate_choices(self):
        self._choices_context = None
        self.choices.setRowCount(0)
        self.apply_button.setEnabled(False)
        self.bluehole_group.setEnabled(False)

    def _show_choices(self):
        self._invalidate_choices()
        state = {'selected': [], 'installed': {}}
        root = None
        found = {}
        if self.release and self.preset.currentText():
            root = self.manager.preset(self.release, self.preset.currentText())
            state = self.library.selection(root)
            found = {item['module']: item for item in scan_preset(root)}
        catalog = self.library.for_preset(root) if root is not None else self.library
        entries = catalog.entries(shared_only=root is None)
        self.catalog_warning.setText('Some packages were skipped:\n' + '\n'.join(catalog.errors))
        self.catalog_warning.setVisible(bool(catalog.errors))
        identities = sorted({addon.identity for addon in entries})
        selected = state['selected']
        actual = {('extension:' + row['module'].split('.')[-1] if row['kind'] == 'Extension' else 'legacy:' + row['module']): row for row in found.values()}
        identities = sorted(set(identities) | set(selected) | set(state['installed']) | set(actual),
                            key=lambda identity: (next((a.name for a in entries if a.identity == identity), identity).casefold(), identity))
        config = state.get('bluehole', bluehole.DEFAULT)
        config = bluehole.validate(config)
        self.bluehole_enabled.setChecked(config['enabled'])
        self.bluehole_branch.setCurrentText(config['branch'])
        self.bluehole_deluxe.setCurrentText('Yes' if config['deluxe'] else 'No')
        current = state.get('installed_bluehole') or state.get('bluehole', {})
        bh = state['installed'].get(bluehole.IDENTITY)
        if bh and bh['module'] in found:
            commit = current.get('commit')
            self.bluehole_installed.setText(f"{current.get('branch', 'Unknown branch')} · {commit[:12] if commit else 'Commit unknown'} · {bh.get('version') or found[bh['module']]['version'] or 'Version unknown'}")
            self.bluehole_installed.setToolTip(commit or 'No installed commit recorded')
        else:
            self.bluehole_installed.setText('Not installed')
            self.bluehole_installed.setToolTip('The selected branch will be checked on launch')
        identities = [identity for identity in identities if identity != bluehole.IDENTITY]
        self.choices.setRowCount(len(identities))
        for row, identity in enumerate(identities):
            releases = [a for a in entries if a.identity == identity]
            latest = max(releases, key=lambda a: version_tuple(a.version), default=None)
            resolved = self.library.resolve(identity, self.release, entries=entries) if self.release else None
            check = qt.QTableWidgetItem('')
            check.setData(qt.Qt.ItemDataRole.UserRole, identity)
            check.setFlags(qt.Qt.ItemFlag.ItemIsEnabled | qt.Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(qt.Qt.CheckState.Checked if identity in selected else qt.Qt.CheckState.Unchecked)
            if not resolved and identity not in selected:
                check.setFlags(qt.Qt.ItemFlag.NoItemFlags)
            self.choices.setItem(row, 0, check)
            installed = state['installed'].get(identity)
            physical = found.get(installed['module']) if installed else actual.get(identity)
            installed_version = (physical.get('version') or (installed.get('version') if installed else None) or 'Unknown') if physical else '—'
            if physical and not installed:
                status = 'Installed outside library'
                check.setToolTip('These files are not managed by Logistics; use Installed files to inspect them.')
                if identity not in selected:
                    check.setFlags(qt.Qt.ItemFlag.NoItemFlags)
            elif installed and not physical:
                status = 'Installed files missing'
            elif physical and identity not in selected:
                status = 'Removal pending'
            elif physical and not resolved:
                status = 'Missing from library' if not releases else 'No compatible version'
            elif physical and resolved and installed['digest'] == resolved.digest:
                status = 'Up to date'
            elif physical:
                status = 'Update available'
                try:
                    if version_tuple(resolved.version) < version_tuple(installed_version):
                        status = 'Different package available'
                except ValueError:
                    pass
            elif identity in selected:
                status = 'Installation pending' if resolved else 'No compatible version'
            else:
                status = 'Available' if resolved else 'Incompatible'
            title = latest.name if latest else installed.get('name', identity) if installed else physical.get('name', identity) if physical else identity
            values = (title, installed_version, resolved.version if resolved else '—', status, source_label(resolved.source) if resolved else '—')
            for column, value in enumerate(values, 1):
                self.choices.setItem(row, column, qt.QTableWidgetItem(value))
            if resolved:
                detail = f"Blender {resolved.minimum}+" + (f"; below {resolved.maximum}" if resolved.maximum else '')
                detail += f"\n{resolved.package_name or resolved.package.name}" + (f"\nPackage date: {resolved.published}" if resolved.published else '')
                self.choices.item(row, 3).setToolTip(detail)
            if installed:
                self.choices.item(row, 2).setToolTip(f"{source_label(installed.get('source', 'Managed'))}\n{installed['path']}\n{installed.get('package_name', '')}")
        self.choices.resizeColumnsToContents()
        if root is not None:
            self._choices_context = (self.release.version, self.preset.currentText())
            self.bluehole_group.setEnabled(True)
            self.apply_button.setEnabled(True)

    def _apply_addons(self):
        if not self.release or self._choices_context != (self.release.version, self.preset.currentText()):
            self.status.setText('Refresh this preset before saving its addon selection.')
            return
        identities = [self.choices.item(row, 0).data(qt.Qt.ItemDataRole.UserRole) for row in range(self.choices.rowCount())
                      if self.choices.item(row, 0).checkState() == qt.Qt.CheckState.Checked]
        release, name = self.release, self.preset.currentText()
        config = {'enabled': self.bluehole_enabled.isChecked(), 'branch': self.bluehole_branch.currentText(),
                  'deluxe': self.bluehole_deluxe.currentText() == 'Yes'}
        # Store intent independently of installing Blender/downloading addons.
        import json
        try:
            self.manager._require_idle(release, name)
            root = self.manager.preset(release, name)
            state = self.library.selection(root)
            if 'installed_bluehole' not in state and state.get('bluehole', {}).get('commit'):
                state['installed_bluehole'] = {key: state['bluehole'].get(key) for key in ('branch', 'commit')}
            if config['deluxe']:
                config['deluxe_stamp'] = state.get('bluehole', {}).get('deluxe_stamp')
            staged = self.manager._contained(root, '.logistics-addons.tmp')
            staged.write_text(json.dumps({**state, 'selected': identities, 'bluehole': config}, indent=2), encoding='utf-8')
            staged.replace(root / '.logistics-addons.json')
            self._show_choices()
            self.status.setText('Addon selection saved. It will be applied on the next launch.')
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

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
