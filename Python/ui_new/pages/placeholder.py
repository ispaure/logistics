"""
Simple placeholder page used while new Logistics pages are being migrated.
"""

from commonUtils.ui import pyside


class PlaceholderPage(pyside.QWidget):
    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)

        layout = pyside.QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(12)

        title_label = pyside.QLabel(title)
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 8)
        title_font.setBold(True)
        title_label.setFont(title_font)

        description_label = pyside.QLabel(description)
        description_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addStretch()
