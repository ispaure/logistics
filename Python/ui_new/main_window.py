"""
Main window for Logistics.
"""

from commonUtils.ui import pyside
from features import registry
from ui_new.pages.debug import DebugPage
from ui_new.pages.folders import FoldersPage
from ui_new.pages.settings import SettingsPage
from ui_new.file_browser import FileBrowserPage


CORE_TABS = (
    (0, 'File Browser', FileBrowserPage),
    (5, 'Known Folders', FoldersPage),
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

        self._build_layout()
        self._core_pages = []
        self._feature_pages = {}
        self._populate_tabs()
        self._unsubscribe = registry.subscribe(self._features_changed)
        self.dlg.destroyed.connect(self._unsubscribe)
        self.tabs.currentChanged.connect(self._tab_changed)
        self._close_guard = _CloseGuard(self)

    def _build_layout(self):
        central_widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

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

        tabs = [
            (order, name, page_type(parent=self.dlg))
            for order, name, page_type in CORE_TABS
        ]
        self._core_pages = list(tabs)
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

    def _tab_changed(self, _index):
        """Refresh the active page when that page exposes a refresh method."""

        current_widget = self.tabs.currentWidget()

        if current_widget is None:
            return

        refresh = getattr(current_widget, 'refresh', None)

        if callable(refresh):
            refresh()

    def can_close(self):
        pages = [page for _, _, page in self._core_pages] + list(self._feature_pages.values())
        # Resolve unsaved settings before asking browser workers/controllers to stop.
        if not all(getattr(page, 'can_close', lambda: True)() for page in pages):
            return False
        ready = True
        for page in pages:
            if not getattr(page, 'prepare_close', lambda: True)():
                ready = False
        return ready
