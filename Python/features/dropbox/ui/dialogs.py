"""
Dropbox workflow dialogs.
"""

from pathlib import Path

from commonUtils import ui
from commonUtils.ui import pyside

from features.dropbox import conflicts
from ui_new.dialogs.tool_dialog import coerce_initial_path


class DropboxConflictsDialog(pyside.QDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(parent)

        self.setWindowTitle('Dropbox Conflicting Copies')
        self.setMinimumWidth(620)

        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(14)

        title = pyside.QLabel('Dropbox Conflicting Copies')
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        title.setFont(title_font)

        description = pyside.QLabel(
            'Analyze Dropbox conflicted-copy files or delete them only when the existing safety checks confirm '
            'that every conflict still has its original.'
        )
        description.setWordWrap(True)

        form = pyside.QFormLayout()
        self.target_dir = pyside.QLineEdit(coerce_initial_path(initial_path))

        browse_button = pyside.QPushButton('Browse...')
        target_widget = pyside.QWidget()
        target_layout = pyside.QHBoxLayout(target_widget)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(8)
        target_layout.addWidget(self.target_dir, 1)
        target_layout.addWidget(browse_button)

        self.recursive = pyside.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)

        form.addRow('Target folder:', target_widget)
        form.addRow('Recursive:', self.recursive)

        report_button = pyside.QPushButton('Print Conflicting Copies')
        delete_button = pyside.QPushButton('Delete Conflicting Copies')
        close_button = pyside.QPushButton('Close')

        action_layout = pyside.QHBoxLayout()
        action_layout.addWidget(report_button)
        action_layout.addWidget(delete_button)

        close_layout = pyside.QHBoxLayout()
        close_layout.addStretch()
        close_layout.addWidget(close_button)

        root_layout.addWidget(title)
        root_layout.addWidget(description)
        root_layout.addLayout(form)
        root_layout.addLayout(action_layout)
        root_layout.addLayout(close_layout)

        browse_button.clicked.connect(self._browse)
        report_button.clicked.connect(self._report)
        delete_button.clicked.connect(self._delete)
        close_button.clicked.connect(self.accept)

    def _browse(self):
        start_path = self.target_dir.text().strip() or str(Path.home())

        selected = pyside.QFileDialog.getExistingDirectory(
            self,
            'Select Directory',
            start_path
        )

        if selected:
            self.target_dir.setText(selected)

    def _get_target(self):
        value = self.target_dir.text().strip()

        if value == '':
            ui.display_msg_box_ok(
                'Dropbox Conflicting Copies',
                'Choose a target directory first.'
            )
            return None

        return Path(value)

    def _report(self):
        target = self._get_target()

        if target is None:
            return

        conflicts.print_conflicting_copies(
            target,
            recursive=self.recursive.isChecked()
        )

    def _delete(self):
        target = self._get_target()

        if target is None:
            return

        confirmed = ui.display_msg_box_ok_cancel(
            'Delete Conflicting Copies',
            'Delete Dropbox conflicting-copy files that pass the existing safety checks?'
        )

        if not confirmed:
            return

        conflicts.delete_conflicting_copies(
            target,
            recursive=self.recursive.isChecked()
        )
