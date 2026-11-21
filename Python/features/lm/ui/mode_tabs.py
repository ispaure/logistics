"""Chat/Code navigation tabs; conversation modes remain persisted properties."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.ui import pyside as qt


class ModeTabs(qt.QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        for label, key in (('Chat', 'chat'), ('Code', 'code')):
            self.setTabData(self.addTab(label), key)
        self.setExpanding(True)
        self.setAccessibleName('Conversation mode')

    def currentData(self):
        return self.tabData(self.currentIndex())

    def findData(self, value):
        return next((index for index in range(self.count()) if self.tabData(index) == value), -1)

