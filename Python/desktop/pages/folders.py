"""
Generic folder sources, selection, and feature actions.
"""

from commonUtils.ui.appearance.typography import point_size, setting_size
from pathlib import Path

from commonUtils.ui import pyside
from commonUtils.ui.tasks.operation_progress import OperationProgress

from features.application import registry
from features.contributions import UIAction
from services.folders.sources import discover_folder_sources
from services.folders.workspaces import SOURCE_NAMES, source_category, workspace_remote_sources
from desktop.pages.workspace_panes import WorkspacePanes, WORKSPACE_PANES_LOCKED
from desktop.pages.workspace_tree import WorkspaceTree
from desktop.settings.workspaces import workspace_visibility
from desktop.actions import execute_action
from services.workflow_host import StateAttribute
from .folder_controller import FolderController


LOCAL_SOURCE_NAME = 'Local'


class FoldersPage(pyside.QWidget):
    browse_requested = pyside.Signal(object)
    _refresh_generation = StateAttribute('controller', 'refresh_generation')
    _refresh_pending = StateAttribute('controller', 'refresh_pending')
    _detail_generation = StateAttribute('controller', 'detail_generation')
    _detail_pending = StateAttribute('controller', 'detail_pending')

    def __init__(self, parent=None, *, panes_locked=WORKSPACE_PANES_LOCKED):
        super().__init__(parent)
        from .folder_tree import FolderTreePresentation
        self.tree_presentation = FolderTreePresentation(self)

        self.controller = FolderController()
        self.panes_locked = panes_locked
        self._browser_view = None
        self._actions_unlock_view = None
        self._browser_key = None
        self._retired_browsers = []
        self._sources = None
        self.source_tabs = pyside.QTabBar()
        self.source_tabs.setExpanding(True)
        self.source_tabs.setAccessibleName('Folder sources')
        self.local_source_tabs = pyside.QTabBar()
        self.local_source_tabs.setExpanding(True)
        self.local_source_tabs.setAccessibleName('Local folder sources')
        for name in ('Dropbox', 'Rclone', 'Others'):
            self.local_source_tabs.addTab(name)
        self.local_source_tabs.setCurrentIndex(1)
        self.cloud_source_tabs = pyside.QTabBar()
        self.cloud_source_tabs.setExpanding(True)
        self.cloud_source_tabs.setAccessibleName('Cloud folder sources')
        self.cloud_source_tabs.addTab('rclone')
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
        self.refresh_button = pyside.QToolButton()
        self.refresh_button.setIcon(self.style().standardIcon(pyside.QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_button.setToolTip('Refresh folders')
        self.refresh_button.setAccessibleName('Refresh folders')
        self.refresh_button.setAutoRaise(True)
        self.refresh_button.clicked.connect(self.refresh)
        self.rclone_credentials_button = pyside.QToolButton()
        self.rclone_credentials_button.setText('+')
        self.rclone_credentials_button.setToolTip('Open rclone credentials')
        self.rclone_credentials_button.setAccessibleName('Open rclone credentials')
        self.rclone_credentials_button.setAutoRaise(True)
        self.rclone_credentials_button.clicked.connect(self._add_rclone)
        self.discovery = OperationProgress(self)
        self.discovery.completed.connect(self._discovered)
        self.details = OperationProgress(self)
        self.details.completed.connect(self._details_ready)
        self._detail_generation = 0
        self._detail_pending = None

        self.folder_tree = WorkspaceTree()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setMinimumWidth(140)

        self.selected_entry_name = None
        self._entry_items = {}

        self.detail_scroll = pyside.QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(pyside.QFrame.Shape.NoFrame)

        self.info_scroll = pyside.QScrollArea()
        self.info_scroll.setWidgetResizable(True)
        self.info_scroll.setFrameShape(pyside.QFrame.Shape.NoFrame)
        self.details_tabs = pyside.QTabWidget()
        self.details_tabs.setAccessibleName('Workspace details')
        self.details_tabs.addTab(self.info_scroll, 'Info')
        self.details_tabs.addTab(self.detail_scroll, 'Actions')
        self.details_tabs.setCurrentWidget(self.detail_scroll)

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

        source_font = self.credential_label.font()
        source_font.setBold(True)
        self.credential_label.setFont(source_font)

        header = pyside.QHBoxLayout()
        header.addWidget(self.source_tabs, 1)
        left_layout.addLayout(header)
        left_layout.addWidget(self.local_source_tabs)
        left_layout.addWidget(self.cloud_source_tabs)
        left_layout.addWidget(self.credential_label)
        credential_row = pyside.QHBoxLayout()
        credential_row.addWidget(self.credential_combo, 1)
        credential_row.addWidget(self.rclone_credentials_button)
        credential_row.addWidget(self.refresh_button)
        left_layout.addLayout(credential_row)
        self.folder_list_panel = pyside.QFrame()
        self.folder_list_panel.setFrameShape(pyside.QFrame.Shape.StyledPanel)
        self.folder_tree.setFrameShape(pyside.QFrame.Shape.NoFrame)
        folder_list_layout = pyside.QVBoxLayout(self.folder_list_panel)
        folder_list_layout.setContentsMargins(0, 0, 0, 0)
        folder_list_layout.setSpacing(0)
        self.home_server_notice = pyside.QLabel('Pending Implementation')
        pending_font = self.home_server_notice.font()
        pending_font.setItalic(True)
        self.home_server_notice.setFont(pending_font)
        self.home_server_notice.setAlignment(pyside.Qt.AlignmentFlag.AlignCenter)
        folder_list_layout.addWidget(self.home_server_notice)
        folder_list_layout.addWidget(self.folder_tree, 1)
        left_layout.addWidget(self.folder_list_panel, 1)

        self.browser_stack = pyside.QStackedWidget()
        self.browser_notice = pyside.QLabel('Select a folder to browse its files.')
        self.browser_notice.setAlignment(pyside.Qt.AlignmentFlag.AlignCenter)
        self.browser_notice.setWordWrap(True)
        self.browser_notice.setMargin(12)
        self.browser_stack.addWidget(self.browser_notice)
        self.cloud_setup = pyside.QWidget()
        setup_layout = pyside.QVBoxLayout(self.cloud_setup)
        setup_layout.addStretch()
        card = pyside.QWidget()
        card.setMaximumWidth(420)
        card_layout = pyside.QVBoxLayout(card)
        card_layout.setSpacing(14)
        title = pyside.QLabel('Connect your cloud storage')
        font = title.font()
        font.setBold(True)
        font.setPointSizeF(point_size(setting_size(font) + 3))
        title.setFont(font)
        title.setAlignment(pyside.Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)
        self.cloud_setup_note = pyside.QLabel()
        self.cloud_setup_note.setWordWrap(True)
        self.cloud_setup_note.setMinimumHeight(self.cloud_setup_note.fontMetrics().lineSpacing() * 4)
        self.cloud_setup_note.setAlignment(pyside.Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.cloud_setup_note)
        self.add_rclone_button = pyside.QPushButton('+ rclone')
        self.add_rclone_button.setMinimumHeight(36)
        self.add_rclone_button.setAccessibleName('Add an rclone account')
        self.add_rclone_button.clicked.connect(self._add_rclone)
        card_layout.addWidget(self.add_rclone_button, alignment=pyside.Qt.AlignmentFlag.AlignHCenter)
        setup_layout.addWidget(card, alignment=pyside.Qt.AlignmentFlag.AlignHCenter)
        setup_layout.addStretch()
        self.browser_stack.addWidget(self.cloud_setup)
        self.panes = WorkspacePanes(self.browser_stack, self.details_tabs, self,
                                    sources=left_widget, locked=self.panes_locked)
        root_layout.addWidget(self.panes, 1)
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
        self.local_source_tabs.currentChanged.connect(self._local_source_changed)
        self.folder_tree.currentItemChanged.connect(self._selection_changed)
        self.visibility.changed.connect(self.tree_presentation.refresh)

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
        # Resolve declarations on the GUI thread; only provider I/O runs in the worker.
        remotes = tuple(registry.get_remote_folder_sources())
        locals_ = tuple(registry.get_local_folder_sources())
        self._folder_features = sorted(registry.get_folder_features(),
            key=lambda registered: (registered.contribution.order, registered.contribution.name.casefold()))
        self.discovery.start(self.controller.discovery_work(remotes, locals_, discover_folder_sources),
                             message='Loading folder sources…')

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
        from desktop.location_context import location_catalog
        location_catalog().publish(sources)
        self._remote_sources = workspace_remote_sources(sources)
        self._local_folders = sources.local_folders
        with pyside.QSignalBlocker(self.source_tabs):
            self._rebuild_source_tabs(selected_source_key)
        self.source_tabs.setVisible(self.source_tabs.count() > 0)
        self.source_tabs.updateGeometry()
        if self._source_key(self.source_tabs.currentIndex()) != selected_source_key:
            selected_credential = None
        self._refresh_credentials(selected_credential)
        self.tree_presentation.refresh()

    def _rebuild_source_tabs(self, selected_source_key):
        """Keep the same three source categories as mobile, including empty ones."""
        while self.source_tabs.count():
            self.source_tabs.removeTab(0)
        for name in SOURCE_NAMES:
            index = self.source_tabs.addTab(name)
            sources = [source for source in self._remote_sources
                       if source_category(source) == name]
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
        self.tree_presentation.refresh()
        # A source can change while the hub remains open (for example when
        # credentials are loaded in another window). Show the cached list now,
        # then reconcile it without blocking the tab switch.
        self.refresh()

    def _local_source_changed(self, _index):
        self._selected_entry_key = None
        self._refresh_credentials()
        self.tree_presentation.refresh()

    def _credential_changed(self, _index):
        self._selected_entry_key = None
        self.tree_presentation.refresh()

    def _get_selected_source(self):
        return self.source_tabs.tabData(self.source_tabs.currentIndex())

    def _refresh_credentials(self, selected_credential=None):
        """Filter local rclone copies and Cloud by their credential group."""
        selected_source = self._get_selected_source()
        is_remote = selected_source is not None and selected_source[0] == 'remote'
        category = self.source_tabs.tabText(self.source_tabs.currentIndex())
        local_rclone = not is_remote and self.local_source_tabs.tabText(self.local_source_tabs.currentIndex()) == 'Rclone'
        cloud = is_remote and category == 'Cloud'
        sources = (selected_source[2] if cloud else
                   [source for source in self._sources.remote_sources if source.feature_name == 'rclone'])
        with pyside.QSignalBlocker(self.credential_combo):
            self.credential_combo.clear()
            self.credential_combo.addItem('All', None)
            if cloud or local_rclone:
                for source in sources:
                    self.credential_combo.addItem(source.source.name, source.source.context)
            if selected_credential is not None:
                for index in range(self.credential_combo.count()):
                    current = self.credential_combo.itemData(index)
                    association = getattr(selected_credential, 'item', None)
                    same_account = False
                    if association is not None and isinstance(current, Path):
                        from features.rclone import session
                        same_account = current == association.context and session.package_path(current) == association.package
                    if current == selected_credential or same_account:
                        self.credential_combo.setCurrentIndex(index)
                        break
        self.local_source_tabs.setVisible(not is_remote)
        self.cloud_source_tabs.setVisible(cloud)
        self.credential_label.setText('Credential')
        self.credential_label.setVisible(cloud or local_rclone)
        self.credential_combo.setVisible(cloud or local_rclone)
        self.rclone_credentials_button.setVisible(cloud or local_rclone)
        self.refresh_button.setVisible(cloud or local_rclone)
        self.home_server_notice.setVisible(category == 'Home Server')

    @staticmethod
    def _entry_key(entry):
        """Keep same-named folders from different credentials independently selectable."""

        context = (str(Path(entry.remote_context)) if entry.remote_source == 'rclone'
                   and entry.remote_context is not None else str(entry.remote_context))
        return (entry.name, entry.remote_source, context,
                str(entry.local.path) if entry.local is not None else None)


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
        from desktop.pages.workspace_icons import folder_icon
        private = getattr(entry.local, 'private', False)
        state = None
        online = self._get_selected_source()[0] == 'remote'
        if online and entry.remote_source == 'rclone':
            from features.rclone import session
            context = Path(entry.remote_context) if entry.remote_context is not None else None
            association = getattr(entry.remote_context, 'item', None)
            if context is None or (context.suffix == '.session' and
                    (session.credentials(context) is None or (association is not None
                     and session.package_path(context) != association.package))):
                state = 'locked'
            elif context.suffix == '.session' or any(
                    source.source.context == entry.remote_context and entry.remote_name in source.encrypted_remote_names
                    for source in self._remote_sources):
                state = 'unlocked'
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
            location, association = self._entry_browser_source(entry, online=online)
            view = (self.open_browser_location(location, package=association.package) if association
                    else self.open_browser_location(location))
            if view is not None:
                self._browser_key = key
                item = self._entry_items.get(self._entry_key(entry))
                if item is not None:
                    self._style_folder_item(item, entry)
            else:
                self.browser_notice.setText('Unlock this workspace to browse its files. Reselect the folder to try again.')
        except Exception as error:
            self.browser_notice.setText(f'Cannot browse this workspace: {error}')

    @staticmethod
    def _entry_browser_source(entry, *, online):
        """Resolve the selected copy and retained credential association before mounting."""
        if online:
            if entry.remote_context is None:
                raise ValueError('Load the matching credential package in Settings, then refresh folders.')
            from features.rclone.ui.remote_browser import RemoteLocation
            location = RemoteLocation(Path(entry.remote_context), entry.remote_name)
        elif getattr(entry.local, 'private', False):
            from desktop.file_browser import _PrivateBrowserLocation
            location = _PrivateBrowserLocation(entry.local.connection, entry.local.path)
        elif entry.local is not None:
            location = entry.local.path
        else:
            raise ValueError('This workspace has no available local copy.')
        association = getattr(entry.remote_context, 'item', None) if online else None
        return location, association

    def open_browser_location(self, location, *, package=None):
        """Feature Browse actions stay in this page's docked browser."""
        self._clear_browser('Opening workspace…')
        view = self._create_browser(location, package=package) if package is not None else self._create_browser(location)
        if view is None:
            return None
        from features.rclone.ui.workspace_unlock import WorkspaceUnlockView
        self.panes.set_actions_available(not isinstance(view, WorkspaceUnlockView))
        self._browser_view = view
        self.browser_stack.addWidget(view)
        self.browser_stack.setCurrentWidget(view)
        view.idle.connect(self._browser_idle)
        return view

    def _create_browser(self, location, *, package=None):
        from desktop.file_browser import _browser_view
        from features.rclone.ui.workspace_unlock import unlock_target, WorkspaceUnlockView
        target = unlock_target(location, package=package)
        if target is not None:
            name = getattr(location, 'remote', None) or getattr(getattr(location, 'item', None), 'remote', None)
            view = WorkspaceUnlockView(*target, parent=self, workspace_name=name or self.selected_entry_name)
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
        else:
            self._browser_key = key
        self._refresh_lock_icons()
        self.refresh()
        item = self.folder_tree.currentItem()
        entry = item.data(0, pyside.Qt.ItemDataRole.UserRole) if item is not None else None
        if entry is not None:
            self._show_entry(entry)

    def _refresh_lock_icons(self):
        # One credential ZIP can unlock several workspace roots at once.
        for item in self._entry_items.values():
            entry = item.data(0, pyside.Qt.ItemDataRole.UserRole)
            if entry is not None:
                self._style_folder_item(item, entry)

    @staticmethod
    def _entry_unlock_target(entry):
        from features.rclone.ui.workspace_unlock import unlock_target
        from features.rclone.ui.remote_browser import RemoteLocation
        from desktop.file_browser import _PrivateBrowserLocation
        if getattr(entry.local, 'private', False):
            return unlock_target(_PrivateBrowserLocation(entry.local.connection, entry.local.path))
        if entry.remote_source == 'rclone' and entry.remote_context is not None:
            association = getattr(entry.remote_context, 'item', None)
            return unlock_target(RemoteLocation(Path(entry.remote_context), entry.remote_name),
                                 package=association.package if association else None)
        return None

    def _retire_actions_unlock(self):
        view, self._actions_unlock_view = self._actions_unlock_view, None
        if view is not None:
            # Retain the parent until any password worker has discarded its result.
            self._retired_browsers.append(view)
            view.setParent(self.browser_stack)
            view.hide()
            self._browser_idle()

    def _actions_unlocked(self, view, entry):
        if self._closing or self._actions_unlock_view is not view:
            return
        self._refresh_lock_icons()
        self._show_entry(entry)
        if self._selected_entry_key == self._entry_key(entry):
            self.refresh()

    def _clear_browser(self, message):
        self.panes.set_actions_available(True)
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

    def _add_rclone(self):
        from desktop.settings.window import open_settings
        page = open_settings(self.window(), category='feature:rclone')
        page.scope_selector.setCurrentIndex(page.scope_selector.findData('personal'))
        feature = page.panels.get('feature:rclone')
        if feature is not None:
            widget = feature.custom.get('credentials')
            if widget is not None:
                for tabs in feature.findChildren(pyside.QTabWidget):
                    if tabs.indexOf(widget) >= 0:
                        tabs.setCurrentWidget(widget)
                widget.import_button.setFocus()

    def _show_empty_state(self, message=None):
        self.panes.set_actions_available(True)
        self._retire_actions_unlock()
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
                       'No visible remote folders. Add an account, choose another credential, or enable Legacy in Settings if needed.')

        label = pyside.QLabel(message)
        label.setWordWrap(True)

        layout.addWidget(label)
        layout.addStretch()

        self.detail_scroll.setWidget(widget)
        info = pyside.QLabel(message)
        info.setWordWrap(True)
        info.setMargin(8)
        info.setAlignment(pyside.Qt.AlignmentFlag.AlignTop)
        self.info_scroll.setWidget(info)
        self._clear_browser(message)
        if (source_type == 'remote' and not self._entry_items
                and self.source_tabs.tabText(self.source_tabs.currentIndex()) == 'Cloud'):
            has_remotes = any(source.remote_names for source in selected_source[2])
            self.cloud_setup_note.setText(
                'No folders match this view. Choose another credential or enable Show Legacy in Settings.'
                if has_remotes else
                'Import a credential ZIP to add an account.\nRemembered accounts ask for a password.')
            self.panes.set_actions_available(False)
            self.browser_stack.setCurrentWidget(self.cloud_setup)

    def _show_entry(self, entry):
        self._retire_actions_unlock()
        self._detail_generation += 1
        self._detail_pending = None
        self.details.request_cancel()
        self._tools_status = None
        self._show_info(entry)
        target = self._entry_unlock_target(entry)
        needs_credentials = (self._get_selected_source()[0] == 'remote'
                             and entry.remote_source == 'rclone' and entry.remote_context is None)
        online = self._get_selected_source()[0] == 'remote'
        self.panes.set_actions_available(not (target is not None and
            (online or getattr(entry.local, 'private', False))))
        if target is not None or needs_credentials:
            widget = pyside.QWidget()
            layout = pyside.QVBoxLayout(widget)
            label = pyside.QLabel('Unlock the workspace credentials to load its actions.')
            label.setWordWrap(True)
            layout.addWidget(label)
            online = self._get_selected_source()[0] == 'remote'
            if needs_credentials:
                label.setText('Load the matching credential package in Settings to load this workspace’s actions.')
            elif not online and not getattr(entry.local, 'private', False):
                # Plain local files remain browsable; only the remote actions need a password.
                from features.rclone.ui.workspace_unlock import WorkspaceUnlockView
                view = WorkspaceUnlockView(*target, parent=widget, purpose='load this workspace’s actions',
                                           workspace_name=entry.name)
                self._actions_unlock_view = view
                view.unlocked.connect(lambda: self._actions_unlocked(view, entry))
                view.idle.connect(self._browser_idle)
                layout.addWidget(view)
            else:
                label.setText('Unlock this workspace in Files to load its actions.')
            layout.addStretch()
            self.detail_scroll.setWidget(widget)
            return
        self._prepare_workspace_actions(entry)

    def _prepare_workspace_actions(self, entry):
        """Mount accepted action scope before starting/coalescing its retained detail job."""
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title_label = pyside.QLabel(entry.name)
        title_label.setTextFormat(pyside.Qt.TextFormat.PlainText)
        title_label.setWordWrap(True)
        title_font = title_label.font()
        title_font.setPointSizeF(point_size(setting_size(title_font) + 3))
        title_font.setBold(True)
        title_label.setFont(title_font)

        layout.addWidget(title_label)
        scope = pyside.QLabel('Actions apply to this workspace root. Browsing or selecting files in Files does not change this target.')
        scope.setWordWrap(True)
        layout.addWidget(scope)
        self._tools_status = pyside.QLabel('Checking workspace tools…')
        layout.addWidget(self._tools_status)
        layout.addStretch()
        self.detail_scroll.setWidget(widget)
        from dataclasses import replace
        self._detail_pending = replace(entry, storage_scope=(
            'remote' if self._get_selected_source()[0] == 'remote' else 'local'))
        if self.details.busy:
            self.details.request_cancel()
        else:
            self._start_details()

    def _start_details(self):
        entry, self._detail_pending = self._detail_pending, None
        features = tuple(self._folder_features)
        from features.rclone import session
        config = (entry.local.connection.context if getattr(entry.local, 'private', False) else
                  entry.remote_context if entry.remote_source == 'rclone' else None)
        self._detail_credentials_revoked = (session.revocation_check(Path(config))
            if config is not None and Path(config).suffix == '.session' else lambda: False)
        self.details.start(self.controller.detail_work(entry, features), show_progress=False)

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
        if self._detail_credentials_revoked() or self._entry_unlock_target(entry) is not None:
            # Credential changes can race with provider detection on its worker.
            self._show_entry(entry)
            self._refresh_lock_icons()
            return
        self._mount_action_sections(entry, found)

    def _mount_action_sections(self, entry, found):
        """Project only the detail result admitted by generation and credential guards."""
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

    def _show_info(self, entry):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        title = pyside.QLabel(entry.name)
        title.setTextFormat(pyside.Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self._create_general_section(entry))
        layout.addStretch()
        self.info_scroll.setWidget(widget)

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

        if entry.remote_source == 'rclone' and entry.remote_context is not None:
            if Path(entry.remote_context).suffix == '.session':
                note = pyside.QLabel(
                    'Session-only credentials enable Cloud browsing and transfers. '
                    'A session-loaded crypt remote can create a LocalCrypt copy; '
                    'its encrypted files remain on disk when credentials lock.')
                note.setWordWrap(True)
                status_layout.addWidget(note, next_row + 1, 0, 1, 2)

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
        for view in [self._browser_view, self._actions_unlock_view, *self._retired_browsers]:
            if view is not None and not view.prepare_close():
                browsers_ready = False
        return not (self.discovery.busy or self.details.busy) and browsers_ready

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()
