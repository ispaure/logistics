"""Feature entry point; the document window stays independent of browser hosts."""

from commonUtils.ui import pyside as qt
from .service import editor_service


class TextEditorPage(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = editor_service()
        self.service.idle.connect(self.idle)
        self.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        layout = qt.QVBoxLayout(self)
        description = qt.QLabel(
            "Open a document to change editor preferences."
        )
        description.setWordWrap(True)
        button = qt.QPushButton("Open Text Editor")
        button.clicked.connect(lambda: self.service.open())
        for widget in (description, button):
            layout.addWidget(widget)

    def prepare_close(self):
        return self.service.prepare_close()
