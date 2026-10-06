"""Library-bounded location control and back/forward history."""

from pathlib import Path
from commonUtils.ui import pyside as qt


class NavigationBar(qt.QWidget):
    requested = qt.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.library = None
        self.directory = None
        self.history = []
        self.position = -1
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.back = qt.QPushButton('Back')
        self.forward = qt.QPushButton('Forward')
        self.up = qt.QPushButton('Up')
        self.location = qt.QComboBox()
        self.location.setAccessibleName('Current folder and parent folders')
        self.location.setSizeAdjustPolicy(qt.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.location.setMinimumContentsLength(20)
        for button in (self.back, self.forward, self.up):
            layout.addWidget(button)
        layout.addWidget(self.location, 1)
        self.back.clicked.connect(lambda: self._history(-1))
        self.forward.clicked.connect(lambda: self._history(1))
        self.up.clicked.connect(lambda: self.requested.emit(self.directory.parent))
        self.location.activated.connect(lambda index: self.requested.emit(self.location.itemData(index)))
        self.set_library(None)

    def set_library(self, path):
        self.library = Path(path) if path is not None else None
        self.directory = None
        self.history = []
        self.position = -1
        self.set_directory(self.library)

    def set_directory(self, path):
        if path is not None:
            path = Path(path)
            if self.library is None or (path != self.library and self.library not in path.parents):
                return
        self.directory = path
        if path is not None and (self.position < 0 or self.history[self.position] != path):
            self.history = self.history[:self.position + 1] + [path]
            self.position += 1
        blocker = qt.QSignalBlocker(self.location)
        self.location.clear()
        if path is not None:
            parents = [path]
            while parents[-1] != self.library:
                parents.append(parents[-1].parent)
            for folder in reversed(parents):
                label = self.library.name if folder == self.library else str(folder.relative_to(self.library))
                self.location.addItem(label, folder)
            self.location.setCurrentIndex(self.location.count() - 1)
            self.location.setToolTip(str(path))
        blocker.unblock()
        self.up.setEnabled(path is not None and path != self.library)
        self.back.setEnabled(self.position > 0)
        self.forward.setEnabled(self.position >= 0 and self.position < len(self.history) - 1)
        self.location.setEnabled(path is not None)

    def _history(self, offset):
        position = self.position + offset
        if 0 <= position < len(self.history):
            self.position = position
            self.requested.emit(self.history[position])
