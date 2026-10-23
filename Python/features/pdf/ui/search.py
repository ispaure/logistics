"""Asynchronous Qt PDF search; closing cancels work and retires search text."""
from concurrent.futures import ThreadPoolExecutor
from commonUtils.ui import pyside as qt
from features.pdf.search import search_pdf
from features.pdf.search_controller import PDFSearchController, SearchRequest


class PDFSearchBar(qt.QWidget):
    def __init__(self, data, go, parent=None):
        super().__init__(parent)
        self.data, self.go = data, go
        self.controller = PDFSearchController()
        self.request = None
        self.future = None
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

    def render(self):
        state = self.controller.state
        self.previous.setEnabled(state.previous_enabled)
        self.following.setEnabled(state.next_enabled)
        self.status.setText(state.status)

    def changed(self, *args):
        self.controller.set_query(self.input.text())
        self.render()

    def next_match(self):
        self.find(1)

    def find(self, direction):
        self.controller.set_query(self.input.text())
        action = self.controller.step(direction)
        if isinstance(action, SearchRequest):
            try:
                self.future = self.executor.submit(search_pdf, self.data, action.query,
                                                  cancelled=action.cancelled.is_set)
            except Exception as error:
                self.controller.fail(action, error)
            else:
                self.request = action
                self.timer.start()
        else:
            self.show_match(action)
        self.render()

    def poll(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        request, self.request = self.request, None
        self.timer.stop()
        try:
            results = future.result()
        except Exception as error:
            self.controller.fail(request, error)
        else:
            self.show_match(self.controller.complete(request, results))
        self.render()

    def show_match(self, match):
        if match is not None:
            revision = self.controller.revision
            try:
                self.go(match.page)
            except Exception as error:
                self.controller.navigation_failed(revision, error)

    def dispose(self):
        self.controller.dispose()
        self.timer.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.future = self.request = None
        self.data, self.go = b'', lambda page: None
        self.input.clear()
        self.render()
