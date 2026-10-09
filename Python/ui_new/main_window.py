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


class MainWindow(pyside.Window):
    def __init__(self):
        super().__init__('Logistics', main_window=True)

        self.width = 1250
        self.height = 800
        self.dlg.resize(self.width, self.height)
        self.dlg.setMinimumSize(850, 550)

        self.tabs = pyside.QTabWidget()
        self.tabs.tabBar().hide()
        self.sidebar = pyside.QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setAccessibleName('Main destinations')
        self.sidebar.setMinimumWidth(160)
        self.sidebar.setMaximumWidth(210)
        self.sidebar.setStyleSheet('QTreeWidget { border: none; background: palette(window); }')
        self.sidebar.currentItemChanged.connect(self._destination_changed)
        self._sidebar_items = {}
        self.documents = DocumentsPage(self._show_documents, self.dlg)
        self.documents.changed.connect(self._documents_changed)
        self.documents.idle.connect(self._retry_close)
        self._closing = False

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
        register_document_host(self.documents)
        self._refresh_sidebar()

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
            page = contribution.create_page(self.dlg)
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
        if self.documents.count:
            entries.append((80, 'Open documents', self.documents))
        for registered in pages:
            contribution = registered.contribution
            if contribution.page_id in seen:
                raise ValueError(f'Duplicate contributed page ID: {contribution.page_id}')
            seen.add(contribution.page_id)
            key = (registered.feature_name, contribution.page_id)
            if key not in self._feature_pages:
                self._feature_pages[key] = contribution.create_page(self.dlg)
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
        with pyside.QSignalBlocker(self.sidebar):
            self.sidebar.clear()
            self._sidebar_items = {}
            tools = pyside.QTreeWidgetItem(['Tools'])
            tools.setFlags(tools.flags() & ~pyside.Qt.ItemFlag.ItemIsSelectable)
            core = {page: (order, name) for order, name, page in self._core_pages}
            browser_item = None
            for index in range(self.tabs.count()):
                page = self.tabs.widget(index)
                if page is self.documents:
                    continue
                item = pyside.QTreeWidgetItem([self.tabs.tabText(index)])
                item.setData(0, pyside.Qt.ItemDataRole.UserRole, index)
                self._sidebar_items[page] = item
                if page in core and (core[page][0] < 10 or core[page][1] == 'Settings'):
                    self.sidebar.addTopLevelItem(item)
                    if core[page][0] == 0:
                        browser_item = item
                else:
                    tools.addChild(item)
            if browser_item is not None and self.documents.count:
                item = pyside.QTreeWidgetItem([f'Open documents ({self.documents.count})'])
                item.setData(0, pyside.Qt.ItemDataRole.UserRole, self.tabs.indexOf(self.documents))
                browser_item.addChild(item); browser_item.setExpanded(True)
                self._sidebar_items[self.documents] = item
            self.sidebar.insertTopLevelItem(min(2, self.sidebar.topLevelItemCount()), tools)
            tools.setExpanded(True)
            item = self._sidebar_items.get(self.tabs.currentWidget())
            if item is not None:
                self.sidebar.setCurrentItem(item)

    def _destination_changed(self, item, previous):
        if item is not None:
            index = item.data(0, pyside.Qt.ItemDataRole.UserRole)
            if index is not None:
                self.tabs.setCurrentIndex(index)

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
        if self.tabs.indexOf(self.documents) < 0:
            self.tabs.addTab(self.documents, 'Open documents')
        self.tabs.setCurrentWidget(self.documents)
        self.dlg.show(); self.dlg.raise_(); self.dlg.activateWindow()

    def _documents_changed(self):
        from shiboken6 import isValid
        if not isValid(self.tabs):
            return
        if not self.documents.count and self.tabs.indexOf(self.documents) >= 0:
            self.tabs.removeTab(self.tabs.indexOf(self.documents))
        self._refresh_sidebar()

    def _retry_close(self):
        from shiboken6 import isValid
        if self._closing and isValid(self.dlg):
            pyside.QTimer.singleShot(0, self.dlg, self._finish_close)

    def _finish_close(self):
        from shiboken6 import isValid
        if self._closing and isValid(self.dlg):
            self.dlg.close()

    def _tab_changed(self, _index):
        """Refresh the active page when that page exposes a refresh method."""

        current_widget = self.tabs.currentWidget()
        item = self._sidebar_items.get(current_widget)
        if item is not None:
            with pyside.QSignalBlocker(self.sidebar):
                self.sidebar.setCurrentItem(item)

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
            return False
        self._closing = True
        self.documents.closing = True
        from commonUtils.ui.process_progress import prepare_close_all
        ready = prepare_close_all(self.dlg.close)
        ready = self.documents.prepare_close() and ready
        if self.documents.close_veto:
            self._closing = False
            self.documents.closing = False
            return False
        for page in pages:
            if not getattr(page, 'prepare_close', lambda: True)():
                ready = False
        return ready
