"""Background file operations shared by the comics browser and editor."""

from commonUtils.ui import pyside as qt


class Operation(qt.QThread):
    completed = qt.Signal(object, str)

    def __init__(self, callback, parent):
        super().__init__(parent)
        self.callback = callback

    def run(self):
        try:
            self.completed.emit(self.callback(), '')
        except Exception as error:
            self.completed.emit(None, str(error))

