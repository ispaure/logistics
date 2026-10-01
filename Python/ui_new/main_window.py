"""
Main window for Logistics.
"""

from commonUtils.ui import pyside
from features import registry
from ui_new.pages.debug import DebugPage
from ui_new.pages.folders import FoldersPage


CORE_TABS = (
    (0, 'Folders', FoldersPage),
    (100, 'Debug', DebugPage),
)


class MainWindow(pyside.Window):
    def __init__(self):
        super().__init__('Logistics', main_window=True)

        self.width = 850
        self.height = 550
        self.dlg.resize(self.width, self.height)
        self.dlg.setMinimumSize(850, 550)

        self.tabs = pyside.QTabWidget()

        self._build_layout()
        self._populate_tabs()

    def _build_layout(self):
        central_widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

        self.dlg.setCentralWidget(central_widget)

        self.tabs.currentChanged.connect(self._tab_changed)

    def _populate_tabs(self):
        """Build core and feature-contributed tabs in one ordered list."""

        tabs = [
            (order, name, page_type(parent=self.dlg))
            for order, name, page_type in CORE_TABS
        ]

        seen_page_ids = set()

        for registered in registry.get_pages():
            contribution = registered.contribution

            if contribution.page_id in seen_page_ids:
                raise ValueError(
                    f'Duplicate contributed page ID: {contribution.page_id}'
                )

            seen_page_ids.add(contribution.page_id)

            tabs.append(
                (
                    contribution.order,
                    contribution.name,
                    contribution.create_page(self.dlg)
                )
            )

        for _order, name, page in sorted(
            tabs,
            key=lambda item: (item[0], item[1].casefold())
        ):
            self.tabs.addTab(page, name)

    def _tab_changed(self, _index):
        """Refresh the active page when that page exposes a refresh method."""

        current_widget = self.tabs.currentWidget()

        if current_widget is None:
            return

        refresh = getattr(current_widget, 'refresh', None)

        if callable(refresh):
            refresh()
