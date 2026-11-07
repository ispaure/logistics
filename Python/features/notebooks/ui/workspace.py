"""Desktop Notebooks page and .rmdoc activation using the same native-ink model."""
import json
from pathlib import Path

from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.status_line import StatusLine
from services.documents.storage import export_local_document, read_local_bytes, local_document_resource
from PySide6 import QtQuick, QtQuickWidgets
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from ..notebook import Notebook, MAX_ARCHIVE
from ..recovery import Repository
from ..editor import Editor
from ..progress import notebook_progress_state, open_notebook_progress, page_location, restore_notebook_progress
from ..bridge import Bridge
from ..protocol import brush_color_script, document_state, save_status, stroke_script, update_script, validate_action
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
        self.progress = None
        self.web = None
        self.busy = False
        qt.QApplication.instance().paletteChanged.connect(self.refresh_appearance)
        self.layout = qt.QVBoxLayout(self)
        if library:
            self.library()

    @property
    def repository(self):
        if self.document is not None and self.document.recovery is not None:
            self._repository = self.document.recovery
        if self._repository is None:
            self._repository = Repository(self.repository_root)
        return self._repository

    def load_progress(self, book, key):
        from commonUtils.filesystem.storage import cache_directory

        resource = self.document.resource if self.document else None
        draft_path = self.repository_root / key / 'base.rmdoc' if resource is None and key else None
        return open_notebook_progress(book, cache_directory(create=False), resource=resource, draft_path=draft_path)

    def retire_progress(self):
        if self.progress is not None:
            self.progress.flush()
            self.progress.retire()
            self.progress = None

    def clear(self):
        self.retire_progress()
        if self.web is not None:
            self.web.page().bridge.retire()
        self.web = None
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def library(self):
        if not self.can_leave():
            return
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
        self.status = StatusLine()
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
        self.layout.addWidget(scroll, 1)
        self.layout.addWidget(self.status)

    def new(self):
        try:
            from .setup import choose_new_notebook
            book = choose_new_notebook(self)
            if book is None:
                return
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
            book = Notebook.read(read_local_bytes(path, max_bytes=MAX_ARCHIVE))
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
        if not self.can_leave():
            if document is not self.document:
                document.close()
            return
        self.document = document
        self.open(document.book, document.key)

    def can_leave(self):
        if getattr(self.editor, 'checkpoint_unconfirmed', False):
            qt.QMessageBox.warning(self, 'Notebook recovery is unconfirmed',
                                  'Your draft remains open. Use Save As before leaving it.')
            return False
        return True

    def state(self):
        value = document_state(self.editor, self.document)
        menus = getattr(self.document_window, 'notebook_menus', None)
        if menus is not None:
            menus.update(value)
        return value

    def save_status(self):
        return save_status(self.document)

    def acknowledge_stroke(self):
        # Share the queued-ink protocol without rebuilding or replaying the page.
        editor = self.editor
        menus = getattr(self.document_window, 'notebook_menus', None)
        if menus is not None:
            menus.update(dict(index=editor.index, count=len(editor.notebook.pages),
                              undo=bool(editor.undo), redo=bool(editor.redo)))
        self.web.page().runJavaScript(stroke_script(editor, self.document))

    def request_command(self, action):
        if self.web is not None:
            self.web.page().runJavaScript('window.notebookCommand && window.notebookCommand(' + json.dumps(action) + ')')

    def request_ui(self, name, value=None):
        if self.web is not None:
            self.web.page().runJavaScript('window.notebookUI && window.notebookUI(' + json.dumps(name) + ',' + json.dumps(value) + ')')

    def open(self, book, key):
        if not self.can_leave():
            return
        if self.document is not None and self.document.book is not book:
            self.document.close()
            self.document = None
        self.key = key
        if self.document_window is not None:
            self.document_window.setWindowTitle(book.name)
        self.editor = Editor(book, self.document.checkpoint if self.document else lambda book: self.repository.save(key, book))
        self.clear()
        self.progress, saved = self.load_progress(book, key)
        restore_notebook_progress(self.editor, saved)
        self.bridge = Bridge()
        self._position_sequence = -1
        self.web = QWebEngineView(self)
        page = CanvasPage(self.web, self.bridge)
        self.web.setPage(page)
        self.web.installEventFilter(self)
        page.command.connect(lambda action: self.deliver(page, action))
        page.loadFinished.connect(self.refresh_appearance)
        page.loadFinished.connect(self.install_gesture_filter)
        self.web.setHtml(editor_html(self.state(), self.bridge.url, console_bridge=True, desktop=True,
                                    stylesheet=self.appearance_stylesheet()))
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.addWidget(self.web, 1)
        from commonUtils.ui.tasks.operation_progress import OperationProgress
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self.saved)
        self.layout.addWidget(self.operation)

    def appearance_stylesheet(self):
        from services.appearance_palette import DARK, LIGHT
        palette = qt.QApplication.palette()
        role = qt.QPalette.ColorRole
        colors = {name: palette.color(value).name() for name, value in {
            'window': role.Window, 'surface': role.Base, 'alternate': role.AlternateBase,
            'text': role.Text, 'muted': role.PlaceholderText, 'border': role.Mid,
            'control_border': role.Mid,
            'accent': role.Link, 'hover': role.Midlight,
        }.items()}
        scheme = 'dark' if palette.color(role.Window).lightness() < 128 else 'light'
        colors['destructive'] = (DARK if scheme == 'dark' else LIGHT)['destructive']
        return ':root{color-scheme:' + scheme + ';' + ';'.join(
            '--' + name + ':' + value for name, value in colors.items()) + '}'

    def refresh_appearance(self, *_):
        if self.web is not None:
            self.web.page().runJavaScript('window.notebookAppearance && window.notebookAppearance('
                                         + json.dumps(self.appearance_stylesheet()) + ')')

    def install_gesture_filter(self, *_):
        if self.web is not None and self.web.focusProxy() is not None:
            self.web.focusProxy().installEventFilter(self)

    def eventFilter(self, receiver, event):
        if (event.type() == qt.QEvent.Type.NativeGesture and self.web is not None
                and isinstance(receiver, qt.QWidget)
                and (receiver is self.web or self.web.isAncestorOf(receiver))):
            gesture = event.gestureType()
            if gesture == qt.Qt.NativeGestureType.ZoomNativeGesture:
                point = self.web.mapFromGlobal(event.globalPosition().toPoint())
                self.web.page().runJavaScript('window.notebookNativeZoom && window.notebookNativeZoom('
                    + json.dumps([1 + event.value(), point.x(), point.y()])[1:-1] + ')')
                event.accept()
                return True
            if gesture in (qt.Qt.NativeGestureType.BeginNativeGesture, qt.Qt.NativeGestureType.EndNativeGesture):
                event.accept()
                return True
        return super().eventFilter(receiver, event)

    def deliver(self, page, action):
        # A queued event from a retired canvas must not edit the next notebook.
        if self.web is not None and self.web.page() is page:
            self.perform(action)

    def perform(self, action):
        if self.busy:
            return
        try:
            op = validate_action(action)
        except ValueError as failure:
            # The bridge consumed this envelope; release its JS queue even
            # when validation rejects it before dispatch or busy ownership.
            self.web.page().runJavaScript(update_script(self.state(), str(failure)))
            return
        if op == 'export':
            return self.export_document()
        if op in {'save', 'save-as'}:
            return self.save_document(save_as=op == 'save-as')
        self.busy = True
        error = ''
        previous_page = page_location(self.editor)
        try:
            if op == 'brush-color':
                self.editor.brush_colors[action['tool']] = action['color']
                page = self.web.page()
                self._position_sequence = page.bridge.sequence
                status = self.progress.save(notebook_progress_state(self.editor)) if self.progress is not None else None
                page.runJavaScript(brush_color_script(status))
                return
            if op == 'page-previews':
                from ..previews import page_previews
                rows = page_previews(self.editor.notebook, action['start'])
                self.web.page().runJavaScript('window.notebookPagePreviews(' + json.dumps(rows) + ')')
            elif op == 'library':
                from commonUtils.ui.document_host import current_document_host
                host = current_document_host()
                if host is not None:
                    self.web.page().runJavaScript(update_script(self.state(), ''))
                    host.activate()
                else:
                    self.library()
                return
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
        if op == 'stroke' and not error:
            self.acknowledge_stroke()
        else:
            script = update_script(self.state(), error)
            location = page_location(self.editor)
            progress = self.progress
            page = self.web.page()
            position_sequence = page.bridge.sequence
            if not error and progress is not None and location != previous_page:
                script += ';state.page_id === ' + json.dumps(location['page_id']) + ' && state.index === ' + str(location['index'])
                def displayed(result):
                    if (result is True and self.progress is progress and self.web is not None
                            and self.web.page() is page and position_sequence >= self._position_sequence):
                        self._position_sequence = position_sequence
                        if progress.save(notebook_progress_state(self.editor, location)) == 'write-failed':
                            page.runJavaScript("document.getElementById('status').textContent='Could not save the notebook page position.'")
                page.runJavaScript(script, displayed)
            else:
                page.runJavaScript(script)

    def export_document(self):
        """Keep archive encoding and publication off the UI event loop."""
        if not self.confirm_export():
            self.web.page().runJavaScript(update_script(self.state(), 'Export cancelled.'))
            return
        path, _ = qt.QFileDialog.getSaveFileName(self, 'Export notebook copy',
            self.editor.notebook.name + '.rmdoc', 'reMarkable notebook (*.rmdoc)')
        if not path:
            self.web.page().runJavaScript(update_script(self.state(), 'Export cancelled. Your notebook remains open.'))
            return
        if not path.lower().endswith('.rmdoc'):
            path += '.rmdoc'
            if Path(path).exists() and qt.QMessageBox.question(self, 'Replace notebook copy?',
                    'The export destination already exists. Replace it?',
                    qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                    qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Yes:
                self.web.page().runJavaScript(update_script(self.state(), 'Export cancelled.'))
                return
        book = self.editor.notebook
        self._pending_choice = None
        self._pending_canvas = self.bridge
        self._pending_operation = self.operation
        self.busy = True
        def work(report, cancelled):
            from commonUtils.runtime.operations import check_cancelled
            from ..remarkable_export import export_rmdoc
            check_cancelled(cancelled)
            data = export_rmdoc(book, cancelled=cancelled)
            export_local_document(path, data, max_bytes=MAX_ARCHIVE,
                                  validate=Notebook.read, cancelled=cancelled)
        self.operation.start(work, message='Exporting notebook…')

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
        canvas = self.bridge
        book = self.editor.notebook
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
            recovery = self.repository if DocumentPolicy.for_provider(choice.provider).persistent else None
            def work(cancelled):
                data = book.to_bytes()
                DocumentResource.publish(choice.provider, choice.path, data, max_bytes=MAX_ARCHIVE, validate=Notebook.read, cancelled=cancelled)
                resource = DocumentResource(choice.provider, choice.path, max_bytes=MAX_ARCHIVE)
                try:
                    resource.read()
                    return NotebookDocument(book, resource=resource, recovery=recovery)
                except Exception:
                    resource.close()
                    raise
        if canvas is not self.bridge or not canvas.active:
            if self._pending_choice is not None:
                self._pending_choice.close()
                self._pending_choice = None
            return False
        self._pending_canvas = canvas
        self._pending_operation = self.operation
        self.busy = True
        self.operation.start(lambda report, cancelled: work(cancelled), message='Saving notebook…')
        return True

    def saved(self, document, error):
        choice, self._pending_choice = self._pending_choice, None
        if choice is not None:
            choice.close()
        canvas = self._pending_canvas
        self._pending_operation.hide()
        if canvas is not self.bridge or not canvas.active:
            if document is not None:
                document.close()
            self.busy = False
            return
        if not error:
            self.editor.checkpoint_unconfirmed = False
        if document is not None and not error:
            previous = self.document
            self.retire_progress()
            self.document = document
            self.key = document.key
            self.editor.checkpoint = document.checkpoint
            self.progress, _ = self.load_progress(document.book, document.key)
            if self.progress is not None:
                self.progress.save(notebook_progress_state(self.editor))
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
        self.retire_progress()
        if self.document is not None:
            self.document.close()
            self.document = None
        self.editor = None
        self.clear()


class NotebookWindow(qt.QMainWindow):
    document_editor_id = 'rmdoc'
    document_editor_name = 'Notebook (.rmdoc)'
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
        if (getattr(getattr(panel, 'editor', None), 'checkpoint_unconfirmed', False)
                and not (panel.document and panel.document.dirty)):
            qt.QMessageBox.warning(self, 'Notebook recovery is unconfirmed',
                                  'Your draft remains open. Use Save As before closing it.')
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
            if answer == qt.QMessageBox.StandardButton.Discard:
                try:
                    panel.document.discard()
                except (OSError, ValueError, KeyError) as error:
                    event.ignore()
                    qt.QMessageBox.warning(self, 'Notebook could not close',
                        'Could not discard the changes. Your draft remains open. ' + str(error))
                    return
        panel.dispose()
        event.accept()


def open_workspace(parent=None, path=None, *, resource=None, document=None):
    if path is not None and resource is None and document is None:
        resource = local_document_resource(path, max_bytes=MAX_ARCHIVE)
    window = NotebookWindow(parent)
    window.setWindowTitle('Notebook')
    panel = NotebookWorkspace(window, library=resource is None and document is None)
    window.setCentralWidget(panel)
    from .menus import NotebookMenus
    window.notebook_menus = NotebookMenus(window)
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
