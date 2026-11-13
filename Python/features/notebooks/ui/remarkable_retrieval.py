"""Desktop Debug workflow for retrieving one native notebook over SSH."""
from pathlib import Path
import re

from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from ..remarkable_ssh import DEFAULT_HOST, DEFAULT_PORT, TABLET_USER, export_document, list_snapshot
from ..remarkable_store import TabletSnapshot
from .remarkable_browser import TabletBrowser

TITLE = 'Retrieve RMDOC from reMarkable Tablet'


class RetrievalDialog(qt.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.resize(820, 560)
        self.connected_endpoint = None
        self.choosing_destination = False
        self.connection_generation = 0
        self.restore_browse = None
        layout = qt.QVBoxLayout(self)
        hint = qt.QLabel('Connect the tablet by USB and leave it awake. OpenSSH handles any password prompt.')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        connection = qt.QHBoxLayout()
        self.host = qt.QLineEdit(DEFAULT_HOST)
        address_label = qt.QLabel('&Address')
        address_label.setBuddy(self.host)
        self.port = qt.QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(DEFAULT_PORT)
        port_label = qt.QLabel('&Port')
        port_label.setBuddy(self.port)
        self.connect_button = qt.QPushButton('Connect')
        self.connect_button.clicked.connect(self.connect_tablet)
        self.host.returnPressed.connect(self.connect_tablet)
        self.host.textChanged.connect(self.update_actions)
        self.port.valueChanged.connect(self.update_actions)
        connection.addWidget(address_label)
        connection.addWidget(self.host, 1)
        connection.addWidget(port_label)
        connection.addWidget(self.port)
        connection.addWidget(qt.QLabel(f'Username: {TABLET_USER}'))
        connection.addWidget(self.connect_button)
        layout.addLayout(connection)

        self.browser_layout = qt.QVBoxLayout()
        layout.addLayout(self.browser_layout, 1)
        self.browser = None
        self.install_snapshot(TabletSnapshot.from_metadata({}))
        self.progress = OperationProgress(self)
        self.progress.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.progress.completed.connect(self.completed)
        layout.addWidget(self.progress)

        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Close)
        self.save_button = buttons.addButton('Retrieve…', qt.QDialogButtonBox.ButtonRole.ActionRole)
        self.save_button.clicked.connect(self.choose_destination)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.update_actions()

    def update_actions(self, *_):
        idle = not self.progress.busy and not self.choosing_destination
        connected = (self.host.text().strip(), self.port.value()) == self.connected_endpoint
        self.host.setEnabled(idle)
        self.port.setEnabled(idle)
        self.connect_button.setEnabled(idle and bool(self.host.text().strip()))
        self.browser.setEnabled(idle and connected)
        selected = self.browser.selected()
        document = self.browser.snapshot.entries.get(selected)
        self.save_button.setEnabled(idle and connected and document is not None and not document.directory)

    def connect_tablet(self):
        host = self.host.text().strip()
        port = self.port.value()
        if self.progress.busy or self.choosing_destination or not host:
            return
        self.restore_browse = None
        if self.connected_endpoint == (host, port):
            self.restore_browse = (self.browser.snapshot.ancestry(self.browser.directory), self.browser.selected(),
                                   self.browser.search.text(), self.browser.view_selector.currentIndex())
        self.connected_endpoint = None
        self.connection_generation += 1
        generation = self.connection_generation
        self.progress.start(lambda _report, cancelled: (generation, (host, port), list_snapshot(host, cancelled, port=port)),
                            message='Connecting and reading the tablet’s folders…')
        self.update_actions()

    def install_snapshot(self, snapshot):
        if self.browser is not None:
            if self.browser.stop():
                raise RuntimeError('Wait for tablet browser operations to retire.')
            self.browser_layout.removeWidget(self.browser)
            self.browser.hide()
            self.browser.deleteLater()
        self.browser = TabletBrowser(snapshot, self)
        self.browser_layout.addWidget(self.browser)
        if self.restore_browse is not None:
            ancestry, selected, query, view = self.restore_browse
            directory = next(key for key in reversed(ancestry) if key in snapshot.children)
            self.browser.navigate(directory)
            self.browser.search.setText(query)
            self.browser.view_selector.setCurrentIndex(view)
            if selected in snapshot.entries and directory in snapshot.ancestry(selected):
                index = self.browser.model.browse_index(selected)
                if index.isValid():
                    self.browser.views.select_source(index)
        self.browser.selection_changed.connect(self.update_actions)
        self.browser.retrieve.connect(self.choose_destination)
        self.browser.refresh_requested.connect(self.connect_tablet)

    def choose_destination(self, *_):
        if not self.save_button.isEnabled():
            return
        snapshot = self.browser.snapshot
        identity = self.browser.selected()
        document = snapshot.entries[identity]
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', document.title).strip(' .')[:100] or 'Notebook'
        downloads = qt.QStandardPaths.writableLocation(qt.QStandardPaths.StandardLocation.DownloadLocation)
        host, port = self.connected_endpoint
        from .remarkable_destination import choose_destination
        self.choosing_destination = True
        self.update_actions()
        try:
            choice = choose_destination(self, Path(downloads) / f'{name}.rmdoc')
        except (OSError, ValueError) as error:
            qt.QMessageBox.warning(self, 'Retrieve notebook', str(error))
            return
        finally:
            self.choosing_destination = False
            self.update_actions()
        if (choice is None or self.browser.snapshot is not snapshot
                or (self.host.text().strip(), self.port.value()) != (host, port)):
            return
        destination, revision = choice
        self.progress.start(lambda report, cancelled: export_document(
            host, identity, destination, port=port, expected_revision=revision, report=report, cancelled=cancelled),
            message='Connecting to retrieve notebook…')
        self.update_actions()

    def completed(self, result, error):
        if self.progress.cancelled.is_set() and not isinstance(result, Path):
            self.progress.message.setText('Cancelled.')
        elif not error and isinstance(result, tuple):
            generation, endpoint, snapshot = result
            if generation != self.connection_generation or endpoint != (self.host.text().strip(), self.port.value()):
                self.update_actions()
                return
            self.install_snapshot(snapshot)
            self.connected_endpoint = endpoint
            count = sum(not entry.directory for entry in snapshot.entries.values())
            self.progress.message.setText(f'Found {count} documents. Tablet browsing is read-only.')
        elif not error and isinstance(result, Path):
            self.progress.message.setText(f'Saved {result}')
        self.update_actions()

    def reject(self):
        if self.choosing_destination:
            return
        if self.progress.busy:
            self.progress.request_cancel()
            return
        if not self.browser.stop():
            super().reject()

    def closeEvent(self, event):
        if self.choosing_destination:
            event.ignore()
            return
        if self.progress.busy:
            self.progress.request_cancel()
            event.ignore()
            return
        if self.browser.stop():
            event.ignore()
        else:
            super().closeEvent(event)
