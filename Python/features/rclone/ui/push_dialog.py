"""
Modern rclone Push workflow for the Logistics feature UI.
"""

from pathlib import Path

from commonUtils import ui
from commonUtils.ui import pyside

from features.rclone import actions
from models.folder_entry import FolderEntry


class RclonePushDialog(pyside.QDialog):
    def __init__(self, entry: FolderEntry, parent=None):
        super().__init__(parent)

        if entry.local is None or entry.remote_name is None:
            raise ValueError('rclone Push requires a folder with both local and remote data.')

        self.entry = entry

        self.setWindowTitle(f'Push - {entry.name}')
        self.setMinimumWidth(620)

        self.regular_radio = pyside.QRadioButton('Entire local folder')
        self.specific_radio = pyside.QRadioButton('Specific folder')

        self.track_renames = pyside.QCheckBox('Track renames')

        self.specific_path = pyside.QLineEdit()
        self.specific_path.setPlaceholderText('Choose a folder to add or update on the remote...')

        self.browse_button = pyside.QPushButton('Browse...')

        self.bandwidth_limit = pyside.QLineEdit()
        self.bandwidth_limit.setPlaceholderText('Unlimited')
        self.bandwidth_limit.setValidator(pyside.QIntValidator(1, 1000000, self))

        self.result_source = pyside.QLabel()
        self.result_source.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result_source.setWordWrap(True)

        self.result_destination = pyside.QLabel()
        self.result_destination.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result_destination.setWordWrap(True)

        self.result_explanation = pyside.QLabel()
        self.result_explanation.setWordWrap(True)

        self.cancel_button = pyside.QPushButton('Cancel')
        self.push_button = pyside.QPushButton('PUSH')

        self._build_layout()
        self._connect_signals()

        self.regular_radio.setChecked(True)
        self._update_mode()

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(16)

        title = pyside.QLabel(f'Push - {self.entry.name}')
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        title.setFont(title_font)

        intro = pyside.QLabel(
            'Choose whether to synchronize the entire local folder or only one specific '
            'subfolder. Review the resulting source and destination below before pushing.'
        )
        intro.setWordWrap(True)

        root_layout.addWidget(title)
        root_layout.addWidget(intro)
        root_layout.addWidget(self._create_mode_group())
        root_layout.addWidget(self._create_result_group())

        button_layout = pyside.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.push_button)

        self.push_button.setDefault(True)

        root_layout.addLayout(button_layout)

    def _create_mode_group(self):
        group = pyside.QGroupBox('Push Options')
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self.regular_radio)

        regular_options = pyside.QHBoxLayout()
        regular_options.setContentsMargins(24, 0, 0, 0)
        regular_options.addWidget(self.track_renames)
        regular_options.addStretch()
        layout.addLayout(regular_options)

        layout.addWidget(self.specific_radio)

        specific_options = pyside.QGridLayout()
        specific_options.setContentsMargins(24, 0, 0, 0)
        specific_options.setHorizontalSpacing(8)
        specific_options.setVerticalSpacing(8)

        specific_options.addWidget(pyside.QLabel('Folder:'), 0, 0)
        specific_options.addWidget(self.specific_path, 0, 1)
        specific_options.addWidget(self.browse_button, 0, 2)

        specific_options.addWidget(pyside.QLabel('Bandwidth limit:'), 1, 0)
        specific_options.addWidget(self.bandwidth_limit, 1, 1)
        specific_options.addWidget(pyside.QLabel('MB/s'), 1, 2)

        specific_help = pyside.QLabel(
            'Specific-folder mode syncs only the selected folder into a matching '
            'subfolder on the remote. Other sibling folders at the remote root are '
            'outside this sync target.'
        )
        specific_help.setWordWrap(True)

        specific_options.addWidget(specific_help, 2, 0, 1, 3)
        specific_options.setColumnStretch(1, 1)

        layout.addLayout(specific_options)

        return group

    def _create_result_group(self):
        group = pyside.QGroupBox('Resulting Sync')
        layout = pyside.QFormLayout(group)

        layout.addRow('Local source:', self.result_source)
        layout.addRow('Remote destination:', self.result_destination)
        layout.addRow('', self.result_explanation)

        return group

    def _connect_signals(self):
        self.regular_radio.toggled.connect(self._update_mode)
        self.specific_radio.toggled.connect(self._update_mode)
        self.specific_path.textChanged.connect(self._update_result_preview)

        self.browse_button.clicked.connect(self._browse_for_folder)
        self.cancel_button.clicked.connect(self.reject)
        self.push_button.clicked.connect(self._push)

    def _update_mode(self):
        regular_enabled = self.regular_radio.isChecked()
        specific_enabled = self.specific_radio.isChecked()

        self.track_renames.setEnabled(regular_enabled)

        self.specific_path.setEnabled(specific_enabled)
        self.browse_button.setEnabled(specific_enabled)
        self.bandwidth_limit.setEnabled(specific_enabled)

        self._update_result_preview()

    def _update_result_preview(self):
        if self.regular_radio.isChecked():
            self.result_source.setText(str(self.entry.local.path))
            self.result_destination.setText(f'{self.entry.remote_name}:')
            self.result_explanation.setText(
                'The entire local folder will be synchronized with the remote root. '
                'Files at that destination may be added, updated, or removed to match the local source.'
            )
            return

        directory_path = self.specific_path.text().strip()

        if directory_path == '':
            self.result_source.setText('Choose a folder above.')
            self.result_destination.setText(f'{self.entry.remote_name}:<selected folder>')
            self.result_explanation.setText(
                'Only the selected remote subfolder will be synchronized. '
                'Other folders beside it at the remote root are not part of this operation.'
            )
            return

        directory = Path(directory_path)
        remote_destination = f'{self.entry.remote_name}:{directory.name}'

        self.result_source.setText(str(directory))
        self.result_destination.setText(remote_destination)
        self.result_explanation.setText(
            f'Only "{directory.name}" on the remote is the sync destination. '
            'Other sibling folders at the remote root are not touched by this operation. '
            'Within that destination subfolder, rclone sync will make the remote match the selected local folder.'
        )

    def _browse_for_folder(self):
        starting_path = self.specific_path.text().strip()

        if starting_path == '':
            starting_path = str(self.entry.local.path)

        selected_path = pyside.QFileDialog.getExistingDirectory(
            self,
            'Select Folder to Push',
            starting_path
        )

        if selected_path:
            self.specific_path.setText(selected_path)

    def _push(self):
        if self.regular_radio.isChecked():
            actions.push_to_cloud(
                self.entry.local,
                track_renames=self.track_renames.isChecked()
            )
            self.accept()
            return

        directory_path = self.specific_path.text().strip()

        if directory_path == '':
            ui.display_msg_box_ok(
                'Push Specific Folder',
                'Choose a folder to push.'
            )
            return

        bandwidth_limit = self.bandwidth_limit.text().strip()

        if actions.push_specific_directory(
            self.entry.local,
            directory_path,
            bandwidth_limit
        ):
            self.accept()
