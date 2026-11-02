"""Offline searchable notices for the desktop runtime."""
from commonUtils.ui import pyside as qt
from services.open_source import installed_notices


class LicensesPanel(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.notices = installed_notices()
        layout = qt.QVBoxLayout(self)
        layout.addWidget(qt.QLabel('Open-source licenses'))
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Search components')
        self.search.setAccessibleName('Search components')
        layout.addWidget(self.search)
        splitter = qt.QSplitter()
        self.components = qt.QListWidget()
        self.components.setAccessibleName('Components')
        self.text = qt.QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setAccessibleName('License and notices')
        splitter.addWidget(self.components)
        splitter.addWidget(self.text)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        self.components.currentRowChanged.connect(self.select)
        self.search.textChanged.connect(self.filter)
        self.filter('')

    def filter(self, query):
        self.components.clear()
        self.visible = [notice for notice in self.notices
                        if query.casefold() in (notice.title + ' ' + notice.license).casefold()]
        self.components.addItems([notice.title for notice in self.visible])
        self.components.setCurrentRow(0 if self.visible else -1)
        if not self.visible:
            self.text.setPlainText('No matching components.')

    def select(self, index):
        if index >= 0:
            self.text.setPlainText(self.visible[index].content)
