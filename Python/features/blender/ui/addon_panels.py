"""The Blender preset Addons and Installed files tabs and Blue Hole controls."""
from pathlib import Path

from commonUtils.ui import pyside as qt
from features.blender.addons import bluehole
from features.blender.addons.library import version_tuple
from features.blender.addons.ui.page import source_label


def build_addon_selection(page, controls, manage_layout):
    page.choices = qt.QTableWidget(0, 7)
    page.choices.setHorizontalHeaderLabels(['Load', 'Addon', 'Installed', 'Latest compatible', 'Status', 'Library', 'Type'])
    page.choices.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)
    page.choices.horizontalHeader().setStretchLastSection(False)
    for column in range(page.choices.columnCount()):
        page.choices.horizontalHeader().setSectionResizeMode(column, qt.QHeaderView.ResizeMode.Stretch if column == 1 else qt.QHeaderView.ResizeMode.ResizeToContents)
    page.apply_button = qt.QPushButton('Save Addon Selection')
    page.apply_button.clicked.connect(page._apply_addons)
    page.tabs = qt.QTabWidget()
    selection_page = qt.QWidget()
    selection_layout = qt.QVBoxLayout(selection_page)
    note = qt.QLabel('Choose addons from the library for this preset. Installed shows the current files. Latest compatible and Type show what the next launch will apply.')
    note.setWordWrap(True)
    selection_layout.addWidget(note)
    page.catalog_warning = qt.QLabel()
    page.catalog_warning.setTextFormat(qt.Qt.TextFormat.PlainText)
    page.catalog_warning.setWordWrap(True)
    page.catalog_warning.hide()
    selection_layout.addWidget(page.catalog_warning)
    page.bluehole_group = qt.QGroupBox('Blue Hole')
    bluehole_form = qt.QFormLayout(page.bluehole_group)
    page.bluehole_enabled = qt.QCheckBox('Enable Blue Hole')
    page.bluehole_source = qt.QComboBox()
    page.bluehole_source.addItems(['GitHub', 'Local'])
    page.bluehole_source.setAccessibleName('Blue Hole source')
    page.bluehole_checkout = qt.QLineEdit()
    page.bluehole_checkout.setAccessibleName('Blue Hole checkout folder')
    page.bluehole_checkout.setToolTip('Link this preset to the selected checkout, including uncommitted changes.')
    browse = qt.QPushButton('Browse…')
    browse.clicked.connect(page._browse_bluehole_checkout)
    page.bluehole_checkout_row = qt.QWidget()
    checkout_layout = qt.QHBoxLayout(page.bluehole_checkout_row)
    checkout_layout.setContentsMargins(0, 0, 0, 0)
    checkout_layout.addWidget(page.bluehole_checkout, 1)
    checkout_layout.addWidget(browse)
    page.bluehole_branch = qt.QComboBox()
    page.bluehole_branch.addItems(bluehole.BRANCHES)
    page.bluehole_branch.setAccessibleName('Blue Hole branch')
    page.bluehole_deluxe = qt.QComboBox()
    page.bluehole_deluxe.addItems(['No', 'Yes'])
    page.bluehole_deluxe.setAccessibleName('Blue Hole Deluxe')
    bluehole_form.addRow(page.bluehole_enabled)
    bluehole_form.addRow('Source', page.bluehole_source)
    bluehole_form.addRow('Branch', page.bluehole_branch)
    bluehole_form.addRow('Checkout', page.bluehole_checkout_row)
    bluehole_form.addRow('Deluxe', page.bluehole_deluxe)
    page.bluehole_form = bluehole_form
    page.bluehole_source.currentTextChanged.connect(page._show_bluehole_source)
    page._show_bluehole_source()
    page.bluehole_installed = qt.QLabel('Not installed')
    page.bluehole_installed.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
    bluehole_form.addRow('Currently installed', page.bluehole_installed)
    page.bluehole_deluxe_note = qt.QLabel()
    page.bluehole_deluxe_note.setWordWrap(True)
    bluehole_form.addRow(page.bluehole_deluxe_note)
    controls.insertWidget(1, page.bluehole_group)
    selection_layout.addWidget(page.choices)
    selection_layout.addWidget(page.apply_button, 0, qt.Qt.AlignmentFlag.AlignLeft)
    page.tabs.addTab(selection_page, 'Addons')
    manage_layout.addWidget(page.tabs, 1)


def build_installed_files(page):
    page.table = qt.QTableWidget(0, 6)
    page.table.setHorizontalHeaderLabels(['Addon', 'Version', 'Type', 'Enabled', 'Source', 'Location'])
    page.table.setSelectionBehavior(qt.QAbstractItemView.SelectionBehavior.SelectRows)
    page.table.setSelectionMode(qt.QAbstractItemView.SelectionMode.SingleSelection)
    page.table.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)
    page.table.horizontalHeader().setStretchLastSection(True)
    page.table.setSortingEnabled(True)
    page.tabs.addTab(page.table, 'Installed files')


class PresetAddonPresentation:
    """Populate retained controls from the page’s current preset and catalog."""

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

    def _show_bluehole_source(self):
        local = self.bluehole_source.currentText() == 'Local'
        self.bluehole_form.setRowVisible(self.bluehole_branch, not local)
        self.bluehole_form.setRowVisible(self.bluehole_checkout_row, local)

    def _browse_bluehole_checkout(self):
        path = qt.QFileDialog.getExistingDirectory(self, 'Choose Blue Hole Checkout', self.bluehole_checkout.text())
        if path:
            self.bluehole_checkout.setText(path)

    def _project_bluehole_choice(self, state, found):
        """Show requested channel settings beside the separately recorded installation."""
        config = state.get('bluehole', bluehole.DEFAULT)
        config = bluehole.validate(config)
        self.bluehole_enabled.setChecked(config['enabled'])
        self.bluehole_source.setCurrentText('Local' if config.get('source') == 'local' else 'GitHub')
        self.bluehole_checkout.setText(config.get('path', ''))
        self.bluehole_branch.setCurrentText(config['branch'])
        runtime_deluxe = self.release is not None and bluehole.uses_runtime_deluxe(self.release)
        self.bluehole_form.setRowVisible(self.bluehole_deluxe, not runtime_deluxe)
        self.bluehole_deluxe.setCurrentText('Yes' if config['deluxe'] else 'No')
        self.bluehole_deluxe_note.setText(
            'Enable Deluxe Keymaps in Blender under Blue Hole → Updates & Deluxe.'
            if runtime_deluxe else 'Deluxe copies Blue Hole keymaps and stamps this preset’s saved preferences.')
        current = state.get('installed_bluehole') or state.get('bluehole', {})
        bh = state['installed'].get(bluehole.IDENTITY)
        if bh and bh['module'] in found and current.get('source') == 'local':
            self.bluehole_installed.setText(f"Local checkout · {current['version']}")
            self.bluehole_installed.setToolTip(current.get('path', ''))
        elif bh and bh['module'] in found:
            commit = current.get('commit')
            self.bluehole_installed.setText(f"{current.get('branch', 'Unknown branch')} · {commit[:12] if commit else 'Commit unknown'} · {bh.get('version') or found[bh['module']]['version'] or 'Version unknown'}")
            self.bluehole_installed.setToolTip(commit or 'No installed commit recorded')
        else:
            self.bluehole_installed.setText('Not installed')
            self.bluehole_installed.setToolTip('The selected source will be checked on launch')

    def _project_addon_choices(self, identities, groups, selected, installed_groups, found, unmanaged):
        """Render one admitted catalog/selection/filesystem snapshot into retained rows."""
        self.choices.setRowCount(len(identities))
        for row, identity in enumerate(identities):
            releases = groups.get(identity, [])
            latest = max(releases, key=lambda a: version_tuple(a.version), default=None)
            replacements = {addon.identity: identity for addon in releases}
            resolved = (self.library.resolve(identity, self.release, entries=releases, replacements=replacements)
                        if self.release else None)
            check = qt.QTableWidgetItem('')
            check.setData(qt.Qt.ItemDataRole.UserRole, identity)
            check.setFlags(qt.Qt.ItemFlag.ItemIsEnabled | qt.Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(qt.Qt.CheckState.Checked if identity in selected else qt.Qt.CheckState.Unchecked)
            if not resolved and identity not in selected:
                check.setFlags(qt.Qt.ItemFlag.NoItemFlags)
            self.choices.setItem(row, 0, check)
            managed = installed_groups.get(identity, {})
            installed = managed.get(resolved.identity) if resolved else None
            if not installed and managed:
                installed = next((entry for entry in managed.values() if entry['module'] in found),
                                 next(iter(managed.values())))
            unmanaged_copy = unmanaged.get(identity)
            physical = found.get(installed['module']) if installed else unmanaged_copy
            installed_version = (physical.get('version') or (installed.get('version') if installed else None) or 'Unknown') if physical else '—'
            if unmanaged_copy:
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
            elif physical and len(managed) > 1:
                status = 'Package cleanup pending'
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
            kind = resolved.kind if resolved else physical['kind'] if physical else latest.kind if latest else '—'
            values = (title, installed_version, resolved.version if resolved else '—', status,
                      source_label(resolved.source) if resolved else '—', kind)
            for column, value in enumerate(values, 1):
                self.choices.setItem(row, column, qt.QTableWidgetItem(value))
            if resolved:
                detail = f"Blender {resolved.minimum}+" + (f"; below {resolved.maximum}" if resolved.maximum else '')
                detail += f"\n{resolved.package_name or resolved.package.name}" + (f"\nPackage date: {resolved.published}" if resolved.published else '')
                self.choices.item(row, 3).setToolTip(detail)
            if installed:
                installed_kind = 'Extension' if installed['module'].startswith('bl_ext.') else 'Legacy addon'
                self.choices.item(row, 2).setToolTip(
                    f"{installed_kind} · {source_label(installed.get('source', 'Managed'))}\n"
                    f"{installed['path']}\n{installed.get('package_name', '')}")
        self.choices.resizeColumnsToContents()
