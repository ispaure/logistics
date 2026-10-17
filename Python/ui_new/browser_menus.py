"""Browser header commands reuse the browser's selection and toolbar owners."""
from pathlib import Path
from commonUtils.ui import pyside as qt


class BrowserMenus(qt.QObject):
    def __init__(self, view):
        super().__init__(view)
        self.view, self.browser = view, view.file_browser
        self.rules = []
        bar = view.menuBar()
        bar.setNativeMenuBar(False)
        self.menus = {name: bar.addMenu(name) for name in ('File', 'Edit', 'View', 'Navigate', 'Index', 'Help')}
        self.add('File', 'Open Folder…', self.open_folder)
        self.add('File', 'New Browser Tab', self.new_tab)
        self.add('File', 'Close Browser Tab', self.close_tab)
        from features.rclone.ui.remote_browser import choose_remote
        self.add('File', 'Open Remote…', lambda: choose_remote(self.view))
        self.menus['File'].addSeparator()
        self.selection = self.menus['File'].addMenu('Selected Items')
        self.selection.aboutToShow.connect(self.selection_menu)
        self.selection_source = None
        self.copy = self.add('Edit', 'Copy Selected Items', lambda: self.browser.file_actions.copy(self.browser.selected_objects()))
        self.cut = self.add('Edit', 'Cut Selected Items', lambda: self.browser.file_actions.copy(self.browser.selected_objects(), move=True))
        self.paste = self.add('Edit', 'Paste into Current Folder', self.browser.file_actions.paste_current)
        self.menus['Edit'].addSeparator()
        self.rename = self.add('Edit', 'Rename Selected Item', self.browser.file_actions.rename_selected)
        self.trash = self.add('Edit', 'Move Selected Items to Trash / Recycle Bin…',
                              lambda: self.browser.file_actions.delete(self.browser.selected_objects()))
        self.mode_actions = []
        for index, title in enumerate(('List', 'Tiles', 'Columns', 'Treemap', 'Radial')):
            action = self.add('View', title, lambda index=index: self.browser.view_selector.setCurrentIndex(index))
            action.setCheckable(True)
            self.mode_actions.append(action)
        self.menus['View'].addSeparator()
        self.preview = self.add('View', 'Selection Preview', self.browser.preview_toggle.toggle)
        self.preview.setCheckable(True)
        self.search = self.add('View', 'Search Files and Folders', self.browser.search_button.toggle)
        self.search.setCheckable(True)
        for title, button in (('Back', self.browser.navigation.back), ('Forward', self.browser.navigation.forward),
                              ('Parent Folder', self.browser.navigation.up)):
            action = self.add('Navigate', title, button.click)
            self.rules.append((action, button))
        self.add('Navigate', 'Home Folder', lambda: self.view._open_location(Path.home()))
        self.add('Index', 'Refresh Index', self.browser.refresh)
        self.pause = self.add('Index', 'Pause Indexing', self.browser._toggle_index_pause)
        self.add('Index', 'Index Details…', self.browser.show_index_details)
        self.add('Help', 'File Browser Guide', self.guide)
        for menu in self.menus.values():
            menu.aboutToShow.connect(self.update)

    def add(self, menu, title, callback):
        action = self.menus[menu].addAction(title)
        action.triggered.connect(lambda checked=False: self.browser._run(callback))
        return action

    def guide(self):
        from services.documentation import open_guide
        open_guide(Path(__file__).resolve().parents[2] / 'docs/user/files-and-documents.md',
                      parent=self.view.window(), detached=True, allow_new_tabs=False)

    def workspace(self):
        parent = self.view.parentWidget()
        while parent is not None:
            workspace = getattr(parent, 'workspace', None)
            if workspace is not None and hasattr(workspace, 'add_view'):
                return workspace
            parent = parent.parentWidget()

    def open_folder(self):
        folder = qt.QFileDialog.getExistingDirectory(self.view, 'Open Folder', str(self.browser.navigation.directory))
        if folder:
            self.view._open_location(folder)

    def new_tab(self):
        workspace = self.workspace()
        if workspace is not None:
            workspace.add_view(self.browser.navigation.directory)

    def close_tab(self):
        workspace = self.workspace()
        if workspace is not None:
            workspace.close_active()

    def selection_menu(self):
        self.selection.clear()
        if self.selection_source is not None:
            self.selection_source.deleteLater()
        objects = self.browser.selected_objects()
        index = self.browser.model.index(str(objects[0].path)) if objects else qt.QModelIndex()
        self.selection_source = self.browser.context_menu_for(index, directory=self.browser.navigation.directory)
        if self.selection_source is not None:
            for action in self.selection_source.actions():
                self.selection.addAction(action)

    def update(self):
        for action, button in self.rules:
            action.setEnabled(button.isEnabled())
        for index, action in enumerate(self.mode_actions):
            action.setChecked(self.browser.view_selector.currentIndex() == index)
            action.setEnabled(self.browser.view_selector.buttons[index].isEnabled())
        self.preview.setChecked(self.browser.preview_toggle.isChecked())
        self.search.setChecked(self.browser.search_button.isChecked())
        self.pause.setText('Resume Indexing' if self.browser._index_paused else 'Pause Indexing')
        self.selection.setEnabled(bool(self.browser.selected_objects()))
        from commonUtils.ui.file_browser.file_actions import clipboard_files
        selected = self.browser.selected_objects()
        idle = not self.browser.file_actions.busy and not self.browser.stopping
        self.copy.setEnabled(bool(selected) and not self.browser.stopping)
        self.cut.setEnabled(bool(selected) and idle)
        self.paste.setEnabled(idle and bool(clipboard_files()[0]))
        self.rename.setEnabled(len(selected) == 1 and idle)
        self.trash.setEnabled(bool(selected) and idle)
        workspace = self.workspace()
        self.menus['File'].actions()[1].setEnabled(workspace is not None and workspace.allow_new_tabs)
        self.menus['File'].actions()[2].setEnabled(workspace is not None and workspace.close_action.isEnabled())
