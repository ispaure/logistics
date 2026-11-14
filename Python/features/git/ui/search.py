"""Repository history search with explicit fields and date bounds."""
from commonUtils.search.policy import SEARCH_DEBOUNCE_MS
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
        self.timer.setInterval(SEARCH_DEBOUNCE_MS)
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


def build_search(workspace):
    search_view = qt.QSplitter(qt.Qt.Orientation.Vertical)
    search_view.addWidget(workspace.search_results)
    search_bottom = qt.QSplitter(qt.Qt.Orientation.Horizontal)
    search_bottom.addWidget(workspace.search_results.details)
    search_preview_host = qt.QWidget()
    workspace.search_preview_layout = qt.QVBoxLayout(search_preview_host)
    workspace.search_preview_layout.setContentsMargins(0, 0, 0, 0)
    search_bottom.addWidget(search_preview_host)
    search_bottom.setSizes([450, 550])
    search_view.addWidget(search_bottom)
    search_view.setSizes([440, 300])
    workspace.views.addTab(search_view, 'Search')
