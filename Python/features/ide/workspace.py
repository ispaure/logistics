"""A retained project workspace."""
from commonUtils.ui import pyside as qt


class ProjectWorkspace(qt.QWidget):
    changed = qt.Signal()
    idle = qt.Signal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        layout = qt.QVBoxLayout(self)
        self.root_label = qt.QLabel()
        layout.addWidget(self.root_label)
        self.reset_root()

    def reset_root(self):
        self.root_label.setText(str(self.project.root) + ('' if self.project.root.is_dir() else ' — directory unavailable; registration retained'))

    def state(self):
        return self.project.layout

    def can_close(self):
        return True

    def prepare_close(self):
        return True
