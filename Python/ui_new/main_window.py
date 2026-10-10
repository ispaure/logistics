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
from ui_new.folder_actions import FolderActionsPage
from commonUtils.ui.process_host import register_process_host


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

        self._build_layout()
        self._core_pages = []
        self._feature_pages = {}
        try:
            self._populate_tabs()
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

    def _build_layout(self):
        central_widget = pyside.QWidget()
        layout = pyside.QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.tabs, 1)

        self.dlg.setCentralWidget(central_widget)

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
        from commonUtils.ui.workspace import Workspace
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
        self._bind_docking_preview(page)
        idle = getattr(page, 'idle', None)
        if idle is not None and callable(getattr(idle, 'connect', None)):
            idle.connect(self._retry_close)
        return page

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

    def _destination_changed(self, page):
        if page is not None and self.tabs.indexOf(page) >= 0:
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
        if self.tabs.currentWidget() is not self.documents:
            self._last_destination = self.tabs.currentWidget()
        if self.tabs.indexOf(self.documents) < 0:
            self.tabs.addTab(self.documents, 'Open documents')
        self.tabs.setCurrentWidget(self.documents)
        self.dlg.show(); self.dlg.raise_(); self.dlg.activateWindow()

    def _show_bulk_rename(self, directory=None, *, paths=()):
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
        self.dlg.setWindowTitle(f'Logistics: {name}' if name else 'Logistics')

    def _tab_changed(self, _index):
        """Refresh the active page when that page exposes a refresh method."""

        current_widget = self.tabs.currentWidget()
        self._update_window_title()
        self.sidebar.set_current(current_widget)
        from commonUtils.ui.workspace_menus import sync_native_menus
        document = self.documents.workspace.active_view if current_widget is self.documents else None
        sync_native_menus(self.dlg, getattr(document, 'document', None))
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
        from commonUtils.ui.process_progress import prepare_close_all
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
