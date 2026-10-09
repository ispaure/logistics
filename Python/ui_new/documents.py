"""Retained readers/editors hosted in the main window, with optional detachment."""
import weakref
from commonUtils.ui import pyside as qt
from shiboken6 import isValid


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
        layout = qt.QVBoxLayout(self)
        self.tabs = qt.QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        controls = qt.QWidget()
        row = qt.QHBoxLayout(controls); row.setContentsMargins(4, 0, 4, 0)
        self.detach_button = qt.QPushButton('Detach')
        self.detach_button.clicked.connect(self.detach_current)
        self.attach_button = qt.QToolButton()
        self.attach_button.setText('Bring back')
        self.attach_button.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.attach_menu = qt.QMenu(self.attach_button)
        self.attach_menu.aboutToShow.connect(self._attach_menu)
        self.attach_button.setMenu(self.attach_menu)
        row.addWidget(self.detach_button); row.addWidget(self.attach_button)
        self.tabs.setCornerWidget(controls)
        self.tabs.currentChanged.connect(self._update_controls)
        layout.addWidget(self.tabs, 1)
        self.empty = qt.QLabel('Readers and editors open here. Detached documents can be brought back into this window.')
        self.empty.setWordWrap(True)
        self.empty.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty, 1)
        self._update_controls()

    @property
    def count(self):
        return sum(not record['closed'] for record in self.records.values())

    def present(self, window):
        record = self.records.get(window)
        if record and record['detached'] and not record['closed']:
            window.showNormal() if window.isMinimized() else window.show()
            window.raise_(); window.activateWindow()
            return
        if record is None:
            record = dict(container=None, flags=window.windowFlags(), native=None, detached=False, closed=False, waiting=set())
            self.records[window] = record
            if isinstance(window, qt.QMainWindow):
                record['native'] = window.menuBar().isNativeMenuBar()
            window.installEventFilter(self)
            window.windowTitleChanged.connect(lambda title, view=window: self._title_changed(view, title))
            window.destroyed.connect(lambda obj=None, view=window: self._destroyed(view))
            signals = [getattr(window, 'idle', None), getattr(window, 'closed', None),
                       getattr(getattr(window, 'reader', None), 'idle', None)]
            for signal in signals:
                if signal is not None:
                    signal.connect(self.idle)
            if isinstance(window, qt.QDialog):
                window.finished.connect(lambda result, view=window: self._dialog_finished(view))
        record['closed'] = False
        record['detached'] = False
        if record['container'] is None:
            container = qt.QWidget()
            layout = qt.QVBoxLayout(container); layout.setContentsMargins(0, 0, 0, 0)
            window.setParent(container, qt.Qt.WindowType.Widget)
            if record['native'] is not None:
                window.menuBar().setNativeMenuBar(False)
            layout.addWidget(window)
            record['container'] = container
            self.tabs.addTab(container, window.windowTitle())
        self.tabs.setCurrentWidget(record['container'])
        window.show()
        self.activate()
        self._update_controls()
        self.changed.emit()

    def _title_changed(self, window, title):
        record = self.records.get(window)
        if record and record['container'] is not None:
            self.tabs.setTabText(self.tabs.indexOf(record['container']), title)

    def _unembed(self, window):
        record = self.records.get(window)
        if record is None or record['container'] is None:
            return
        container = record['container']
        self.tabs.removeTab(self.tabs.indexOf(container))
        if isValid(window):
            window.setParent(None, record['flags'])
            if record['native'] is not None:
                window.menuBar().setNativeMenuBar(record['native'])
        record['container'] = None
        container.deleteLater()

    def detach_current(self):
        container = self.tabs.currentWidget()
        window = next((view for view, record in self.records.items() if record['container'] is container), None)
        if window is None:
            return
        self._unembed(window)
        self.records[window]['detached'] = True
        window.show(); window.raise_(); window.activateWindow()
        self._update_controls(); self.changed.emit()

    def attach(self, window):
        self.records[window]['detached'] = False
        self.present(window)

    def _attach_menu(self):
        self.attach_menu.clear()
        for window, record in self.records.items():
            if record['detached'] and not record['closed'] and isValid(window):
                self.attach_menu.addAction(window.windowTitle(), lambda view=window: self.attach(view))

    def close_tab(self, index):
        container = self.tabs.widget(index)
        window = next((view for view, record in self.records.items() if record['container'] is container), None)
        if window is not None:
            window.close()  # Its existing close handler protects dirty documents and workers.

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
        if not isValid(self) or not isValid(self.tabs):
            return
        self._unembed(window)
        self._update_controls(); self.changed.emit()

    def _dialog_finished(self, window):
        if window in self.records:
            self.records[window]['closed'] = True
            qt.QTimer.singleShot(0, self, lambda view=window: self._retire(view))
            self.idle.emit()

    def _destroyed(self, window):
        record = self.records.pop(window, None)
        self._close_events.discard(window)
        if not isValid(self.tabs):
            return
        if record and record['container'] is not None:
            self.tabs.removeTab(self.tabs.indexOf(record['container']))
            record['container'].deleteLater()
        self._update_controls(); self.changed.emit(); self.idle.emit()

    def _update_controls(self, *args):
        if not isValid(self.tabs):
            return
        self.detach_button.setEnabled(self.tabs.count() > 0)
        self.attach_button.setEnabled(any(record['detached'] and not record['closed'] for record in self.records.values()))
        self.empty.setVisible(self.tabs.count() == 0)

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
            window.close()
            # Comic readers hide immediately while their decode/cache workers retire.
            owners = [window, getattr(window, 'task', None), getattr(window, 'page_cache', None)]
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


def show_document(window):
    app = qt.QApplication.instance()
    reference = getattr(app, '_logistics_document_host', None)
    host = reference() if reference else None
    if host is not None and isValid(host) and host.window().isVisible() and not host.closing:
        host.present(window)
    else:
        window.showNormal() if window.isMinimized() else window.show()
        window.raise_(); window.activateWindow()
    return window


def register_document_host(host):
    qt.QApplication.instance()._logistics_document_host = weakref.ref(host)


def document_is_open(window):
    reference = getattr(qt.QApplication.instance(), '_logistics_document_host', None)
    host = reference() if reference else None
    if host is not None and isValid(host) and window in host.records:
        return not host.records[window]['closed']
    return isValid(window) and window.isVisible()
