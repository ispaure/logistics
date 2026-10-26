"""Desktop Notebooks page and .rmdoc activation using the same native-ink model."""
from pathlib import Path

from commonUtils.ui import pyside as qt
from services.documents.storage import export_local_document
from PySide6 import QtQuick, QtQuickWidgets
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from ..notebook import Notebook, MAX_ARCHIVE
from ..workspace import Repository, Editor
from ..bridge import Bridge, update_script
from ..canvas import editor_html

# Register Quick wrapper types before WebEngine creates internal objects.
# PySide6 6.12 can otherwise crash while application event filters wrap them.
_WEBENGINE_TYPE_BINDINGS = (QtQuick, QtQuickWidgets)
_windows = []


class CanvasPage(QWebEnginePage):
    command = qt.Signal(object)

    def __init__(self, parent, bridge):
        profile = QWebEngineProfile()
        super().__init__(profile, parent)
        profile.setParent(self)
        self.private_profile = profile
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
    def __init__(self, parent=None, *, root=None, library=True):
        super().__init__(parent)
        location = root or Path(qt.QStandardPaths.writableLocation(qt.QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'notebooks'
        self.document_window = parent if isinstance(parent, qt.QMainWindow) else None
        self.repository_root = location
        self._repository = None
        self.document = None
        self.editor = None
        self.web = None
        self.busy = False
        self.layout = qt.QVBoxLayout(self)
        if library:
            self.library()

    @property
    def repository(self):
        if self._repository is None:
            self._repository = Repository(self.repository_root)
        return self._repository

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

    def open_resource(self, document):
        self.document = document
        self.open(document.book, document.key)

    def state(self):
        value = self.editor.state()
        if self.document is not None:
            if self.document.resource is None and self.document.recovery is None:
                value['save_status'] = 'Unsaved changes' if self.document.dirty else 'Not saved yet'
            else:
                value['save_status'] = 'Unsaved changes' if self.document.dirty else 'Saved'
            value['read_only'] = not self.document.writable
        return value

    def open(self, book, key):
        if self.document is not None and self.document.book is not book:
            self.document.close()
            self.document = None
        self.key = key
        if self.document_window is not None:
            self.document_window.setWindowTitle(book.name)
        self.editor = Editor(book, self.document.checkpoint if self.document else lambda book: self.repository.save(key, book))
        self.bridge = Bridge()
        self.clear()
        self.web = QWebEngineView(self)
        page = CanvasPage(self.web, self.bridge)
        self.web.setPage(page)
        page.command.connect(lambda action: self.deliver(page, action))
        self.web.setHtml(editor_html(self.state(), self.bridge.url, console_bridge=True))
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.addWidget(self.web)
        from commonUtils.ui.tasks.operation_progress import OperationProgress
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self.saved)
        self.layout.addWidget(self.operation)

    def deliver(self, page, action):
        # A queued event from a retired canvas must not edit the next notebook.
        if self.web is not None and self.web.page() is page:
            self.perform(action)

    def perform(self, action):
        if self.busy:
            return
        if action['op'] in {'save', 'save-as'}:
            return self.save_document(save_as=action['op'] == 'save-as')
        self.busy = True
        error = ''
        try:
            op = action['op']
            if op == 'library':
                from commonUtils.ui.document_host import current_document_host
                host = current_document_host()
                if host is not None:
                    self.web.page().runJavaScript(update_script(self.state(), ''))
                    host.activate()
                else:
                    self.library()
                return
            if op == 'export':
                if not self.confirm_export():
                    self.web.page().runJavaScript(update_script(self.state(), 'Export cancelled.'))
                    return
                path, _ = qt.QFileDialog.getSaveFileName(self, 'Export notebook copy',
                    self.editor.notebook.name + '.rmdoc', 'reMarkable notebook (*.rmdoc)')
                if path:
                    if not path.lower().endswith('.rmdoc'):
                        path += '.rmdoc'
                        # The native picker confirmed the entered name, which
                        # may differ from this format-suffixed destination.
                        if Path(path).exists() and qt.QMessageBox.question(self, 'Replace notebook copy?',
                                'The export destination already exists. Replace it?',
                                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                                qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Yes:
                            self.web.page().runJavaScript(update_script(self.state(), 'Export cancelled.'))
                            return
                    export_local_document(path, self.editor.notebook.to_bytes(),
                                          max_bytes=MAX_ARCHIVE, validate=Notebook.read)
                else:
                    error = 'Export cancelled. Your notebook is saved on this device.'
            elif op == 'transfer':
                if not self.confirm_export():
                    self.web.page().runJavaScript(update_script(self.state(), 'Copy cancelled.'))
                    return
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
        if self.document_window is not None:
            self.document_window.setWindowTitle(self.editor.notebook.name)
        self.web.page().runJavaScript(update_script(self.state(), error))

    def confirm_export(self):
        if self.document is None or self.document.resource is None or self.document.resource.policy.persistent:
            return True
        return qt.QMessageBox.question(self, 'Export to unencrypted storage?',
            'This creates a decrypted copy outside private storage. Continue?',
            qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
            qt.QMessageBox.StandardButton.Cancel) == qt.QMessageBox.StandardButton.Yes

    def save_document(self, *, save_as=False):
        if self.busy:
            return False
        from services.documents.storage import DocumentResource, DocumentPolicy
        from services.documents.ui.editors import choose_editor_resource
        from ..storage import NotebookDocument
        document = self.document
        if not save_as and document is not None and document.resource is not None:
            self._pending_choice = None
            work = lambda cancelled: document.save(cancelled=cancelled)
        else:
            current = document.resource.provider if document and document.resource else None
            choice = choose_editor_resource(self, 'save', current,
                name=self.editor.notebook.name + '.rmdoc', extensions=('.rmdoc',))
            if choice is None:
                self.web.page().runJavaScript(update_script(self.state(), 'Save As cancelled.'))
                return False
            if document and document.resource and document.resource.policy.confirm_plaintext(DocumentPolicy.for_provider(choice.provider)):
                if not self.confirm_export():
                    choice.close()
                    self.web.page().runJavaScript(update_script(self.state(), 'Save As cancelled.'))
                    return False
            self._pending_choice = choice
            def work(cancelled):
                data = self.editor.notebook.to_bytes()
                DocumentResource.publish(choice.provider, choice.path, data, max_bytes=MAX_ARCHIVE, validate=Notebook.read, cancelled=cancelled)
                resource = DocumentResource(choice.provider, choice.path, max_bytes=MAX_ARCHIVE)
                try:
                    resource.read()
                    recovery = self.repository if resource.policy.persistent else None
                    return NotebookDocument(self.editor.notebook, resource=resource, recovery=recovery)
                except Exception:
                    resource.close()
                    raise
        self.busy = True
        self.operation.start(lambda report, cancelled: work(cancelled), message='Saving notebook…')
        return True

    def saved(self, document, error):
        choice, self._pending_choice = self._pending_choice, None
        if choice is not None:
            choice.close()
        if document is not None and not error:
            previous = self.document
            self.document = document
            self.key = document.key
            self.editor.checkpoint = document.checkpoint
            if previous is not None:
                previous.close()
        self.busy = False
        self.operation.hide()
        if self.web is not None:
            self.web.page().runJavaScript(update_script(self.state(), error or ''))
        if self.document_window is not None:
            if self.document is not None and self.document.resource is not None:
                from services.documents.ui.private_views import protect_private_view
                protect_private_view(self.document_window, self.document.resource.provider)
            if not error and getattr(self.document_window, 'pending_close', False):
                self.document_window.close()

    def dispose(self):
        if self.document is not None:
            self.document.close()
            self.document = None
        self.editor = None
        self.clear()


class NotebookWindow(qt.QMainWindow):
    pending_close = False

    def resource_provider(self):
        document = self.centralWidget().document
        return document.resource.provider if document and document.resource else None

    def prepare_credential_lock(self):
        panel = self.centralWidget()
        if panel.busy:
            return False
        if panel.document and panel.document.dirty:
            from services.documents.ui.private_views import resolve_private_edits_before_lock
            return resolve_private_edits_before_lock(self, panel.save_document)
        return True

    def retire_private_content(self):
        self.centralWidget().dispose()

    def closeEvent(self, event):
        panel = self.centralWidget()
        if panel.busy:
            event.ignore()
            return
        if panel.document and panel.document.dirty:
            answer = qt.QMessageBox.question(self, 'Unsaved notebook changes',
                'Save changes before closing?', qt.QMessageBox.StandardButton.Save |
                qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel)
            if answer == qt.QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == qt.QMessageBox.StandardButton.Save:
                self.pending_close = panel.save_document()
                event.ignore()
                return
        panel.dispose()
        event.accept()


def open_workspace(parent=None, path=None, *, resource=None, document=None):
    if path is not None and resource is None and document is None:
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.storage import DocumentResource
        path = Path(path).absolute()
        resource = DocumentResource(LocalFiles(path.parent), path.name, max_bytes=MAX_ARCHIVE)
    window = NotebookWindow(parent)
    window.setWindowTitle('Notebook')
    panel = NotebookWorkspace(window, library=resource is None and document is None)
    window.setCentralWidget(panel)
    window.resize(1000, 850)
    window.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
    _windows.append(window)
    window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
    try:
        if resource is not None:
            from ..storage import NotebookDocument
            book = Notebook.read(resource.read())
            document = NotebookDocument(book, resource=resource,
                                        recovery=panel.repository if resource.policy.persistent else None)
        if document is not None:
            if document.resource is not None and document.resource.policy.persistent and document.recovery is None:
                document.recovery = panel.repository
                document.key = panel.repository.create(document.book)
            panel.open_resource(document)
            if document.resource is not None:
                from services.documents.ui.private_views import protect_private_view
                protect_private_view(window, document.resource.provider)
        elif path is not None:
            panel.import_path(path)
        from commonUtils.ui.document_host import show_document
        show_document(window)
    except BaseException:
        if document is not None:
            document.close()
        elif resource is not None:
            resource.close()
        panel.dispose()
        if window in _windows:
            _windows.remove(window)
        window.deleteLater()
        raise
    return window
