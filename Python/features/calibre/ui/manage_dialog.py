"""
Calibre library management workflow for the Logistics feature UI.
"""

from commonUtils import ui
from commonUtils.ui import pyside

from features.calibre import actions
from models.local_folder import LocalFolder


class CalibreManageDialog(pyside.QDialog):
    def __init__(self, folder: LocalFolder, parent=None):
        super().__init__(parent)

        if not isinstance(folder, LocalFolder):
            raise TypeError(f'Expected LocalFolder, got {type(folder).__name__}.')

        self.folder = folder
        self.libraries = actions.get_libraries(folder)

        self.library_list = pyside.QListWidget()
        self.library_list.setMinimumWidth(220)
        self.library_list.setMaximumWidth(320)

        self.library_name = pyside.QLabel()
        self.library_path = pyside.QLabel()
        self.library_path.setWordWrap(True)
        self.library_path.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)

        self.open_folder_button = pyside.QPushButton('Open Library Folder')
        self.launch_calibre_button = pyside.QPushButton('Launch Calibre')
        self.echo_boox_button = pyside.QPushButton('Echo EPUBs to BOOX-SD')

        self.close_button = pyside.QPushButton('Close')

        self.setWindowTitle(f'Calibre - {folder.name}')
        self.resize(820, 480)
        self.setMinimumSize(700, 400)

        self._build_layout()
        self._connect_signals()
        self._populate_libraries()

    def _build_layout(self):
        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(14)

        title = pyside.QLabel(f'Calibre Libraries - {self.folder.name}')
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        title.setFont(title_font)

        intro = pyside.QLabel(
            'Select a Calibre library on the left, then choose an action for that library.'
        )
        intro.setWordWrap(True)

        root_layout.addWidget(title)
        root_layout.addWidget(intro)

        splitter = pyside.QSplitter(pyside.Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_library_list_panel())
        splitter.addWidget(self._create_library_details_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 540])

        root_layout.addWidget(splitter, 1)

        button_layout = pyside.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        root_layout.addLayout(button_layout)

    def _create_library_list_panel(self):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = pyside.QLabel('Libraries')
        label_font = label.font()
        label_font.setBold(True)
        label.setFont(label_font)

        layout.addWidget(label)
        layout.addWidget(self.library_list)

        return widget

    def _create_library_details_panel(self):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(12)

        self.library_name.setText('Select a library')
        name_font = self.library_name.font()
        name_font.setPointSize(name_font.pointSize() + 4)
        name_font.setBold(True)
        self.library_name.setFont(name_font)

        path_group = pyside.QGroupBox('Library')
        path_layout = pyside.QFormLayout(path_group)
        path_layout.addRow('Path:', self.library_path)

        actions_group = pyside.QGroupBox('Actions')
        actions_layout = pyside.QVBoxLayout(actions_group)
        actions_layout.setSpacing(8)
        actions_layout.addWidget(self.open_folder_button)
        actions_layout.addWidget(self.launch_calibre_button)
        actions_layout.addWidget(self.echo_boox_button)

        boox_help = pyside.QLabel(
            'BOOX echo mirrors EPUB files from this library to '
            '/Volumes/BOOX-SD/Calibre [EPUBs]/<library>.'
        )
        boox_help.setWordWrap(True)
        actions_layout.addWidget(boox_help)

        layout.addWidget(self.library_name)
        layout.addWidget(path_group)
        layout.addWidget(actions_group)
        layout.addStretch()

        return widget

    def _connect_signals(self):
        self.library_list.currentItemChanged.connect(self._selection_changed)

        self.open_folder_button.clicked.connect(self._open_library_folder)
        self.launch_calibre_button.clicked.connect(self._launch_calibre)
        self.echo_boox_button.clicked.connect(self._echo_to_boox)

        self.close_button.clicked.connect(self.accept)

    def _populate_libraries(self):
        self.library_list.clear()

        for library in self.libraries:
            item = pyside.QListWidgetItem(library.name)
            item.setData(pyside.Qt.ItemDataRole.UserRole, library)
            self.library_list.addItem(item)

        if self.library_list.count() == 0:
            self._set_actions_enabled(False)
            self.library_name.setText('No Calibre libraries found')
            self.library_path.setText('')
            return

        self.library_list.setCurrentRow(0)

    def _selection_changed(self, current, _previous):
        if current is None:
            self._set_actions_enabled(False)
            return

        library = current.data(pyside.Qt.ItemDataRole.UserRole)

        if library is None:
            self._set_actions_enabled(False)
            return

        self.library_name.setText(library.name)
        self.library_path.setText(str(library.path))
        self._set_actions_enabled(True)

    def _get_selected_library(self):
        current = self.library_list.currentItem()

        if current is None:
            return None

        return current.data(pyside.Qt.ItemDataRole.UserRole)

    def _set_actions_enabled(self, enabled: bool):
        self.open_folder_button.setEnabled(enabled)
        self.launch_calibre_button.setEnabled(enabled)
        self.echo_boox_button.setEnabled(enabled)

    def _open_library_folder(self):
        library = self._get_selected_library()

        if library is None:
            return

        actions.open_library(library)

    def _launch_calibre(self):
        library = self._get_selected_library()

        if library is None:
            return

        actions.launch_calibre(library)

    def _echo_to_boox(self):
        library = self._get_selected_library()

        if library is None:
            return

        confirmed = ui.display_msg_box_ok_cancel(
            'Echo EPUBs to BOOX-SD',
            f'Echo EPUB files from "{library.name}" to BOOX-SD?\n\n'
            'The destination is treated as a mirror. Files that no longer exist '
            'in the Calibre library may be removed from the destination.'
        )

        if not confirmed:
            return

        try:
            actions.echo_epubs_to_boox_sd(library)
        except (OSError, ValueError, RuntimeError) as error:
            ui.display_msg_box_ok('Calibre Export Failed', str(error))
