"""
YouTube Downloader workflow for the Logistics feature UI.
"""

from pathlib import Path

from commonUtils import ui
from commonUtils.ui import pyside

from features import registry
from features.youtube_downloader import detection, downloader
from models.folder_entry import FolderEntry


class YouTubeDownloaderDialog(pyside.QDialog):
    def __init__(self, entry: FolderEntry, parent=None):
        super().__init__(parent)

        if not isinstance(entry, FolderEntry):
            raise TypeError(f'Expected FolderEntry, got {type(entry).__name__}.')

        if entry.local is None:
            raise ValueError('YouTube Downloader requires a local folder.')

        self.entry = entry
        self.folder = entry.local
        self.rclone_config_path = None

        if entry.remote_source == 'rclone' and entry.remote_context is not None:
            self.rclone_config_path = Path(entry.remote_context)

        self.config_path = detection.get_config_path(self.folder)

        if self.config_path is None:
            raise ValueError(f'No YouTube Downloader configuration found for "{entry.name}".')

        self.setWindowTitle(f'YouTube Downloader - {entry.name}')
        self.resize(720, 520)
        self.setMinimumSize(640, 480)

        self._build_layout()

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(14)

        title = pyside.QLabel(f'YouTube Downloader - {self.entry.name}')
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        title.setFont(title_font)

        description = pyside.QLabel(
            'Run downloads from this folder’s configured YouTube INI files, or synchronize '
            'the downloader configuration and downloaded Season folders with its matching remote.'
        )
        description.setWordWrap(True)

        root_layout.addWidget(title)
        root_layout.addWidget(description)
        root_layout.addWidget(self._create_configuration_group())
        root_layout.addWidget(self._create_download_group())
        root_layout.addWidget(self._create_remote_sync_group())

        close_layout = pyside.QHBoxLayout()
        close_layout.addStretch()

        close_button = pyside.QPushButton('Close')
        close_button.clicked.connect(self.accept)

        close_layout.addWidget(close_button)
        root_layout.addLayout(close_layout)

    def _create_configuration_group(self):
        group = pyside.QGroupBox('Configuration')
        layout = pyside.QFormLayout(group)

        folder_label = self._selectable_label(str(self.folder.path))
        config_label = self._selectable_label(str(self.config_path))
        remote_label = self._selectable_label(
            f'{self.entry.remote_name}:' if self.entry.remote_name is not None else 'Not configured'
        )

        layout.addRow('Folder:', folder_label)
        layout.addRow('YouTube config:', config_label)
        layout.addRow('Remote:', remote_label)

        return group

    def _create_download_group(self):
        group = pyside.QGroupBox('Download')
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        explanation = pyside.QLabel(
            'Download all missing videos described by the INI files in the configured YouTube directory. '
            'The existing downloader updates yt-dlp before processing the configs.'
        )
        explanation.setWordWrap(True)

        download_button = pyside.QPushButton('Download All Channels')
        download_button.clicked.connect(self._download_all)

        layout.addWidget(explanation)
        layout.addWidget(download_button)

        return group

    def _create_remote_sync_group(self):
        group = pyside.QGroupBox('YouTube Remote Sync')
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        if self.entry.remote_name is None:
            explanation = pyside.QLabel(
                'No matching rclone remote is configured for this folder. '
                'Remote sync actions are unavailable.'
            )
            explanation.setWordWrap(True)
            layout.addWidget(explanation)

        push_seasons_button = pyside.QPushButton('Push Local Season Folders')
        push_config_button = pyside.QPushButton('Push Local Config')
        pull_config_button = pyside.QPushButton('Pull Remote Config')

        rclone_available = registry.is_feature_available('rclone')
        remote_enabled = (
            self.entry.remote_name is not None
            and self.rclone_config_path is not None
            and rclone_available
        )

        if not rclone_available:
            explanation = pyside.QLabel(
                'The optional rclone feature is not installed. '
                'Downloads remain available, but remote sync actions are disabled.'
            )
            explanation.setWordWrap(True)
            layout.addWidget(explanation)

        push_seasons_button.setEnabled(remote_enabled)
        push_config_button.setEnabled(remote_enabled)
        pull_config_button.setEnabled(remote_enabled)

        push_seasons_button.setToolTip(
            'Sync each discovered Season folder to its matching path on the remote.'
        )
        push_config_button.setToolTip(
            'Sync the configured YouTube INI/config directory to the remote.'
        )
        pull_config_button.setToolTip(
            'Sync the remote YouTube INI/config directory back to the local folder.'
        )

        push_seasons_button.clicked.connect(self._push_seasons)
        push_config_button.clicked.connect(self._push_config)
        pull_config_button.clicked.connect(self._pull_config)

        layout.addWidget(push_seasons_button)
        layout.addWidget(push_config_button)
        layout.addWidget(pull_config_button)

        return group

    def _selectable_label(self, text: str):
        label = pyside.QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _download_all(self):
        downloader.download_all(self.config_path)

    def _push_seasons(self):
        confirmed = ui.display_msg_box_ok_cancel(
            'Push YouTube Season Folders',
            f'Sync discovered local Season folders from "{self.entry.name}" to its rclone remote?'
        )

        if confirmed:
            downloader.push_seasons(self.folder, self.rclone_config_path)

    def _push_config(self):
        confirmed = ui.display_msg_box_ok_cancel(
            'Push YouTube Config',
            f'Sync the local YouTube configuration to remote "{self.entry.remote_name}"?\n\n'
            f'Source: {self.config_path}'
        )

        if confirmed:
            downloader.push_config(self.folder, self.rclone_config_path)

    def _pull_config(self):
        confirmed = ui.display_msg_box_ok_cancel(
            'Pull YouTube Config',
            f'Sync the remote YouTube configuration from "{self.entry.remote_name}" to the local folder?\n\n'
            f'Destination: {self.config_path}'
        )

        if confirmed:
            downloader.pull_config(self.folder, self.rclone_config_path)
