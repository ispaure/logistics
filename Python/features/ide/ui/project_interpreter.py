"""Choose an interpreter and inspect its local package inventory."""
from importlib import metadata
import json
import os
from pathlib import Path
import sys

from commonUtils.ui import pyside as qt


PACKAGE_PROBE = """
import json, platform
from importlib.metadata import distributions

packages = [[d.metadata['Name'], d.version] for d in distributions() if d.metadata['Name']]
print(json.dumps([platform.python_version(), packages]))
"""
MAX_OUTPUT = 1024 * 1024


def interpreter_executable(root, value):
    path = Path(os.path.abspath(root / Path(value).expanduser()))
    if path.is_dir():
        candidates = ('Scripts/python.exe', 'python.exe') if os.name == 'nt' else ('bin/python',)
        path = next((path / name for name in candidates if (path / name).is_file()), path)
    return path


class ProjectInterpreter(qt.QWidget):
    def __init__(self, interpreter, structure, parent=None):
        super().__init__(parent)
        self.structure = structure
        self.inspecting = False
        self.output = bytearray()
        layout = qt.QVBoxLayout(self)
        row = qt.QHBoxLayout()
        label = qt.QLabel('Python interpreter')
        self.path = qt.QLineEdit(interpreter or '')
        self.path.setPlaceholderText('Automatic (default environment)')
        label.setBuddy(self.path)
        self.path.setAccessibleName('Python interpreter')
        row.addWidget(label)
        row.addWidget(self.path, 1)
        browse = qt.QPushButton('Browse…')
        browse.setAutoDefault(False)
        self.browse_menu = qt.QMenu(browse)
        self.browse_menu.addAction('Python Executable…', lambda: self.choose_path(False))
        self.browse_menu.addAction('Environment Folder…', lambda: self.choose_path(True))
        browse.setMenu(self.browse_menu)
        row.addWidget(browse)
        layout.addLayout(row)

        toolbar = qt.QHBoxLayout()
        self.status = qt.QLabel()
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        toolbar.addWidget(self.status, 1)
        self.load = qt.QPushButton('Load Packages')
        self.load.setAutoDefault(False)
        self.load.clicked.connect(self.inspect)
        toolbar.addWidget(self.load)
        layout.addLayout(toolbar)

        self.table = qt.QTreeWidget()
        self.table.setAccessibleName('Installed packages')
        self.table.setHeaderLabels(['Package', 'Installed Version'])
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setAlternatingRowColors(True)
        self.table.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.table.header().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, qt.Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.table, 1)

        self.process = qt.QProcess(self)
        self.process.setStandardErrorFile(qt.QProcess.nullDevice())
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.stop('The interpreter took too long to respond.'))
        self.path.textChanged.connect(self.clear_inventory)
        structure.root_path.textChanged.connect(self.clear_inventory)
        self.clear_inventory()

    def choose_path(self, directory):
        start = self.path.text().strip() or self.structure.root_path.text()
        if directory:
            selected = qt.QFileDialog.getExistingDirectory(self, 'Choose Python Environment', start)
        else:
            selected, _ = qt.QFileDialog.getOpenFileName(self, 'Choose Python Executable', start)
        if selected:
            self.path.setText(selected)

    def clear_inventory(self, *args):
        self.inventory_loaded = False
        self.table.clear()
        self.load.setText('Load Packages')
        message = ('Load packages from the selected Python executable or environment folder.'
                   if self.path.text().strip() else 'Load packages from the Logistics Python runtime.')
        self.stop(message)

    def inspect_if_needed(self):
        if self.path.text().strip() and not self.inventory_loaded and self.load.isEnabled():
            self.inspect()

    def inspect(self):
        self.inventory_loaded = False
        value = self.path.text().strip()
        self.table.clear()
        if not value:
            try:
                packages = [(dist.metadata['Name'], dist.version) for dist in metadata.distributions()]
                self.show_packages('.'.join(map(str, sys.version_info[:3])), packages)
            except (OSError, ValueError, TypeError):
                self.status.setText('Could not read installed package metadata.')
            return
        root = self.structure.resolved_root()
        if root is None:
            self.status.setText('Enter a valid project root first.')
            return
        try:
            executable = interpreter_executable(root, value)
            available = executable.is_file()
        except (OSError, RuntimeError, ValueError):
            available = False
        if not available:
            self.status.setText('Python executable unavailable. Choose an executable or environment folder.')
            return
        self.inspecting = True
        self.output.clear()
        self.load.setEnabled(False)
        self.status.setText('Reading installed packages…')
        self.process.setWorkingDirectory(str(Path.home()))
        self.timer.start(8000)
        self.process.start(str(executable), ['-I', '-c', PACKAGE_PROBE])

    def read_output(self):
        data = self.process.readAllStandardOutput().data()
        if self.inspecting:
            if len(self.output) + len(data) > MAX_OUTPUT:
                self.stop('The interpreter returned too much package data.')
            else:
                self.output.extend(data)

    def stop(self, message=''):
        self.inspecting = False
        self.timer.stop()
        self.output.clear()
        self.status.setText(message)
        if self.process.state() != qt.QProcess.ProcessState.NotRunning:
            self.process.kill()

    def process_error(self, error):
        if error == qt.QProcess.ProcessError.FailedToStart:
            self.stop('Could not start the selected Python executable.')
            self.load.setEnabled(True)

    def finished(self, code, exit_status):
        self.timer.stop()
        self.load.setEnabled(True)
        self.read_output()
        if not self.inspecting:
            return
        self.inspecting = False
        try:
            if code != 0 or exit_status != qt.QProcess.ExitStatus.NormalExit:
                raise ValueError
            version, packages = json.loads(self.output)
            self.show_packages(version, packages)
        except (ValueError, TypeError):
            self.status.setText('Could not read package metadata. Inspection requires Python 3.8 or newer.')
        finally:
            self.output.clear()

    def show_packages(self, version, packages):
        if not isinstance(version, str) or not isinstance(packages, (list, tuple)):
            raise ValueError
        rows = []
        for name, installed in packages:
            if isinstance(name, str) and isinstance(installed, str):
                rows.append(qt.QTreeWidgetItem([name, installed]))
        self.table.addTopLevelItems(rows)
        self.inventory_loaded = True
        self.status.setText(f'Python {version} · {len(rows)} installed packages')
        self.load.setText('Refresh Packages')
