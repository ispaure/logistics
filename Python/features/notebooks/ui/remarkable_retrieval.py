"""Desktop Debug workflow for retrieving one native notebook over SSH."""
from pathlib import Path
import re

from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from ..remarkable_ssh import DEFAULT_HOST, DEFAULT_PORT, TABLET_USER, export_document, list_documents

TITLE = 'Retrieve RMDOC from reMarkable Tablet'


class RetrievalDialog(qt.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.resize(640, 500)
        self.documents = []
        self.connected_endpoint = None
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

        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Filter by document or folder')
        self.search.setAccessibleName('Filter tablet documents')
        self.search.textChanged.connect(self.filter_documents)
        layout.addWidget(self.search)
        self.listing = qt.QListWidget()
        self.listing.setAccessibleName('Tablet documents')
        self.listing.itemSelectionChanged.connect(self.update_actions)
        self.listing.itemDoubleClicked.connect(self.choose_destination)
        layout.addWidget(self.listing, 1)
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
        idle = not self.progress.busy
        connected = (self.host.text().strip(), self.port.value()) == self.connected_endpoint
        self.host.setEnabled(idle)
        self.port.setEnabled(idle)
        self.connect_button.setEnabled(idle and bool(self.host.text().strip()))
        self.search.setEnabled(idle and connected and bool(self.documents))
        self.listing.setEnabled(idle and connected)
        self.save_button.setEnabled(idle and connected and self.listing.currentItem() is not None)

    def connect_tablet(self):
        host = self.host.text().strip()
        port = self.port.value()
        if self.progress.busy or not host:
            return
        self.connected_endpoint = None
        self.documents = []
        self.listing.clear()
        self.progress.start(lambda _report, cancelled: ((host, port), list_documents(host, cancelled, port=port)),
                            message='Connecting and reading the tablet’s document list…')
        self.update_actions()

    def filter_documents(self):
        current = self.listing.currentItem()
        selected = current.data(qt.Qt.ItemDataRole.UserRole) if current is not None else None
        query = self.search.text().strip().casefold()
        self.listing.clear()
        for document in self.documents:
            label = f'{document.folder} / {document.title}' if document.folder else document.title
            if query not in label.casefold():
                continue
            item = qt.QListWidgetItem(label, self.listing)
            item.setData(qt.Qt.ItemDataRole.UserRole, document.id)
            if document.id == selected:
                self.listing.setCurrentItem(item)
        self.update_actions()

    def choose_destination(self, *_):
        if not self.save_button.isEnabled():
            return
        identity = self.listing.currentItem().data(qt.Qt.ItemDataRole.UserRole)
        document = next(item for item in self.documents if item.id == identity)
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', document.title).strip(' .')[:100] or 'Notebook'
        downloads = qt.QStandardPaths.writableLocation(qt.QStandardPaths.StandardLocation.DownloadLocation)
        path, _ = qt.QFileDialog.getSaveFileName(self, 'Save retrieved notebook',
            str(Path(downloads) / f'{name}.rmdoc'), 'reMarkable notebook (*.rmdoc)',
            options=qt.QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != '.rmdoc':
            destination = destination.with_name(destination.name + '.rmdoc')
        host, port = self.connected_endpoint
        self.progress.start(lambda report, cancelled: export_document(
            host, identity, destination, port=port, report=report, cancelled=cancelled),
            message='Connecting to retrieve notebook…')
        self.update_actions()

    def completed(self, result, error):
        if self.progress.cancelled.is_set() and result is None:
            self.progress.message.setText('Cancelled.')
        elif not error and isinstance(result, tuple):
            self.connected_endpoint, self.documents = result
            self.filter_documents()
            self.progress.message.setText(f'Found {len(self.documents)} documents.')
        elif not error and isinstance(result, Path):
            self.progress.message.setText(f'Saved {result}')
        self.update_actions()

    def reject(self):
        if self.progress.busy:
            self.progress.request_cancel()
            return
        super().reject()

    def closeEvent(self, event):
        if self.progress.busy:
            self.progress.request_cancel()
            event.ignore()
            return
        super().closeEvent(event)
