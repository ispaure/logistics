"""EPUB work uses the shared finish-safe result contract."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.ui.tasks.operations import ResultWorker


class BookTask(ResultWorker):
    def __init__(self, operation, parent=None):
        self.operation = operation
        super().__init__(lambda: operation(self.isInterruptionRequested), parent)
