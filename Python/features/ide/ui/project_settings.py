"""Project settings shared by registration and the desktop IDE Project menu."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.ui import pyside as qt
from features.ide.ui.project_interpreter import ProjectInterpreter
from features.ide.ui.project_structure import ProjectStructure


class ProjectSettings(qt.QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle('IDE Project Settings')
        self.resize(880, 610)
        layout = qt.QVBoxLayout(self)

        general = qt.QFormLayout()
        self.name = qt.QLineEdit(project.name)
        general.addRow('Display name', self.name)
        self.column_guide = qt.QSpinBox()
        self.column_guide.setRange(0, 1000)
        self.column_guide.setSpecialValueText('Off')
        self.column_guide.setValue(project.column_guide)
        self.column_guide.setToolTip('Visual line-length guide for source editors in this project.')
        general.addRow('Column guide', self.column_guide)
        layout.addLayout(general)

        self.tabs = qt.QTabWidget()
        self.structure = ProjectStructure(project, self.tabs)
        self.interpreter = ProjectInterpreter(project.python_interpreter, self.structure, self.tabs)
        self.tabs.addTab(self.structure, 'Project Structure')
        self.tabs.addTab(self.interpreter, 'Python Interpreter')
        self.tabs.currentChanged.connect(self.load_interpreter_packages)
        layout.addWidget(self.tabs, 1)

        self.error = qt.QLabel()
        self.error.hide()
        layout.addWidget(self.error)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok |
                                     qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.finished.connect(lambda _: self.interpreter.stop())

    def load_interpreter_packages(self, index):
        if self.tabs.widget(index) is self.interpreter:
            self.interpreter.inspect_if_needed()

    def accept(self):
        if not self.name.text().strip():
            self.error.setText('Enter a project display name.')
            self.name.setFocus()
        elif self.structure.resolved_root() is None:
            self.error.setText('Enter a valid project root.')
            self.tabs.setCurrentWidget(self.structure)
            self.structure.root_path.setFocus()
        else:
            super().accept()
            return
        self.error.show()

    def apply_to(self, project):
        project.name = self.name.text().strip()
        project.root_path = str(self.structure.resolved_root())
        project.source_paths = list(self.structure.sources.values)
        project.excluded_paths = list(self.structure.exclusions.values)
        project.excluded_patterns = list(self.structure.patterns)
        project.python_interpreter = self.interpreter.path.text().strip() or None
        project.column_guide = self.column_guide.value()
