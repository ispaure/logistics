"""
rclone management page for the Logistics feature UI.
"""

from commonUtils import ui
from commonUtils.ui import pyside

from features.rclone import configuration, credentials


class RclonePage(pyside.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.credential_list = pyside.QListWidget()
        self.credential_list.setMinimumWidth(220)
        self.credential_list.setMaximumWidth(320)

        self.package_name = pyside.QLabel('Select a credential package')
        self.package_path = pyside.QLabel()
        self.package_path.setWordWrap(True)
        self.package_path.setTextInteractionFlags(
            pyside.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.generated_config_path = pyside.QLabel()
        self.generated_config_path.setWordWrap(True)
        self.generated_config_path.setTextInteractionFlags(
            pyside.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.loaded_status = pyside.QLabel('Not loaded')

        self.password_input = pyside.QLineEdit()
        self.password_input.setEchoMode(pyside.QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText('Credential archive password')
        self.password_input.setMinimumHeight(self.password_input.sizeHint().height())

        self.load_button = pyside.QPushButton('Load / Replace Credentials')
        self.remove_button = pyside.QPushButton('Remove Loaded Config')

        self.remote_list = pyside.QListWidget()

        self.config_directory = pyside.QLabel()
        self.config_directory.setWordWrap(True)
        self.config_directory.setTextInteractionFlags(
            pyside.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.clear_all_button = pyside.QPushButton('Clear All .conf Files')

        self.status_label = pyside.QLabel()
        self.status_label.setWordWrap(True)

        self._build_layout()
        self._connect_signals()
        self.refresh()

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        title = pyside.QLabel('Credential packages')
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 7)
        title_font.setBold(True)
        title.setFont(title_font)

        description = pyside.QLabel(
            'Load each credential ZIP into its own same-named rclone .conf. '
            'Credential ZIP packages remain unchanged and can be loaded again later.'
        )
        description.setWordWrap(True)

        root_layout.addWidget(title)
        root_layout.addWidget(description)

        splitter = pyside.QSplitter(pyside.Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_packages_panel())
        details_scroll = pyside.QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setFrameShape(pyside.QFrame.Shape.NoFrame)
        details_scroll.setWidget(self._create_details_panel())
        splitter.addWidget(details_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 740])

        root_layout.addWidget(splitter, 1)

    def _create_packages_panel(self):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = pyside.QLabel('Credential Packages')
        label_font = label.font()
        label_font.setBold(True)
        label.setFont(label_font)

        help_label = pyside.QLabel(
            'Available encrypted ZIP packages from the Logistics '
            'RemoteCredentials folder and Marc’s Dropbox when available.'
        )
        help_label.setWordWrap(True)

        layout.addWidget(label)
        layout.addWidget(help_label)
        layout.addWidget(self.credential_list)

        return widget

    def _create_details_panel(self):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(14)

        package_group = pyside.QGroupBox('Selected Credential Package')
        package_layout = pyside.QVBoxLayout(package_group)
        package_layout.setSpacing(10)

        name_font = self.package_name.font()
        name_font.setPointSize(name_font.pointSize() + 3)
        name_font.setBold(True)
        self.package_name.setFont(name_font)

        package_form = pyside.QFormLayout()
        package_form.setFieldGrowthPolicy(
            pyside.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        package_form.addRow('ZIP path:', self.package_path)
        package_form.addRow('Generated config:', self.generated_config_path)
        package_form.addRow('Status:', self.loaded_status)
        package_form.addRow('Password:', self.password_input)

        package_buttons = pyside.QHBoxLayout()
        package_buttons.addWidget(self.load_button)
        package_buttons.addWidget(self.remove_button)

        package_layout.addWidget(self.package_name)
        package_layout.addLayout(package_form)
        package_layout.addLayout(package_buttons)

        remotes_group = pyside.QGroupBox('Configured Remotes')
        remotes_layout = pyside.QVBoxLayout(remotes_group)
        remotes_layout.addWidget(self.remote_list)

        global_group = pyside.QGroupBox('rclone Configuration Folder')
        global_layout = pyside.QVBoxLayout(global_group)
        global_layout.setSpacing(10)

        config_form = pyside.QFormLayout()
        config_form.addRow('Folder:', self.config_directory)

        clear_help = pyside.QLabel(
            'Clear every .conf file in this folder, including the legacy '
            'rclone.conf and all generated credential configs. '
            'Credential ZIP packages are not deleted.'
        )
        clear_help.setWordWrap(True)

        global_layout.addLayout(config_form)
        global_layout.addWidget(clear_help)
        global_layout.addWidget(self.clear_all_button)

        layout.addWidget(package_group)
        layout.addWidget(remotes_group, 1)
        layout.addWidget(global_group)
        layout.addWidget(self.status_label)

        return widget

    def _connect_signals(self):
        self.credential_list.currentItemChanged.connect(
            self._credential_selection_changed
        )
        self.password_input.returnPressed.connect(
            self._load_selected_credentials
        )
        self.load_button.clicked.connect(self._load_selected_credentials)
        self.remove_button.clicked.connect(self._remove_selected_config)
        self.clear_all_button.clicked.connect(self._clear_all_configs)

    def refresh(self):
        """Refresh credential packages and generated config state."""

        selected_package_path = None
        current_item = self.credential_list.currentItem()

        if current_item is not None:
            current_package = current_item.data(
                pyside.Qt.ItemDataRole.UserRole
            )

            if current_package is not None:
                selected_package_path = current_package.path

        self.config_directory.setText(
            str(configuration.get_rclone_config_dir())
        )

        self._refresh_credential_packages(selected_package_path)
        self._refresh_clear_all_state()

    def _refresh_credential_packages(self, selected_package_path=None):
        self.credential_list.blockSignals(True)
        self.credential_list.clear()

        packages = credentials.get_logistics_remote_credentials_zip_lst()
        selected_row = 0
        from collections import Counter
        names = Counter(package.name_without_ext.casefold() for package in packages)

        for row, package in enumerate(packages):
            config_path = configuration.get_credential_config_path(
                package.path
            )

            label = package.name_without_ext
            if names[label.casefold()] > 1:
                label += f' — {package.path.parent}'

            if config_path.is_file():
                label += ' [Loaded]'

            item = pyside.QListWidgetItem(label)
            item.setToolTip(str(package.path))
            item.setData(pyside.Qt.ItemDataRole.UserRole, package)
            self.credential_list.addItem(item)

            if (
                selected_package_path is not None
                and package.path == selected_package_path
            ):
                selected_row = row

        self.credential_list.blockSignals(False)

        if not packages:
            self.package_name.setText('No credential packages found')
            self.package_path.setText('')
            self.generated_config_path.setText('')
            self.loaded_status.setText('Not loaded')
            self.password_input.clear()
            self.password_input.setEnabled(False)
            self.load_button.setEnabled(False)
            self.remove_button.setEnabled(False)
            self.remote_list.clear()
            self.remote_list.addItem('(No credential package selected)')
            return

        self.password_input.setEnabled(True)
        self.load_button.setEnabled(True)
        self.credential_list.setCurrentRow(selected_row)
        self._refresh_selected_package()

    def _credential_selection_changed(self, _current, _previous):
        self._refresh_selected_package()

    def _refresh_selected_package(self):
        package = self._get_selected_package()

        self.password_input.clear()
        self.status_label.clear()
        self.remote_list.clear()

        if package is None:
            self.package_name.setText('Select a credential package')
            self.package_path.setText('')
            self.generated_config_path.setText('')
            self.loaded_status.setText('Not loaded')
            self.remove_button.setEnabled(False)
            self.remote_list.addItem('(No credential package selected)')
            return

        config_path = configuration.get_credential_config_path(package.path)
        is_loaded = config_path.is_file()

        self.package_name.setText(package.name_without_ext)
        self.package_path.setText(str(package.path))
        self.generated_config_path.setText(str(config_path))
        self.loaded_status.setText('Loaded' if is_loaded else 'Not loaded')
        self.remove_button.setEnabled(is_loaded)

        remote_names = configuration.get_rclone_remote_names(config_path)

        for remote_name in remote_names:
            self.remote_list.addItem(remote_name)

        if not remote_names:
            if is_loaded:
                self.remote_list.addItem('(No remotes configured)')
            else:
                self.remote_list.addItem('(Credential package not loaded)')

    def _refresh_clear_all_state(self):
        self.clear_all_button.setEnabled(
            bool(configuration.get_all_conf_paths())
        )

    def _get_selected_package(self):
        current = self.credential_list.currentItem()

        if current is None:
            return None

        return current.data(pyside.Qt.ItemDataRole.UserRole)

    def _load_selected_credentials(self):
        package = self._get_selected_package()

        if package is None:
            ui.display_msg_box_ok(
                'Load Remote Credentials',
                'Select a credential package first.'
            )
            return

        password = self.password_input.text()

        if password == '':
            ui.display_msg_box_ok(
                'Load Remote Credentials',
                'Enter the password for the selected credential package.'
            )
            return

        if not credentials.load_remote_from_zip_to_config(
            package.path,
            password
        ):
            return

        config_path = configuration.get_credential_config_path(package.path)

        self.password_input.clear()
        self.refresh()
        self.status_label.setText(
            f'Loaded "{package.name_without_ext}" into "{config_path.name}".'
        )

    def _remove_selected_config(self):
        package = self._get_selected_package()

        if package is None:
            return

        config_path = configuration.get_credential_config_path(package.path)

        if not config_path.is_file():
            self.refresh()
            return

        confirmed = ui.display_msg_box_ok_cancel(
            'Remove Loaded rclone Config',
            f'Delete the generated config?\n\n{config_path}\n\n'
            f'The credential ZIP remains available at:\n{package.path}'
        )

        if not confirmed:
            return

        configuration.delete_config_file(config_path)
        self.refresh()
        self.status_label.setText(
            f'Removed "{config_path.name}". Credential ZIP was kept.'
        )

    def _clear_all_configs(self):
        config_paths = configuration.get_all_conf_paths()

        if not config_paths:
            self._refresh_clear_all_state()
            return

        config_directory = configuration.get_rclone_config_dir()

        confirmed = ui.display_msg_box_ok_cancel(
            'Clear All rclone Configs',
            f'Delete all {len(config_paths)} .conf file(s) in:\n\n'
            f'{config_directory}\n\n'
            'This includes rclone.conf if present. Credential ZIP packages '
            'will not be deleted.'
        )

        if not confirmed:
            return

        deleted_paths = configuration.clear_all_conf_files()

        self.refresh()
        self.status_label.setText(
            f'Cleared {len(deleted_paths)} rclone .conf file(s).'
        )
