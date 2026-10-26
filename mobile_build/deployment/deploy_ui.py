"""Logistics policy and launcher shell for the manager's deployment controls."""
import json
import os
from pathlib import Path
import sys

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QTabWidget, QVBoxLayout, QWidget
from build_manager.deployment_commands import Command
from build_manager.deployment_commands_ui import CommandAction, CommandInventory, CommandPanel, CommandTarget

from .deployment_confirmation import MARKER

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv/bin/python'


class LogisticsDeployment:
    confirmation_marker = MARKER
    confirmation_title = 'Upload prepared build?'
    hint = ('Test devices: saved iPhones/iPads and authorized Android connections.\n'
            'iOS and Android deploy together; devices on each platform run one at a time.\n'
            'Samsung: USB debugging. Boox: Wireless debugging on the same Wi-Fi.\n'
            'Refresh reconnects paired devices; Repair Android restarts a stuck ADB connection.')

    def __init__(self, root):
        self.root = Path(root)

    @property
    def actions(self):
        from .manager_settings import settings
        try:
            configured, _ = settings(self.root)
        except (OSError, ValueError):
            configured = {'firebase.group': 'configure destination', 'testflight.external_group': 'configure destination'}
        testflight = 'TestFlight → ' + configured['testflight.external_group']
        if not configured.get('testflight.enabled', True):
            testflight += ' (external distribution disabled)'
        return (
            CommandAction('devices', 'Deploy test devices'),
            CommandAction('firebase', 'Firebase → ' + configured['firebase.group']),
            CommandAction('testflight', testflight),
            CommandAction('refresh', 'Refresh', inventory=True),
            CommandAction('repair', 'Repair Android', inventory=True,
                tooltip='Restarts local ADB and reconnects paired wireless devices. '
                        'Other active ADB connections will briefly disconnect.'),
        )

    def command(self, action, target):
        module, arguments = {
            'devices': ('test_devices', []),
            'firebase': ('firebase_deploy', ['--gui']),
            'testflight': ('testflight_deploy', ['--gui']),
            'refresh': ('test_devices', ['--list']),
            'repair': ('test_devices', ['--list', '--repair-android']),
        }[action]
        if action == 'devices' and target:
            arguments += ['--platform', target['platform'], '--device', target['id']]
        environment = dict(PYTHONUNBUFFERED='1', PATH=os.pathsep.join((str(self.root / '.tools/go/bin'),
            '/opt/homebrew/bin', '/usr/local/bin', os.environ.get('PATH', ''))))
        from .manager_settings import profile_path, settings
        python = PYTHON
        if profile_path(self.root).exists():
            values, _ = settings(self.root)
            python = values['tools.mobile_python']
            environment['LOGISTICS_MANAGER_PROFILE'] = str(profile_path(self.root))
            for key, variable in [('tools.android_sdk', 'ANDROID_HOME'), ('tools.java', 'JAVA_HOME'),
                                  ('tools.xcode', 'DEVELOPER_DIR')]:
                if values[key]:
                    environment[variable] = values[key]
        return Command((str(python), '-u', '-m', 'mobile_build.deployment.' + module, *arguments),
                       str(self.root.parent), environment)

    def inventory(self, text):
        inventory = json.loads(text)
        devices = inventory['devices']
        targets = tuple(CommandTarget(d['platform'] + ' · ' + d['name'] + (' (offline)' if not d['online'] else ''),
                        {key: d[key] for key in ('platform', 'id')}) for d in devices)
        names = [d['platform'] + ' · ' + d['name'] + (' (ready)' if d['online'] else ' (offline)') for d in devices]
        return CommandInventory(targets, '\n'.join(names) or 'No test devices found. Connect the S8+ and Refresh.',
                                tuple(inventory['errors']))

    def logs(self, action):
        return self.root / ('.deploy-workspaces' if action in ('devices', 'refresh', 'repair', '') else 'logs')


class DeploymentWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Logistics · Build and Deployment Manager')
        self.resize(1100, 800)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        from build_manager.ui import ManagerPanel
        from Scripts.build_project import LogisticsProject
        sys.path.insert(0, str(ROOT.parent / 'Python'))
        from commonUtils.ui.settings.navigation import SettingsNavigation
        project = LogisticsProject(ROOT.parent)
        project.settings_navigation = SettingsNavigation
        self.manager = ManagerPanel(project, self)
        tabs.addTab(self.manager, 'Plans, tests and builds')
        self.deployment = CommandPanel(LogisticsDeployment(ROOT), self)
        tabs.addTab(self.deployment, 'Devices and tester distribution')
        self.manager.busy_changed.connect(self.deployment.set_external_busy)
        self.deployment.busy_changed.connect(lambda busy: self.manager.setEnabled(not busy))
        self.manager.settings_saved.connect(self.deployment.refresh_labels)
        QTimer.singleShot(0, lambda: self.deployment.start('refresh'))

    def closeEvent(self, event):
        if self.deployment.busy or self.deployment.external_busy:
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
