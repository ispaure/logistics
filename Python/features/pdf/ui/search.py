"""Asynchronous Qt PDF search; closing cancels work and retires search text."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from commonUtils.ui import pyside as qt
from features.pdf.search import Results, search_pdf, result_text


class PDFSearchBar(qt.QWidget):
    def __init__(self, data, go, parent=None):
        super().__init__(parent)
        self.data, self.go = data, go
        self.results, self.cursor, self.query = Results(()), -1, None
        self.future = None
        self.cancelled = Event()
        self.disposed = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pdf-search')
        self.input = qt.QLineEdit()
        self.input.setPlaceholderText('Find in PDF…')
        self.input.setMaxLength(256)
        self.input.setAccessibleName('Find in PDF')
        self.previous = qt.QPushButton('Previous match')
        self.following = qt.QPushButton('Next match')
        self.status = qt.QLabel('')
        self.status.setWordWrap(True)
        self.input.returnPressed.connect(self.next_match)
        self.input.textChanged.connect(self.changed)
        self.previous.clicked.connect(lambda: self.find(-1))
        self.following.clicked.connect(self.next_match)
        row = qt.QHBoxLayout()
        for widget in (self.input, self.previous, self.following):
            row.addWidget(widget)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.status)
        self.timer = qt.QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.poll)

    def changed(self, *args):
        self.cancelled.set()
        self.query, self.results, self.cursor = None, Results(()), -1
        self.status.setText('')

    def next_match(self):
        self.find(1)

    def find(self, direction):
        if self.disposed or self.future is not None:
            return
        query = ' '.join(self.input.text().split())
        if not query:
            self.changed()
            return
        if self.query == query:
            self.show_match(direction)
            return
        self.cancelled = Event()
        try:
            self.future = self.executor.submit(search_pdf, self.data, query, cancelled=self.cancelled.is_set)
        except (OSError, RuntimeError) as error:
            self.query = None
            self.status.setText('Cannot search PDF: ' + (str(error)[:200] or type(error).__name__))
            return
        self.query, self.direction = query, direction
        self.previous.setEnabled(False)
        self.following.setEnabled(False)
        self.status.setText('Searching PDF…')
        self.timer.start()

    def poll(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.timer.stop()
        self.previous.setEnabled(True)
        self.following.setEnabled(True)
        if self.disposed or self.cancelled.is_set():
            return
        try:
            self.results = future.result()
            self.cursor = -1 if self.direction > 0 else 0
            self.show_match(self.direction)
        except Exception as error:
            self.query = None
            self.status.setText('Cannot search PDF: ' + (str(error)[:200] or type(error).__name__))

    def show_match(self, direction):
        if self.results.matches:
            self.cursor = (self.cursor + direction) % len(self.results.matches)
            self.go(self.results.matches[self.cursor].page)
        self.status.setText(result_text(self.results, self.cursor))

    def dispose(self):
        self.disposed = True
        self.cancelled.set()
        self.timer.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.future = None
        self.data, self.go = b'', lambda page: None
        self.input.clear()
        self.status.clear()
        self.results, self.query, self.cursor = Results(()), None, -1
