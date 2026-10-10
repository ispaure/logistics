"""EPUB work uses the shared finish-safe result contract."""
from commonUtils.ui.operations import ResultWorker


class BookTask(ResultWorker):
    def __init__(self, operation, parent=None):
        self.operation = operation
        super().__init__(lambda: operation(self.isInterruptionRequested), parent)
