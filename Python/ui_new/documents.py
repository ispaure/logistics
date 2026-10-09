"""Retained readers/editors hosted in the main window, with optional detachment."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.document_host import show_document, register_document_host, document_is_open
from shiboken6 import isValid
from commonUtils.ui.workspace import Workspace, DockTabHeader


class DocumentPane(qt.QWidget):
    """Keep the original reader/editor as the authority for closing its document."""
    def __init__(self, window):
        super().__init__()
        self.document = window
        self.view_title = window.windowTitle()
        self.setMinimumSize(320, 220)
        layout = qt.QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        window.setParent(self, qt.Qt.WindowType.Widget)
        layout.addWidget(window)
        window.show()

    def prepare_close(self):
        self.document.close()
        # DocumentsPage retires the dock after the original close handler accepts
        # or hides the document. A veto or running worker retains its owner.
        return False


class DocumentWorkspace(Workspace):
    def __init__(self, page):
        self.page = page
        super().__init__(DocumentPane, page, allow_new_tabs=False, dock_group=page)
        self.close_action.setEnabled(False)  # Keep each reader/editor's own close shortcut.
        self._drop_target.widget().setText('Drag a reader or editor tab here to bring it back.')

    def eventFilter(self, watched, event):
        if (event.type() == qt.QEvent.Type.MouseMove and event.buttons() & qt.Qt.MouseButton.LeftButton
                and isinstance(watched, DockTabHeader) and watched.parentWidget().isFloating()):
            # Reveal the original docking area as a native floating window moves
            # over the main application, even when another destination is active.
            point = watched.mapToGlobal(event.position().toPoint())
            if self.page.window().frameGeometry().contains(point):
                self.page.activate()
        return super().eventFilter(watched, event)


class DocumentsPage(qt.QWidget):
    changed = qt.Signal()
    idle = qt.Signal()

    def __init__(self, activate, parent=None):
        super().__init__(parent)
        self.activate = activate
        self.records = {}
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
        for window, record in self.records.items():
            if not record['closed']:
                entries = getattr(window, 'document_entries', lambda: [(window.windowTitle(), None)])()
                for title, tab in entries:
                    yield window, title, tab, record['detached']

    def present(self, window):
        record = self.records.get(window)
        if record and record['detached'] and not record['closed']:
            self.activate()  # Make its native return area available too.
            dock = record['dock']
            dock.showNormal() if dock.isMinimized() else dock.show()
            dock.raise_(); dock.activateWindow()
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
            for signal in (getattr(window, 'idle', None), getattr(window, 'closed', None),
                           getattr(getattr(window, 'reader', None), 'idle', None)):
                if signal is not None:
                    signal.connect(self.idle)
            if isinstance(window, qt.QDialog):
                window.finished.connect(lambda result, view=window: self._dialog_finished(view))
        record['closed'] = False
        record['detached'] = False
        self.activate()
        if record['dock'] is None:
            if record['native'] is not None:
                window.menuBar().setNativeMenuBar(False)
            pane = self.workspace.add_view(window)
            dock = next(item for item in self.workspace.docks if item.widget() is pane)
            record['container'], record['dock'] = pane, dock
            dock.tab_header.installEventFilter(self.workspace)
            dock.topLevelChanged.connect(lambda floating, view=window: self._docking_changed(view, floating))
        elif record['dock'].isFloating():
            self.workspace.adopt(record['dock'])
        record['dock'].show(); record['dock'].raise_()
        self.workspace._activate(record['dock'])
        window.show()
        self.changed.emit()

    def _docking_changed(self, window, floating):
        if window in self.records:
            self.records[window]['detached'] = floating
            if not floating and not self.closing and not self.records[window]['closed']:
                self.activate()
            self.changed.emit()

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
            window.setParent(None, record['flags'])
            if record['native'] is not None:
                window.menuBar().setNativeMenuBar(record['native'])
        record['container'] = record['dock'] = None
        dock.hide()
        if dock in self.workspace.docks:
            self.workspace.remove_view(dock)
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
            if not getattr(window, 'prepare_close', lambda: True)():
                ready = False
                if hasattr(window, 'documents') and not window.task.busy and not window._close_pending:
                    self.close_veto = True
                continue
            accepted = window.close()
            # Comic readers hide immediately while their decode/cache workers retire.
            owners = [window, getattr(window, 'task', None), getattr(window, 'page_cache', None)]
            if not accepted and not self.records.get(window, {}).get('closed', True) and not any(getattr(owner, 'busy', False) for owner in owners):
                self.close_veto = True
                ready = False
            if any(getattr(owner, 'busy', False) for owner in owners):
                ready = False
                for operation in (getattr(window, 'operation', None), getattr(window, 'worker', None),
                                  getattr(getattr(window, 'page_cache', None), 'operation', None)):
                    if operation is not None and hasattr(operation, 'finished') and operation not in self.records[window]['waiting']:
                        self.records[window]['waiting'].add(operation)
                        operation.finished.connect(self.idle)
            if any(getattr(editor, 'busy', False) for editor in getattr(window, 'metadata_windows', ())):
                ready = False
        return ready
