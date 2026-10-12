"""
Main window for Logistics.
"""

from commonUtils.ui import pyside
from features import registry
from ui_new.pages.debug import DebugPage
from ui_new.pages.folders import FoldersPage
from ui_new.pages.settings import SettingsPage
from ui_new.file_browser import FileBrowserPage
from ui_new.documents import DocumentsPage, register_document_host
from ui_new.sidebar import DestinationRail
from ui_new.landing import LandingPage, LaunchSurface
from ui_new.folder_actions import FolderActionsPage
from commonUtils.ui.tasks.process_host import register_process_host


CORE_TABS = (
    (0, 'File Browser', FileBrowserPage),
    (5, 'Folder Hub', FoldersPage),
    (90, 'Settings', SettingsPage),
    (100, 'Debug', DebugPage),
)


class _CloseGuard(pyside.QObject):
    def __init__(self, owner):
        super().__init__(owner.dlg)
        self.owner = owner
        owner.dlg.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == pyside.QEvent.Type.Close:
            if not self.owner.can_close():
                event.ignore()
                return True
        return super().eventFilter(watched, event)


class _ToastStatusGuard(pyside.QObject):
    """Reserve footer space only while the transient notice is shown."""
    def __init__(self, toast, status_bar):
        super().__init__(toast)
        self.status_bar = status_bar
        toast.installEventFilter(self)
        toast.hide()
        status_bar.hide()

    def eventFilter(self, watched, event):
        if event.type() == pyside.QEvent.Type.ShowToParent:
            self.status_bar.show()
        elif event.type() == pyside.QEvent.Type.HideToParent:
            self.status_bar.hide()
        return super().eventFilter(watched, event)


class MainWindow(pyside.Window):
    def __init__(self):
        super().__init__('Logistics', main_window=True)

        self.width = 1250
        self.height = 800
        self.dlg.resize(self.width, self.height)
        self.dlg.setMinimumSize(850, 550)

        self.tabs = pyside.QTabWidget()
        self.tabs.tabBar().hide()
        self.documents = DocumentsPage(self._show_documents, self.dlg)
        self.actions = FolderActionsPage(self._show_actions, self.dlg)
        self.sidebar = DestinationRail(self.documents, self.dlg)
        self.sidebar.actions = self.actions
        self.sidebar.selected.connect(self._destination_changed)
        self.documents.changed.connect(self._documents_changed)
        self.documents.idle.connect(self._retry_close)
        self.actions.changed.connect(self._actions_changed)
        self.actions.idle.connect(self._retry_close)
        self._docking_preview = False
        self._closing = False
        self.bulk_rename = None
        self._launch_mode = 'landing'
        self._standalone_page = None

        self._build_layout()
        self._core_pages = []
        self._feature_pages = {}
        try:
            self._populate_tabs()
            for _, _, page in self._core_pages:
                if isinstance(page, SettingsPage):
                    page.reveal = self._show_settings
        except BaseException:
            self._cleanup_failed_startup()
            raise
        self._unsubscribe = registry.subscribe(self._features_changed)
        self.dlg.destroyed.connect(self._unsubscribe)
        self.tabs.currentChanged.connect(self._tab_changed)
        self._close_guard = _CloseGuard(self)
        self._last_destination = self.tabs.currentWidget()
        self._bind_docking_preview(self.documents)
        for _, _, page in self._core_pages:
            self._bind_docking_preview(page)
        register_document_host(self.documents)
        register_process_host(self.actions)
        from ui_new.bulk_rename import register_bulk_rename_host
        register_bulk_rename_host(self._show_bulk_rename)
        from .notifications import notification_service, Toast
        self.toast = Toast(notification_service(), self.dlg)
        self.dlg.statusBar().addWidget(self.toast, 1)
        self._toast_status_guard = _ToastStatusGuard(self.toast, self.dlg.statusBar())
        self._refresh_sidebar()
        self._update_window_title()
        self.dlg.workspace_menu_document = self._menu_document
        from .header_menus import HeaderMenus
        self.header_menus = HeaderMenus(self)
        self.dlg.workspace_publish_menus = True
        self.dlg.workspace_menu_actions = [self.header_menus.menu.menuAction()]
        self.documents.workspace.active_changed.connect(self._sync_menus)
        self._sync_menus()

    def _build_layout(self):
        central_widget = self.launch_surface = LaunchSurface()
        outer = pyside.QVBoxLayout(central_widget)
        outer.setContentsMargins(0, 0, 0, 0)
        self.launch_stack = pyside.QStackedWidget(central_widget)
        outer.addWidget(self.launch_stack)
        self.landing = LandingPage()
        self.landing.launch_requested.connect(self._launch)
        self.landing.document_requested.connect(self._launch_document)
        self.launch_stack.addWidget(self.landing)
        self.hub = pyside.QWidget()
        layout = pyside.QHBoxLayout(self.hub)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.tabs, 1)
        self.launch_stack.addWidget(self.hub)
        self.sidebar.hide()

        self.settings_button = central_widget.settings_button
        menu = pyside.QMenu(self.settings_button)
        self.show_settings_action = menu.addAction('Settings', self._show_settings)
        menu.addSeparator()
        self.return_to_tool_action = menu.addAction('Return to tool', self._return_to_tool)
        self.open_documents_action = menu.addAction('Open Documents', self._show_documents)
        self.choose_launch_mode_action = menu.addAction('Choose launch mode', self._show_landing)
        self.open_hub_action = menu.addAction('Open full hub with sidebar', lambda: self._launch('hub'))
        self.settings_button.setMenu(menu)
        menu.aboutToShow.connect(self._update_navigation_menu)
        rail_settings = self.sidebar.buttons['settings']
        rail_settings.clicked.disconnect()
        rail_settings.setCheckable(False)
        rail_settings.setMenu(menu)
        rail_settings.setPopupMode(pyside.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.return_to_tool_action.setEnabled(False)
        central_widget.position_settings()

        self.dlg.setCentralWidget(central_widget)

    def _update_navigation_menu(self):
        showing_hub = self.launch_stack.currentWidget() is self.hub
        current = self.tabs.currentWidget() if showing_hub else None
        settings = next((page for _, _, page in self._core_pages if isinstance(page, SettingsPage)), None)
        self.show_settings_action.setVisible(current is not settings or settings is None)
        self.open_documents_action.setVisible(current is not self.documents)
        self.choose_launch_mode_action.setVisible(self.launch_stack.currentWidget() is not self.landing)
        self.open_hub_action.setVisible(self._launch_mode != 'hub')
        self.return_to_tool_action.setVisible(self._standalone_page is not None and current is not self._standalone_page)

    def _show_document_chooser(self):
        self._show_documents()
        return self.documents.new_document_chooser(self.documents.workspace)

    @staticmethod
    def _launch_key(feature, page_id):
        return {'git.workspace': 'git', 'ide.workspace': 'ide'}.get(page_id, 'feature:' + feature + ':' + page_id)

    def _launch_targets(self):
        targets = {}
        for _, _, page in self._core_pages:
            if isinstance(page, FileBrowserPage):
                targets['browser'] = page
            elif isinstance(page, FoldersPage):
                targets['folders'] = page
        for (feature, page_id), page in self._feature_pages.items():
            if page.property('navigation_icon') and self.tabs.indexOf(page) >= 0:
                targets[self._launch_key(feature, page_id)] = page
        if self.actions.count:
            targets['actions'] = self.actions
        if self.bulk_rename is not None:
            targets['bulk_rename'] = self.bulk_rename
        return targets

    def _tool_launchers(self):
        targets = self._launch_targets()
        entries = []
        for key, title, detail, icon in (
                ('browser', 'File Browser', 'Browse and organize files.', 'browser'),
                ('folders', 'Folder Hub', 'Browse configured folders and services.', 'hub'),
                ('bulk_rename', 'Bulk Rename', 'Preview and rename files and folders.', 'rename')):
            if key in targets or key == 'bulk_rename':
                entries.append((key, title, detail, icon))
        states = {state.name: state for state in registry.get_feature_states()}
        for registered in registry.get_pages():
            contribution = registered.contribution
            key = self._launch_key(registered.feature_name, contribution.page_id)
            if contribution.navigation_icon and key in targets:
                state = states.get(registered.feature_name)
                detail = contribution.launch_description or getattr(state, 'description', '') or f'Open {contribution.name}.'
                entries.append((key, contribution.name, detail, contribution.navigation_icon))
        if 'actions' in targets:
            entries.append(('actions', 'Folder Actions', 'Continue running operations and review their results.', 'actions'))
        return entries

    def _launch(self, mode):
        if mode == 'bulk_rename' and self.bulk_rename is None:
            self._show_bulk_rename()
        targets = self._launch_targets()
        page = targets.get(mode)
        if mode != 'hub' and (page is None or self.tabs.indexOf(page) < 0):
            return
        self._launch_mode = mode
        self._standalone_page = page
        self.launch_stack.setCurrentWidget(self.hub)
        self.sidebar.setVisible(mode == 'hub')
        self.settings_button.setVisible(mode != 'hub')
        self.return_to_tool_action.setText('Return to tool')
        self.return_to_tool_action.setEnabled(page is not None)
        if page is None:
            page = targets.get('browser')
        if page is not None:
            self.tabs.setCurrentWidget(page)
        self.launch_surface.position_settings()
        self._update_window_title()
        self._sync_menus()

    def _show_landing(self):
        self._launch_mode = 'landing'
        self._standalone_page = None
        self.return_to_tool_action.setEnabled(False)
        self.sidebar.hide()
        self.launch_stack.setCurrentWidget(self.landing)
        self.settings_button.show()
        self.launch_surface.position_settings()
        self._update_window_title()
        self._sync_menus()

    def _show_settings(self):
        settings = next((page for _, _, page in self._core_pages
                         if isinstance(page, SettingsPage)), None)
        if settings is not None:
            self._reveal_hub()
            self.tabs.setCurrentWidget(settings)

    def _launch_document(self, key, new=False):
        launcher = self.sidebar.launchers.get(key)
        if launcher is None:
            return
        callback = launcher.new_document if new else launcher.open_document
        # The document host reveals successful opens. A cancelled picker keeps
        # the chooser and the current launch mode intact.
        if callback is not None:
            callback(self.documents)

    def _return_to_tool(self):
        page = self._standalone_page
        if page is not None and self.tabs.indexOf(page) >= 0:
            self.tabs.setCurrentWidget(page)

    def _reveal_hub(self):
        """Hosted documents and jobs may reveal content from the launch screen."""
        self.launch_stack.setCurrentWidget(self.hub)
        self.launch_surface.position_settings()
        self._update_window_title()
        self._sync_menus()

    def _populate_tabs(self):
        """Build core and feature-contributed tabs in one ordered list."""

        pages = registry.get_pages()
        seen_page_ids = set()
        for registered in pages:
            contribution = registered.contribution

            if contribution.page_id in seen_page_ids:
                raise ValueError(
                    f'Duplicate contributed page ID: {contribution.page_id}'
                )

            seen_page_ids.add(contribution.page_id)

        tabs = []
        # Keep each constructed page owned even if a later page fails at startup.
        for order, name, page_type in CORE_TABS:
            page = page_type(parent=self.dlg)
            tabs.append((order, name, page))
            self._core_pages.append((order, name, page))
            if isinstance(page, FoldersPage):
                page.browse_requested.connect(self._browse_folder)
        for registered in pages:
            contribution = registered.contribution
            page = self._create_feature_page(contribution)
            page.setProperty('navigation_icon', contribution.navigation_icon)
            self._feature_pages[(registered.feature_name, contribution.page_id)] = page
            tabs.append(
                (
                    contribution.order,
                    contribution.name,
                    page
                )
            )

        for _order, name, page in sorted(
            tabs,
            key=lambda item: (item[0], item[1].casefold())
        ):
            self.tabs.addTab(page, name)

    def _cleanup_failed_startup(self):
        """Cancel already-created pages and drain Qt workers before destruction."""
        pages = [page for _, _, page in self._core_pages] + list(self._feature_pages.values())
        loop = pyside.QEventLoop()
        timer = pyside.QTimer()
        timer.setInterval(20)

        def stopped():
            ready = True
            for page in pages:
                if not getattr(page, 'prepare_close', lambda: True)():
                    ready = False
            return ready

        def check():
            if stopped():
                loop.quit()

        if not stopped():
            timer.timeout.connect(check)
            timer.start()
            loop.exec()
            timer.stop()
        self.dlg.close()
        self.dlg.deleteLater()

    def _bind_docking_preview(self, page):
        from commonUtils.ui.workspaces.workspace import Workspace
        for workspace in page.findChildren(Workspace):
            workspace.drop_reveal = lambda target=page: self._preview_docking(target)

    def _preview_docking(self, page):
        previous = self.tabs.currentWidget()
        previous_destination = self._last_destination
        focus = pyside.QApplication.focusWidget()
        self._docking_preview = True
        try:
            if self.tabs.indexOf(page) < 0:
                self.tabs.addTab(page, 'Open documents')
            self.tabs.setCurrentWidget(page)
        finally:
            self._docking_preview = False
        def restore():
            from shiboken6 import isValid
            if not isValid(self.tabs) or previous is None or not isValid(previous):
                return
            self._docking_preview = True
            try:
                self.tabs.setCurrentWidget(previous)
                self._last_destination = previous_destination
                if focus is not None and isValid(focus):
                    focus.setFocus()
            finally:
                self._docking_preview = False
        return restore

    def _create_feature_page(self, contribution):
        page = contribution.create_page(self.dlg)
        if contribution.page_id == 'git.workspace':
            page.working_file_opener = self._open_git_file_in_ide
        settings_requested = getattr(page, 'feature_settings_requested', None)
        if settings_requested is not None:
            settings_requested.connect(self._show_feature_settings)
        self._bind_docking_preview(page)
        idle = getattr(page, 'idle', None)
        if idle is not None and callable(getattr(idle, 'connect', None)):
            idle.connect(self._retry_close)
        return page

    def _open_git_file_in_ide(self, path):
        page = self._feature_pages.get(('ide', 'ide.workspace'))
        if page is None or self.tabs.indexOf(page) < 0:
            return False
        if not page.open_registered_file(path):
            return False
        if self._launch_mode == 'hub':
            self._reveal_hub()
            self.tabs.setCurrentWidget(page)
        else:
            self._launch('ide')
        return True

    def _show_feature_settings(self, feature):
        settings = next(page for _, _, page in self._core_pages if isinstance(page, SettingsPage))
        settings.show_feature(feature)
        self._reveal_hub()
        self.tabs.setCurrentWidget(settings)

    def _features_changed(self):
        pyside.QTimer.singleShot(0, self._sync_feature_pages)

    def _sync_feature_pages(self):
        from shiboken6 import isValid
        if not isValid(self.dlg):
            return
        current = self.tabs.currentWidget()
        pages = registry.get_pages()
        seen = set()
        entries = list(self._core_pages)
        # Once opened, Documents remains a destination even with zero tabs.
        # Feature refresh must not remove it based on attached document count.
        if self.tabs.indexOf(self.documents) >= 0:
            entries.append((80, 'Open documents', self.documents))
        if self.actions.count:
            entries.append((85, 'Folder Actions', self.actions))
        if self.bulk_rename is not None:
            entries.append((86, 'Bulk Rename', self.bulk_rename))
        for registered in pages:
            contribution = registered.contribution
            if contribution.page_id in seen:
                raise ValueError(f'Duplicate contributed page ID: {contribution.page_id}')
            seen.add(contribution.page_id)
            key = (registered.feature_name, contribution.page_id)
            if key not in self._feature_pages:
                self._feature_pages[key] = self._create_feature_page(contribution)
                self._feature_pages[key].setProperty('navigation_icon', contribution.navigation_icon)
            entries.append((contribution.order, contribution.name, self._feature_pages[key]))
        with pyside.QSignalBlocker(self.tabs):
            while self.tabs.count():
                page = self.tabs.widget(0)
                self.tabs.removeTab(0)
                page.hide()
            for _, name, page in sorted(entries, key=lambda entry: (entry[0], entry[1].casefold())):
                self.tabs.addTab(page, name)
            index = self.tabs.indexOf(current)
            if index >= 0:
                self.tabs.setCurrentIndex(index)
        self._tab_changed(self.tabs.currentIndex())
        self._refresh_sidebar()

    def _refresh_sidebar(self):
        self.sidebar.refresh(self.tabs, self._core_pages)
        self.landing.set_document_launchers(self.sidebar.launchers)
        self.landing.set_tool_launchers(self._tool_launchers())
        if self._standalone_page is not None and self.tabs.indexOf(self._standalone_page) < 0:
            self._show_landing()

    def _destination_changed(self, page):
        if page is not None and self.tabs.indexOf(page) >= 0:
            self._reveal_hub()
            self.tabs.setCurrentWidget(page)

    def _browse_folder(self, path):
        page = next((page for _, _, page in self._core_pages if isinstance(page, FileBrowserPage)), None)
        if page is None:
            return
        view = page.workspace.active_view
        root = view.file_browser.navigation.library
        if root is not None and (path == root or root in path.parents):
            view.file_browser.navigate(path)
        else:
            page.workspace.add_view(path)
        self.tabs.setCurrentWidget(page)

    def _show_documents(self):
        if self._launch_mode == 'landing':
            self._launch_mode = 'documents'
            self._standalone_page = self.documents
            self.return_to_tool_action.setText('Return to documents')
            self.return_to_tool_action.setEnabled(True)
        self._reveal_hub()
        if self.tabs.currentWidget() is not self.documents:
            self._last_destination = self.tabs.currentWidget()
        if self.tabs.indexOf(self.documents) < 0:
            self.tabs.addTab(self.documents, 'Open documents')
        self.tabs.setCurrentWidget(self.documents)
        self.dlg.show(); self.dlg.raise_(); self.dlg.activateWindow()

    def _show_bulk_rename(self, directory=None, *, paths=()):
        self._reveal_hub()
        from ui_new.bulk_rename import BulkRenameWidget
        if self.bulk_rename is None:
            self.bulk_rename = BulkRenameWidget(directory, self.dlg, paths=paths)
            self.bulk_rename.idle.connect(self._retry_close)
            self.tabs.addTab(self.bulk_rename, 'Bulk Rename')
        elif directory is not None or paths:
            self.bulk_rename.set_inputs(directory, paths=paths)
        self.tabs.setCurrentWidget(self.bulk_rename)
        self.dlg.show(); self.dlg.raise_(); self.dlg.activateWindow()
        self._refresh_sidebar()
        return self.bulk_rename

    def _show_actions(self):
        self._reveal_hub()
        if self.tabs.indexOf(self.actions) < 0:
            self.tabs.addTab(self.actions, 'Folder Actions')
        self.tabs.setCurrentWidget(self.actions)
        self.dlg.show(); self.dlg.raise_(); self.dlg.activateWindow()
        self.actions.acknowledge_current()

    def _actions_changed(self):
        from shiboken6 import isValid
        if not isValid(self.tabs):
            return
        if not self.actions.count and self.tabs.indexOf(self.actions) >= 0:
            self.tabs.removeTab(self.tabs.indexOf(self.actions))
        self._refresh_sidebar()

    def _documents_changed(self):
        from shiboken6 import isValid
        if not isValid(self.tabs):
            return
        self._refresh_sidebar()

    def _retry_close(self):
        from shiboken6 import isValid
        if self._closing and isValid(self.dlg):
            pyside.QTimer.singleShot(0, self.dlg, self._finish_close)

    def _finish_close(self):
        from shiboken6 import isValid
        if self._closing and isValid(self.dlg):
            self.dlg.close()

    def _update_window_title(self):
        index = self.tabs.currentIndex()
        name = self.tabs.tabText(index) if index >= 0 else ''
        if self.launch_stack.currentWidget() is self.landing:
            name = ''
        self.dlg.setWindowTitle(f'Logistics: {name}' if name else 'Logistics')

    def _tab_changed(self, _index):
        """Refresh the active page when that page exposes a refresh method."""

        current_widget = self.tabs.currentWidget()
        self._update_window_title()
        self.sidebar.set_current(current_widget)
        self._sync_menus()
        if self._docking_preview:
            return
        if current_widget is self.actions:
            pyside.QTimer.singleShot(0, self.actions, self.actions.acknowledge_current)
        if current_widget is not self.documents:
            self._last_destination = current_widget

        if current_widget is None:
            return

        refresh = getattr(current_widget, 'refresh', None)

        if callable(refresh):
            refresh()

    def _menu_document(self):
        if self.launch_stack.currentWidget() is self.landing:
            return None
        page = self.tabs.currentWidget()
        workspace = getattr(page, 'workspace', None)
        view = workspace.active_view if workspace is not None else page
        document = view if isinstance(view, pyside.QMainWindow) else getattr(view, 'document', None)
        if document is None and hasattr(self, 'header_menus'):
            document = self.header_menus.context_document(page)
        return document

    def _sync_menus(self, *args):
        from commonUtils.ui.workspaces.workspace_menus import sync_native_menus
        sync_native_menus(self.dlg, self._menu_document())

    def can_close(self):
        pages = [page for _, _, page in self._core_pages] + list(self._feature_pages.values())
        # Resolve unsaved settings before asking browser workers/controllers to stop.
        if not all(getattr(page, 'can_close', lambda: True)() for page in pages):
            self._closing = False
            self.documents.closing = False
            self.actions.closing = False
            return False
        self._closing = True
        self.documents.closing = True
        self.actions.closing = True
        from commonUtils.ui.tasks.process_progress import prepare_close_all
        ready = prepare_close_all(self.dlg.close)
        ready = self.documents.prepare_close() and ready
        ready = self.actions.prepare_close() and ready
        if self.bulk_rename is not None:
            ready = self.bulk_rename.prepare_close() and ready
        if self.documents.close_veto:
            self._closing = False
            self.documents.closing = False
            self.actions.closing = False
            return False
        for page in pages:
            if not getattr(page, 'prepare_close', lambda: True)():
                ready = False
        return ready
