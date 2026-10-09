"""One owned worker per reader; payload delivery happens after thread completion."""
from commonUtils.ui import pyside as qt


class BookTask(qt.QThread):
    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.operation(self.isInterruptionRequested)
        except Exception as error:
            self.error = str(error)
