"""Application navigation stays available alongside the active tool's menus."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from features import registry


class HeaderMenus(qt.QObject):
    def __init__(self, owner):
        super().__init__(owner.dlg)
        self.owner = owner
        self.menu = owner.dlg.menuBar().addMenu('Logistics')
        self.destinations = self.menu.addMenu('Go to Tool')
        self.documents = self.menu.addAction('New / Open Document…', owner._show_document_chooser)
        self.menu.addSeparator()
        self.menu.addAction('Bulk Rename…', lambda: owner._show_bulk_rename())
        self.refresh = self.menu.addAction('Refresh Current Tool', self.refresh_current)
        self.menu.addSeparator()
        self.menu.addAction(owner.show_settings_action)
        self.menu.addAction(owner.open_documents_action)
        self.feature_settings = self.menu.addMenu('Tool Settings')
        self.menu.addAction(owner.choose_launch_mode_action)
        self.menu.addAction(owner.open_hub_action)
        self.menu.addSeparator()
        self.guides = self.menu.addMenu('Help / Guides')
        self.menu.addSeparator()
        self.menu.addAction('Close Logistics Window', owner.dlg.close)
        self.sources = {}
        self.menu.aboutToShow.connect(self.update)
        self.destinations.aboutToShow.connect(self.update_destinations)
        self.feature_settings.aboutToShow.connect(self.update_settings)
        self.guides.aboutToShow.connect(self.update_guides)

    def update(self):
        self.owner._update_navigation_menu()
        page = self.owner.tabs.currentWidget()
        self.refresh.setEnabled(self.owner.launch_stack.currentWidget() is self.owner.hub
                                and callable(getattr(page, 'refresh', None)))
        self.update_destinations()
        self.update_documents()
        self.update_settings()
        self.update_guides()

    def refresh_current(self):
        callback = getattr(self.owner.tabs.currentWidget(), 'refresh', None)
        if callable(callback):
            callback()

    def update_destinations(self):
        self.destinations.clear()
        tabs = self.owner.tabs
        for index in range(tabs.count()):
            page = tabs.widget(index)
            if page is tabs.currentWidget() and self.owner.launch_stack.currentWidget() is self.owner.hub:
                continue
            action = self.destinations.addAction(tabs.tabText(index), lambda checked=False, page=page:
                                                 self.owner._destination_changed(page))
            action.setCheckable(True)
            action.setChecked(tabs.currentWidget() is page and self.owner.launch_stack.currentWidget() is self.owner.hub)
        if tabs.indexOf(self.owner.documents) < 0:
            self.destinations.addAction('Open Documents', self.owner._show_documents)

    def update_documents(self):
        self.documents.setEnabled(bool(self.owner.sidebar.launchers))

    def update_settings(self):
        self.feature_settings.clear()
        for state in sorted(registry.get_feature_states(), key=lambda state: state.label.casefold()):
            self.feature_settings.addAction(state.label, lambda checked=False, name=state.name:
                                           self.owner._show_feature_settings(name))
        self.feature_settings.setEnabled(bool(self.feature_settings.actions()))

    def guide(self, menu, title, path):
        if path.is_file():
            from commonUtils.ui.markdown import open_markdown
            menu.addAction(title, lambda checked=False: open_markdown(
                path, parent=self.owner.dlg, detached=True, allow_new_tabs=False))

    def update_guides(self):
        self.guides.clear()
        self.guide(self.guides, 'Logistics Guide', Path(__file__).with_name('user_docs') / 'README.md')
        self.guide(self.guides, 'Bulk Rename Guide', Path(__file__).with_name('bulk_rename') / 'user_docs' / 'README.md')
        for state in sorted(registry.get_feature_states(), key=lambda state: state.label.casefold()):
            # External features own their documentation; keep it in their settings.
            if state.name == 'emulation':
                continue
            self.guide(self.guides, state.label, Path(registry.__file__).parent / state.name / 'user_docs' / 'index.md')

    def context_document(self, page):
        if page is None:
            return None
        if page in self.sources:
            return self.sources[page]
        key = next((key for key, candidate in self.owner._feature_pages.items() if candidate is page), None)
        bulk = page is self.owner.bulk_rename
        if not bulk and key not in (('ide', 'ide.workspace'), ('git', 'git.workspace')):
            return None
        source = qt.QMainWindow(page)
        source.hide()
        source.menuBar().setNativeMenuBar(False)
        if bulk:
            from .bulk_rename.menus import build_menus
            source.header_menus = build_menus(source, page)
        elif key == ('ide', 'ide.workspace'):
            menu = source.menuBar().addMenu('Project')
            menu.addAction('Open Project…', lambda: page.register_project(page.workspace))
            menu.addAction('Reopen Project…', lambda: page.reopen(page.workspace))
        else:
            menu = source.menuBar().addMenu('Repository')
            menu.addAction('Open Repository…', lambda: page._repository_menu(page.workspace))
        self.sources[page] = source
        return source
