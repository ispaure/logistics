"""
Generic form/dialog helpers used by feature-owned maintenance workflows.
"""

from pathlib import Path

from commonUtils import ui
from commonUtils.ui import pyside
from commonUtils.ui.operation_progress import OperationProgress


def coerce_initial_path(initial_path) -> str:
    """Convert an optional path for a text field without changing its contents."""

    if initial_path is None:
        return ''

    return str(initial_path)


class ToolDialog(pyside.QDialog):
    def __init__(self, title: str, description: str, action_text: str, destructive: bool, parent=None):
        super().__init__(parent)

        self.task = OperationProgress(self)
        self.task.cancel_button.hide()
        self.task.completed.connect(self._background_completed)
        self._background_callback = None
        self.action_text = action_text
        self.destructive = destructive

        self.setWindowTitle(title)
        self.setMinimumWidth(620)

        self.root_layout = pyside.QVBoxLayout(self)
        self.root_layout.setContentsMargins(20, 20, 20, 20)
        self.root_layout.setSpacing(14)

        title_label = pyside.QLabel(title)
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        title_label.setFont(title_font)

        description_label = pyside.QLabel(description)
        description_label.setWordWrap(True)

        self.form = pyside.QFormLayout()
        self.form.setHorizontalSpacing(12)
        self.form.setVerticalSpacing(10)

        self.cancel_button = pyside.QPushButton('Cancel')
        self.action_button = pyside.QPushButton(action_text)

        self.root_layout.addWidget(title_label)
        self.root_layout.addWidget(description_label)
        self.root_layout.addLayout(self.form)
        self.root_layout.addWidget(self.task)

        button_layout = pyside.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.action_button)
        self.root_layout.addLayout(button_layout)

        self.cancel_button.clicked.connect(self.reject)
        self.action_button.clicked.connect(self._execute)
        self.action_button.setDefault(True)

    @property
    def busy(self):
        return self.task.busy

    def _run_background(self, work, completed, *, cancel_text='Cancel after current item',
                        cancel_message='Cancellation requested. Finishing the current item…'):
        if self.busy:
            return
        self._background_callback = completed
        self._disabled_widgets = []
        for row in range(self.form.count()):
            widget = self.form.itemAt(row).widget()
            if widget is not None:
                self._disabled_widgets.append((widget, widget.isEnabled()))
                widget.setEnabled(False)
        self.action_button.setEnabled(False)
        self.cancel_button.setText(cancel_text)
        self.task.start(work, cancel_text=cancel_text, cancel_message=cancel_message)

    def _background_completed(self, result, error):
        for widget, was_enabled in self._disabled_widgets:
            widget.setEnabled(was_enabled)
        self._disabled_widgets = []
        self.action_button.setEnabled(True)
        self.cancel_button.setText('Close')
        self.cancel_button.setEnabled(True)
        if error:
            self.task.message.setText(f'Operation failed: {error}')
            return
        self._background_callback(result)

    def reject(self):
        if self.busy:
            self.task.request_cancel()
            self.cancel_button.setEnabled(False)
        else:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)

    def _add_directory_field(self, label: str, default: str = '') -> pyside.QLineEdit:
        line_edit = pyside.QLineEdit(default)
        browse = pyside.QPushButton('Browse...')

        row_widget = pyside.QWidget()
        row_layout = pyside.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(line_edit, 1)
        row_layout.addWidget(browse)

        browse.clicked.connect(lambda _checked=False, line_edit=line_edit: self._browse_directory(line_edit))
        self.form.addRow(label, row_widget)

        return line_edit

    def _browse_directory(self, line_edit: pyside.QLineEdit):
        start_path = line_edit.text().strip()

        if start_path == '':
            start_path = str(Path.home())

        selected = pyside.QFileDialog.getExistingDirectory(
            self,
            'Select Directory',
            start_path
        )

        if selected:
            line_edit.setText(selected)

    def _require_directory(self, line_edit: pyside.QLineEdit) -> Path | None:
        value = line_edit.text().strip()

        if value == '':
            ui.display_msg_box_ok(
                self.windowTitle(),
                'Choose a target directory first.'
            )
            return None

        return Path(value)

    def _confirm(self) -> bool:
        if not self.destructive:
            return True

        return ui.display_msg_box_ok_cancel(
            self.windowTitle(),
            f'Run "{self.action_text}"?\n\nThis action may modify files.'
        )

    def _execute(self):
        raise NotImplementedError
