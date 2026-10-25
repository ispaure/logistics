"""Small desktop front end for the existing Logistics deployment workflows."""
import codecs
import json
import os
from pathlib import Path
import sys

from PySide6.QtCore import QLockFile, QProcess, QProcessEnvironment, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from .deployment_confirmation import MARKER

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv/bin/python'


class DeploymentWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Logistics · Build and Deployment Manager')
        self.resize(1100, 800)
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(ROOT.parent))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert('PYTHONUNBUFFERED', '1')
        environment.insert('PATH', os.pathsep.join((str(ROOT / '.tools/go/bin'), '/opt/homebrew/bin',
                                                   '/usr/local/bin', environment.value('PATH'))))
        self.process.setProcessEnvironment(environment)
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.busy = False
        self.mode = ''
        self.pending = ''
        self.raw_output = ''
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        from build_manager.ui import ManagerPanel
        from Scripts.build_project import LogisticsProject
        self.manager = ManagerPanel(LogisticsProject(ROOT.parent), self)
        tabs.addTab(self.manager, 'Plans, tests and builds')
        deployment = QWidget()
        tabs.addTab(deployment, 'Devices and tester distribution')
        layout = QVBoxLayout(deployment)
        self.devices = QLabel('Checking test devices…')
        self.devices.setWordWrap(True)
        layout.addWidget(self.devices)
        selection = QHBoxLayout()
        selection.addWidget(QLabel('Deploy to:'))
        self.target = QComboBox()
        self.target.addItem('All available devices', None)
        selection.addWidget(self.target, 1)
        layout.addLayout(selection)
        row = QHBoxLayout()
        self.actions = []
        self.distribution_buttons = {}
        from .manager_settings import settings
        try:
            configured, _ = settings(ROOT)
        except (OSError, ValueError):
            configured = {'firebase.group': 'configure destination', 'testflight.external_group': 'configure destination'}
        for label, script, arguments in [
            ('Deploy test devices', 'test_devices.py', []),
            ('Firebase → ' + configured['firebase.group'], 'firebase_deploy.py', ['--gui']),
            ('TestFlight → ' + configured['testflight.external_group'], 'testflight_deploy.py', ['--gui']),
            ('Refresh', 'test_devices.py', ['--list']),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, s=script, a=arguments: self.start(s, a))
            row.addWidget(button)
            self.actions.append(button)
            if script in ('firebase_deploy.py', 'testflight_deploy.py'):
                self.distribution_buttons[script] = button
        layout.addLayout(row)
        hint = QLabel('Test devices: saved iPhones/iPads and authorized Android connections.\n'
                      'iOS and Android deploy together; devices on each platform run one at a time.\n'
                      'Samsung: USB debugging. Boox: Wireless debugging on the same Wi-Fi.\n'
                      'Refresh reconnects paired devices; Repair Android restarts a stuck ADB connection.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(6000)
        layout.addWidget(self.output)
        footer = QHBoxLayout()
        self.status = QLabel('Ready')
        footer.addWidget(self.status, 1)
        repair = QPushButton('Repair Android')
        repair.setToolTip('Restarts local ADB and reconnects paired wireless devices. '
                          'Other active ADB connections will briefly disconnect.')
        repair.clicked.connect(lambda: self.start('test_devices.py', ['--list', '--repair-android']))
        self.actions.append(repair)
        footer.addWidget(repair)
        logs = QPushButton('Open logs')
        logs.clicked.connect(self.open_logs)
        footer.addWidget(logs)
        layout.addLayout(footer)
        self.manager.busy_changed.connect(lambda busy: self.set_busy(busy, manager=True))
        self.manager.settings_saved.connect(self.refresh_distribution_labels)
        QTimer.singleShot(0, lambda: self.start('test_devices.py', ['--list']))

    def open_logs(self):
        path = ROOT / ('.deploy-workspaces' if self.mode in ('test_devices.py', 'list', '') else 'logs')
        path.mkdir(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def refresh_distribution_labels(self):
        from .manager_settings import settings
        values, _ = settings(ROOT)
        self.distribution_buttons['firebase_deploy.py'].setText('Firebase → ' + values['firebase.group'])
        label = 'TestFlight → ' + values['testflight.external_group']
        if not values['testflight.enabled']:
            label += ' (external distribution disabled)'
        self.distribution_buttons['testflight_deploy.py'].setText(label)

    def set_busy(self, busy, *, manager=False):
        self.busy = busy
        self.manager.setEnabled(not busy or manager)
        self.target.setEnabled(not busy)
        for button in self.actions:
            button.setEnabled(not busy)

    def start(self, script, arguments):
        if self.busy:
            return
        arguments = list(arguments)
        if script == 'test_devices.py' and '--list' not in arguments:
            target = self.target.currentData()
            if target:
                arguments += ['--platform', target['platform'], '--device', target['id']]
        self.mode = 'list' if '--list' in arguments else script
        self.pending = self.raw_output = ''
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.error_decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.set_busy(True)
        self.status.setText('Checking devices…' if self.mode == 'list' else 'Running…')
        if self.mode != 'list':
            self.output.clear()
        from .manager_settings import profile_path, settings
        python = PYTHON
        if profile_path(ROOT).exists():
            values, _ = settings(ROOT)
            python = values['tools.mobile_python']
            environment = self.process.processEnvironment()
            environment.insert('LOGISTICS_MANAGER_PROFILE', str(profile_path(ROOT)))
            for key, variable in [('tools.android_sdk', 'ANDROID_HOME'), ('tools.java', 'JAVA_HOME'),
                                  ('tools.xcode', 'DEVELOPER_DIR')]:
                if values[key]:
                    environment.insert(variable, values[key])
            self.process.setProcessEnvironment(environment)
        self.process.start(str(python), ['-u', '-m', 'mobile_build.deployment.' + Path(script).stem, *arguments])

    def update_targets(self, devices):
        previous = self.target.currentData()
        previous_label = self.target.currentText()
        self.target.clear()
        self.target.addItem('All available devices', None)
        for device in devices:
            label = device['platform'] + ' · ' + device['name']
            if not device['online']:
                label += ' (offline)'
            self.target.addItem(label, {key: device[key] for key in ('platform', 'id')})
        if previous:
            index = next((i for i in range(1, self.target.count())
                          if self.target.itemData(i) == previous), -1)
            if index < 0:
                self.target.addItem(previous_label + ' (unavailable)', previous)
                index = self.target.count() - 1
            self.target.setCurrentIndex(index)

    def append(self, text):
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()

    def read_stdout(self):
        text = self.decoder.decode(bytes(self.process.readAllStandardOutput()))
        if self.mode == 'list':
            self.raw_output += text
            return
        self.pending += text
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            if line.startswith(MARKER):
                prompt = json.loads(line[len(MARKER):])
                answer = QMessageBox.question(self, 'Upload prepared build?', prompt,
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                              QMessageBox.StandardButton.No)
                self.process.write(b'y\n' if answer == QMessageBox.StandardButton.Yes else b'n\n')
            else:
                self.append(line + '\n')

    def read_stderr(self):
        self.append(self.error_decoder.decode(bytes(self.process.readAllStandardError())))

    def finished(self, code, exit_status):
        self.read_stdout()
        self.read_stderr()
        self.append(self.pending)
        ok = code == 0 and exit_status == QProcess.ExitStatus.NormalExit
        if self.mode == 'list' and ok:
            try:
                inventory = json.loads(self.raw_output)
                self.update_targets(inventory['devices'])
                names = [d['platform'] + ' · ' + d['name'] + (' (ready)' if d['online'] else ' (offline)')
                         for d in inventory['devices']]
                self.devices.setText('\n'.join(names) or 'No test devices found. Connect the S8+ and Refresh.')
                for error in inventory['errors']:
                    self.append(error + '\n')
                if inventory['errors']:
                    ok = False
            except (ValueError, KeyError, TypeError) as error:
                self.append('Could not read device list: ' + str(error) + '\n')
                ok = False
        self.status.setText(('Devices refreshed' if self.mode == 'list' else 'Finished — see output')
                            if ok else 'Failed — see output and logs')
        self.set_busy(False)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.append('Could not start mobile_build/.venv/bin/python. Check the mobile environment.\n')
            self.status.setText('Could not start')
            self.set_busy(False)

    def closeEvent(self, event):
        if self.busy:
            QMessageBox.information(self, 'Deployment running', 'Wait for the current operation to finish before closing.')
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    (ROOT / '.tools').mkdir(exist_ok=True)
    lock = QLockFile(str(ROOT / '.tools/deploy-ui.lock'))
    if not lock.tryLock(0):
        QMessageBox.information(None, 'Logistics · Deploy', 'The deployment window is already open.')
        return
    window = DeploymentWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
