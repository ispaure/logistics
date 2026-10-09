"""Feature entry point; the document window stays independent of browser hosts."""
from commonUtils.ui import pyside as qt
from .service import editor_service


class TextEditorPage(qt.QWidget):
    idle=qt.Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.service=editor_service();self.service.idle.connect(self.idle)
        layout=qt.QVBoxLayout(self)
        title=qt.QLabel('Text Editor');font=title.font();font.setPointSize(20);font.setBold(True);title.setFont(font)
        description=qt.QLabel('Edit scripts, configuration, Markdown and other text in an independent window. Documents share tabs across all Logistics browsers.');description.setWordWrap(True)
        button=qt.QPushButton('Open Text Editor');button.clicked.connect(lambda:self.service.open())
        for widget in (title,description,button):layout.addWidget(widget)
        layout.addStretch()
    def prepare_close(self):return self.service.prepare_close()
