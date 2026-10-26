"""Notebook commands published through the shared desktop document menu host."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.document_host import close_document, document_creation_scope


class NotebookMenus:
    def __init__(self, window):
        self.window = window
        self.actions = {}
        self.menus = {name: window.menuBar().addMenu(name) for name in ('File', 'Edit', 'View', 'Page')}
        keys = qt.QKeySequence.StandardKey
        self.add('File', 'new', 'New Notebook', self.new, keys.New, document=False)
        self.add('File', 'open', 'Open Notebook…', self.open, keys.Open, document=False)
        self.menus['File'].addSeparator()
        self.add('File', 'save', 'Save', lambda: self.command('save'), keys.Save)
        self.add('File', 'save-as', 'Save As…', lambda: self.command('save-as'), keys.SaveAs)
        self.add('File', 'export', 'Export Copy…', lambda: self.command('export'))
        self.add('File', 'rename', 'Rename Notebook…', self.rename)
        self.menus['File'].addSeparator()
        self.add('File', 'close', 'Close Document', lambda: close_document(window), keys.Close, document=False)
        self.add('Edit', 'undo', 'Undo', lambda: self.command('undo'), keys.Undo)
        self.add('Edit', 'redo', 'Redo', lambda: self.command('redo'), keys.Redo)
        self.menus['Edit'].addSeparator()
        for key, title in [('ink', 'Draw'), ('erase', 'Eraser Type and Size…'), ('select', 'Select and Move')]:
            self.add('Edit', key, title, lambda key=key: self.ui(key))
        self.add('View', 'toolbar', 'Drawing Toolbar', lambda: self.ui('toolbar'), checkable=True)
        self.add('View', 'grayscale', 'Grayscale Preview', lambda: self.ui('grayscale'), checkable=True)
        self.add('View', 'finger', 'Draw with Finger', lambda: self.ui('finger'), checkable=True)
        zoom = self.menus['View'].addMenu('Zoom')
        zoom_in = [*qt.QKeySequence.keyBindings(keys.ZoomIn), qt.QKeySequence('Ctrl+='),
                   qt.QKeySequence('Ctrl+Shift+=')]
        self.add(zoom, 'zoom-in', 'Zoom In', lambda: self.ui('zoom-in'), zoom_in)
        self.add(zoom, 'zoom-out', 'Zoom Out', lambda: self.ui('zoom-out'), keys.ZoomOut)
        zoom.addSeparator()
        self.add(zoom, 'fit-page', 'Fit Page', lambda: self.ui('zoom', 'page'), 'Ctrl+0')
        for label, value in [('Fit Width', 'fit'), ('100%', '1'), ('150%', '1.5'), ('200%', '2')]:
            action = zoom.addAction(label)
            action.triggered.connect(lambda checked=False, value=value: self.ui('zoom', value))
        self.zoom_menu = zoom
        self.add('Page', 'pages-overview', 'Pages Overview…', lambda: self.ui('pagesOverview'))
        self.menus['Page'].addSeparator()
        for key, label, shortcut in [('prev', 'Previous Page', 'Alt+Left'), ('next', 'Next Page', 'Alt+Right'),
                                      ('add-page', 'Add Page', None), ('duplicate-page', 'Duplicate Page', None),
                                      ('delete-page', 'Delete Page…', None), ('move-earlier', 'Move Earlier', None),
                                      ('move-later', 'Move Later', None), ('transfer', 'Copy Page to Notebook…', None)]:
            self.add('Page', key, label, lambda key=key: self.page(key), shortcut)
        self.update(None)
        self.actions['toolbar'].setChecked(True)
        for menu in self.menus.values():
            menu.aboutToShow.connect(self.refresh)
        self.menus['View'].aboutToShow.connect(self.read_view)

    @property
    def panel(self):
        return self.window.centralWidget()

    def add(self, menu, key, label, callback, shortcut=None, *, checkable=False, document=True):
        parent = self.menus[menu] if isinstance(menu, str) else menu
        action = parent.addAction(label)
        action.setCheckable(checkable)
        action.setData(document)
        if shortcut is not None:
            if isinstance(shortcut, (tuple, list)):
                action.setShortcuts(list(dict.fromkeys(shortcut)))
            else:
                action.setShortcut(qt.QKeySequence(shortcut))
            action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.window.addAction(action)
        action.triggered.connect(lambda checked=False: callback())
        self.actions[key] = action

    def refresh(self):
        self.update(self.panel.state() if self.panel.editor is not None else None)

    def update(self, state):
        ready = state is not None and not self.panel.busy
        for action in self.actions.values():
            action.setEnabled(ready if action.data() else not self.panel.busy)
        self.zoom_menu.setEnabled(ready)
        if state is not None:
            for key, enabled in [('undo', state['undo']), ('redo', state['redo']),
                                 ('prev', state['index'] > 0), ('next', state['index'] + 1 < state['count']),
                                 ('move-earlier', state['index'] > 0), ('move-later', state['index'] + 1 < state['count']),
                                 ('delete-page', state['count'] > 1)]:
                self.actions[key].setEnabled(ready and enabled)

    def command(self, op, **fields):
        self.panel.request_command(dict(op=op, **fields))

    def ui(self, name, value=None):
        self.panel.request_ui(name, value)

    def read_view(self):
        if self.panel.web is not None:
            self.panel.web.page().runJavaScript('window.notebookViewState && window.notebookViewState()', self.view_state)

    def view_state(self, state):
        if isinstance(state, dict):
            for key in ('toolbar', 'grayscale', 'finger'):
                self.actions[key].setChecked(bool(state[key]))

    def new(self):
        from services.documents.ui.notebooks import new_notebook_document
        with document_creation_scope(self.window):
            new_notebook_document(self.window)

    def open(self):
        from .. import launch
        with document_creation_scope(self.window):
            launch(self.window)

    def rename(self):
        name, accepted = qt.QInputDialog.getText(self.window, 'Rename Notebook', 'Notebook name',
                                                text=self.panel.editor.notebook.name)
        if accepted:
            self.command('rename', name=name)

    def page(self, key):
        editor = self.panel.editor
        if key == 'delete-page':
            if qt.QMessageBox.question(self.window, 'Delete Page', 'Delete this page? Undo is available.',
                    qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                    qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Yes:
                return
        if key in ('prev', 'next'):
            self.command('page', index=editor.index + (-1 if key == 'prev' else 1))
        elif key in ('move-earlier', 'move-later'):
            self.command('move-page', index=editor.index + (-1 if key == 'move-earlier' else 1))
        else:
            self.command(key)
