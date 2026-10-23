"""
rclone management page for the Logistics feature UI.
"""

from commonUtils.ui.pyside.passwords import password_field
from commonUtils.ui.appearance.typography import point_size, setting_size
from commonUtils import ui
from commonUtils.ui import pyside
from commonUtils.ui.appearance.status_line import StatusLine
from commonUtils.ui.tasks.operation_progress import OperationProgress

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
        password_field(self.password_input)
        self.password_input.setPlaceholderText('Credential archive password')
        self.password_input.setMinimumHeight(self.password_input.sizeHint().height())

        self._active_modes = {}
        self.load_button = pyside.QPushButton('Load on Disk')
        self.load_session_button = pyside.QPushButton('Load for Session')
        self.load_button.setToolTip('Save a same-named rclone config on disk.')
        self.load_session_button.setToolTip('Keep credentials in memory until Logistics exits. Enables Cloud browsing and LocalCrypt creation.')
        self.remove_button = pyside.QPushButton('Forget Credentials')
        self.lock_button = pyside.QPushButton('Lock Package')

        self.remote_list = pyside.QListWidget()

        self.config_directory = pyside.QLabel()
        self.config_directory.setWordWrap(True)
        self.config_directory.setTextInteractionFlags(
            pyside.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.clear_all_button = pyside.QPushButton('Clear All Saved Configs')
        self.clear_sessions_button = pyside.QPushButton('Lock All Session Credentials')

        self.status_label = StatusLine()
        self.status_label.setWordWrap(True)

        self.load_operation = OperationProgress(self)
        self.load_operation.completed.connect(self._credentials_loaded)
        self._loading_package = None

        self._build_layout()
        self._connect_signals()
        self.refresh()

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
            'Load for Session keeps credentials in memory and makes its remotes available in Cloud '
            '(or Home Server for network shares). Session-loaded crypt remotes can create LocalCrypt copies. '
            'LocalCrypt files stay encrypted on disk after the session ends. '
            'Load on Disk instead saves a same-named rclone config.'
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
            'Encrypted ZIP packages'
        )
        help_label.setWordWrap(True)

        layout.addWidget(label)
        self.credential_list.setToolTip(help_label.text())
        help_label.deleteLater()
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
        package_form.addRow('ZIP path:', self.package_path)
        package_form.addRow('Generated config:', self.generated_config_path)
        package_form.addRow('Status:', self.loaded_status)
        package_form.addRow('Password:', self.password_input)

        package_buttons = pyside.QHBoxLayout()
        package_buttons.addWidget(self.load_button)
        package_buttons.addWidget(self.load_session_button)
        package_buttons.addWidget(self.lock_button)

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
        layout.addWidget(global_group)
        layout.addWidget(self.load_operation)
        layout.addWidget(self.status_label)

        return widget

    def _connect_signals(self):
        self.credential_list.currentItemChanged.connect(
            self._credential_selection_changed
        )
        self.password_input.returnPressed.connect(
            lambda: self._load_selected_credentials(remember=False)
        )
        self.load_button.clicked.connect(lambda: self._load_selected_credentials(remember=True))
        self.load_session_button.clicked.connect(lambda: self._load_selected_credentials(remember=False))
        self.remove_button.clicked.connect(self._remove_selected_config)
        self.clear_all_button.clicked.connect(self._clear_all_configs)
        self.clear_sessions_button.clicked.connect(self._clear_sessions)
        self.lock_button.clicked.connect(self._lock_selected)

    def refresh(self):
        """Refresh credential packages and generated config state."""

        if self.load_operation.busy:
            return
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
                label += ' [Saved]'
            from features.rclone import session
            if session.names(config_path.with_suffix('.session')) is not None:
                label += ' [Session]'

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
            self.load_session_button.setEnabled(False)
            self.remove_button.setEnabled(False)
            self.remote_list.clear()
            self.remote_list.addItem('(No credential package selected)')
            return

        self.password_input.setEnabled(True)
        self.load_button.setEnabled(True)
        self.load_session_button.setEnabled(True)
        self.credential_list.setCurrentRow(selected_row)
        self._refresh_selected_package()

    def _credential_selection_changed(self, _current, _previous):
        self._refresh_selected_package()
        self._refresh_clear_all_state()

    def _refresh_selected_package(self, *_):
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

        config_path = self._selected_config_path(package)
        from features.rclone import session
        is_session = session.names(config_path) is not None
        is_loaded = config_path.is_file() or is_session

        self.package_name.setText(package.name_without_ext)
        self.package_path.setText(str(package.path))
        self.generated_config_path.setText('Memory only — no file created' if config_path.suffix == '.session' else str(config_path))
        self.loaded_status.setText('Session only' if is_session else ('Saved' if is_loaded else 'Not loaded'))
        self.remove_button.setEnabled(is_loaded)

        remote_names = configuration.get_rclone_remote_names(config_path)

        for remote_name in remote_names:
            self.remote_list.addItem(remote_name)

        if not remote_names:
            if is_loaded:
                self.remote_list.addItem('(No remotes configured)')
            else:
                self.remote_list.addItem('(Credential package not loaded)')

    def _clear_sessions(self):
        from features.rclone import session
        if not self._prepare_lock(session.paths()):
            return
        from features.rclone.desktop_service import service
        service.credentials.lock()
        self.refresh()
        self.status_label.setText('Session credentials locked. Saved .conf files were kept.')

    def _prepare_lock(self, paths):
        from services.documents.ui.private_views import prepare_credential_lock
        if not prepare_credential_lock(paths):
            self.status_label.setText('Finish the private operation or save/discard your edits, then lock again.')
            return False
        return True

    def _lock_selected(self):
        package = self._get_selected_package()
        if package is None:
            return
        from features.rclone.desktop_service import service
        path = configuration.get_credential_config_path(package.path).with_suffix('.session')
        if self._prepare_lock([path]):
            service.credentials.lock(path)
            self.refresh()
            self.status_label.setText('Package session locked. Saved credentials and ZIP were kept.')

    def _refresh_clear_all_state(self):
        from features.rclone import session
        self.clear_sessions_button.setEnabled(bool(session.paths()))
        package = self._get_selected_package()
        self.lock_button.setEnabled(package is not None and session.names(
            configuration.get_credential_config_path(package.path).with_suffix('.session')) is not None)
        self.clear_all_button.setEnabled(
            bool(configuration.get_all_conf_paths())
        )

    def _get_selected_package(self):
        current = self.credential_list.currentItem()

        if current is None:
            return None

        return current.data(pyside.Qt.ItemDataRole.UserRole)

    def _selected_config_path(self, package):
        path = configuration.get_credential_config_path(package.path)
        from features.rclone import session
        prefer_disk = self._active_modes.get(package.path, session.names(path.with_suffix('.session')) is None)
        if not prefer_disk and session.names(path.with_suffix('.session')) is not None:
            return path.with_suffix('.session')
        return path

    def _load_selected_credentials(self, *, remember=True):
        if self.load_operation.busy:
            return
        package = self._get_selected_package()

        if package is None:
            ui.display_msg_box_ok(
                'Load Remote Credentials',
                'Select a credential package first.'
            )
            return

        password = self.password_input.text()
        self.password_input.clear()

        if password == '':
            ui.display_msg_box_ok(
                'Load Remote Credentials',
                'Enter the password for the selected credential package.'
            )
            return

        from features.rclone import session
        from features.rclone.desktop_service import service
        from features.rclone.desktop_credentials import DesktopCredentialLoad
        from features.rclone.credential_loading import CredentialContext
        config_path = configuration.get_credential_config_path(package.path)
        if not self._prepare_lock([config_path, config_path.with_suffix('.session')]):
            return
        self._loading_package = package, remember, config_path
        for widget in self._credential_controls():
            widget.setEnabled(False)

        def load(report, cancelled):
            request = DesktopCredentialLoad(package.path,
                config_path if remember else config_path.with_suffix('.session'), remember)
            context = CredentialContext(cancelled)
            try:
                if remember:
                    return service.credentials.load(request, password, context)
                return service.credentials.prepare_load(request, password, context)
            except Exception:
                if cancelled():
                    return None
                raise ValueError('Could not load credentials. Check the password and local file access.') from None

        self.load_operation.start(load, message='Loading credentials locally…')

    def _credential_controls(self):
        return (self.credential_list, self.password_input, self.load_button,
                self.load_session_button, self.remove_button, self.clear_all_button,
                self.clear_sessions_button, self.lock_button)

    def _credentials_loaded(self, values, error):
        from features.rclone import session
        package, remember, config_path = self._loading_package
        self._loading_package = None
        self.load_operation.hide()
        for widget in self._credential_controls():
            widget.setEnabled(True)
        if values is not None and not error and not remember:
            from features.rclone.desktop_service import service
            if self.load_operation.cancelled.is_set():
                service.credentials.discard(values)
                values = None
            else:
                try:
                    values = service.credentials.unlock(values)
                except Exception:
                    values, error = None, 'Credential loading is no longer current.'
            config_path = config_path.with_suffix('.session')
        if values is not None and not error:
            self._active_modes[package.path] = remember
            # Do not rescan credential roots (which may be cloud-backed) on completion.
            self.loaded_status.setText('Saved' if remember else 'Session only')
            self.generated_config_path.setText(str(config_path) if remember else 'Memory only — no file created')
            self.remote_list.clear()
            self.remote_list.addItems(list(values.remotes))
            item = self.credential_list.currentItem()
            label = item.text().replace(' [Saved]', '').replace(' [Session]', '')
            if remember or config_path.with_suffix('.conf').is_file():
                label += ' [Saved]'
            if session.names(config_path.with_suffix('.session')) is not None:
                label += ' [Session]'
            item.setText(label)
            self.remove_button.setEnabled(True)
            self.status_label.setText(f'Loaded "{package.path.name}" locally. No connection has been made.')
        else:
            self.remove_button.setEnabled(self.loaded_status.text() in ('Saved', 'Session only'))
            self.status_label.setText('Credential loading failed. Check the ZIP password and local file access.'
                                      if error else 'Credential loading cancelled.')
        self._refresh_clear_all_state()

    def can_close(self):
        if self.load_operation.busy:
            self.load_operation.request_cancel()
            return False
        return True

    prepare_close = can_close

    def closeEvent(self, event):
        if self.can_close():
            super().closeEvent(event)
        else:
            event.ignore()

    def _remove_selected_config(self):
        package = self._get_selected_package()

        if package is None:
            return

        from features.rclone import session
        disk_path = configuration.get_credential_config_path(package.path)
        paths = [path for path in (disk_path, disk_path.with_suffix('.session'))
                 if path.is_file() or session.names(path) is not None]
        if not paths:
            self.refresh()
            return
        confirmed = ui.display_msg_box_ok_cancel(
            'Remove Loaded rclone Config',
            f'Forget the selected package’s saved and session credentials?\n\n'
            + '\n'.join(path.name for path in paths) + '\n\n'
            + f'The credential ZIP remains available at:\n{package.path}'
        )

        if not confirmed:
            return

        if not self._prepare_lock(paths):
            return
        from features.rclone.desktop_service import service
        failure = None
        for path in paths:
            try:
                service.credentials.forget(path)
            except Exception as error:
                failure = failure or error
        self.refresh()
        if failure is not None:
            self.status_label.setText('Some credential cleanup failed. Access may already be locked; retry forgetting.')
            return
        self.status_label.setText(
            f'Forgot credentials for "{package.path.name}". Credential ZIP was kept.'
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

        if not self._prepare_lock(config_paths):
            return
        from features.rclone.desktop_service import service
        try:
            deleted_paths = service.credentials.forget()
        except Exception:
            self.refresh()
            self.status_label.setText('Some saved configs could not be removed. Access may already be locked; retry clearing.')
            return

        self.refresh()
        self.status_label.setText(
            f'Cleared {len(deleted_paths)} rclone .conf file(s).'
        )
