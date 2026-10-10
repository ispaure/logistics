"""Repository history search with explicit fields and date bounds."""
from commonUtils.ui import pyside as qt
from .history import HistoryPanel


class SearchPanel(HistoryPanel):
    search_requested = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        filters = self.layout().itemAt(0).layout()
        filters.removeWidget(self.branch_filter)
        self.branch_filter.hide()
        self.search.setPlaceholderText('Enter a string to search for')
        self.search.setAccessibleName('Search repository history')
        self.search.setClearButtonEnabled(True)
        filters.addWidget(qt.QLabel('Search:'))
        self.mode = qt.QComboBox()
        self.mode.addItems(['Commit Message', 'Commit SHA', 'Branch', 'File Changes', 'User'])
        self.mode.setAccessibleName('Search field')
        filters.addWidget(self.mode)
        self.from_date = qt.QDateEdit(qt.QDate(1980, 1, 1))
        self.to_date = qt.QDateEdit(qt.QDate.currentDate().addYears(1))
        for label, field in [('From:', self.from_date), ('To:', self.to_date)]:
            field.setDisplayFormat('yyyy-MM-dd')
            field.setCalendarPopup(True)
            field.setAccessibleName(label.removesuffix(':') + ' date')
            filters.addWidget(qt.QLabel(label))
            filters.addWidget(field)
        self.table.setAccessibleName('Commit search results')
        self.table.setColumnHidden(0, True)
        self.more.setText('Load 200 more results')
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.search_requested)
        self.search.textChanged.connect(self._schedule)
        self.search.returnPressed.connect(self._request)
        self.mode.currentIndexChanged.connect(self._schedule)
        self.from_date.dateChanged.connect(self._schedule)
        self.to_date.dateChanged.connect(self._schedule)
        self.limit = 200
        self.stale = True

    def _filter(self, *args):
        # Git performs the search across repository history, beyond loaded rows.
        pass

    def _schedule(self, *args):
        self.limit = 200
        self.stale = True
        self.timer.start()

    def _request(self):
        self.timer.stop()
        self.search_requested.emit()

    def query(self):
        return (self.search.text(), self.mode.currentText(),
                self.from_date.date().toString('yyyy-MM-dd'), self.to_date.date().toString('yyyy-MM-dd'))
