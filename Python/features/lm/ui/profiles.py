"""Server profile editing with identity-preserving optimistic publication."""
from copy import deepcopy
from uuid import uuid4
from commonUtils.ui import pyside as qt


class ProfilesDialog(qt.QDialog):
    def __init__(self, store, parent):
        super().__init__(parent)
        self.store = store
        self.expected = store.profiles()
        self.profiles = deepcopy(self.expected)
        self.setWindowTitle('LM server profiles')
        self.resize(650, 340)
        layout = qt.QVBoxLayout(self)
        note = qt.QLabel('Enter the OpenAI-compatible API base URL, e.g. http://localhost:1234/v1. Tokens are entered on the chat page and kept only for this session.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = qt.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Name', 'API base URL'])
        self.table.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(qt.QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)
        for entry in self.profiles:
            self.add_row(entry)
        row = qt.QHBoxLayout()
        add = qt.QPushButton('Add server')
        add.clicked.connect(lambda: self.add_row(dict(id=uuid4().hex, name='New server', base_url='http://localhost:1234/v1')))
        remove = qt.QPushButton('Remove')
        remove.clicked.connect(self.remove_row)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        self.error = qt.QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Save | qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_row(self, entry):
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = qt.QTableWidgetItem(entry['name'])
        name.setData(qt.Qt.ItemDataRole.UserRole, entry['id'])
        self.table.setItem(row, 0, name)
        self.table.setItem(row, 1, qt.QTableWidgetItem(entry['base_url']))

    def remove_row(self):
        if self.table.currentRow() >= 0:
            self.table.removeRow(self.table.currentRow())

    def save(self):
        profiles = [dict(id=self.table.item(i, 0).data(qt.Qt.ItemDataRole.UserRole),
                         name=self.table.item(i, 0).text(), base_url=self.table.item(i, 1).text())
                    for i in range(self.table.rowCount())]
        try:
            self.store.save_profiles(profiles, self.expected)
        except (OSError, ValueError) as error:
            self.error.setText(str(error))
            return
        self.accept()

