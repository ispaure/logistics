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
        self.package_path.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)

        self.password_input = pyside.QLineEdit()
        self.password_input.setEchoMode(pyside.QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText('Credential archive password')

        self.load_button = pyside.QPushButton('Load Credentials')

        self.config_path = pyside.QLabel()
        self.config_path.setWordWrap(True)
        self.config_path.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)

        self.remote_list = pyside.QListWidget()
        self.clear_button = pyside.QPushButton('Clear rclone.conf')

        self.status_label = pyside.QLabel()
        self.status_label.setWordWrap(True)

        self._build_layout()
        self._connect_signals()
        self.refresh()

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        title = pyside.QLabel('rclone')
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 7)
        title_font.setBold(True)
        title.setFont(title_font)

        description = pyside.QLabel(
            'Load packaged remote credentials and manage the local rclone configuration.'
        )
        description.setWordWrap(True)

        root_layout.addWidget(title)
        root_layout.addWidget(description)

        splitter = pyside.QSplitter(pyside.Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_packages_panel())
        splitter.addWidget(self._create_details_panel())
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
            'Available encrypted ZIP packages from the Logistics RemoteCredentials folder.'
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
        package_form.addRow('Path:', self.package_path)
        package_form.addRow('Password:', self.password_input)

        package_layout.addWidget(self.package_name)
        package_layout.addLayout(package_form)
        package_layout.addWidget(self.load_button)

        config_group = pyside.QGroupBox('Current rclone Configuration')
        config_layout = pyside.QVBoxLayout(config_group)
        config_layout.setSpacing(10)

        config_form = pyside.QFormLayout()
        config_form.addRow('Config path:', self.config_path)
        config_layout.addLayout(config_form)

        remotes_label = pyside.QLabel('Configured Remotes')
        remotes_font = remotes_label.font()
        remotes_font.setBold(True)
        remotes_label.setFont(remotes_font)

        config_layout.addWidget(remotes_label)
        config_layout.addWidget(self.remote_list, 1)
        config_layout.addWidget(self.clear_button)

        layout.addWidget(package_group)
        layout.addWidget(config_group, 1)
        layout.addWidget(self.status_label)

        return widget

    def _connect_signals(self):
        self.credential_list.currentItemChanged.connect(self._credential_selection_changed)
        self.password_input.returnPressed.connect(self._load_selected_credentials)
        self.load_button.clicked.connect(self._load_selected_credentials)
        self.clear_button.clicked.connect(self._clear_rclone_conf)

    def refresh(self):
        """Refresh available credential packages and the current rclone configuration."""

        selected_package_path = None
        current_item = self.credential_list.currentItem()

        if current_item is not None:
            current_package = current_item.data(pyside.Qt.ItemDataRole.UserRole)

            if current_package is not None:
                selected_package_path = current_package.path

        self._refresh_credential_packages(selected_package_path)
        self._refresh_rclone_configuration()

    def _refresh_credential_packages(self, selected_package_path=None):
        self.credential_list.clear()

        packages = credentials.get_logistics_remote_credentials_zip_lst()

        selected_row = 0

        for row, package in enumerate(packages):
            item = pyside.QListWidgetItem(package.name_without_ext)
            item.setData(pyside.Qt.ItemDataRole.UserRole, package)
            self.credential_list.addItem(item)

            if selected_package_path is not None and package.path == selected_package_path:
                selected_row = row

        if not packages:
            self.package_name.setText('No credential packages found')
            self.package_path.setText('')
            self.password_input.clear()
            self.password_input.setEnabled(False)
            self.load_button.setEnabled(False)
            return

        self.password_input.setEnabled(True)
        self.load_button.setEnabled(True)
        self.credential_list.setCurrentRow(selected_row)

    def _refresh_rclone_configuration(self):
        config_path = configuration.get_rclone_conf_path()
        remote_names = configuration.get_rclone_remote_names()

        self.config_path.setText(str(config_path))
        self.remote_list.clear()

        for remote_name in remote_names:
            self.remote_list.addItem(remote_name)

        if not remote_names:
            self.remote_list.addItem('(No remotes configured)')

        self.clear_button.setEnabled(config_path.is_file())

    def _credential_selection_changed(self, current, _previous):
        if current is None:
            self.package_name.setText('Select a credential package')
            self.package_path.setText('')
            self.password_input.clear()
            return

        package = current.data(pyside.Qt.ItemDataRole.UserRole)

        if package is None:
            return

        self.package_name.setText(package.name_without_ext)
        self.package_path.setText(str(package.path))
        self.password_input.clear()
        self.status_label.clear()

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

        if not credentials.add_remote_from_zip_to_rclone_conf(package.path, password):
            return

        self.password_input.clear()
        self.status_label.setText(f'Loaded credentials from "{package.name_without_ext}".')
        self._refresh_rclone_configuration()

    def _clear_rclone_conf(self):
        config_path = configuration.get_rclone_conf_path()

        if not config_path.is_file():
            self._refresh_rclone_configuration()
            return

        confirmed = ui.display_msg_box_ok_cancel(
            'Clear rclone.conf',
            f'Delete the local rclone configuration?\n\n{config_path}\n\n'
            'This removes all currently configured remotes from this computer.'
        )

        if not confirmed:
            return

        configuration.clear_rclone_conf()

        self.status_label.setText('rclone.conf was cleared.')
        self._refresh_rclone_configuration()
