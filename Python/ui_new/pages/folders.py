"""
Generic folder sources, selection, and feature actions.
"""

from commonUtils.ui.appearance.typography import point_size, setting_size
from collections import Counter
from pathlib import Path

from commonUtils.ui import pyside
from commonUtils.ui.tasks.operation_progress import OperationProgress

from features import registry
from features.contributions import UIAction
from services.folders.policy import folder_parts
from services.folders.sources import discover_folder_sources
from services.folders.workspaces import SOURCE_NAMES, local_entries, local_entry_category, remote_entries, source_category
from ui_new.pages.workspace_panes import WorkspacePanes, WORKSPACE_PANES_LOCKED
from ui_new.pages.workspace_tree import WorkspaceTree
from ui_new.settings.workspaces import workspace_visibility
from ui_new.actions import execute_action


LOCAL_SOURCE_NAME = 'Local'


class FoldersPage(pyside.QWidget):
    browse_requested = pyside.Signal(object)
    def __init__(self, parent=None, *, panes_locked=WORKSPACE_PANES_LOCKED):
        super().__init__(parent)

        self.panes_locked = panes_locked
        self._browser_view = None
        self._browser_key = None
        self._retired_browsers = []
        self._sources = None
        self.source_tabs = pyside.QTabBar()
        self.source_tabs.setExpanding(True)
        self.source_tabs.setAccessibleName('Folder sources')
        self.credential_combo = pyside.QComboBox()
        self.credential_label = pyside.QLabel('Credential')
        self._remote_sources = []
        self._local_folders = []
        self._selected_entry_key = None
        self._folder_features = []
        self._refresh_generation = 0
        self._refresh_pending = False
        self._closing = False
        self.visibility = workspace_visibility()
        self.refresh_button = pyside.QPushButton('Refresh folders')
        self.refresh_button.clicked.connect(self.refresh)
        self.discovery = OperationProgress(self)
        self.discovery.completed.connect(self._discovered)
        self.details = OperationProgress(self)
        self.details.completed.connect(self._details_ready)
        self._detail_generation = 0
        self._detail_pending = None

        self.folder_tree = WorkspaceTree()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setMinimumWidth(220)
        self.folder_tree.setMaximumWidth(380)

        self.selected_entry_name = None
        self._entry_items = {}

        self.detail_scroll = pyside.QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(pyside.QFrame.Shape.NoFrame)

        self._build_layout()
        self._connect_signals()
        self.refresh()

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        left_widget = pyside.QWidget()
        left_layout = pyside.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        title_label = pyside.QLabel('Workspaces')
        title_font = title_label.font()
        title_font.setPointSizeF(point_size(setting_size(title_font) + 1.5))
        title_font.setBold(True)
        title_label.setFont(title_font)

        source_font = self.credential_label.font()
        source_font.setBold(True)
        self.credential_label.setFont(source_font)

        left_layout.addWidget(title_label)
        subtitle = pyside.QLabel('Libraries, servers and remote folders')
        subtitle.setWordWrap(True)
        left_layout.addWidget(subtitle)
        left_layout.addWidget(self.source_tabs)
        left_layout.addWidget(self.credential_label)
        left_layout.addWidget(self.credential_combo)
        left_layout.addWidget(self.folder_tree, 1)
        left_layout.addWidget(self.refresh_button)

        splitter = pyside.QSplitter(pyside.Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        self.browser_stack = pyside.QStackedWidget()
        self.browser_notice = pyside.QLabel('Select a folder to browse its files.')
        self.browser_notice.setAlignment(pyside.Qt.AlignmentFlag.AlignCenter)
        self.browser_notice.setWordWrap(True)
        self.browser_notice.setMargin(12)
        self.browser_stack.addWidget(self.browser_notice)
        self.panes = WorkspacePanes(self.browser_stack, self.detail_scroll, self, locked=self.panes_locked)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.panes)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 750])

        root_layout.addWidget(splitter, 1)
        # Match the workspace notice row: progress belongs below both panes,
        # rather than taking three rows out of the folder list.
        self.discovery.layout().setDirection(pyside.QBoxLayout.Direction.LeftToRight)
        self.discovery.layout().setSpacing(6)
        self.discovery.layout().setStretch(0, 1)
        self.discovery.bar.setFixedSize(100, 6)
        self.discovery.bar.setTextVisible(False)
        self.discovery.bar.setStyleSheet('QProgressBar { min-height: 0px; }')
        self.discovery.cancel_button.setStyleSheet('QPushButton { min-height: 0px; padding: 2px 6px; }')
        root_layout.addWidget(self.discovery)

    def _connect_signals(self):
        self.source_tabs.currentChanged.connect(self._source_changed)
        self.credential_combo.currentIndexChanged.connect(self._credential_changed)
        self.folder_tree.currentItemChanged.connect(self._selection_changed)
        self.visibility.changed.connect(self._refresh_folder_tree)

    def refresh(self):
        """Refresh source groups while preserving the selected credential and folder."""

        if self._closing:
            return
        self._refresh_generation += 1
        if self.discovery.busy:
            self._refresh_pending = True
            self.discovery.request_cancel()
            return
        self._start_discovery()

    def _start_discovery(self):
        generation = self._refresh_generation
        # Resolve declarations on the GUI thread; only provider I/O runs in the worker.
        remotes = tuple(registry.get_remote_folder_sources())
        locals_ = tuple(registry.get_local_folder_sources())
        self._folder_features = sorted(registry.get_folder_features(),
            key=lambda registered: (registered.contribution.order, registered.contribution.name.casefold()))
        self.discovery.start(lambda report, cancelled: (generation, discover_folder_sources(
            remote_providers=remotes, local_providers=locals_, cancelled=cancelled)), message='Loading folder sources…')

    def _discovered(self, result, error):
        if self._closing:
            self.window().close()
            return
        if self._refresh_pending:
            self._refresh_pending = False
            self._start_discovery()
            return
        if error or result is None or result[0] != self._refresh_generation:
            return
        try:
            self._apply_sources(result[1])
        except Exception as error:
            self.discovery.message.setText(f'Folder display failed: {error}')
            return
        self.discovery.hide()

    def _apply_sources(self, sources):
        selected_source_key = self._source_key(self.source_tabs.currentIndex())
        selected_credential = self.credential_combo.currentData()
        self._sources = sources
        from ui_new.location_context import location_catalog
        location_catalog().publish(sources)
        self._remote_sources = sources.remote_sources
        self._local_folders = sources.local_folders
        with pyside.QSignalBlocker(self.source_tabs):
            self._rebuild_source_tabs(selected_source_key)
        self.source_tabs.setVisible(self.source_tabs.count() > 0)
        self.source_tabs.updateGeometry()
        if self._source_key(self.source_tabs.currentIndex()) != selected_source_key:
            selected_credential = None
        self._refresh_credentials(selected_credential)
        self._refresh_folder_tree()

    def _rebuild_source_tabs(self, selected_source_key):
        """Keep the same three source categories as mobile, including empty ones."""
        while self.source_tabs.count():
            self.source_tabs.removeTab(0)
        for name in SOURCE_NAMES:
            index = self.source_tabs.addTab(name)
            sources = [source for source in self._remote_sources
                       if not hasattr(source.source.context, 'item') and source_category(source) == name]
            self.source_tabs.setTabData(index, ('local', None) if name == 'Local' else ('remote', None, sources))
        self.source_tabs.setCurrentIndex(self._find_source_index(selected_source_key))

    def _source_key(self, index):
        data = self.source_tabs.tabData(index)
        if data is None:
            return ('local', None, LOCAL_SOURCE_NAME)
        return (data[0], data[1], self.source_tabs.tabText(index))

    def _find_source_index(self, source_key) -> int:
        for index in range(self.source_tabs.count()):
            if self._source_key(index) == source_key:
                return index
        return 0

    def _source_changed(self, _index):
        self._selected_entry_key = None
        self._refresh_credentials()
        self._refresh_folder_tree()
        # A source can change while the hub remains open (for example when
        # credentials are loaded in another window). Show the cached list now,
        # then reconcile it without blocking the tab switch.
        self.refresh()

    def _credential_changed(self, _index):
        self._selected_entry_key = None
        self._refresh_folder_tree()

    def _get_selected_source(self):
        return self.source_tabs.tabData(self.source_tabs.currentIndex())

    def _refresh_credentials(self, selected_credential=None):
        """Offer provider groups locally and credential groups for remote sources."""

        selected_source = self._get_selected_source()
        is_remote = selected_source is not None and selected_source[0] == 'remote'
        with pyside.QSignalBlocker(self.credential_combo):
            self.credential_combo.clear()
            if is_remote:
                self.credential_combo.addItem('All', None)
                for source in selected_source[2]:
                    self.credential_combo.addItem(source.source.name, source.source.context)
            else:
                for name in ('Dropbox', 'Rclone', 'Others'):
                    self.credential_combo.addItem(name, name)
                self.credential_combo.setCurrentIndex(self.credential_combo.findData('Rclone'))
            if selected_credential is not None:
                for index in range(self.credential_combo.count()):
                    if self.credential_combo.itemData(index) == selected_credential:
                        self.credential_combo.setCurrentIndex(index)
                        break
        self.credential_label.setText('Credential' if is_remote else 'Source')
        self.credential_label.setVisible(True)
        self.credential_combo.setVisible(True)

    @staticmethod
    def _entry_key(entry):
        """Keep same-named folders from different credentials independently selectable."""

        return (entry.name, entry.remote_source, str(entry.remote_context),
                str(entry.local.path) if entry.local is not None else None)

    def _refresh_folder_tree(self):
        if self._closing or self._sources is None:
            return
        selected_source = self._get_selected_source()
        source_type = selected_source[0] if selected_source is not None else 'local'
        entry_labels = {}

        if source_type == 'local':
            entries = local_entries(self._sources)
            category = self.credential_combo.currentData()
            if category is not None:
                entries = [entry for entry in entries if local_entry_category(entry, self._sources) == category]
            entry_labels.update((self._entry_key(entry), str(entry.local.path)) for entry in entries)
        else:
            _source_type, _feature_name, sources = selected_source
            selected_credential = self.credential_combo.currentData()
            entries = []
            for source in sources:
                if selected_credential is not None and source.source.context != selected_credential:
                    continue
                source_entries = remote_entries(source, self._local_folders)
                entries.extend(source_entries)
                for entry in source_entries:
                    entry_labels[self._entry_key(entry)] = source.source.name

        if not self.visibility.show_legacy:
            entries = [entry for entry in entries if not entry.name.casefold().startswith('legacy-')]
        entries.sort(key=lambda entry: (entry.name.casefold(), str(entry.remote_context)))
        name_counts = Counter(entry.name for entry in entries)
        copy_labels = {self._entry_key(entry): getattr(entry.local, 'storage_label', 'Local')
                       if entry.local is not None else 'Remote' for entry in entries}
        copy_counts = Counter((entry.name, copy_labels[self._entry_key(entry)]) for entry in entries)

        self.folder_tree.clear()
        self._entry_items = {}

        if not entries:
            self.selected_entry_name = None
            self._show_empty_state()
            return

        tree_items = {}

        for entry in entries:
            name_parts = folder_parts(entry.name)
            parent_item = None
            path_parts = []
            entry_key = self._entry_key(entry)

            for index, name_part in enumerate(name_parts):
                path_parts.append(name_part)
                item_path = tuple(path_parts)
                is_leaf = index == len(name_parts) - 1
                if is_leaf and name_counts[entry.name] > 1:
                    item_path = (*item_path, entry_key)
                    label = copy_labels[entry_key]
                    if copy_counts[entry.name, label] > 1:
                        label += ' · ' + entry_labels[entry_key]
                    name_part = f'{name_part} [{label}]'

                item = tree_items.get(item_path)

                if item is None:
                    item = pyside.QTreeWidgetItem([name_part])
                    tree_items[item_path] = item

                    if parent_item is None:
                        self.folder_tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)

                if index == len(name_parts) - 1:
                    item.setData(0, pyside.Qt.ItemDataRole.UserRole, entry)
                    self._style_folder_item(item, entry)
                    item.setToolTip(0, '\n'.join(filter(None, (entry.name, copy_labels[entry_key],
                        entry_labels.get(entry_key, ''), str(entry.local.path) if entry.local is not None else ''))))
                    self._entry_items[entry_key] = item

                parent_item = item

        for item in tree_items.values():
            if item.data(0, pyside.Qt.ItemDataRole.UserRole) is None:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                item.setFlags(item.flags() & ~pyside.Qt.ItemFlag.ItemIsSelectable)

        self.folder_tree.expandAll()

        selected_item = self._entry_items.get(self._selected_entry_key)

        if selected_item is None:
            self._show_empty_state('Select a folder to browse its files.')
            return

        self.folder_tree.setCurrentItem(selected_item)

    def _selection_changed(self, current, _previous):
        if current is None:
            return

        entry = current.data(0, pyside.Qt.ItemDataRole.UserRole)

        if entry is None:
            return

        self.selected_entry_name = entry.name
        self._selected_entry_key = self._entry_key(entry)
        self._show_entry(entry)
        if self.isVisible():
            self._browse_entry(entry)

    def showEvent(self, event):
        super().showEvent(event)
        item = self.folder_tree.currentItem()
        entry = item.data(0, pyside.Qt.ItemDataRole.UserRole) if item is not None else None
        if entry is not None and not self._closing:
            self._browse_entry(entry)

    def _style_folder_item(self, item, entry):
        from ui_new.pages.workspace_icons import folder_icon
        private = getattr(entry.local, 'private', False)
        state = None
        online = self._get_selected_source()[0] == 'remote'
        if online:
            for source in self._remote_sources:
                if (source.source.context == entry.remote_context
                        and entry.remote_name in source.encrypted_remote_names):
                    from features.rclone import session
                    config = Path(entry.remote_context)
                    state = 'locked' if config.suffix == '.session' and session.credentials(config) is None else 'unlocked'
                    break
        elif private:
            from features.rclone import session
            connection = entry.local.connection
            unlocked = (session.credentials(connection.context) is not None
                        and session.package_path(connection.context) == connection.package)
            state = 'unlocked' if unlocked else 'locked'
        item.setIcon(0, folder_icon(self, state))
        storage = ('Remote' if self._get_selected_source()[0] == 'remote' else
                   getattr(entry.local, 'storage_label', 'Local'))
        item.setData(0, pyside.Qt.ItemDataRole.AccessibleDescriptionRole,
                     storage + (', ' + state if state else ''))

    def _browse_entry(self, entry, *, force=False):
        source = self._get_selected_source()
        online = source is not None and source[0] == 'remote'
        key = (online, self._entry_key(entry))
        if key == self._browser_key and not force:
            return
        self._clear_browser('Opening workspace…')
        try:
            if online:
                from features.rclone.ui.remote_browser import RemoteLocation
                location = RemoteLocation(Path(entry.remote_context), entry.remote_name)
            elif getattr(entry.local, 'private', False):
                from ui_new.file_browser import _PrivateBrowserLocation
                location = _PrivateBrowserLocation(entry.local.connection, entry.local.path)
            elif entry.local is not None:
                location = entry.local.path
            else:
                raise ValueError('This workspace has no available local copy.')
            view = self.open_browser_location(location)
            if view is not None:
                self._browser_key = key
                item = self._entry_items.get(self._entry_key(entry))
                if item is not None:
                    self._style_folder_item(item, entry)
            else:
                self.browser_notice.setText('Unlock this workspace to browse its files. Reselect the folder to try again.')
        except Exception as error:
            self.browser_notice.setText(f'Cannot browse this workspace: {error}')

    def open_browser_location(self, location, *, package=None):
        """Feature Browse actions stay in this page's docked browser."""
        self._clear_browser('Opening workspace…')
        view = self._create_browser(location, package=package) if package is not None else self._create_browser(location)
        if view is None:
            return None
        self._browser_view = view
        self.browser_stack.addWidget(view)
        self.browser_stack.setCurrentWidget(view)
        view.idle.connect(self._browser_idle)
        return view

    def _create_browser(self, location, *, package=None):
        from ui_new.file_browser import _browser_view
        from features.rclone.ui.workspace_unlock import unlock_target, WorkspaceUnlockView
        target = unlock_target(location, package=package)
        if target is not None:
            view = WorkspaceUnlockView(*target, parent=self)
            view.unlocked.connect(lambda: self._workspace_unlocked(view, location))
            return view
        view = _browser_view(location)
        browser = getattr(view, 'file_browser', None)
        if browser is not None:
            browser.preview_toggle.setChecked(False)
        return view

    def _workspace_unlocked(self, view, location):
        if self._closing or self._browser_view is not view:
            return
        key = self._browser_key
        try:
            self.open_browser_location(location)
        except Exception as error:
            self._clear_browser(f'Cannot browse this workspace: {error}')
            return
        self._browser_key = key
        # One credential ZIP can unlock several workspace roots at once.
        for item in self._entry_items.values():
            entry = item.data(0, pyside.Qt.ItemDataRole.UserRole)
            if entry is not None:
                self._style_folder_item(item, entry)

    def _clear_browser(self, message):
        self._browser_key = None
        view, self._browser_view = self._browser_view, None
        self.browser_notice.setText(message)
        self.browser_stack.setCurrentWidget(self.browser_notice)
        if view is not None:
            self._retired_browsers.append(view)
        self._browser_idle()

    def _browser_idle(self):
        for view in list(self._retired_browsers):
            if view.prepare_close():
                self._retired_browsers.remove(view)
                self.browser_stack.removeWidget(view)
                view.deleteLater()
        if self._closing:
            pyside.QTimer.singleShot(0, self.window().close)

    def _show_empty_state(self, message=None):
        self.selected_entry_name = None
        self._selected_entry_key = None
        self._detail_generation += 1
        self._detail_pending = None
        self.details.request_cancel()
        self._tools_status = None
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        selected_source = self._get_selected_source()
        source_type = selected_source[0] if selected_source is not None else 'local'

        if message is None:
            message = ('No local copies were found for this source. Choose another source to browse its workspaces.'
                       if source_type == 'local' else
                       'No loaded remote folders were found for this source. Load credentials in Settings to browse online.')

        label = pyside.QLabel(message)
        label.setWordWrap(True)

        layout.addWidget(label)
        layout.addStretch()

        self.detail_scroll.setWidget(widget)
        self._clear_browser(message)

    def _show_entry(self, entry):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title_label = pyside.QLabel(entry.name)
        title_label.setTextFormat(pyside.Qt.TextFormat.PlainText)
        title_font = title_label.font()
        title_font.setPointSizeF(point_size(setting_size(title_font) + 3))
        title_font.setBold(True)
        title_label.setFont(title_font)

        layout.addWidget(title_label)
        scope = pyside.QLabel('Actions apply to this workspace root. Browsing or selecting files in Files does not change this target.')
        scope.setWordWrap(True)
        layout.addWidget(scope)
        layout.addWidget(self._create_general_section(entry))
        self._tools_status = pyside.QLabel('Checking workspace tools…')
        layout.addWidget(self._tools_status)
        layout.addStretch()
        self.detail_scroll.setWidget(widget)
        self._detail_generation += 1
        self._detail_pending = entry
        if self.details.busy:
            self.details.request_cancel()
        else:
            self._start_details()

    def _start_details(self):
        entry, self._detail_pending = self._detail_pending, None
        generation = self._detail_generation
        features = tuple(self._folder_features)
        def work(report, cancelled):
            from commonUtils.runtime.operations import check_cancelled
            found = []
            for registered in features:
                check_cancelled(cancelled)
                contribution = registered.contribution
                # Private folder paths identify ciphertext, not a LocalFolder.
                # Only backend-aware tools may inspect or operate on them.
                if getattr(entry.local, 'private', False) and not contribution.supports_private_folders:
                    continue
                if contribution.is_available(entry):
                    actions = None if contribution.create_widget else contribution.get_actions(entry)
                    found.append((contribution, actions))
            check_cancelled(cancelled)
            return generation, entry, found
        self.details.start(work, show_progress=False)

    def _details_ready(self, result, error):
        if self._closing:
            if not self.discovery.busy:
                self.window().close()
            return
        if self._detail_pending is not None:
            self._start_details()
            return
        if result is None or result[0] != self._detail_generation:
            if error and self._tools_status is not None:
                self._tools_status.setText(f'Workspace tools unavailable: {error}')
            return
        _, entry, found = result
        layout = self.detail_scroll.widget().layout()
        self._tools_status.hide()
        try:
            for contribution, actions in found:
                if contribution.create_widget is not None:
                    widget = contribution.create_widget(entry, self)
                elif actions:
                    widget = self._create_action_section(contribution.name, actions, entry.name,
                                                         horizontal=contribution.actions_horizontal)
                else:
                    continue
                if widget is not None:
                    layout.insertWidget(layout.count() - 1, widget)
        except Exception as error:
            self._tools_status.setText(f'Workspace tools unavailable: {error}')
            self._tools_status.show()

    def _create_general_section(self, entry):
        group = pyside.QGroupBox('General')
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        status_layout = pyside.QGridLayout()

        status_layout.addWidget(pyside.QLabel('Local:'), 0, 0)
        status_layout.addWidget(
            pyside.QLabel('Available' if entry.has_local else 'Not available'),
            0,
            1
        )

        status_layout.addWidget(pyside.QLabel('Remote:'), 1, 0)
        status_layout.addWidget(
            pyside.QLabel('Configured' if entry.has_remote else 'Not configured'),
            1,
            1
        )

        next_row = 2

        if entry.local is not None:
            status_layout.addWidget(pyside.QLabel('Local path:'), next_row, 0)

            path_label = pyside.QLabel(str(entry.local.path))
            path_label.setTextFormat(pyside.Qt.TextFormat.PlainText)
            path_label.setTextInteractionFlags(
                pyside.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            path_label.setWordWrap(True)
            status_layout.addWidget(path_label, next_row, 1)

            next_row += 1

        if entry.remote_name is not None:
            status_layout.addWidget(pyside.QLabel('Remote name:'), next_row, 0)

            remote_label = pyside.QLabel(entry.remote_name)
            remote_label.setTextFormat(pyside.Qt.TextFormat.PlainText)
            remote_label.setTextInteractionFlags(
                pyside.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            status_layout.addWidget(remote_label, next_row, 1)

        status_layout.setColumnStretch(1, 1)
        layout.addLayout(status_layout)

        return group

    def _create_action_section(
        self,
        title: str,
        actions: list[UIAction],
        entry_name: str,
        horizontal: bool = False
    ):
        group = pyside.QGroupBox(title)
        layout = pyside.QHBoxLayout(group) if horizontal else pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        for action in actions:
            button = pyside.QPushButton(action.name)
            button.setEnabled(action.enabled)

            if action.description is not None:
                button.setToolTip(action.description)

            button.clicked.connect(
                lambda _checked=False, action=action, entry_name=entry_name:
                self._execute_action(action, entry_name)
            )

            layout.addWidget(button)

        return group

    def _execute_action(self, action: UIAction, entry_name: str):
        return execute_action(action, self, subject=entry_name, refresh=self.refresh)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == pyside.QEvent.Type.PaletteChange and hasattr(self, '_entry_items'):
            for item in self._entry_items.values():
                self._style_folder_item(item, item.data(0, pyside.Qt.ItemDataRole.UserRole))

    def prepare_close(self):
        self._closing = True
        self._refresh_pending = False
        self._detail_pending = None
        for task in (self.discovery, self.details):
            task.request_cancel()
        browsers_ready = True
        for view in [self._browser_view, *self._retired_browsers]:
            if view is not None and not view.prepare_close():
                browsers_ready = False
        return not (self.discovery.busy or self.details.busy) and browsers_ready

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()
