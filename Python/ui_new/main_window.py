"""
Main window for the replacement Logistics UI.
"""

from commonUtils.ui import pyside
from features import registry
from ui_new.pages.folders import FoldersPage
from ui_new.pages.placeholder import PlaceholderPage


class MainWindow(pyside.Window):
    def __init__(self):
        super().__init__('Logistics', main_window=True)

        self.width = 1100
        self.height = 700
        self.dlg.resize(self.width, self.height)
        self.dlg.setMinimumSize(850, 550)

        self.tabs = pyside.QTabWidget()
        self.folders_page = None

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
        contributed_pages = {
            registered.contribution.page_id: registered.contribution
            for registered in registry.get_pages()
        }

        self.folders_page = FoldersPage()
        self.tabs.addTab(self.folders_page, 'Folders')

        rclone_page = contributed_pages.get('rclone')

        if rclone_page is not None:
            from ui_new.pages.rclone import RclonePage

            self.tabs.addTab(RclonePage(), rclone_page.name)

        self.tabs.addTab(
            PlaceholderPage(
                'Servers',
                'Game-server providers will populate this page. Selecting a '
                'server on the left will show its available actions on the right.'
            ),
            'Servers'
        )

        smart_home_page = contributed_pages.get('smart_home')

        if smart_home_page is not None:
            self.tabs.addTab(
                PlaceholderPage(
                    smart_home_page.name,
                    'Smart Home controls will be migrated here.'
                ),
                smart_home_page.name
            )

        links_page = contributed_pages.get('links')

        if links_page is not None:
            self.tabs.addTab(
                PlaceholderPage(
                    links_page.name,
                    'Links will be organized here into Self-Improvement, '
                    'Quick Links, and Entertainment.'
                ),
                links_page.name
            )

        self.tabs.addTab(
            PlaceholderPage(
                'Debug',
                'Debug actions contributed by enabled features will be generated here.'
            ),
            'Debug'
        )

    def _tab_changed(self, _index):
        """
        Refresh dynamic pages when they become active.

        rclone configuration changes can alter the logical folder list, so the
        Folders page is refreshed whenever the user returns to it.
        """

        current_widget = self.tabs.currentWidget()

        if current_widget is self.folders_page:
            self.folders_page.refresh()
