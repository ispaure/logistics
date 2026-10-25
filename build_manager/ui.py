"""Optional Qt presentation for an explicitly supplied project adapter."""
import json
import os
import subprocess
from uuid import uuid4

from PySide6.QtCore import QElapsedTimer, QProcess, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)


class SettingsDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project, self.controls = project, {}
        self.setWindowTitle('Settings and effective value sources')
        self.resize(800, 650)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        section = None
        for name, entry in project.settings_view().items():
            group = name.split('.')[0]
            if group != section:
                heading = QLabel(group.replace('_', ' ').title())
                heading.setStyleSheet('font-weight: bold; margin-top: 8px')
                form.addRow(heading)
                section = group
            if entry.get('kind') == 'bool':
                control = QCheckBox()
                control.setChecked(bool(entry['value']))
            else:
                control = QLineEdit(str(entry['value']))
            control.setEnabled(not entry.get('read_only', False))
            self.controls[name] = control
            row = QHBoxLayout()
            row.addWidget(control)
            if entry.get('kind') in ('reference', 'directory'):
                browse = QPushButton('Locate…')
                browse.setEnabled(not entry.get('read_only', False))
                browse.clicked.connect(lambda checked=False, field=control, kind=entry['kind']: self.locate(field, kind))
                row.addWidget(browse)
            row.addWidget(QLabel(entry.get('origin', 'repository default')))
            form.addRow(entry.get('label', name), row)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        help_text = QLabel('Save changes to the local profile. One-run build overrides belong in the plan. '
                           'Credential fields contain file references, never private-key contents.')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        if hasattr(project, 'set_app_version'):
            version = QPushButton('Change tracked app version…')
            version.clicked.connect(self.change_version)
            layout.addWidget(version)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def locate(self, control, kind):
        if kind == 'directory':
            path = QFileDialog.getExistingDirectory(self, 'Locate tool/runtime directory', control.text())
        else:
            path, _ = QFileDialog.getOpenFileName(self, 'Locate existing credential or tool file', control.text())
        if path:
            control.setText(path)

    def change_version(self):
        value, accepted = QInputDialog.getText(self, 'Change tracked app version',
            'App version (this edits pyproject.toml and requires a commit):')
        if not accepted:
            return
        if QMessageBox.question(self, 'Edit tracked source?', 'Change the source app version to ' + value + '?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.project.set_app_version(value)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Version not changed', str(error))

    def save(self):
        values = {name: field.isChecked() if isinstance(field, QCheckBox) else field.text()
                  for name, field in self.controls.items() if field.isEnabled()}
        try:
            self.project.save_settings(values)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Settings were not saved', str(error))
            return
        self.accept()


class ManagerPanel(QWidget):
    busy_changed = Signal(bool)
    settings_saved = Signal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project, self.plan, self.result = project, None, None
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(project.runner_directory))
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_errors)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.buffer = ''
        from .redaction import Redactor
        self.redact = Redactor(os.environ.get(name) for name in ('GH_TOKEN', 'GITHUB_TOKEN', 'FIREBASE_TOKEN'))
        self.elapsed = QElapsedTimer()
        self.phase_elapsed = QElapsedTimer()
        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self.show_elapsed)
        self.current_phase = 'queued'
        layout = QVBoxLayout(self)
        self.identity = QLabel(project.description)
        self.identity.setWordWrap(True)
        layout.addWidget(self.identity)
        form = QFormLayout()
        self.operation = QComboBox()
        self.operation.addItems(project.operations)
        self.platform = QComboBox()
        self.platform.addItems(project.platforms)
        self.backend = QComboBox()
        self.platform.currentTextChanged.connect(self.refresh_backends)
        self.operation.currentTextChanged.connect(self.refresh_backends)
        self.revision = QLineEdit('working-tree')
        self.pattern = QLineEdit()
        self.pattern.setPlaceholderText('Blank: full declared suite; filename glob: focused contracts')
        self.build_override = QLineEdit()
        self.build_override.setPlaceholderText('Automatic allocation; explicit value is for this run only')
        self.release_tag = QLineEdit()
        self.release_tag.setPlaceholderText('Explicit channel/tag, e.g. v0.2.0-alpha.1; unrelated to mobile build number')
        for label, control in [('Operation', self.operation), ('Platform', self.platform),
                               ('Backend', self.backend), ('Source revision', self.revision),
                               ('Focused test pattern', self.pattern), ('Mobile build override', self.build_override),
                               ('GitHub release tag', self.release_tag)]:
            form.addRow(label, control)
        self.include_ipad = QCheckBox('Include iPad independent-window coverage in the sequential local run')
        form.addRow(self.include_ipad)
        layout.addLayout(form)
        controls = QHBoxLayout()
        self.prepare = QPushButton('Inspect plan')
        self.prepare.clicked.connect(self.inspect_plan)
        self.start = QPushButton('Run reviewed plan')
        self.start.setEnabled(False)
        self.start.clicked.connect(self.run_plan)
        self.cancel = QPushButton('Cancel operation')
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_operation)
        self.settings = QPushButton('Settings…')
        self.settings.clicked.connect(self.edit_settings)
        self.verify = QPushButton('Verify connections/settings')
        self.verify.clicked.connect(self.verify_settings)
        for button in (self.prepare, self.start, self.cancel, self.settings, self.verify):
            controls.addWidget(button)
        layout.addLayout(controls)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumBlockCount(6000)
        layout.addWidget(self.preview)
        self.status = QLabel('Inspect a plan before running. No deployment follows a passing test automatically.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        for control in (self.operation, self.platform, self.backend):
            control.currentTextChanged.connect(self.invalidate)
        for control in (self.revision, self.pattern, self.build_override, self.release_tag):
            control.textChanged.connect(self.invalidate)
        self.include_ipad.toggled.connect(self.invalidate)
        self.refresh_backends()

    def refresh_backends(self, *_):
        self.backend.clear()
        self.backend.addItems(self.project.backend_options(self.platform.currentText(), self.operation.currentText()))

    def invalidate(self, *_):
        self.plan = None
        self.start.setEnabled(False)

    def edit_settings(self):
        try:
            if SettingsDialog(self.project, self).exec():
                self.invalidate()
                self.settings_saved.emit()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def inspect_plan(self):
        try:
            self.plan = self.project.make_plan(self.operation.currentText(), self.platform.currentText(),
                self.backend.currentText(), revision=self.revision.text(), pattern=self.pattern.text(),
                build_override=self.build_override.text(), include_ipad=self.include_ipad.isChecked(),
                release_tag=self.release_tag.text())
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
            self.status.setText(str(error))
            self.invalidate()
            return
        self.preview.setPlainText(json.dumps(self.plan.data(), indent=2))
        self.start.setEnabled(True)
        self.status.setText('Plan ready. Source and ordered phases above identify exactly what will run.')

    def verify_settings(self):
        try:
            self.plan = self.project.verification_plan()
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
            self.status.setText(str(error))
            return
        self.preview.setPlainText(json.dumps(self.plan.data(), indent=2))
        self.run_plan()

    def run_plan(self):
        if self.plan is None or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        confirmed = self.plan.effect in {'deploy', 'upload', 'publish'}
        if confirmed and QMessageBox.question(self, 'Confirm reviewed operation',
                f'{self.plan.operation} on {self.plan.backend}? Review the source and destinations above.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        run = self.project.results_directory / uuid4().hex
        run.parent.mkdir(parents=True, exist_ok=True)
        path = run.with_suffix('.plan.json')
        self.plan.save(path)
        self.result = run / 'result.json'
        self.cancel_file = run.with_suffix('.cancel')
        self.buffer = ''
        arguments = ['-m', 'build_manager', str(path), '--output', str(run), '--cancel-file', str(self.cancel_file)]
        if confirmed:
            arguments.append('--confirm')
        self.set_busy(True)
        self.status.setText('Queued…')
        self.process.start(str(self.project.interpreter), arguments)

    def set_busy(self, busy):
        if busy:
            self.phase_elapsed.invalidate()
            self.elapsed.start()
            self.current_phase = 'queued'
            self.clock.start()
        else:
            self.clock.stop()
        for control in (self.prepare, self.start, self.settings, self.verify, self.operation,
                        self.platform, self.backend, self.revision, self.pattern, self.build_override, self.release_tag,
                        self.include_ipad):
            control.setEnabled(not busy)
        self.start.setEnabled(not busy and self.plan is not None)
        self.cancel.setEnabled(busy)
        self.busy_changed.emit(busy)

    def show_elapsed(self):
        phase = self.phase_elapsed.elapsed()/1000 if self.phase_elapsed.isValid() else 0
        self.status.setText(f'{self.current_phase}; phase {phase:.0f}s; total {self.elapsed.elapsed()/1000:.0f}s')

    def read_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            try:
                event = json.loads(line)
            except ValueError:
                self.preview.appendPlainText(line)
                continue
            if event.get('type') == 'output':
                self.preview.appendPlainText(event['text'].rstrip())
            elif event.get('type') == 'phase':
                if event['status'] == 'running':
                    self.phase_elapsed.start()
                self.current_phase = event['id'] + ': ' + event['status']
                self.show_elapsed()
            elif event.get('type') == 'error':
                self.status.setText(event['error'])

    def read_errors(self):
        text = bytes(self.process.readAllStandardError()).decode('utf-8', errors='replace')
        self.preview.appendPlainText(self.redact(text))

    def cancel_operation(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.current_phase = 'Cancelling active work and running owned cleanup…'
            self.show_elapsed()
            # Windows console processes do not reliably receive QProcess's
            # WM_CLOSE. The CLI observes this owned marker and retains its
            # structured cancelled result while it stops the phase's job/tree.
            self.cancel_file.touch()

    def process_error(self, *_):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.set_busy(False)
            self.status.setText('Operation could not start: ' + self.process.errorString())

    def finished(self, code, *_):
        self.read_output()
        self.set_busy(False)
        status = 'failed'
        if self.result and self.result.is_file():
            report = json.loads(self.result.read_text())
            status = report['status']
            self.preview.appendPlainText(json.dumps(report, indent=2))
            for phase in report['phases']:
                for artifact in phase.get('artifacts', []):
                    from pathlib import Path
                    if Path(artifact['path']).suffix == '.json':
                        # Immutable report captured by the executor, not values
                        # reconstructed from a subsequently edited profile.
                        self.preview.appendPlainText(Path(artifact['path']).read_text())
        self.status.setText(f'{status}; exit {code}. Results: {self.result}')
