"""Retained readers/editors hosted in the main window, with optional detachment."""
from contextlib import contextmanager
from dataclasses import replace
import sys
from commonUtils.ui import pyside as qt
from commonUtils.ui.document_host import show_document, register_document_host, document_is_open, close_document, request_document_close, CloseOutcome
from shiboken6 import isValid
from commonUtils.ui.workspace import Workspace
from commonUtils.ui.workspace_policy import WorkspacePolicy


class DocumentPane(qt.QWidget):
    """Keep the original reader/editor as the authority for closing its document."""
    def __init__(self, window):
        super().__init__()
        self.document = window
        self.view_title = window.windowTitle()
        self.setMinimumSize(320, 220)
        layout = qt.QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.workspace_controls = getattr(window, 'workspace_controls', None)
        if self.workspace_controls is None:
            self.workspace_controls_widget = qt.QWidget(self)
            self.workspace_controls = qt.QHBoxLayout(self.workspace_controls_widget)
            self.workspace_controls.setContentsMargins(4, 0, 4, 0)
            self.workspace_controls.addStretch()
            self.workspace_controls_widget.hide()
            if (sys.platform != 'darwin' and isinstance(window, qt.QMainWindow) and window.menuBar().actions()
                    and window.menuBar().cornerWidget() is None):
                window.menuBar().setCornerWidget(self.workspace_controls_widget)
            else:
                layout.addWidget(self.workspace_controls_widget)
        window.setAttribute(qt.Qt.WidgetAttribute.WA_QuitOnClose, False)
        window.setParent(self, qt.Qt.WindowType.Widget)
        layout.addWidget(window)
        window.show()

    def prepare_close(self):
        close_document(self.document)
        # DocumentsPage retires the dock after the original close handler accepts
        # or hides the document. A veto or running worker retains its owner.
        return False


class DocumentWorkspace(Workspace):
    def __init__(self, page):
        self.page = page
        super().__init__(DocumentPane, page, dock_group=page,
                         policy=WorkspacePolicy(show_single_tab_in_detached=False,
                                                detached_title='Documents: {title}'),
                         new_view=page.new_document_menu)
        self.close_action.setEnabled(False)  # Keep each reader/editor's own close shortcut.
        self._drop_target.widget().setText('Open a document with +, or drop a detached reader or editor here to bring it back.')


class DocumentsPage(qt.QWidget):
    changed = qt.Signal()
    idle = qt.Signal()

    def __init__(self, activate, parent=None):
        super().__init__(parent)
        self.activate = activate
        self.records = {}
        self._creation_workspace = None
        self._close_events = set()
        self.close_veto = False
        self.closing = False
        layout = qt.QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.workspace = DocumentWorkspace(self)
        layout.addWidget(self.workspace)

    @property
    def count(self):
        return sum(not record['closed'] for record in self.records.values())

    @property
    def attached_count(self):
        return sum(not record['closed'] and not record['detached'] for record in self.records.values())

    def document_entries(self):
        for dock in self.workspace.all_docks:
            window = dock.widget().document
            record = self.records[window]
            if not record['closed']:
                entries = getattr(window, 'document_entries', lambda: [(window.windowTitle(), None)])()
                for title, tab in entries:
                    yield window, title, tab, record['detached']

    def present(self, window, *, detached=False, allow_new_tabs=True):
        destination = self._creation_workspace or self.workspace
        record = self.records.get(window)
        if self._creation_workspace is None and record and record['detached'] and not record['closed']:
            dock = record['dock']
            dock.window().showNormal() if dock.window().isMinimized() else dock.window().show()
            dock.raise_(); dock.workspace._activate(dock); dock.window().raise_(); dock.window().activateWindow()
            return
        if record is None:
            record = dict(container=None, dock=None, flags=window.windowFlags(), native=None,
                          detached=False, closed=False, waiting=set())
            self.records[window] = record
            if isinstance(window, qt.QMainWindow):
                record['native'] = window.menuBar().isNativeMenuBar()
            window.installEventFilter(self)
            window.windowTitleChanged.connect(lambda title, view=window: self._title_changed(view, title))
            window.destroyed.connect(lambda obj=None, view=window: self._destroyed(view))
            for signal in (getattr(window, 'idle', None), getattr(window, 'closed', None)):
                if signal is not None:
                    signal.connect(self.idle)
            if isinstance(window, qt.QDialog):
                window.finished.connect(lambda result, view=window: self._dialog_finished(view))
        if detached and record['dock'] is None:
            from commonUtils.ui.workspace_window import WorkspaceWindow
            main = self.workspace
            policy = replace(main.policy, max_tabs=None if allow_new_tabs else 1)
            container = WorkspaceWindow(main, policy=policy, allow_new_tabs=allow_new_tabs,
                                        close_returns_tabs=allow_new_tabs)
            main.detached_windows.append(container)
            container.destroyed.connect(lambda: main.detached_windows.remove(container)
                                        if container in main.detached_windows else None)
            destination = container.workspace
            container.show()
        record['closed'] = False
        record['detached'] = destination.is_detached
        if not destination.is_detached:
            self.activate()
        if record['dock'] is None:
            if record['native'] is not None:
                window.menuBar().setNativeMenuBar(False)
                if sys.platform == "darwin":
                    window.menuBar().hide()
            pane = destination.add_view(window)
            dock = next(item for item in destination.docks if item.widget() is pane)
            record['container'], record['dock'] = pane, dock
            dock.tab_header.installEventFilter(self.workspace)
            dock.topLevelChanged.connect(lambda floating, view=window: self._docking_changed(view, floating))
            dock.owner_changed.connect(lambda owner, view=window: self._owner_changed(view, owner))
        elif record['dock'].workspace is not destination or record['dock'].isFloating():
            destination.adopt(record['dock'], force=True)
        record['dock'].show(); record['dock'].raise_()
        record['dock'].workspace._activate(record['dock'])
        window.show()
        from commonUtils.ui.workspace_menus import sync_native_menus
        sync_native_menus(record["dock"].window(), window)
        self.changed.emit()

    def _docking_changed(self, window, floating):
        if window in self.records:
            self.records[window]['detached'] = floating or self.records[window]['dock'].workspace.is_detached
            if not self.records[window]['detached'] and not self.closing and not self.records[window]['closed']:
                self.activate()
            self.changed.emit()

    def _owner_changed(self, window, owner):
        if window in self.records:
            self.records[window]['detached'] = owner.is_detached
            self.changed.emit()

    def new_document_menu(self, workspace):
        """Bind the existing launcher workflow to the button's owning container."""
        from features import registry
        from features.contributions import DocumentLauncherContribution
        from commonUtils.ui.markdown.window import open_markdown
        def open_markdown_file(parent):
            path, _ = qt.QFileDialog.getOpenFileName(parent, 'Open Markdown', '',
                                                    'Markdown (*.md *.markdown);;All files (*)')
            return open_markdown(path, allow_edit=True) if path else None
        launchers = [DocumentLauncherContribution('markdown', 'Markdown Editor', open_markdown_file,
                     'markdown', 20, lambda parent: open_markdown(None, allow_edit=True))]
        launchers.extend(entry.contribution for entry in registry.get_document_launchers())
        menu = qt.QMenu(workspace)
        for entry in sorted(launchers, key=lambda entry: entry.order):
            sub = menu.addMenu(entry.name)
            if entry.new_document is not None:
                sub.addAction('New', lambda callback=entry.new_document: self.launch_document(workspace, callback))
            sub.addAction('Open…', lambda callback=entry.open_document: self.launch_document(workspace, callback))
        menu.exec(qt.QCursor.pos())
        menu.deleteLater()

    def launch_document(self, workspace, callback):
        if self.closing or not isValid(workspace) or workspace._closing:
            return None
        with self.creation_scope(workspace):
            parent = workspace.window()
            # Dialogs belong to their originating window; shared editor services
            # outlive an emptied detached container and stay with this page.
            parent.document_service_owner = self
            return callback(parent)

    @contextmanager
    def creation_scope(self, origin):
        if isinstance(origin, Workspace):
            workspace = origin
        else:
            record = self.records.get(origin)
            dock = record['dock'] if record else None
            workspace = dock.workspace if dock is not None and isValid(dock) else self.workspace
        if not isValid(workspace) or workspace._closing:
            workspace = self.workspace
        previous = self._creation_workspace
        self._creation_workspace = workspace
        try:
            yield
        finally:
            self._creation_workspace = previous

    def _title_changed(self, window, title):
        record = self.records.get(window)
        if record and record['dock'] is not None:
            record['dock'].setWindowTitle(title)
        self.changed.emit()

    def _unembed(self, window):
        record = self.records.get(window)
        if record is None or record['dock'] is None:
            return
        dock = record['dock']
        if isValid(window):
            # Closed readers stay as hidden children while workers retire. Restoring
            # a native window/menu here races Cocoa's pending menu destruction.
            window.hide()
            window.setParent(self, qt.Qt.WindowType.Widget)
        record['container'] = record['dock'] = None
        dock.hide()
        if dock in dock.workspace.docks:
            dock.workspace.remove_view(dock)
        dock.deleteLater()

    def detach_current(self):
        self.workspace.detach_active()

    def attach(self, window):
        self.records[window]['detached'] = False
        self.present(window)

    def close_tab(self, index):
        attached = [dock for dock in self.workspace.docks if not dock.isFloating()]
        if 0 <= index < len(attached):
            attached[index].close()

    def document_close_finished(self, window, accepted):
        """A rejected close must not turn a subsequent docking hide into retirement."""
        if not accepted:
            self._close_events.discard(window)

    def eventFilter(self, watched, event):
        if watched in self.records:
            if event.type() == qt.QEvent.Type.Close:
                self._close_events.add(watched)
                qt.QTimer.singleShot(0, self, lambda view=watched: self._close_events.discard(view))
            elif event.type() == qt.QEvent.Type.Hide and watched in self._close_events:
                self.records[watched]['closed'] = True
                qt.QTimer.singleShot(0, self, lambda view=watched: self._retire(view))
        return super().eventFilter(watched, event)

    def _retire(self, window):
        if not isValid(self) or not isValid(self.workspace):
            return
        self._unembed(window)
        self.changed.emit()

    def _dialog_finished(self, window):
        if window in self.records:
            self.records[window]['closed'] = True
            qt.QTimer.singleShot(0, self, lambda view=window: self._retire(view))
            self.idle.emit()

    def _destroyed(self, window):
        record = self.records.get(window)
        self._close_events.discard(window)
        if not isValid(self.workspace):
            self.records.pop(window, None)
            return
        if record:
            self._unembed(window)
            self.records.pop(window, None)
        self.changed.emit(); self.idle.emit()

    def prepare_close(self):
        ready = True
        self.close_veto = False
        for window in tuple(self.records):
            if not isValid(window):
                continue
            outcome = request_document_close(window)
            ready = ready and outcome is CloseOutcome.ACCEPTED
            self.close_veto |= outcome is CloseOutcome.VETOED
        return ready
