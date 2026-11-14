"""
rclone management page for the Logistics feature UI.
"""

from commonUtils.ui.pyside.passwords import password_field
from commonUtils import ui
from commonUtils.ui import pyside
from commonUtils.ui.appearance.status_line import StatusLine
from commonUtils.ui.tasks.operation_progress import OperationProgress

from features.rclone import configuration, credentials

from .credential_panels import CredentialPanels


class RclonePage(pyside.QWidget, CredentialPanels):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.credential_list = pyside.QListWidget()
        self.credential_list.setMinimumWidth(220)
        self.credential_list.setMaximumWidth(320)

        self.package_name = pyside.QLabel('Select a credential package')
        self.package_path = pyside.QLabel()
        self.package_name.setTextFormat(pyside.Qt.TextFormat.PlainText)
        self.package_path.setTextFormat(pyside.Qt.TextFormat.PlainText)
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
        self.password_input.setPlaceholderText('Credential ZIP password')
        self.password_input.setMinimumHeight(self.password_input.sizeHint().height())

        self._active_modes = {}
        self.load_button = pyside.QPushButton('Unlock…')
        self.load_button.setToolTip('Choose session-only or persistent credentials before unlocking.')
        self.import_button = pyside.QPushButton('Import credential ZIP…')
        self.refresh_button = pyside.QPushButton('Refresh list')
        self.package_directory = pyside.QLabel()
        self.package_directory.setWordWrap(True)
        self.package_directory.setTextFormat(pyside.Qt.TextFormat.PlainText)
        self.empty_notice = pyside.QLabel('No credentials yet. Import a password-protected credential ZIP to get started.')
        self.empty_notice.setWordWrap(True)
        self.remove_button = pyside.QPushButton('Forget Credentials')
        self.lock_button = pyside.QPushButton('Lock Package')
        self.change_password_button = pyside.QPushButton('Change ZIP password…')
        self._changing_password = False

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
        self.load_operation.completed.connect(self._operation_completed)
        self._importing = None
        self._loading_package = None
        self._discovering = None

        self._build_layout()
        self._connect_signals()
        self.refresh()

    def _connect_signals(self):
        self.credential_list.currentItemChanged.connect(
            self._credential_selection_changed
        )
        self.password_input.returnPressed.connect(self._choose_unlock_mode)
        self.load_button.clicked.connect(self._choose_unlock_mode)
        self.import_button.clicked.connect(self._import_credential_zip)
        self.refresh_button.clicked.connect(self.refresh)
        self.remove_button.clicked.connect(self._remove_selected_config)
        self.clear_all_button.clicked.connect(self._clear_all_configs)
        self.clear_sessions_button.clicked.connect(self._clear_sessions)
        self.lock_button.clicked.connect(self._lock_selected)
        self.change_password_button.clicked.connect(self._change_password)

    def refresh(self, *, selected_package_path=None, message='', focus_password=False):
        """Discover packages in a worker, retaining the previous list until success."""

        if self.load_operation.busy:
            return
        current_item = self.credential_list.currentItem()

        if selected_package_path is None and current_item is not None:
            current_package = current_item.data(
                pyside.Qt.ItemDataRole.UserRole
            )

            if current_package is not None:
                selected_package_path = current_package.path

        self._discovering = selected_package_path, message, focus_password, tuple(
            (widget, widget.isEnabled()) for widget in self._credential_controls())
        for widget in self._credential_controls():
            widget.setEnabled(False)

        def discover(report, cancelled):
            directories = credentials.get_credential_package_directories()
            packages = credentials.get_logistics_remote_credentials_zip_lst(
                directories=directories, cancelled=cancelled)
            return directories[0], packages

        self.load_operation.start(discover, message='Finding credential packages…')

    def _discovery_completed(self, values, error):
        selected, message, focus_password, controls = self._discovering
        self._discovering = None
        self.load_operation.hide()
        for widget, enabled in controls:
            widget.setEnabled(enabled)
        if values is not None and not error and not self.load_operation.cancelled.is_set():
            directory, packages = values
            try:
                self._refresh_credential_packages(packages, selected)
            except (OSError, ValueError) as failure:
                error = str(failure)
            else:
                self.config_directory.setText(str(configuration.get_rclone_config_dir()))
                self.package_directory.setText(str(directory))
                self.status_label.setText(message)
        elif not error:
            self.status_label.setText('Credential refresh cancelled. Previous list kept.')
        if error:
            self.status_label.setText('Could not refresh credential packages. Previous list kept. ' + error)
        available = self.credential_list.count() > 0
        self.password_input.setEnabled(available)
        self.load_button.setEnabled(available)
        if not available:
            self.remove_button.setEnabled(False)
        elif focus_password and not error and not self.load_operation.cancelled.is_set():
            self.password_input.setFocus()
        self._refresh_clear_all_state()

    def _refresh_credential_packages(self, packages, selected_package_path=None):
        # Resolve labels before changing the retained list. A filesystem error
        # during preparation must not discard the existing selection or rows.
        items = []
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
                label += ' [Persistent save]'
            from features.rclone import session
            if session.names(config_path.with_suffix('.session')) is not None:
                label += ' [Session-Only]'
            elif not config_path.is_file():
                from features.rclone import desktop_catalog
                if desktop_catalog.read(config_path.with_suffix('.session')) is not None:
                    label += ' [Locked]'

            item = pyside.QListWidgetItem(label)
            item.setToolTip(str(package.path))
            item.setData(pyside.Qt.ItemDataRole.UserRole, package)
            items.append(item)

            if (
                selected_package_path is not None
                and package.path == selected_package_path
            ):
                selected_row = row

        with pyside.QSignalBlocker(self.credential_list):
            self.credential_list.clear()
            for item in items:
                self.credential_list.addItem(item)
            self.credential_list.setCurrentRow(selected_row if items else -1)

        self.empty_notice.setVisible(not packages)
        if not packages:
            self.lock_button.setEnabled(False)
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
        from features.rclone import desktop_catalog
        remembered = desktop_catalog.read(config_path) if config_path.suffix == '.session' else None

        self.package_name.setText(package.name_without_ext)
        self.package_path.setText(str(package.path))
        self.generated_config_path.setText('In memory — no saved credential config' if config_path.suffix == '.session' else str(config_path))
        self.loaded_status.setText('Session-Only' if is_session else ('Persistent save' if is_loaded else 'Locked'))
        self.remove_button.setEnabled(is_loaded or remembered is not None)

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
        self.refresh(message='Session credentials locked. Saved .conf files were kept.')

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
            self.refresh(message='Package session locked. Saved credentials and ZIP were kept.')

    def _refresh_clear_all_state(self):
        from features.rclone import session
        self.clear_sessions_button.setEnabled(bool(session.paths()))
        package = self._get_selected_package()
        unlocked = package is not None and session.names(
            configuration.get_credential_config_path(package.path).with_suffix('.session')) is not None
        self.lock_button.setEnabled(unlocked)
        self.lock_button.setVisible(unlocked)
        self.change_password_button.setEnabled(package is not None and (unlocked or configuration.get_credential_config_path(package.path).is_file()))
        saved = bool(configuration.get_all_conf_paths())
        self.clear_all_button.setEnabled(saved)
        from features.rclone import desktop_catalog
        known = bool(desktop_catalog.contexts())
        self.manage_button.setVisible(saved or known or bool(session.paths()))
        self.management_group.setVisible(self.manage_button.isChecked() and (saved or known or bool(session.paths())))

    def _get_selected_package(self):
        current = self.credential_list.currentItem()

        if current is None:
            return None

        return current.data(pyside.Qt.ItemDataRole.UserRole)

    def _selected_config_path(self, package):
        path = configuration.get_credential_config_path(package.path)
        from features.rclone import session
        prefer_disk = self._active_modes.get(package.path, session.names(path.with_suffix('.session')) is None)
        from features.rclone import desktop_catalog
        if (not prefer_disk and session.names(path.with_suffix('.session')) is not None
                or not path.is_file() and desktop_catalog.read(path.with_suffix('.session')) is not None):
            return path.with_suffix('.session')
        return path

    def _import_credential_zip(self):
        if self.load_operation.busy:
            return
        filename, _ = pyside.QFileDialog.getOpenFileName(
            self, 'Import credential ZIP', '', 'Credential ZIP files (*.zip *.ZIP)')
        if not filename:
            return
        self._importing = filename
        for widget in self._credential_controls():
            widget.setEnabled(False)
        self.load_operation.start(lambda report, cancelled:
            credentials.import_credential_package(filename, cancelled=cancelled),
            message='Importing credential ZIP…')

    def _operation_completed(self, values, error):
        if self._changing_password:
            self._changing_password = False
            self.load_operation.hide()
            for widget in self._credential_controls():
                widget.setEnabled(True)
            self.refresh(message=error or values or 'Password change cancelled.')
            return
        if self._discovering is not None:
            self._discovery_completed(values, error)
            return
        if self._importing is None:
            self._credentials_loaded(values, error)
            return
        self._importing = None
        self.load_operation.hide()
        for widget in self._credential_controls():
            widget.setEnabled(True)
        if values is not None and not error:
            self.refresh(selected_package_path=values,
                         message='Credential ZIP imported. Enter its password, then choose Unlock.',
                         focus_password=True)
        else:
            self.refresh(message=str(error) if error else 'Credential import cancelled.')

    def _choose_unlock_mode(self):
        if self.load_operation.busy:
            return
        package = self._get_selected_package()
        if package is None:
            return
        if not self.password_input.text():
            self.status_label.setText('Enter the credential ZIP password, then choose Unlock.')
            self.password_input.setFocus()
            return
        from .credential_unlock import choose_credential_retention
        remember = choose_credential_retention(package.path,
            configuration.get_credential_config_path(package.path), self)
        if remember is not None:
            self._load_selected_credentials(remember=remember)

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
                self.import_button, self.refresh_button, self.remove_button, self.clear_all_button,
                self.clear_sessions_button, self.lock_button, self.change_password_button)

    def _change_password(self):
        package = self._get_selected_package()
        if package is None or self.load_operation.busy:
            return
        context = self._selected_config_path(package)
        from features.rclone import session
        state = session.registry.state_credentials(context)
        current = None
        if state is not None:
            state[1][:] = b'\0' * len(state[1])
        else:
            current, accepted = pyside.QInputDialog.getText(self, 'Current ZIP password',
                'Current credential ZIP password:', pyside.QLineEdit.EchoMode.Password)
            if not accepted:
                return
        password, accepted = pyside.QInputDialog.getText(self, 'Change ZIP password',
            'New credential ZIP password:', pyside.QLineEdit.EchoMode.Password)
        if not accepted:
            return
        confirmation, accepted = pyside.QInputDialog.getText(self, 'Confirm new ZIP password',
            'Enter the new password again:', pyside.QLineEdit.EchoMode.Password)
        if not accepted:
            return
        if not password or password != confirmation:
            self.status_label.setText('New passwords must be non-empty and match. ZIP preserved.')
            return
        if not self._prepare_lock([context, context.with_suffix('.session')]):
            return
        from features.rclone.credential_password import change_password
        self._changing_password = True
        for widget in self._credential_controls():
            widget.setEnabled(False)
        self.password_input.clear()
        self.load_operation.start(lambda report, cancelled: change_password(
            package.path, context, password, current_password=current, cancelled=cancelled),
            message='Changing credential ZIP password…')

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
            self.loaded_status.setText('Persistent save' if remember else 'Session-Only')
            self.generated_config_path.setText(str(config_path) if remember else 'In memory — no saved credential config')
            self.remote_list.clear()
            self.remote_list.addItems(list(values.remotes))
            item = self.credential_list.currentItem()
            label = item.text().replace(' [Persistent save]', '').replace(' [Session-Only]', '').replace(' [Locked]', '')
            if remember or config_path.with_suffix('.conf').is_file():
                label += ' [Persistent save]'
            if session.names(config_path.with_suffix('.session')) is not None:
                label += ' [Session-Only]'
            item.setText(label)
            self.remove_button.setEnabled(True)
            self.status_label.setText(f'Unlocked "{package.path.name}" ({"saved on this device" if remember else "session only"}). '
                                      'Return to Workspaces → Cloud or Home Server to browse or pull files. '
                                      'No connection has been made yet.')
        else:
            self.remove_button.setEnabled(self.loaded_status.text() in ('Persistent save', 'Session-Only'))
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
        from features.rclone import desktop_catalog
        paths = [path for path in (disk_path, disk_path.with_suffix('.session'))
                 if path.is_file() or session.names(path) is not None
                 or path.suffix == '.session' and desktop_catalog.read(path) is not None]
        if not paths:
            self.refresh()
            return
        confirmed = ui.display_msg_box_ok_cancel(
            'Remove Loaded rclone Config',
            f'Forget this package’s saved credentials, session and remembered remote names?\n\n'
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
        if failure is not None:
            self.refresh(message='Some credential cleanup failed. Access may already be locked; retry forgetting.')
            return
        self.refresh(message=(
            f'Forgot credentials for "{package.path.name}". Credential ZIP was kept.'
        ))

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
            self.refresh(message='Some saved configs could not be removed. Access may already be locked; retry clearing.')
            return

        self.refresh(message=(
            f'Cleared {len(deleted_paths)} rclone .conf file(s).'
        ))
