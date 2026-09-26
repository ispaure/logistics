"""
Plex Media Server backup and restore workflow for the replacement Logistics UI.
"""

from commonUtils import ui
from commonUtils.osUtils import OS, get_os
from commonUtils.ui import pyside

from features.plex import actions, detection
from models.local_folder import LocalFolder


class PlexManagePMSDialog(pyside.QDialog):
    def __init__(self, folder: LocalFolder, parent=None):
        super().__init__(parent)

        if not isinstance(folder, LocalFolder):
            raise TypeError(f'Expected LocalFolder, got {type(folder).__name__}.')

        self.folder = folder
        self.local_pmsdata = actions.get_local_cls_pmsdata(folder)
        self.remote_pmsdata = actions.get_remote_cls_pmsdata(folder)
        self.pms_data_path = detection.get_pms_data_path()

        self.setWindowTitle(f'Manage PMS - {folder.name}')
        self.resize(760, 620)
        self.setMinimumSize(680, 560)

        self._build_layout()

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(14)

        title = pyside.QLabel(f'Manage Plex Media Server - {self.folder.name}')
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        title.setFont(title_font)

        description = pyside.QLabel(
            'Back up or restore the local Plex Media Server installation using '
            f'the paired "{self.local_pmsdata.name}" package.'
        )
        description.setWordWrap(True)

        root_layout.addWidget(title)
        root_layout.addWidget(description)
        root_layout.addWidget(self._create_locations_group())
        root_layout.addWidget(self._create_restore_group())
        root_layout.addWidget(self._create_backup_group())

        close_layout = pyside.QHBoxLayout()
        close_layout.addStretch()

        close_button = pyside.QPushButton('Close')
        close_button.clicked.connect(self.accept)

        close_layout.addWidget(close_button)
        root_layout.addLayout(close_layout)

    def _create_locations_group(self):
        group = pyside.QGroupBox('Locations')
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(10)

        form = pyside.QFormLayout()

        pms_path = str(self.pms_data_path) if self.pms_data_path is not None else 'Unavailable'
        local_package_path = str(self.local_pmsdata.path)
        remote_package_path = str(self.remote_pmsdata.path)

        form.addRow('Plex Media Server data:', self._selectable_label(pms_path))
        form.addRow('Local package:', self._selectable_label(local_package_path))
        form.addRow('Remote package:', self._selectable_label(remote_package_path))

        layout.addLayout(form)

        buttons = pyside.QHBoxLayout()

        open_local = pyside.QPushButton('Open Local -PMSDATA')
        open_local.clicked.connect(
            lambda _checked=False: actions.open_dir_local_cls_pmsdata(self.folder)
        )

        open_remote = pyside.QPushButton('Open Remote -PMSDATA')
        open_remote.clicked.connect(
            lambda _checked=False: actions.open_dir_remote_cls_pmsdata(self.folder)
        )

        clear_local = pyside.QPushButton('Clear Local -PMSDATA')
        clear_local.clicked.connect(self._clear_local_pmsdata)

        buttons.addWidget(open_local)
        buttons.addWidget(open_remote)
        buttons.addWidget(clear_local)

        layout.addLayout(buttons)

        return group

    def _create_restore_group(self):
        group = pyside.QGroupBox('Restore Plex Media Server from Remote')
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        explanation = pyside.QLabel(
            'Restore is a two-step workflow: first sync the remote package locally, '
            'then unpack that local package into the platform Plex Media Server data location.'
        )
        explanation.setWordWrap(True)

        pull_button = pyside.QPushButton(
            f'1. Pull {self.local_pmsdata.name} from Remote to Local'
        )
        pull_button.clicked.connect(self._pull_pms)

        target_name = self._get_platform_target_name()
        unpackage_button = pyside.QPushButton(
            f'2. Unpackage Local {self.local_pmsdata.name} to {target_name} PMS'
        )
        unpackage_button.clicked.connect(self._unpackage_pms)

        layout.addWidget(explanation)
        layout.addWidget(pull_button)
        layout.addWidget(unpackage_button)

        return group

    def _create_backup_group(self):
        group = pyside.QGroupBox('Back Up Plex Media Server to Remote')
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        explanation = pyside.QLabel(
            'Backup is a two-step workflow: first package the current Plex Media Server data locally, '
            'then sync that package to the paired remote.'
        )
        explanation.setWordWrap(True)

        target_name = self._get_platform_target_name()
        package_button = pyside.QPushButton(
            f'1. Package {target_name} PMS to Local {self.local_pmsdata.name}'
        )
        package_button.clicked.connect(self._package_pms)

        push_button = pyside.QPushButton(
            f'2. Push {self.local_pmsdata.name} from Local to Remote'
        )
        push_button.clicked.connect(self._push_pms)

        layout.addWidget(explanation)
        layout.addWidget(package_button)
        layout.addWidget(push_button)

        return group

    def _selectable_label(self, text: str):
        label = pyside.QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _get_platform_target_name(self) -> str:
        match get_os():
            case OS.WIN:
                return 'AppData'
            case OS.MAC:
                return 'Application Support'
            case _:
                return 'Platform'

    def _clear_local_pmsdata(self):
        confirmed = ui.display_msg_box_ok_cancel(
            'Clear Local -PMSDATA',
            f'Delete the contents of the local Plex package?\n\n{self.local_pmsdata.path}'
        )

        if confirmed:
            actions.clear_local_pmsdata(self.folder)

    def _pull_pms(self):
        confirmed = ui.display_msg_box_ok_cancel(
            'Pull Plex Media Server Data',
            f'Sync remote "{self.remote_pmsdata.name}" to the local package?\n\n'
            f'Destination: {self.local_pmsdata.path}'
        )

        if confirmed:
            actions.pull_pms(self.folder)

    def _unpackage_pms(self):
        confirmed = ui.display_msg_box_ok_cancel(
            'Restore Plex Media Server Data',
            f'Replace the current Plex Media Server data with the contents of:\n\n'
            f'{self.local_pmsdata.path}'
        )

        if confirmed:
            actions.unpackage_pms(self.folder)

    def _package_pms(self):
        confirmed = ui.display_msg_box_ok_cancel(
            'Package Plex Media Server Data',
            f'Rebuild the local Plex package from the current Plex Media Server data?\n\n'
            f'Package: {self.local_pmsdata.path}'
        )

        if confirmed:
            actions.package_pms(self.folder)

    def _push_pms(self):
        confirmed = ui.display_msg_box_ok_cancel(
            'Push Plex Media Server Data',
            f'Sync the local Plex package to remote "{self.remote_pmsdata.name}"?\n\n'
            'The remote package destination will be synchronized to match the local package.'
        )

        if confirmed:
            actions.push_pms(self.folder)
