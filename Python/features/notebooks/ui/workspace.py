"""Desktop Notebooks page and .rmdoc activation using the same native-ink model."""
from pathlib import Path

from commonUtils.ui import pyside as qt
from commonUtils.persistence.atomic import atomic_write_bytes
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from ..notebook import Notebook, MAX_ARCHIVE
from ..workspace import Repository, Editor
from ..bridge import Bridge, update_script
from ..canvas import editor_html

_windows = []


class CanvasPage(QWebEnginePage):
    command = qt.Signal(object)

    def __init__(self, parent, bridge):
        super().__init__(parent)
        self.bridge = bridge
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)

    def javaScriptConsoleMessage(self, level, message, line, source):
        # Unlike custom-scheme navigation, this also works for queued commands
        # after Chromium's transient user activation has expired.
        action = self.bridge.command(message)
        if action is not None:
            qt.QTimer.singleShot(0, lambda: self.command.emit(action))
            return
        super().javaScriptConsoleMessage(level, message, line, source)

    def acceptNavigationRequest(self, url, kind, main):
        action = self.bridge.command(url.toString())
        if action is not None:
            # Leave Chromium's navigation callback before changing widgets.
            qt.QTimer.singleShot(0, lambda: self.command.emit(action))
            return False
        return url.scheme() in ('data', 'about')


class NotebookWorkspace(qt.QWidget):
    def __init__(self, parent=None, *, root=None):
        super().__init__(parent)
        location = root or Path(qt.QStandardPaths.writableLocation(qt.QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'notebooks'
        self.repository = Repository(location)
        self.editor = None
        self.web = None
        self.busy = False
        self.layout = qt.QVBoxLayout(self)
        self.library()

    def clear(self):
        self.web = None
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def library(self):
        self.clear()
        title = qt.QLabel('Notebooks')
        self.layout.addWidget(title)
        self.layout.addWidget(qt.QLabel('Editable reMarkable ink. Imported originals stay untouched.'))
        actions = qt.QHBoxLayout()
        # Place the row in a widget so clear() owns its complete lifetime.
        row = qt.QWidget()
        row.setLayout(actions)
        self.layout.addWidget(row)
        for label, callback in [('New notebook', self.new), ('Open .rmdoc…', self.choose_import)]:
            button = qt.QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        self.status = qt.QLabel('')
        self.layout.addWidget(self.status)
        listing = qt.QWidget()
        listing_layout = qt.QVBoxLayout(listing)
        for key, name in self.repository.list():
            button = qt.QPushButton(name)
            button.clicked.connect(lambda checked=False, key=key: self.reopen(key))
            listing_layout.addWidget(button)
        listing_layout.addStretch()
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(listing)
        self.layout.addWidget(scroll)

    def new(self):
        try:
            book = Notebook.new()
            key = self.repository.create(book)
            self.open(book, key)
        except Exception as error:
            self.status.setText(str(error))

    def choose_import(self):
        path, _ = qt.QFileDialog.getOpenFileName(self, 'Open reMarkable notebook', '', 'reMarkable notebook (*.rmdoc)')
        if path:
            self.import_path(path)

    def import_path(self, path):
        try:
            with Path(path).open('rb') as stream:
                book = Notebook.read(stream.read(MAX_ARCHIVE + 1))
            key = self.repository.create(book)
            self.open(book, key)
        except Exception as error:
            self.library()
            self.status.setText(str(error))

    def reopen(self, key):
        try:
            self.open(self.repository.open(key), key)
        except Exception as error:
            self.status.setText(str(error))

    def open(self, book, key):
        self.key = key
        self.editor = Editor(book, lambda book: self.repository.save(key, book))
        self.bridge = Bridge()
        self.clear()
        self.web = QWebEngineView(self)
        page = CanvasPage(self.web, self.bridge)
        self.web.setPage(page)
        page.command.connect(lambda action: self.deliver(page, action))
        self.web.setHtml(editor_html(self.editor.state(), self.bridge.url, console_bridge=True))
        self.layout.addWidget(self.web)

    def deliver(self, page, action):
        # A queued event from a retired canvas must not edit the next notebook.
        if self.web is not None and self.web.page() is page:
            self.perform(action)

    def perform(self, action):
        if self.busy:
            return
        self.busy = True
        error = ''
        try:
            op = action['op']
            if op == 'library':
                self.library()
                return
            if op == 'export':
                path, _ = qt.QFileDialog.getSaveFileName(self, 'Export notebook copy',
                    self.editor.notebook.name + '.rmdoc', 'reMarkable notebook (*.rmdoc)')
                if path:
                    if not path.lower().endswith('.rmdoc'):
                        path += '.rmdoc'
                    atomic_write_bytes(path, self.editor.notebook.to_bytes())
                else:
                    error = 'Export cancelled. Your notebook is saved on this device.'
            elif op == 'transfer':
                choices = [(key, name) for key, name in self.repository.list() if key != self.key]
                labels = [f'{name} ({key[:6]})' for key, name in choices]
                if not choices:
                    error = 'Create or import a second notebook first.'
                else:
                    label, accepted = qt.QInputDialog.getItem(self, 'Copy page', 'Destination notebook', labels, 0, False)
                    if accepted:
                        key = choices[labels.index(label)][0]
                        target = self.repository.open(key)
                        target.copy_page(self.editor.notebook, self.editor.index)
                        self.repository.save(key, target)
                        error = 'Page copied. The source page is unchanged.'
            else:
                self.editor.apply(action)
        except Exception as failure:
            error = str(failure)
        finally:
            self.busy = False
        self.web.page().runJavaScript(update_script(self.editor.state(), error))


def open_workspace(parent=None, path=None):
    window = qt.QMainWindow(parent)
    window.setWindowTitle('Notebooks')
    panel = NotebookWorkspace(window)
    window.setCentralWidget(panel)
    window.resize(1000, 850)
    window.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
    _windows.append(window)
    window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
    window.show()
    if path is not None:
        panel.import_path(path)
    return window
