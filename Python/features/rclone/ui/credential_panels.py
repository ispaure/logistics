"""Desktop rclone credential list, package details and management panels."""

from commonUtils.ui import pyside
from commonUtils.ui.appearance.typography import point_size, setting_size


class CredentialPanels:
    """Lay out the retained credential controls supplied by the Settings page."""

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        title = pyside.QLabel('Credential packages')
        title_font = title.font()
        title_font.setPointSizeF(point_size(setting_size(title_font) + 2.25))
        title_font.setBold(True)
        title.setFont(title_font)

        description = pyside.QLabel(
            'Add a credential ZIP, then unlock to connect. '
            'Session-only remembers remote names for next time, never your password.'
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
        root_layout.addWidget(self.load_operation)
        root_layout.addWidget(self.status_label)

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
            'Encrypted ZIP packages'
        )
        help_label.setWordWrap(True)

        layout.addWidget(label)
        self.credential_list.setToolTip(help_label.text())
        help_label.deleteLater()
        layout.addWidget(self.import_button)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.empty_notice)
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
        name_font.setPointSizeF(point_size(setting_size(name_font) + 2.25))
        name_font.setBold(True)
        self.package_name.setFont(name_font)

        package_form = pyside.QFormLayout()
        package_form.setFieldGrowthPolicy(
            pyside.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self.package_details = pyside.QWidget()
        detail_form = pyside.QFormLayout(self.package_details)
        detail_form.setContentsMargins(0, 0, 0, 0)
        detail_form.addRow('Import folder:', self.package_directory)
        detail_form.addRow('ZIP:', self.package_path)
        detail_form.addRow('Saved config:', self.generated_config_path)
        self.package_details.hide()
        self.details_button = pyside.QToolButton()
        self.details_button.setText('Package details')
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self.package_details.setVisible)
        package_form.addRow('Status:', self.loaded_status)
        package_form.addRow('Password:', self.password_input)

        package_buttons = pyside.QHBoxLayout()
        package_buttons.addWidget(self.load_button)
        package_buttons.addWidget(self.lock_button)
        package_buttons.addWidget(self.change_password_button)

        package_layout.addWidget(self.package_name)
        package_layout.addLayout(package_form)
        package_layout.addLayout(package_buttons)
        package_layout.addWidget(self.details_button, alignment=pyside.Qt.AlignmentFlag.AlignLeft)
        package_layout.addWidget(self.package_details)

        remotes_group = pyside.QGroupBox('Loaded remotes')
        remotes_layout = pyside.QVBoxLayout(remotes_group)
        remotes_layout.addWidget(self.remote_list)

        global_group = self.management_group = pyside.QGroupBox('Credential management')
        global_layout = pyside.QVBoxLayout(global_group)
        global_layout.setSpacing(10)

        config_form = pyside.QFormLayout()
        config_form.addRow('Folder:', self.config_directory)

        clear_help = pyside.QLabel(
            'Delete all loaded configs. ZIP packages are kept.'
        )
        clear_help.setWordWrap(True)

        global_layout.addLayout(config_form)
        global_layout.addWidget(clear_help)
        global_layout.addWidget(self.clear_all_button)
        global_layout.addWidget(self.remove_button)
        global_layout.addWidget(self.clear_sessions_button)

        layout.addWidget(package_group)
        layout.addWidget(remotes_group, 1)
        self.manage_button = pyside.QToolButton()
        self.manage_button.setText('Manage credentials…')
        self.manage_button.setCheckable(True)
        self.manage_button.toggled.connect(global_group.setVisible)
        global_group.hide()
        layout.addWidget(self.manage_button, alignment=pyside.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(global_group)

        return widget
