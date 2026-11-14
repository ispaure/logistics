"""Read-only aircraft, airport and performance data in Aviation Tools."""
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHeaderView, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..resources import DATA_DIR


class DatasetBrowser(QWidget):
    """Read-only aircraft, airport and model chart tables in a popup window."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.dataset = QComboBox()
        self.dataset.addItem('Airports', DATA_DIR / 'airports.csv')
        for path in sorted((DATA_DIR / 'aircraft').glob('*.csv')):
            self.dataset.addItem(f'Aircraft: {path.stem}', path)
        for path in sorted((DATA_DIR / 'airplane').glob('*/*.csv')):
            self.dataset.addItem(f'{path.parent.name}: {path.stem.replace("_", " ")}', path)
        layout.addWidget(self.dataset)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        self.dataset.currentIndexChanged.connect(self._load_dataset)
        self._load_dataset()

    def _load_dataset(self, _index=0):
        from commonUtils.formats.csvType import CSVFile
        path = self.dataset.currentData()
        rows = CSVFile(path).read_csv()
        self.table.clear()
        self.table.setColumnCount(len(rows[0]))
        self.table.setRowCount(len(rows) - 1)
        self.table.setHorizontalHeaderLabels(rows[0])
        for row_index, row in enumerate(rows[1:]):
            for column_index, value in enumerate(row):
                self.table.setItem(row_index, column_index, QTableWidgetItem(value))
